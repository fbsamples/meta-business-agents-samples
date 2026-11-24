# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

"""`mba`: configure a Meta Business Agent from agent.yaml.

Built for people and coding agents alike: every command takes --json, never
prompts, and exits with a documented code (see AGENTS.md).
"""

from __future__ import annotations

import argparse
import json
import shlex
import shutil
import sys
import time
import traceback
from pathlib import Path
from typing import Any, Callable

from . import evals as ev, plan as pl
from .client import MBAClient
from .config import (
    contains_secret,
    credentials,
    dump_yaml,
    load_agent,
    load_dotenv,
    SCHEMA_PATH,
    schema_validation_available,
    Scrubber,
    scrubber_for,
    secret_detector,
)
from .errors import (
    ApiError,
    ConfigError,
    EXIT_ERROR,
    EXIT_NEEDS_HUMAN,
    EXIT_OK,
    GateError,
    MBAError,
    NeedsHumanError,
)

TEMPLATES: Path = Path(__file__).resolve().parent.parent / "templates"


class Output:
    """All CLI output goes through here so secrets from .env never print."""

    def __init__(self, as_json: bool, scrub: Scrubber) -> None:
        self.as_json = as_json
        self.scrub = scrub

    def emit(self, data: Any, text: str) -> None:
        print(
            self.scrub(json.dumps(data, indent=2, default=str))
            if self.as_json
            else self.scrub(text)
        )

    def error(self, text: str) -> None:
        print(self.scrub(text), file=sys.stderr)


def _client(args: argparse.Namespace) -> MBAClient:
    creds = credentials(args.env_values)
    return MBAClient(creds["token"], creds["entity_id"])


def _require_yes(args: argparse.Namespace, what: str) -> None:
    if not args.yes:
        raise NeedsHumanError(
            f"{what} changes the live agent.",
            "Confirm with the business owner, then re-run with --yes.",
        )


def _load(args: argparse.Namespace) -> dict[str, Any]:
    return load_agent(
        Path(args.file), args.env_values, credential_files=[Path(args.env)]
    )


def _config_dir(args: argparse.Namespace) -> Path:
    return Path(args.file).resolve().parent


def _evals_dir(args: argparse.Namespace) -> Path:
    return _config_dir(args) / "evals"


def _binding(args: argparse.Namespace, client: MBAClient, create: bool) -> pl.Binding:
    return pl.Binding(
        key=pl.approval_key(args.state, create=create),
        target=client.target,
        origin=str(Path(args.file).resolve()),
    )


def _gate(args: argparse.Namespace, client: MBAClient) -> Callable[[], dict[str, Any]]:
    def gate() -> dict[str, Any]:
        return ev.check_gate(
            args.state,
            target=client.target,
            suite=ev.load_suite(_evals_dir(args))[1],
            live_digest=lambda: pl.live_digest(client),
        )

    return gate


def cmd_init(args: argparse.Namespace, out: Output) -> int:
    src = TEMPLATES / args.template
    if not src.is_dir():
        choices = ", ".join(sorted(p.name for p in TEMPLATES.iterdir() if p.is_dir()))
        raise ConfigError(
            f"Unknown template {args.template!r}.", f"Available: {choices}"
        )
    dest = Path.cwd()
    items = [
        i for i in sorted(src.iterdir()) if i.name not in ("README.md", "mock-backend")
    ]
    conflicts = [i.name for i in items if (dest / i.name).exists()]
    if conflicts and not args.force:
        raise ConfigError(
            f"Already exists: {', '.join(conflicts)}.",
            "Pass --force to overwrite, or move them first.",
        )
    copied = []
    for item in items:
        target = dest / item.name
        if item.is_dir():
            shutil.rmtree(target, ignore_errors=True)
            shutil.copytree(item, target)
        else:
            shutil.copy2(item, target)
        copied.append(item.name)
    out.emit(
        {"template": args.template, "copied": copied},
        f"Copied the {args.template} template: {', '.join(copied)}.\n"
        f"Next: fill in the TODOs in agent.yaml (see templates/{args.template}/README.md), "
        "then `mba plan`.",
    )
    return EXIT_OK


