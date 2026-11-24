# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

"""Diffs agent.yaml against the live agent and applies the difference.

Resources are matched by a natural key (skill title, FAQ question, website URL,
connector name, tool name, consumer phone number), so agent.yaml never needs
server-side IDs. Only sections present in agent.yaml are managed. Remote items
missing from agent.yaml are reported as unmanaged and deleted only with --prune.

A plan ID is an HMAC, keyed by a random per-folder key in .mba/, over the
target, the agent.yaml path, the resolved desired state, the live state and
the operations, so it cannot be reused for another agent or guessed offline.
"""

from __future__ import annotations

import copy
import hashlib
import hmac
import json
import os
import secrets
import stat
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .client import MBAClient
from .errors import ApiError, ConfigError, GateError, NeedsHumanError, PlanStaleError
from .evals import State

SECRET_KEYS = {"value", "api_key", "client_secret", "password", "token", "client_key"}
SETTINGS_FIELDS = ("ai_audience", "handoff", "followup", "never_say_phrases")
SKILL_FIELDS = ("description", "skill")
WEBSITE_FIELDS = (
    "included_sub_domains",
    "included_url_patterns",
    "excluded_sub_domains",
    "excluded_url_patterns",
    "single_urls",
)
# auth_config is never diffed, copied from the live agent or exported: the API
# may return it masked. It is sent only from agent.yaml.
CONNECTOR_FIELDS = (
    "description",
    "base_url",
    "auth_type",
    "connector_protocol",
    "user_auth_injection_config",
)
# Sent only when a connector is created: the API does not report it back.
CONNECTOR_CREATE_ONLY = ("requires_certificate",)
TOOL_FIELDS = (
    "description",
    "user_auth_required",
    "request_definition",
    "transformation_spec",
    "user_auth_action_config",
)
ALL_SECTIONS = (
    "settings",
    "business_info",
    "skills",
    "faqs",
    "websites",
    "allowlist",
    "connectors",
)
NARROW_AUDIENCE = "ALLOWLISTED_ONLY"
DEFAULT_AUDIENCE = "EVERYONE"  # what the API applies when ai_audience is unset

Op = dict[str, Any]


@dataclass(frozen=True)
class Binding:
    """What a plan ID is bound to besides the plan itself."""

    key: bytes
    target: str
    origin: str


def approval_key(state: State, create: bool) -> bytes:
    """The per-folder key plan IDs are MACed with. Never printed or logged."""
    path = state.dir / "approval.key"
    unsafe = ConfigError(
        f"{path} must be a regular file readable only by you, in a real folder.",
        "Delete .mba/approval.key and run `mba plan` again.",
    )
    if state.dir.is_symlink() or path.is_symlink():
        raise unsafe
    if path.exists():
        st = path.stat()
        if not stat.S_ISREG(st.st_mode):
            raise unsafe
        if os.name == "posix" and (st.st_mode & 0o077 or st.st_uid != os.getuid()):
            raise unsafe
        try:
            key = bytes.fromhex(path.read_text().strip())
        except ValueError:
            raise unsafe from None
        if len(key) != 32:
            raise unsafe
        return key
    if not create:
        raise PlanStaleError(
            "No plan has been made in this folder.",
            "Run `mba plan`, review it, and apply the new plan ID.",
        )
    state.dir.mkdir(parents=True, exist_ok=True)
    key = secrets.token_bytes(32)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(key.hex())
    return key


def is_subset(local: Any, remote: Any) -> bool:
    """True if every value set in `local` is equal in `remote`.

    The server fills in defaults the user never wrote, so comparing whole
    objects would report changes forever.
    """
    if isinstance(local, dict):
        if not isinstance(remote, dict):
            return False
        return all(is_subset(v, remote.get(k)) for k, v in local.items())
    if isinstance(local, list):
        if not isinstance(remote, list) or len(local) != len(remote):
            return False
        return all(is_subset(a, b) for a, b in zip(local, remote))
    return local == remote


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            k: ("***" if k in SECRET_KEYS and isinstance(v, str) else redact(v))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [redact(v) for v in value]
    return value


def _norm(text: str) -> str:
    return " ".join(text.split()).casefold()


def _changes(
    local: dict[str, Any], remote: dict[str, Any], fields: tuple[str, ...]
) -> dict[str, Any]:
    return {
        f: {"from": remote.get(f), "to": local[f]}
        for f in fields
        if f in local and not is_subset(local[f], remote.get(f))
    }


