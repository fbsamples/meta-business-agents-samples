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
from unittest import mock

from mba import evals as ev
from mba.client import MBAClient
from mba.errors import GateError

SCENARIO: dict[str, Any] = {
    "name": "s",
    "turns": [{"user": "hi", "expect": {"contains_any": ["hello"]}}],
}


class ScriptedClient(MBAClient):
    def __init__(self, replies: list[dict[str, Any]]) -> None:
        super().__init__(token="test", entity_id="test")
        self.replies = list(replies)

    def agent_test(
        self, user_msg: str, conversation_id: str | None = None
    ) -> dict[str, Any]:
        return {"conversation_id": "c1", **self.replies.pop(0)}


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
        patcher = mock.patch.object(ev, "STATE_DIR", Path(tmp.name) / ".mba")
        patcher.start()
        self.addCleanup(patcher.stop)

    def _run(self, reply: str, complete: bool = True) -> None:
        client = ScriptedClient([{"agent_response": reply}])
        ev.run_scenarios(client, [SCENARIO], complete=complete)

    def test_no_run_fails_the_gate(self) -> None:
        with self.assertRaisesRegex(GateError, "No eval run"):
            ev.check_gate()

    def test_failing_run_fails_the_gate(self) -> None:
        self._run("nope")
        with self.assertRaisesRegex(GateError, "failures"):
            ev.check_gate()

    def test_partial_run_fails_the_gate(self) -> None:
        self._run("hello!", complete=False)
        with self.assertRaisesRegex(GateError, "some scenarios"):
            ev.check_gate()

    def test_passing_run_after_apply_opens_the_gate(self) -> None:
        ev.write_state(last_apply_at=time.time() - 10)
        self._run("hello!")
        self.assertTrue(ev.check_gate()["passed"])

    def test_apply_after_the_run_closes_the_gate(self) -> None:
        self._run("hello!")
        ev.write_state(last_apply_at=time.time() + 1)
        with self.assertRaisesRegex(GateError, "older"):
            ev.check_gate()