def _doctor_remote(client: MBAClient, add: Callable[..., None]) -> None:
    try:
        elig = client.get_eligibility()
        ok = bool(elig.get("is_eligible"))
        add(
            "eligibility",
            ok,
            "eligible" if ok else f"not eligible: {elig.get('ineligibility_reason')}",
            ""
            if ok
            else "See the eligibility criteria in the Meta Business Agent docs.",
        )
    except ApiError as e:
        add("eligibility", False, str(e), e.hint or "")
    try:
        settings = client.get_settings()
        if not settings:
            add(
                "onboarded",
                False,
                "no agent on this number",
                "Run `mba onboard --yes`.",
            )
            return
        s = settings[0]
        enabled = (s.get("rollout") or {}).get("enabled")
        add(
            "onboarded",
            True,
            f"agent {s.get('agent_id')}, enabled={enabled}, audience={s.get('ai_audience')}",
        )
    except ApiError as e:
        add("onboarded", False, str(e), e.hint or "")


def cmd_doctor(args: argparse.Namespace, out: Output) -> int:
    checks: list[dict[str, Any]] = []

    def add(
        name: str, ok: bool, detail: str, fix: str = "", info: bool = False
    ) -> None:
        checks.append(
            {
                "check": name,
                "ok": ok,
                "detail": detail,
                "fix": fix,
                "informational": info,
            }
        )

    client = None
    try:
        client = _client(args)
        add("credentials", True, f"MBA_ENTITY_ID={client.entity_id}")
    except ConfigError as e:
        add("credentials", False, str(e), e.hint or "")

    agent_file = Path(args.file)
    if agent_file.exists():
        try:
            _load(args)
            add("agent.yaml", True, "valid")
        except ConfigError as e:
            add("agent.yaml", False, str(e), e.hint or "")
    else:
        add(
            "agent.yaml",
            True,
            "not created yet",
            "Run `mba init --template post-purchase` or `mba pull`.",
        )
    if not schema_validation_available():
        add(
            "schema validation",
            False,
            "jsonschema is not installed",
            'pip install -e "." to install the kit with its dependencies.',
        )

    if client:
        _doctor_remote(client, add)
        try:
            run = _gate(args, client)()
            add(
                "go-live gate",
                True,
                f"eval run from {time.ctime(run['started_at'])} passed",
            )
        except MBAError as e:
            # Not passing the gate is expected before launch, so it doesn't make the setup unhealthy.
            add("go-live gate", False, f"not yet: {e}", e.hint or "", info=True)

    healthy = all(c["ok"] or c["informational"] for c in checks)
    text = "\n".join(
        f"{'ok  ' if c['ok'] else 'info' if c['informational'] else 'FAIL'} {c['check']}: {c['detail']}"
        + (f"\n     -> {c['fix']}" if c["fix"] else "")
        for c in checks
    )
    out.emit({"healthy": healthy, "checks": checks}, text)
    return EXIT_OK if healthy else EXIT_NEEDS_HUMAN


def cmd_onboard(args: argparse.Namespace, out: Output) -> int:
    _require_yes(args, "Onboarding")
    res = _client(args).onboard()
    out.emit(
        res,
        f"Onboarded. agent_id={res.get('agent_id')}. Data preparation runs in the "
        "background; wait a minute before testing.",
    )
    return EXIT_OK


def cmd_pull(args: argparse.Namespace, out: Output) -> int:
    target = Path(args.out)
    if target.exists() and not args.force:
        raise ConfigError(
            f"{target} exists.", "Pass --force to overwrite, or --out another path."
        )
    doc = pl.snapshot(_client(args))
    header = (
        "# Exported by `mba pull`. Connector auth_config is never exported: add it\n"
        "# to each connector, referencing secrets as ${ENV_VAR} from .env."
    )
    target.write_text(out.scrub(dump_yaml(doc, header)))
    counts = {k: len(v) for k, v in doc.items() if isinstance(v, list)}
    out.emit({"written": str(target), "counts": counts}, f"Wrote {target}.")
    return EXIT_OK


