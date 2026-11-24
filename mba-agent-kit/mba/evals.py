# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

"""Runs scripted conversations through the Agent Test API and checks the replies.

Each file in evals/ is one scenario: a list of user turns, each with optional
deterministic expectations. `success_criteria` are not checked here; they are
printed with the transcript for a person (or Claude) to judge.

Runs and apply records live in `.mba/` next to agent.yaml. The go-live gate
accepts a run only if it covered the whole canonical suite, ran against the
same target and the same live configuration that is live now, and started
after the last configuration change.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .client import MBAClient
from .config import load_yaml
from .errors import ConfigError, GateError


class State:
    """Local state for one configuration folder (`<agent.yaml folder>/.mba`)."""

    def __init__(self, state_dir: Path) -> None:
        self.dir = state_dir

    @property
    def runs_dir(self) -> Path:
        return self.dir / "evals"

    def read(self) -> dict[str, Any]:
        path = self.dir / "state.json"
        return json.loads(path.read_text()) if path.exists() else {}

    def write(self, **updates: Any) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        state = {**self.read(), **updates}
        tmp = self.dir / "state.json.tmp"
        tmp.write_text(json.dumps(state, indent=2))
        tmp.replace(self.dir / "state.json")

    def write_apply(self, target: str, record: dict[str, Any], **updates: Any) -> None:
        """Records the latest apply for one target (API base and entity)."""
        applies = {**self.read().get("applies", {}), target: record}
        self.write(applies=applies, **updates)


def load_suite(
    evals_dir: Path, only: list[str] | None = None
) -> tuple[list[dict[str, Any]], str]:
    """Returns the selected scenarios and a digest of every scenario file, both
    from the same read, so a run is bound to exactly the content it used."""
    if not evals_dir.is_dir():
        raise ConfigError(
            f"{evals_dir}/ not found.",
            "Run `mba init --template post-purchase` to get starter scenarios.",
        )
    h = hashlib.sha256()
    scenarios = []
    for path in sorted(evals_dir.glob("*.yaml")):
        raw = path.read_bytes()
        h.update(path.name.encode() + b"\0" + raw + b"\0")
        doc = load_yaml(raw) or {}
        if not isinstance(doc, dict):
            raise ConfigError(f"{path} must be a YAML mapping.")
        doc.setdefault("name", path.stem)
        if only and doc["name"] not in only:
            continue
        if not doc.get("turns"):
            raise ConfigError(f"{path} has no turns.")
        scenarios.append(doc)
    return scenarios, h.hexdigest()


def load_scenarios(
    evals_dir: Path, only: list[str] | None = None
) -> list[dict[str, Any]]:
    return load_suite(evals_dir, only)[0]


def suite_digest(evals_dir: Path) -> str:
    return load_suite(evals_dir)[1]


def check_turn(expect: dict[str, Any], reply: dict[str, Any]) -> list[str]:
    raw = reply.get("agent_response") or ""
    text = raw.casefold()
    failures = []
    any_of = expect.get("contains_any")
    if any_of and not any(s.casefold() in text for s in any_of):
        failures.append(f"expected one of {any_of}")
    for s in expect.get("contains_all", []):
        if s.casefold() not in text:
            failures.append(f"expected {s!r}")
    for s in expect.get("not_contains", []):
        if s.casefold() in text:
            failures.append(f"must not say {s!r}")
    if "matches" in expect and not re.search(expect["matches"], raw, re.I):
        failures.append(f"expected to match /{expect['matches']}/")
    if "handoff" in expect:
        handed_off = bool(reply.get("handoff_reason"))
        if handed_off != expect["handoff"]:
            failures.append(
                "expected a handoff"
                if expect["handoff"]
                else f"unexpected handoff ({reply.get('handoff_reason')})"
            )
    if expect.get("responds", True) and not raw:
        reason = reply.get("no_response_reason") or "unknown reason"
        failures.append(f"no response ({reason})")
    return failures


def _run_one(client: MBAClient, scenario: dict[str, Any]) -> dict[str, Any]:
    conversation_id = None
    transcript, failures = [], []
    for i, turn in enumerate(scenario["turns"], 1):
        reply = client.agent_test(turn["user"], conversation_id)
        conversation_id = reply.get("conversation_id")
        transcript.append(
            {
                "user": turn["user"],
                "agent": reply.get("agent_response"),
                "handoff_reason": reply.get("handoff_reason"),
                "quick_replies": reply.get("quick_replies"),
            }
        )
        failures += [
            f"turn {i}: {f}" for f in check_turn(turn.get("expect", {}), reply)
        ]
    return {
        "name": scenario["name"],
        "passed": not failures,
        "failures": failures,
        "success_criteria": scenario.get("success_criteria", []),
        "conversation_id": conversation_id,
        "transcript": transcript,
    }


def run_scenarios(
    client: MBAClient,
    scenarios: list[dict[str, Any]],
    state: State,
    *,
    complete: bool,
    suite_dir: Path,
    suite: str,
    config_digest: Callable[[], str],
    scrub: Callable[[str], str] = lambda s: s,
) -> dict[str, Any]:
    """Runs the scenarios and records the run with what it was run against.

    The run is recorded as in progress before the first request, so a run that
    fails or is interrupted becomes the latest run and keeps the gate closed.
    `config_digest` reads the live configuration before and after the run.
    `suite` is the digest of the scenario files the scenarios were loaded from.
    """
    if not scenarios:
        raise ConfigError(
            "No eval scenarios found.",
            "Add at least one scenario file to evals/ before running eval.",
        )
    state.runs_dir.mkdir(parents=True, exist_ok=True)
    started_at = time.time()
    path = state.runs_dir / f"{time.time_ns()}.json"
    run: dict[str, Any] = {
        "status": "in_progress",
        "started_at": started_at,
        "ran_at": started_at,
        "target": client.target,
        "suite_dir": str(suite_dir),
        "suite_digest": suite,
        "complete": False,
        "passed": False,
        "scenarios": [],
    }

    def save() -> None:
        path.write_text(scrub(json.dumps(run, indent=2)))

    save()
    try:
        run["config_digest_start"] = config_digest()
        run["scenarios"] = [_run_one(client, sc) for sc in scenarios]
        run["config_digest_end"] = config_digest()
    except BaseException:
        run.update(status="failed", finished_at=time.time())
        save()
        raise
    run.update(
        status="finished",
        finished_at=time.time(),
        complete=complete,
        passed=all(r["passed"] for r in run["scenarios"]),
    )
    save()
    return run


def latest_run(state: State) -> dict[str, Any] | None:
    runs_dir = state.runs_dir
    runs = (
        [p for p in runs_dir.glob("*.json") if p.stem.isdigit()]
        if runs_dir.is_dir()
        else []
    )
    if not runs:
        return None
    return json.loads(max(runs, key=lambda p: int(p.stem)).read_text())


def _check_record(run: dict[str, Any], state: State, target: str, suite: str) -> None:
    if run.get("status") != "finished":
        raise GateError(
            f"The latest eval run did not finish (status {run.get('status')}).",
            "Run `mba eval` again.",
        )
    if run.get("target") != target:
        raise GateError(
            "The latest eval run was against a different agent or API endpoint.",
            "Run `mba eval` with the current .env.",
        )
    if not run.get("complete"):
        raise GateError(
            "The latest eval run did not cover the whole evals/ suite.",
            "Run `mba eval` without --only or --dir.",
        )
    if run.get("suite_digest") != suite:
        raise GateError(
            "evals/ changed since the latest eval run.",
            "Run `mba eval` again with the current scenarios.",
        )
    if not run.get("passed"):
        failed = [s["name"] for s in run.get("scenarios", []) if not s["passed"]]
        raise GateError(
            f"The latest eval run has failures: {', '.join(failed)}.",
            "Fix the agent config, apply, and re-run `mba eval`.",
        )
    recorded = state.read()
    last_apply = recorded.get("applies", {}).get(target)
    if last_apply and last_apply.get("status") != "complete":
        raise GateError(
            f"The last `mba apply` did not finish (status {last_apply.get('status')}).",
            "Run `mba plan` and apply it (an empty plan records that the live agent "
            "matches agent.yaml), then `mba eval`.",
        )
    if run.get("started_at", 0) < recorded.get("last_config_change_at", 0):
        raise GateError(
            "The latest eval run is older than the latest configuration change.",
            "Run `mba eval` again against the current config.",
        )
    start = run.get("config_digest_start")
    if not start or start != run.get("config_digest_end"):
        raise GateError(
            "The live configuration changed while the eval was running.",
            "Run `mba eval` again.",
        )


def check_gate(
    state: State, *, target: str, suite: str, live_digest: Callable[[], str]
) -> dict[str, Any]:
    """The agent may go to more customers only after a full passing eval run of
    the configuration that is live right now. Fails closed: any record that
    cannot be verified, or any error reading the live configuration, blocks."""
    run = latest_run(state)
    if run is None:
        raise GateError(
            "No eval run found.", "Run `mba eval` and get every scenario passing first."
        )
    _check_record(run, state, target, suite)
    if live_digest() != run["config_digest_start"]:
        raise GateError(
            "The live configuration differs from the one the latest eval ran against.",
            "Run `mba eval` again against the current config.",
        )
    return run
