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
"""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Any, Callable

from .client import MBAClient
from .errors import ApiError, PlanStaleError

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
CONNECTOR_FIELDS = ("description", "base_url", "auth_type", "connector_protocol")
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

Op = dict[str, Any]


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
        body = {k: v for k, v in conn.items() if k != "tools"}
        existing = remote_by_name.get(name)
        if existing is not None:
            # PUT replaces the connector, so keep live fields agent.yaml doesn't set.
            # auth_config is excluded: the API may return it redacted.
            kept_fields = CONNECTOR_FIELDS + ("user_auth_injection_config",)
            kept = {f: existing[f] for f in kept_fields if existing.get(f) is not None}
            body = {**kept, **body}
        if existing is None:
            ops.append(
                {
                    "action": "create",
                    "kind": "connector",
                    "label": name,
                    "collection": "agent_connectors",
                    "body": body,
                }
            )
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
        changes = _changes(body, existing, CONNECTOR_FIELDS)
        if changes:
            ops.append(
                {
                    "action": "update",
                    "kind": "connector",
                    "label": name,
                    "collection": "agent_connectors",
                    "id": existing["id"],
                    "body": body,
                    "changes": changes,
                }
            )
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


def compute_plan(
    desired: dict[str, Any], remote: dict[str, Any], prune: bool = False
) -> dict[str, Any]:
    ops: list[Op] = []
    unmanaged: list[str] = []
    _diff_singletons(ops, desired, remote)
    _diff_knowledge(ops, unmanaged, desired, remote, prune)
    if "connectors" in desired:
        _diff_connectors(ops, unmanaged, desired, remote, prune)

    # Deletes run last, tools before their connectors.
    ops.sort(
        key=lambda o: (
            o["action"] == "delete",
            o["action"] == "delete" and o["kind"] == "connector",
        )
    )
    fingerprint = hashlib.sha256(
        json.dumps(
            {"ops": redact(ops), "remote": redact(remote)}, sort_keys=True, default=str
        ).encode()
    ).hexdigest()[:12]
    return {"plan_id": fingerprint, "ops": ops, "unmanaged": unmanaged}


def render_plan(plan: dict[str, Any]) -> str:
    symbols = {"create": "+", "update": "~", "delete": "-"}
    lines = []
    for op in plan["ops"]:
        line = f"  {symbols[op['action']]} {op['kind']} {op['label']}"
        if op.get("changes"):
            line += f"  ({', '.join(op['changes'])})"
        lines.append(line)
    if not lines:
        lines.append("  No changes. The live agent matches agent.yaml.")
    out = ["Plan " + plan["plan_id"] + ":"] + lines
    if plan["unmanaged"]:
        out.append("")
        out.append("Live but not in agent.yaml (left alone; pass --prune to delete):")
        out.extend(f"  ? {u}" for u in plan["unmanaged"])
    counts = {a: sum(1 for o in plan["ops"] if o["action"] == a) for a in symbols}
    out.append("")
    out.append(
        f"{counts['create']} to create, {counts['update']} to update, "
        f"{counts['delete']} to delete."
    )
    return "\n".join(out)


def _apply_op(client: MBAClient, op: Op, connector_ids: dict[str, str]) -> Any:
    body: dict[str, Any] = copy.deepcopy(op.get("body") or {})
    kind, action = op["kind"], op["action"]
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
    client: MBAClient, desired: dict[str, Any], plan_id: str, prune: bool = False
) -> list[dict[str, Any]]:
    """Recomputes the plan and applies it only if it still matches `plan_id`."""
    remote = fetch_remote(client, desired)
    plan = compute_plan(desired, remote, prune)
    if plan["plan_id"] != plan_id:
        raise PlanStaleError(
            f"Plan {plan_id} is stale: the live agent or agent.yaml changed "
            f"(current plan is {plan['plan_id']}).",
            "Run `mba plan` again, review it, and apply the new plan ID.",
        )
    connector_ids = {c["name"]: c["id"] for c in remote.get("connectors", [])}
    results = []
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
    return results


def snapshot(client: MBAClient) -> dict[str, Any]:
    """Exports the live agent as an agent.yaml document (secrets omitted)."""
    remote = fetch_remote(client, dict.fromkeys(ALL_SECTIONS))
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