def _consumer_key(entry: dict[str, Any]) -> str:
    key = (
        entry.get("consumer_phone_number")
        or entry.get("consumer_bsuid")
        or entry.get("consumer_instagram_username")
        or ""
    )
    return key.lstrip("+")


def fetch_remote(client: MBAClient, desired: dict[str, Any]) -> dict[str, Any]:
    remote: dict[str, Any] = {}
    if "settings" in desired:
        settings = client.get_settings()
        remote["settings"] = settings[0] if settings else {}
    if "business_info" in desired:
        try:
            remote["business_info"] = client.get_business_info()
        except ApiError as e:
            if e.status != 404:
                raise
            remote["business_info"] = {}
    for key, collection in (
        ("skills", "agent_config/skills"),
        ("faqs", "agent_config/faq"),
        ("websites", "agent_config/websites"),
        ("allowlist", "agent_config/allowlist"),
    ):
        if key in desired:
            remote[key] = client.list_items(collection)
    if "connectors" in desired:
        connectors = client.list_items("agent_connectors")
        for c in connectors:
            c["tools"] = client.list_items(f"agent_connectors/{c['id']}/tools")
        remote["connectors"] = connectors
    return remote


def _diff_collection(
    ops: list[Op],
    unmanaged: list[str],
    kind: str,
    collection: str,
    local_items: list[dict[str, Any]],
    remote_items: list[dict[str, Any]],
    key: Callable[[dict[str, Any]], str],
    fields: tuple[str, ...],
    prune: bool,
    label: Callable[[dict[str, Any]], str],
) -> None:
    remote_by_key = {key(r): r for r in remote_items}
    seen = set()
    for item in local_items:
        k = key(item)
        seen.add(k)
        remote = remote_by_key.get(k)
        base = {"kind": kind, "label": label(item), "collection": collection}
        if remote is None:
            ops.append({**base, "action": "create", "body": item})
            continue
        changes = _changes(item, remote, fields)
        if changes:
            kept = {f: remote[f] for f in fields if remote.get(f) is not None}
            ops.append(
                {
                    **base,
                    "action": "update",
                    "id": remote["id"],
                    "body": {**kept, **item},
                    "changes": changes,
                }
            )
    for k, remote in remote_by_key.items():
        if k in seen:
            continue
        if prune:
            ops.append(
                {
                    "action": "delete",
                    "kind": kind,
                    "label": label(remote),
                    "collection": collection,
                    "id": remote["id"],
                }
            )
        else:
            unmanaged.append(f"{kind} {label(remote)}")


def _diff_singletons(
    ops: list[Op], desired: dict[str, Any], remote: dict[str, Any]
) -> None:
    if "settings" in desired:
        local = {k: v for k, v in desired["settings"].items() if k in SETTINGS_FIELDS}
        changes = _changes(local, remote["settings"], SETTINGS_FIELDS)
        if changes:
            ops.append(
                {
                    "action": "update",
                    "kind": "settings",
                    "label": "settings",
                    "body": local,
                    "changes": changes,
                }
            )
    if "business_info" in desired:
        local = desired["business_info"]
        live = remote["business_info"]
        changes = _changes(local, live, tuple(local.keys()))
        if changes:
            merged = {**{k: v for k, v in live.items() if v is not None}, **local}
            ops.append(
                {
                    "action": "update",
                    "kind": "business_info",
                    "label": "business info",
                    "body": merged,
                    "changes": changes,
                }
            )


def _diff_knowledge(
    ops: list[Op],
    unmanaged: list[str],
    desired: dict[str, Any],
    remote: dict[str, Any],
    prune: bool,
) -> None:
    if "skills" in desired:
        _diff_collection(
            ops, unmanaged, "skill", "agent_config/skills",
            desired["skills"], remote["skills"],
            lambda s: s["title"], SKILL_FIELDS, prune,
            lambda s: s.get("title", "?"),
        )  # fmt: skip
    if "faqs" in desired:
        _diff_collection(
            ops, unmanaged, "faq", "agent_config/faq",
            desired["faqs"], remote["faqs"],
            lambda f: _norm(f["question"]), ("answer",), prune,
            lambda f: repr(f["question"][:60]),
        )  # fmt: skip
    if "websites" in desired:
        _diff_collection(
            ops, unmanaged, "website", "agent_config/websites",
            desired["websites"], remote["websites"],
            lambda w: w["url"].rstrip("/"), WEBSITE_FIELDS, prune,
            lambda w: w["url"],
        )  # fmt: skip
    if "allowlist" in desired:
        local = [{"consumer_phone_number": p} for p in desired["allowlist"]]
        _diff_collection(
            ops, unmanaged, "allowlist", "agent_config/allowlist",
            local, remote["allowlist"],
            _consumer_key, (), prune,
            lambda a: a.get("consumer_phone_number") or a.get("consumer_bsuid") or "?",
        )  # fmt: skip


