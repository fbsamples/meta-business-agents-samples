# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

"""Runs scripted conversations through the Agent Test API and checks the replies.

Each file in evals/ is one scenario: a list of user turns, each with optional
deterministic expectations. `success_criteria` are not checked here; they are
printed with the transcript for a person (or Claude) to judge.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

import yaml

from .client import MBAClient
from .errors import ConfigError, GateError

STATE_DIR = Path(".mba")


def load_scenarios(
    evals_dir: Path, only: list[str] | None = None
) -> list[dict[str, Any]]:
    if not evals_dir.is_dir():
        raise ConfigError(
            f"{evals_dir}/ not found.",
            "Run `mba init --template post-purchase` to get starter scenarios.",
        )
    scenarios = []
    for path in sorted(evals_dir.glob("*.yaml")):
        doc = yaml.safe_load(path.read_text()) or {}
        doc.setdefault("name", path.stem)
        if only and doc["name"] not in only:
            continue
        if not doc.get("turns"):
            raise ConfigError(f"{path} has no turns.")
        scenarios.append(doc)
    return scenarios


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
    client: MBAClient, scenarios: list[dict[str, Any]], complete: bool = True
) -> dict[str, Any]:
    results = [_run_one(client, sc) for sc in scenarios]
    run = {
        "ran_at": time.time(),
        "complete": complete,
        "passed": all(r["passed"] for r in results),
        "scenarios": results,
    }
    out_dir = STATE_DIR / "evals"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{int(run['ran_at'] * 1000)}.json").write_text(
        json.dumps(run, indent=2)
    )
    return run


def read_state() -> dict[str, Any]:
    path = STATE_DIR / "state.json"
    return json.loads(path.read_text()) if path.exists() else {}


def write_state(**updates: Any) -> None:
    STATE_DIR.mkdir(exist_ok=True)
    state = {**read_state(), **updates}
    (STATE_DIR / "state.json").write_text(json.dumps(state, indent=2))


def latest_run() -> dict[str, Any] | None:
    runs_dir = STATE_DIR / "evals"
    runs = sorted(runs_dir.glob("*.json")) if runs_dir.is_dir() else []
    return json.loads(runs[-1].read_text()) if runs else None


def check_gate() -> dict[str, Any]:
    """The agent may go to more customers only after a full passing eval run
    that happened after the most recent `mba apply`."""
    run = latest_run()
    last_apply = read_state().get("last_apply_at", 0)
    if run is None:
        raise GateError(
            "No eval run found.", "Run `mba eval` and get every scenario passing first."
        )
    if run["ran_at"] < last_apply:
        raise GateError(
            "The latest eval run is older than the latest `mba apply`.",
            "Run `mba eval` again against the current config.",
        )
    if not run.get("complete"):
        raise GateError(
            "The latest eval run covered only some scenarios.",
            "Run `mba eval` without --only.",
        )
    if not run["passed"]:
        failed = [s["name"] for s in run["scenarios"] if not s["passed"]]
        raise GateError(
            f"The latest eval run has failures: {', '.join(failed)}.",
            "Fix the agent config, apply, and re-run `mba eval`.",
        )
    return run