def _apply_command(args: argparse.Namespace, plan: dict[str, Any], live: bool) -> str:
    parts = ["mba"]
    if args.file != "agent.yaml":
        parts += ["--file", shlex.quote(args.file)]
    if args.env != ".env":
        parts += ["--env", shlex.quote(args.env)]
    parts += ["apply", "--plan-id", plan["plan_id"]]
    if args.prune:
        parts.append("--prune")
    for name in sorted(set(args.rotate_credentials)):
        parts += ["--rotate-credentials", shlex.quote(name)]
    if live and plan["exposure"]["widening"]:
        parts.append("--widen-audience")
    parts.append("--yes")
    return " ".join(parts)


def cmd_plan(args: argparse.Namespace, out: Output) -> int:
    client = _client(args)
    desired = _load(args)
    plan = pl.compute_plan(
        desired,
        pl.fetch_remote(client, desired),
        _binding(args, client, create=True),
        args.prune,
        args.rotate_credentials,
    )
    text = pl.render_plan(plan)
    if plan["ops"]:
        live = pl.is_live(client.get_settings())
        if live and plan["exposure"]["config"]:
            text += (
                "\n\nThe agent is live: disable it before applying configuration "
                "changes, then eval and enable again."
            )
        text += (
            "\n\nAfter the business owner approves this plan, apply it with:\n  "
            + _apply_command(args, plan, live)
        )
    out.emit(pl.redact(plan), text)
    return EXIT_OK


def cmd_apply(args: argparse.Namespace, out: Output) -> int:
    _require_yes(args, "Applying a plan")
    client = _client(args)
    desired = _load(args)
    results = pl.apply_plan(
        client,
        desired,
        args.plan_id,
        _binding(args, client, create=False),
        args.state,
        prune=args.prune,
        rotate=args.rotate_credentials,
        widen_audience=args.widen_audience,
        gate=_gate(args, client),
    )
    lines = [f"  {r['action']} {r['kind']} {r['label']}" for r in results]
    out.emit(
        {"applied": results},
        "Applied:\n"
        + ("\n".join(lines) or "  Nothing to do.")
        + "\n\nNext: `mba eval`.",
    )
    return EXIT_OK


def cmd_test(args: argparse.Namespace, out: Output) -> int:
    res = _client(args).agent_test(args.message, args.conversation_id)
    extra = []
    if res.get("handoff_reason"):
        extra.append(f"[handoff: {res['handoff_reason']}]")
    if res.get("quick_replies"):
        extra.append(f"[quick replies: {', '.join(res['quick_replies'])}]")
    if res.get("no_response_reason"):
        extra.append(f"[no response: {res['no_response_reason']}]")
    text = (
        f"{res.get('agent_response') or ''}\n{' '.join(extra)}\n"
        f"(conversation_id={res.get('conversation_id')})"
    )
    out.emit(res, text.strip())
    return EXIT_OK


def _render_eval(run: dict[str, Any], verbose: bool) -> str:
    lines = []
    for s in run["scenarios"]:
        lines.append(f"{'PASS' if s['passed'] else 'FAIL'} {s['name']}")
        lines += [f"     {f}" for f in s["failures"]]
        if verbose or not s["passed"]:
            for t in s["transcript"]:
                lines.append(f"     > {t['user']}\n     < {t['agent']}")
        if s["success_criteria"]:
            lines.append("     judge: " + "; ".join(s["success_criteria"]))
    passed = sum(1 for s in run["scenarios"] if s["passed"])
    lines.append(f"\n{passed}/{len(run['scenarios'])} scenarios passed.")
    return "\n".join(lines)