def _require_auth(body: dict[str, Any]) -> None:
    if body.get("auth_type") != "NONE" and not body.get("auth_config"):
        raise ConfigError(
            f"Connector {body.get('name')!r} needs auth_config in agent.yaml to be "
            "created or updated (live credentials are never copied).",
            "Add auth_config with ${ENV_VAR} references to secrets in .env.",
        )


def _check_certificate(conn: dict[str, Any], existing: dict[str, Any]) -> None:
    """requires_certificate can't be diffed; refuse a value the live mTLS state
    contradicts or cannot confirm instead of silently ignoring it."""
    if "requires_certificate" not in conn:
        return
    has = (existing.get("mtls_config") or {}).get("has_certificate")
    if not isinstance(has, bool) or has != bool(conn["requires_certificate"]):
        raise ConfigError(
            f"Connector {conn['name']!r}: requires_certificate does not match the "
            "live connector's certificate, and mba cannot change it after creation.",
            "Upload or remove the certificate with the connector API, or remove "
            "requires_certificate from agent.yaml.",
        )


def _connector_op(conn: dict[str, Any], existing: dict[str, Any] | None) -> Op | None:
    name = conn["name"]
    body = {k: v for k, v in conn.items() if k != "tools"}
    if existing is None:
        _require_auth(body)
        return {
            "action": "create",
            "kind": "connector",
            "label": name,
            "collection": "agent_connectors",
            "body": body,
        }
    _check_certificate(conn, existing)
    body = {k: v for k, v in body.items() if k not in CONNECTOR_CREATE_ONLY}
    # PUT replaces the connector, so keep live fields agent.yaml doesn't set.
    kept = {f: existing[f] for f in CONNECTOR_FIELDS if existing.get(f) is not None}
    body = {**kept, **body}
    changes = _changes(body, existing, CONNECTOR_FIELDS)
    if not changes:
        return None
    _require_auth(body)
    return {
        "action": "update",
        "kind": "connector",
        "label": name,
        "collection": "agent_connectors",
        "id": existing["id"],
        "body": body,
        "changes": changes,
    }


def _diff_connectors(
    ops: list[Op],
    unmanaged: list[str],
    desired: dict[str, Any],
    remote: dict[str, Any],
    prune: bool,
) -> None:
    remote_by_name = {c["name"]: c for c in remote["connectors"]}
    for conn in desired["connectors"]:
        name = conn["name"]
        existing = remote_by_name.get(name)
        op = _connector_op(conn, existing)
        if op is not None:
            ops.append(op)
        if existing is None:
            for tool in conn.get("tools", []):
                ops.append(
                    {
                        "action": "create",
                        "kind": "tool",
                        "label": f"{name}.{tool['name']}",
                        "connector": name,
                        "body": tool,
                    }
                )
            continue
        _diff_collection(
            ops, unmanaged, "tool", f"agent_connectors/{existing['id']}/tools",
            conn.get("tools", []), existing.get("tools", []),
            lambda t: t["name"], TOOL_FIELDS, prune,
            lambda t, c=name: f"{c}.{t['name']}",
        )  # fmt: skip
    local_names = {c["name"] for c in desired["connectors"]}
    for name, existing in remote_by_name.items():
        if name in local_names:
            continue
        if prune:
            ops.append(
                {
                    "action": "delete",
                    "kind": "connector",
                    "label": name,
                    "collection": "agent_connectors",
                    "id": existing["id"],
                }
            )
        else:
            unmanaged.append(f"connector {name}")


