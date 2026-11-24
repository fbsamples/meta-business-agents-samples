# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path
from typing import Any

from mba import evals as ev
from mba.client import MBAClient
from mba.errors import ConfigError, GateError

SCENARIO_YAML = "turns:\n  - user: hi\n    expect:\n      contains_any: [hello]\n"


class ScriptedClient(MBAClient):
    def __init__(self, replies: list[Any], entity_id: str = "111") -> None:
        super().__init__(
            token="test", entity_id=entity_id, base_url="https://api.invalid"
        )
        self.replies = list(replies)

    def request(self, *args: Any, **kwargs: Any) -> Any:
        raise AssertionError("tests must not reach the network")

    def agent_test(
        self, user_msg: str, conversation_id: str | None = None
    ) -> dict[str, Any]:
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return {"conversation_id": "c1", **reply}


class CheckTurnTest(unittest.TestCase):
    def test_expectations(self) -> None:
        reply = {"agent_response": "Your order has shipped with UPS."}
        self.assertEqual(
            ev.check_turn({"contains_any": ["shipped"], "handoff": False}, reply), []
        )
        self.assertEqual(
            ev.check_turn({"not_contains": ["UPS"]}, reply), ["must not say 'UPS'"]
        )
        self.assertEqual(
            ev.check_turn({"handoff": True}, reply), ["expected a handoff"]
        )
        self.assertEqual(
            ev.check_turn({}, {"agent_response": "", "no_response_reason": "blocked"}),
            ["no response (blocked)"],
        )


class GateTest(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.folder = Path(tmp.name)
        self.evals_dir = self.folder / "evals"
        self.evals_dir.mkdir()
        (self.evals_dir / "s.yaml").write_text(SCENARIO_YAML)
        self.state = ev.State(self.folder / ".mba")
        self.live = "config-a"

    def _run(
        self, reply: str, complete: bool = True, entity_id: str = "111"
    ) -> dict[str, Any]:
        return self._run_with([{"agent_response": reply}], complete, entity_id)

    def _run_with(
        self,
        replies: list[Any],
        complete: bool = True,
        entity_id: str = "111",
        config_digest: Any = None,
    ) -> dict[str, Any]:
        scenarios, suite = ev.load_suite(self.evals_dir)
        return ev.run_scenarios(
            ScriptedClient(replies, entity_id),
            scenarios,
            self.state,
            complete=complete,
            suite_dir=self.evals_dir,
            suite=suite,
            config_digest=config_digest or (lambda: self.live),
        )

    def _gate(self) -> dict[str, Any]:
        return ev.check_gate(
            self.state,
            target=ScriptedClient([]).target,
            suite=ev.suite_digest(self.evals_dir),
            live_digest=lambda: self.live,
        )

    def test_no_run_fails_the_gate(self) -> None:
        with self.assertRaisesRegex(GateError, "No eval run"):
            self._gate()

    def test_no_scenarios_is_an_error_not_a_pass(self) -> None:
        with self.assertRaises(ConfigError):
            ev.run_scenarios(
                ScriptedClient([]),
                [],
                self.state,
                complete=True,
                suite_dir=self.evals_dir,
                suite="x",
                config_digest=lambda: self.live,
            )
        self.assertIsNone(ev.latest_run(self.state))

    def test_failing_run_fails_the_gate(self) -> None:
        self._run("nope")
        with self.assertRaisesRegex(GateError, "failures"):
            self._gate()

    def test_partial_run_fails_the_gate(self) -> None:
        self._run("hello!", complete=False)
        with self.assertRaisesRegex(GateError, "whole evals"):
            self._gate()

    def test_passing_run_after_config_change_opens_the_gate(self) -> None:
        self.state.write(last_config_change_at=time.time() - 10)
        run = self._run("hello!")
        self.assertTrue(self._gate()["passed"])
        self.assertLessEqual(run["started_at"], run["finished_at"])

    def test_config_change_after_the_run_closes_the_gate(self) -> None:
        self._run("hello!")
        self.state.write(last_config_change_at=time.time() + 1)
        with self.assertRaisesRegex(GateError, "older"):
            self._gate()

    def test_run_against_another_agent_fails_the_gate(self) -> None:
        self._run("hello!", entity_id="222")
        with self.assertRaisesRegex(GateError, "different agent"):
            self._gate()

    def test_live_config_drift_fails_the_gate(self) -> None:
        self._run("hello!")
        self.live = "config-b"
        with self.assertRaisesRegex(GateError, "differs"):
            self._gate()

    def test_config_change_during_the_run_fails_the_gate(self) -> None:
        digests = iter(["config-a", "config-b"])
        self._run_with(
            [{"agent_response": "hello"}], config_digest=lambda: next(digests)
        )
        with self.assertRaisesRegex(GateError, "while the eval was running"):
            self._gate()

    def test_interrupted_new_run_replaces_an_old_green_run(self) -> None:
        (self.evals_dir / "t.yaml").write_text(SCENARIO_YAML)
        self._run_with([{"agent_response": "hello"}, {"agent_response": "hello"}])
        self.assertTrue(self._gate()["passed"])
        with self.assertRaises(RuntimeError):
            self._run_with([{"agent_response": "nope"}, RuntimeError("api down")])
        with self.assertRaisesRegex(GateError, "did not finish"):
            self._gate()

    def test_post_run_digest_error_leaves_a_failed_run(self) -> None:
        self._run("hello")
        digests: list[Any] = ["config-a", RuntimeError("digest read failed")]

        def digest() -> str:
            value = digests.pop(0)
            if isinstance(value, Exception):
                raise value
            return value

        with self.assertRaises(RuntimeError):
            self._run_with([{"agent_response": "hello"}], config_digest=digest)
        run = ev.latest_run(self.state)
        self.assertEqual(run and run["status"], "failed")
        with self.assertRaisesRegex(GateError, "did not finish"):
            self._gate()

    def test_run_is_bound_to_the_scenarios_it_loaded(self) -> None:
        scenarios, suite = ev.load_suite(self.evals_dir)
        (self.evals_dir / "s.yaml").write_text(SCENARIO_YAML + "# edited\n")
        ev.run_scenarios(
            ScriptedClient([{"agent_response": "hello"}]),
            scenarios,
            self.state,
            complete=True,
            suite_dir=self.evals_dir,
            suite=suite,
            config_digest=lambda: self.live,
        )
        with self.assertRaisesRegex(GateError, "evals/ changed"):
            self._gate()

    def test_edited_suite_fails_the_gate(self) -> None:
        self._run("hello!")
        (self.evals_dir / "s.yaml").write_text(SCENARIO_YAML + "# edited\n")
        with self.assertRaisesRegex(GateError, "evals/ changed"):
            self._gate()

    def test_unfinished_apply_fails_the_gate(self) -> None:
        self._run("hello!")
        target = ScriptedClient([]).target
        self.state.write_apply(target, {"status": "in_progress"})
        with self.assertRaisesRegex(GateError, "did not finish"):
            self._gate()
        self.state.write_apply(target, {"status": "complete"})
        self.state.write_apply("https://api.invalid/222", {"status": "failed"})
        self.assertTrue(self._gate()["passed"])

    def test_live_read_error_fails_closed(self) -> None:
        self._run("hello!")

        def broken() -> str:
            raise RuntimeError("boom")

        with self.assertRaises(RuntimeError):
            ev.check_gate(
                self.state,
                target=ScriptedClient([]).target,
                suite=ev.suite_digest(self.evals_dir),
                live_digest=broken,
            )