def cmd_eval(args: argparse.Namespace, out: Output) -> int:
    canonical = _evals_dir(args)
    evals_dir = Path(args.dir).resolve() if args.dir else canonical
    scenarios, suite = ev.load_suite(evals_dir, args.only)
    if contains_secret(json.dumps(scenarios), secret_detector(args.env_values)):
        raise ConfigError(
            f"A scenario in {evals_dir} contains the value of a secret from .env.",
            "Scenario turns are sent to the Agent Test API; remove the secret.",
        )
    client = _client(args)
    run = ev.run_scenarios(
        client,
        scenarios,
        args.state,
        complete=not args.only and evals_dir == canonical,
        suite_dir=evals_dir,
        suite=suite,
        config_digest=lambda: pl.live_digest(client),
        scrub=out.scrub,
    )
    out.emit(run, _render_eval(run, args.verbose))
    return EXIT_OK if run["passed"] else GateError.exit_code


def cmd_eval_remote(args: argparse.Namespace, out: Output) -> int:
    client = _client(args)
    if args.action == "cases":
        res = client.eval_cases()
        text = "\n".join(
            f"{c['id']}  {c['scenario'][:80]}" for c in res.get("eval_cases", [])
        )
    elif args.action == "run":
        res = client.eval_run(args.ids)
        text = (
            f"Started job {res.get('job_id')}. "
            f"Check with: mba eval-remote status {res.get('job_id')}"
        )
    else:
        res = client.eval_status(args.ids[0])
        text = json.dumps(res, indent=2)
    out.emit(res, text)
    return EXIT_OK


def cmd_versions(args: argparse.Namespace, out: Output) -> int:
    res = _client(args).list_versions(args.limit)
    text = "\n".join(
        f"{'*' if v.get('is_active') else ' '} {v['version_id']}  "
        f"{time.ctime(v['activated_at'])}  {v.get('reason', '')}"
        for v in res.get("data", [])
    )
    out.emit(
        res,
        text or "No versions (this number may not be on versioned configuration yet).",
    )
    return EXIT_OK


def cmd_rollback(args: argparse.Namespace, out: Output) -> int:
    _require_yes(args, "Rollback")
    client = _client(args)
    if pl.is_live(client.get_settings()):
        raise GateError(
            "The agent is live, so a rollback would serve customers an untested "
            "configuration.",
            "Run `mba disable --yes`, roll back, run `mba eval`, then `mba enable --yes`.",
        )
    active = client.active_version().get("version_id")
    args.state.write(last_config_change_at=time.time())
    res = client.set_active_version(args.version_id, expected_active_version_id=active)
    out.emit(
        res,
        f"Now serving {res.get('version_id')} (was {active}). agent.yaml no longer "
        "matches; run `mba pull --force` or re-apply.",
    )
    return EXIT_OK


def cmd_enable(args: argparse.Namespace, out: Output) -> int:
    _require_yes(args, "Enabling the agent")
    client = _client(args)
    settings = client.get_settings()
    if not settings:
        raise NeedsHumanError("No agent on this number.", "Run `mba onboard --yes`.")
    audience = settings[0].get("ai_audience") or pl.DEFAULT_AUDIENCE
    if audience != pl.NARROW_AUDIENCE and not args.widen_audience:
        raise NeedsHumanError(
            f"The agent's audience is {audience}: enabling it answers every customer.",
            "Enable with ai_audience ALLOWLISTED_ONLY first, or confirm with the "
            "business owner and re-run with --widen-audience.",
        )
    run = _gate(args, client)()
    res = client.put_settings({"rollout": {"enabled": True}})
    out.emit(
        {"settings": res, "gate_run": run["ran_at"]},
        f"Agent enabled for audience {res.get('ai_audience')}. "
        f"Gate: eval run from {time.ctime(run['ran_at'])}.",
    )
    return EXIT_OK


def cmd_disable(args: argparse.Namespace, out: Output) -> int:
    _require_yes(args, "Disabling the agent")
    res = _client(args).put_settings({"rollout": {"enabled": False}})
    out.emit(res, "Agent disabled. Customers are routed to the business as before.")
    return EXIT_OK


def _find_connector(client: MBAClient, name: str) -> dict[str, Any]:
    conn = next(
        (c for c in client.list_items("agent_connectors") if c["name"] == name), None
    )
    if conn is None:
        raise ConfigError(f"Connector {name!r} not found.", "Apply agent.yaml first.")
    return conn