def _rotation_op(name: str, desired: dict[str, Any], remote: dict[str, Any]) -> Op:
    local = next((c for c in desired.get("connectors", []) if c["name"] == name), None)
    existing = next(
        (c for c in remote.get("connectors", []) if c["name"] == name), None
    )
    if local is None:
        raise ConfigError(
            f"--rotate-credentials {name!r}: no such connector in agent.yaml."
        )
    if existing is None:
        raise ConfigError(
            f"--rotate-credentials {name!r}: the connector does not exist yet; "
            "it is created with the credentials in agent.yaml."
        )
    auth = local.get("auth_config") or {}
    auth_type = local.get("auth_type")
    if auth_type == "API_KEY" and auth.get("api_key"):
        method, body = "upsert_api_key", auth["api_key"]
    elif auth_type == "OAUTH2_CLIENT_CREDENTIALS" and auth.get(
        "oauth2_client_credentials"
    ):
        method, body = "upsert_oauth", auth["oauth2_client_credentials"]
    else:
        raise ConfigError(
            f"--rotate-credentials {name!r}: agent.yaml must supply auth_config "
            "for auth_type API_KEY or OAUTH2_CLIENT_CREDENTIALS."
        )
    return {
        "action": "rotate",
        "kind": "credentials",
        "label": name,
        "id": existing["id"],
        "method": method,
        "body": body,
    }


def classify(ops: Iterable[Op]) -> dict[str, list[str]]:
    """Splits a plan into who-it-reaches changes and behavior changes."""
    out: dict[str, list[str]] = {"widening": [], "narrowing": [], "config": []}
    for op in ops:
        label = f"{op['action']} {op['kind']} {op['label']}"
        if op["kind"] == "allowlist":
            out["widening" if op["action"] == "create" else "narrowing"].append(label)
            continue
        if op["kind"] != "settings":
            out["config"].append(label)
            continue
        changes = op.get("changes", {})
        if "ai_audience" in changes:
            frm = changes["ai_audience"]["from"] or DEFAULT_AUDIENCE
            to = changes["ai_audience"]["to"] or DEFAULT_AUDIENCE
            if frm != to:
                kind = "narrowing" if to == NARROW_AUDIENCE else "widening"
                out[kind].append(f"ai_audience {frm} -> {to}")
        if set(changes) - {"ai_audience"}:
            out["config"].append(label)
    return out


def compute_plan(
    desired: dict[str, Any],
    remote: dict[str, Any],
    binding: Binding,
    prune: bool = False,
    rotate: Iterable[str] = (),
) -> dict[str, Any]:
    ops: list[Op] = []
    unmanaged: list[str] = []
    _diff_singletons(ops, desired, remote)
    _diff_knowledge(ops, unmanaged, desired, remote, prune)
    if "connectors" in desired:
        _diff_connectors(ops, unmanaged, desired, remote, prune)
    rotations = sorted(set(rotate))
    ops += [_rotation_op(name, desired, remote) for name in rotations]

    # Deletes run last, tools before their connectors.
    ops.sort(
        key=lambda o: (
            o["action"] == "delete",
            o["action"] == "delete" and o["kind"] == "connector",
        )
    )
    material = {
        "target": binding.target,
        "origin": binding.origin,
        "desired": desired,
        "remote": remote,
        "prune": prune,
        "rotate": rotations,
        "ops": ops,
    }
    plan_id = hmac.new(
        binding.key,
        json.dumps(material, sort_keys=True, default=str).encode(),
        hashlib.sha256,
    ).hexdigest()[:16]
    return {
        "plan_id": plan_id,
        "target": binding.target,
        "ops": ops,
        "unmanaged": unmanaged,
        "exposure": classify(ops),
    }


def render_plan(plan: dict[str, Any]) -> str:
    symbols = {"create": "+", "update": "~", "delete": "-", "rotate": "*"}
    lines = []
    for op in plan["ops"]:
        line = f"  {symbols[op['action']]} {op['kind']} {op['label']}"
        if op.get("changes"):
            line += f"  ({', '.join(op['changes'])})"
        lines.append(line)
    if not lines:
        lines.append("  No changes. The live agent matches agent.yaml.")
    out = [f"Plan {plan['plan_id']} for {plan['target']}:"] + lines
    if plan["unmanaged"]:
        out.append("")
        out.append("Live but not in agent.yaml (left alone; pass --prune to delete):")
        out.extend(f"  ? {u}" for u in plan["unmanaged"])
    widening = plan["exposure"]["widening"]
    if widening:
        out.append("")
        out.append(
            "Widens who the agent answers (if it is live, apply needs --widen-audience):"
        )
        out.extend(f"  ! {w}" for w in widening)
    counts = {a: sum(1 for o in plan["ops"] if o["action"] == a) for a in symbols}
    out.append("")
    out.append(
        f"{counts['create']} to create, {counts['update']} to update, "
        f"{counts['delete']} to delete, {counts['rotate']} credentials to rotate."
    )
    return "\n".join(out)


def is_live(settings: list[dict[str, Any]]) -> bool:
    """Whether the agent is answering customers. Unknown counts as live."""
    if not settings:
        return False
    enabled = (settings[0].get("rollout") or {}).get("enabled")
    return enabled is not False


def check_exposure(
    plan: dict[str, Any],
    settings: list[dict[str, Any]],
    widen_audience: bool,
    gate: Callable[[], Any],
) -> None:
    """Central rules for what apply may do, given whether the agent is live.

    While the agent is disabled, anything may change: `mba enable` is gated.
    While it is live, behavior changes are refused (disable, apply, eval,
    enable), and widening who it answers needs --widen-audience plus a passing
    eval of the live config. Narrowing is always allowed.
    """
    exposure = plan["exposure"]
    if not is_live(settings):
        return
    if exposure["config"]:
        raise GateError(
            "The agent is live, so this plan's configuration changes would reach "
            "customers untested: " + "; ".join(exposure["config"]) + ".",
            "Run `mba disable --yes`, apply, run `mba eval`, then `mba enable --yes`.",
        )
    if exposure["widening"]:
        if not widen_audience:
            raise NeedsHumanError(
                "This plan widens who the agent answers: "
                + "; ".join(exposure["widening"])
                + ".",
                "Confirm with the business owner, then re-run with --widen-audience.",
            )
        gate()


def _apply_op(client: MBAClient, op: Op, connector_ids: dict[str, str]) -> Any:
    body: dict[str, Any] = copy.deepcopy(op.get("body") or {})
    kind, action = op["kind"], op["action"]
    if action == "rotate":
        if op["method"] == "upsert_api_key":
            return client.upsert_api_key(op["id"], body)
        return client.upsert_oauth(op["id"], body)
    if kind == "settings":
        return client.put_settings(body)
    if kind == "business_info":
        return client.put_business_info(body)
    if kind == "tool" and "connector" in op:
        tools = f"agent_connectors/{connector_ids[op['connector']]}/tools"
        return client.create(tools, body)
    if action == "create":
        res = client.create(op["collection"], body)
        if kind == "connector":
            connector_ids[body["name"]] = res["id"]
        return res
    if action == "update":
        return client.update(op["collection"], op["id"], body)
    return client.delete(op["collection"], op["id"])


def apply_plan(
    client: MBAClient,
    desired: dict[str, Any],
    plan_id: str,
    binding: Binding,
    state: State,
    *,
    prune: bool = False,
    rotate: Iterable[str] = (),
    widen_audience: bool = False,
    gate: Callable[[], Any],
) -> list[dict[str, Any]]:
    """Recomputes the plan, applies it only if it still matches `plan_id` and
    the exposure rules allow it, and records the attempt in `state`."""
    remote = fetch_remote(client, desired)
    plan = compute_plan(desired, remote, binding, prune, rotate)
    if not hmac.compare_digest(plan["plan_id"], plan_id):
        raise PlanStaleError(
            f"Plan {plan_id} is stale: the target, the live agent, agent.yaml, "
            "its secrets or the flags changed.",
            "Run `mba plan` again, review it, and apply the new plan ID.",
        )
    record = {
        "plan_id": plan_id,
        "target": binding.target,
        "status": "in_progress",
        "started_at": time.time(),
        "completed_ops": 0,
    }
    if not plan["ops"]:
        # The reviewed plan shows the live agent already matches agent.yaml,
        # which settles an earlier apply whose outcome was lost. This does
        # not count as a configuration change.
        now = time.time()
        state.write_apply(
            binding.target,
            {**record, "status": "complete", "finished_at": now, "reconciled": True},
        )
        return []
    check_exposure(plan, client.get_settings(), widen_audience, gate)

    updates: dict[str, Any] = {}
    if plan["exposure"]["config"]:
        # Recorded before the first write, so a partial apply still closes the gate.
        updates["last_config_change_at"] = record["started_at"]
    state.write_apply(binding.target, record, **updates)

    connector_ids = {c["name"]: c["id"] for c in remote.get("connectors", [])}
    results = []
    try:
        for op in plan["ops"]:
            res = _apply_op(client, op, connector_ids)
            results.append(
                {
                    "action": op["action"],
                    "kind": op["kind"],
                    "label": op["label"],
                    "result": redact(res),
                }
            )
    except BaseException:
        ops = plan["ops"]
        failed = ops[len(results)] if len(results) < len(ops) else None
        state.write_apply(
            binding.target,
            {
                **record,
                "status": "failed",
                "finished_at": time.time(),
                "completed_ops": len(results),
                "failed_op": failed
                and f"{failed['action']} {failed['kind']} {failed['label']}",
            },
        )
        raise
    state.write_apply(
        binding.target,
        {
            **record,
            "status": "complete",
            "finished_at": time.time(),
            "completed_ops": len(results),
        },
    )
    return results