def cmd_run_tool(args: argparse.Namespace, out: Output) -> int:
    client = _client(args)
    conn = _find_connector(client, args.connector)
    tools = client.list_items(f"agent_connectors/{conn['id']}/tools")
    tool = next((t for t in tools if t["name"] == args.tool), None)
    if tool is None:
        raise ConfigError(f"Tool {args.tool!r} not found on {args.connector!r}.")
    method = (tool.get("request_definition") or {}).get("method")
    if method != "GET" and not args.yes:
        raise NeedsHumanError(
            f"Tool {args.tool!r} uses {method or 'an unknown method'}, so it can "
            "change data in the business's backend.",
            "Confirm with the business owner, then re-run with --yes.",
        )
    res = client.run_tool(conn["id"], tool["id"], args.input)
    out.emit(res, f"status={res.get('status')}\n{res.get('output')}")
    return EXIT_OK


def cmd_logs(args: argparse.Namespace, out: Output) -> int:
    client = _client(args)
    conn = _find_connector(client, args.connector)
    res = client.connector_logs(conn["id"], include_stats="true", limit=args.limit)
    st = res.get("stats") or {}
    rows = "\n".join(
        f"{d.get('event_time')} {d.get('tool_name')} "
        f"{d.get('failure_code_name') or ''} {d.get('error_message') or ''}"
        for d in res.get("data", [])
    )
    text = (
        f"success rate {st.get('success_rate')}, p95 {st.get('p95_latency_s')}s "
        f"over {st.get('time_window_seconds')}s\n{rows}"
    )
    out.emit(res, text)
    return EXIT_OK


def cmd_event(args: argparse.Namespace, out: Output) -> int:
    client = _client(args)
    if args.action == "send":
        _require_yes(args, "Sending an event (it can message a real customer)")
        res = client.send_event(args.to, args.type, args.payload)
        text = f"{res.get('status')} agent_event_id={res.get('agent_event_id')}"
    else:
        res = client.get_event(args.id)
        text = json.dumps(res, indent=2)
    out.emit(res, text)
    return EXIT_OK


def cmd_schema(args: argparse.Namespace, out: Output) -> int:
    print(SCHEMA_PATH.read_text())
    return EXIT_OK


def _add_rotate(sp: argparse.ArgumentParser) -> None:
    sp.add_argument(
        "--rotate-credentials",
        action="append",
        default=[],
        metavar="CONNECTOR",
        help="send this connector's auth_config from agent.yaml (agent must be disabled)",
    )


def _add_widen(sp: argparse.ArgumentParser) -> None:
    sp.add_argument(
        "--widen-audience",
        action="store_true",
        help="confirm a change that makes the agent answer more customers",
    )