def snapshot(client: MBAClient) -> dict[str, Any]:
    """Exports the live agent as an agent.yaml document. auth_config is never
    exported."""
    return _snapshot_doc(fetch_remote(client, dict.fromkeys(ALL_SECTIONS)))


def _snapshot_doc(remote: dict[str, Any]) -> dict[str, Any]:
    s = remote["settings"]
    doc: dict[str, Any] = {
        "version": 1,
        "settings": {k: s[k] for k in SETTINGS_FIELDS if s.get(k) is not None},
    }
    bi = {k: v for k, v in remote["business_info"].items() if v not in (None, "", {})}
    if bi:
        doc["business_info"] = bi
    doc["skills"] = [
        {k: sk[k] for k in ("title",) + SKILL_FIELDS if sk.get(k)}
        for sk in remote["skills"]
    ]
    doc["faqs"] = [
        {"question": f["question"], "answer": f["answer"]} for f in remote["faqs"]
    ]
    doc["websites"] = [
        {k: w[k] for k in ("url",) + WEBSITE_FIELDS if w.get(k)}
        for w in remote["websites"]
    ]
    doc["allowlist"] = [
        a["consumer_phone_number"]
        for a in remote["allowlist"]
        if a.get("consumer_phone_number")
    ]
    doc["connectors"] = []
    for c in remote["connectors"]:
        conn = {k: c[k] for k in ("name",) + CONNECTOR_FIELDS if c.get(k)}
        conn["tools"] = [
            {k: t[k] for k in ("name",) + TOOL_FIELDS if t.get(k) is not None}
            for t in c.get("tools", [])
        ]
        doc["connectors"].append(conn)
    return doc


def _require_unversioned(client: MBAClient) -> None:
    """Refuses numbers on versioned configuration.

    There an A/B experiment can serve other configuration versions to some
    customers, and the public API offers no way to confirm that none runs, so
    an eval of the active version cannot vouch for what customers receive.
    Only `404` (the documented "not migrated" answer) lets the gate continue;
    any other answer, including a malformed one, refuses.
    """
    try:
        active = client.active_version()
    except ApiError as e:
        if e.status != 404:  # 404: the number has no versioned configuration
            raise
        return
    if not isinstance(active, dict) or not isinstance(active.get("version_id"), str):
        raise GateError("Unexpected response reading the active configuration version.")
    raise GateError(
        "This number uses versioned configuration. The public API cannot confirm "
        "that no A/B experiment serves other configuration versions to some "
        "customers, so mba cannot verify what customers receive and refuses eval, "
        "enable and live audience widening on it.",
        "`mba versions` and `mba rollback` remain available for this number.",
    )


def live_digest(client: MBAClient) -> str:
    """Digest of everything that shapes the agent's replies: the live config
    without rollout, audience and allowlist, plus knowledge files and mTLS
    state. Numbers on versioned configuration are refused. Any read error
    propagates (fails closed)."""
    _require_unversioned(client)
    remote = fetch_remote(client, dict.fromkeys(ALL_SECTIONS))
    doc = _snapshot_doc(remote)
    doc["settings"].pop("ai_audience", None)
    doc.pop("allowlist", None)
    doc["skills"].sort(key=lambda s: s.get("title", ""))
    doc["faqs"].sort(key=lambda f: f["question"])
    doc["websites"].sort(key=lambda w: w.get("url", ""))
    mtls = {c["name"]: c.get("mtls_config") or {} for c in remote["connectors"]}
    for c in doc["connectors"]:
        c["mtls"] = {
            k: mtls[c["name"]].get(k) for k in ("has_certificate", "fingerprint")
        }
        c["tools"].sort(key=lambda t: t.get("name", ""))
    doc["connectors"].sort(key=lambda c: c.get("name", ""))
    doc["knowledge_files"] = sorted(
        (
            {"id": f.get("id"), "file_name": f.get("file_name")}
            for f in client.list_items("agent_config/files")
        ),
        key=lambda f: (str(f["file_name"]), str(f["id"])),
    )
    return hashlib.sha256(
        json.dumps(doc, sort_keys=True, default=str).encode()
    ).hexdigest()


def state_for(agent_file: Path) -> State:
    return State(agent_file.resolve().parent / ".mba")