def _add_commands(
    cmd: Callable[[str, Callable[..., int], str], argparse.ArgumentParser],
) -> None:
    sp = cmd(
        "init",
        cmd_init,
        "Start from a use-case template (writes agent.yaml, skills/, evals/).",
    )
    sp.add_argument("--template", required=True)
    sp.add_argument("--force", action="store_true")
    cmd(
        "doctor",
        cmd_doctor,
        "Check credentials, eligibility, onboarding and the go-live gate. Read-only.",
    )
    sp = cmd("onboard", cmd_onboard, "Create the agent on this phone number. Write.")
    sp.add_argument("--yes", action="store_true")
    sp = cmd("pull", cmd_pull, "Export the live agent to agent.yaml. Read-only.")
    sp.add_argument("--out", default="agent.yaml")
    sp.add_argument("--force", action="store_true")
    sp = cmd("plan", cmd_plan, "Show what `apply` would change. Read-only.")
    sp.add_argument(
        "--prune",
        action="store_true",
        help="also delete live items missing from agent.yaml",
    )
    _add_rotate(sp)
    sp = cmd(
        "apply",
        cmd_apply,
        "Apply a reviewed plan. Refuses if the plan is stale. Write.",
    )
    sp.add_argument("--plan-id", required=True)
    sp.add_argument("--prune", action="store_true")
    _add_rotate(sp)
    _add_widen(sp)
    sp.add_argument("--yes", action="store_true")
    sp = cmd(
        "test",
        cmd_test,
        "Send one test message through the Agent Test API (not billed).",
    )
    sp.add_argument("message")
    sp.add_argument("--conversation-id")
    sp = cmd(
        "eval",
        cmd_eval,
        "Run the scenarios in evals/ and record the result for the go-live gate.",
    )
    sp.add_argument(
        "--dir",
        help="scenario folder (default: evals/ next to agent.yaml; "
        "any other folder does not satisfy the gate)",
    )
    sp.add_argument(
        "--only",
        nargs="+",
        help="scenario names (a partial run does not satisfy the gate)",
    )
    sp.add_argument(
        "-v", "--verbose", action="store_true", help="print every transcript"
    )
    sp = cmd(
        "eval-remote",
        cmd_eval_remote,
        "Server-side evals: list cases, start a run, check a run.",
    )
    sp.add_argument("action", choices=["cases", "run", "status"])
    sp.add_argument("ids", nargs="*", help="case IDs for run; job ID for status")
    sp = cmd("versions", cmd_versions, "List configuration versions. Read-only.")
    sp.add_argument("--limit", type=int, default=20)
    sp = cmd("rollback", cmd_rollback, "Serve an earlier configuration version. Write.")
    sp.add_argument("version_id")
    sp.add_argument("--yes", action="store_true")
    sp = cmd(
        "enable",
        cmd_enable,
        "Turn the agent on. Requires a passing eval of the live config. Write.",
    )
    _add_widen(sp)
    sp.add_argument("--yes", action="store_true")
    sp = cmd("disable", cmd_disable, "Turn the agent off. Write.")
    sp.add_argument("--yes", action="store_true")
    sp = cmd(
        "run-tool",
        cmd_run_tool,
        "Call one connector tool directly to check the backend.",
    )
    sp.add_argument("connector")
    sp.add_argument("tool")
    sp.add_argument("--input", default="{}", help="JSON arguments for the tool")
    sp.add_argument(
        "--yes", action="store_true", help="required for tools that are not GET"
    )
    sp = cmd("logs", cmd_logs, "Connector call logs and success rate. Read-only.")
    sp.add_argument("connector")
    sp.add_argument("--limit", type=int, default=20)
    sp = cmd(
        "event", cmd_event, "Send a business event (e.g. order_shipped) or check one."
    )
    sp.add_argument("action", choices=["send", "get"])
    sp.add_argument("--to", help="customer phone number")
    sp.add_argument("--type", help="event type, e.g. order_shipped")
    sp.add_argument("--payload", help="event payload (JSON string)")
    sp.add_argument("--id", help="agent_event_id for get")
    sp.add_argument("--yes", action="store_true")
    cmd("schema", cmd_schema, "Print the JSON Schema for agent.yaml.")  # fmt: skip


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="mba",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--json", action="store_true", help="machine-readable output")
    p.add_argument(
        "--file", default="agent.yaml", help="agent config (default: agent.yaml)"
    )
    p.add_argument(
        "--env", default=".env", help="env file with MBA_TOKEN and MBA_ENTITY_ID"
    )
    sub = p.add_subparsers(dest="command", required=True)

    def cmd(name: str, fn: Callable[..., int], help: str) -> argparse.ArgumentParser:
        sp = sub.add_parser(name, help=help, description=help)
        sp.set_defaults(fn=fn)
        return sp

    _add_commands(cmd)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    args.env_values = load_dotenv(Path(args.env))
    args.state = pl.state_for(Path(args.file))
    out = Output(args.json, scrubber_for(args.env_values))
    try:
        return args.fn(args, out)
    except MBAError as e:
        if args.json:
            payload = {"error": str(e), "hint": e.hint, "exit_code": e.exit_code}
            out.emit(payload, "")
        else:
            hint = f"\nhint: {e.hint}" if e.hint else ""
            out.error(f"error: {e}{hint}")
        return e.exit_code
    except Exception:  # noqa: BLE001 - last resort so tracebacks are scrubbed too
        out.error(traceback.format_exc())
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
