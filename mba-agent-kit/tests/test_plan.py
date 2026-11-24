# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

from __future__ import annotations

import copy
import os
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

from mba import plan as pl
from mba.cli import TEMPLATES
from mba.client import MBAClient
from mba.config import load_agent, load_dotenv
from mba.errors import ConfigError, PlanStaleError

TEMPLATE: Path = TEMPLATES / "post-purchase" / "agent.yaml"
ENV_KEYS: set[str] = {"ORDERS_API_KEY"}


class FakeClient(MBAClient):
    """In-memory stand-in for MBAClient with the same collection semantics."""

    def __init__(self) -> None:
        super().__init__(token="test", entity_id="test")
        self.settings: dict[str, Any] = {
            "agent_id": "a1",
            "ai_audience": "ALLOWLISTED_ONLY",
            "rollout": {"enabled": False},
        }
        self.business_info: dict[str, Any] = {}
        self.collections: dict[str, list[dict[str, Any]]] = {}
        self._next = 100

    def _id(self) -> str:
        self._next += 1
        return str(self._next)

    def get_settings(self) -> list[dict[str, Any]]:
        return [copy.deepcopy(self.settings)]

    def put_settings(self, body: dict[str, Any]) -> dict[str, Any]:
        self.settings.update(body)
        return self.settings

    def get_business_info(self) -> dict[str, Any]:
        return copy.deepcopy(self.business_info)

    def put_business_info(self, body: dict[str, Any]) -> dict[str, Any]:
        self.business_info = dict(body)
        return self.business_info

    def list_items(self, collection: str) -> list[dict[str, Any]]:
        return copy.deepcopy(self.collections.get(collection, []))

    def create(self, collection: str, body: dict[str, Any]) -> dict[str, Any]:
        item = {**copy.deepcopy(body), "id": self._id()}
        self.collections.setdefault(collection, []).append(item)
        return item

    def update(self, collection: str, item_id: str, body: dict[str, Any]) -> Any:
        items = self.collections[collection]
        for i, it in enumerate(items):
            if it["id"] == item_id:
                items[i] = {**copy.deepcopy(body), "id": item_id}
                return items[i]
        raise KeyError(item_id)

    def delete(self, collection: str, item_id: str) -> None:
        self.collections[collection] = [
            i for i in self.collections[collection] if i["id"] != item_id
        ]


class PlanTest(unittest.TestCase):
    def setUp(self) -> None:
        patcher = mock.patch.dict(os.environ, {"ORDERS_API_KEY": "secret-key"})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.desired: dict[str, Any] = load_agent(TEMPLATE, ENV_KEYS)
        self.client = FakeClient()

    def _plan(self, prune: bool = False) -> dict[str, Any]:
        return pl.compute_plan(
            self.desired, pl.fetch_remote(self.client, self.desired), prune
        )

    def _apply(self) -> None:
        pl.apply_plan(self.client, self.desired, self._plan()["plan_id"])

    def test_template_loads_and_inlines_skill_files(self) -> None:
        titles = [s["title"] for s in self.desired["skills"]]
        self.assertEqual(
            titles,
            [
                "order-status",
                "returns-and-exchanges",
                "refund-status",
                "problems-and-handoff",
            ],
        )
        self.assertTrue(all(s["skill"] for s in self.desired["skills"]))
        self.assertGreaterEqual(len(self.desired["faqs"]), 5)
        header = self.desired["connectors"][0]["auth_config"]["api_key"]["headers"][0]
        self.assertEqual(header["value"], "secret-key")

    def test_first_apply_creates_everything_then_converges(self) -> None:
        kinds = {(o["action"], o["kind"]) for o in self._plan()["ops"]}
        self.assertIn(("create", "connector"), kinds)
        self.assertIn(("create", "tool"), kinds)
        self._apply()
        connector_id = self.client.collections["agent_connectors"][0]["id"]
        tools = self.client.collections[f"agent_connectors/{connector_id}/tools"]
        self.assertEqual(len(tools), 4)
        self.assertEqual(self._plan()["ops"], [])

    def test_server_defaults_do_not_cause_diffs(self) -> None:
        self._apply()
        for item in self.client.collections["agent_config/skills"]:
            item["status"] = "active"
            item["created_at"] = 1
        self.assertEqual(self._plan()["ops"], [])

    def test_edit_is_an_update_and_secrets_are_redacted(self) -> None:
        self._apply()
        self.desired["faqs"][0]["answer"] = "Two days."
        plan = self._plan()
        self.assertEqual(
            [(o["action"], o["kind"]) for o in plan["ops"]], [("update", "faq")]
        )
        remote = pl.fetch_remote(self.client, self.desired)
        self.assertNotIn("secret-key", str(pl.redact(remote)))

    def test_connector_update_keeps_live_fields_not_in_yaml(self) -> None:
        self._apply()
        conn = self.client.collections["agent_connectors"][0]
        conn["user_auth_injection_config"] = {"location": "headers"}
        self.desired["connectors"][0]["description"] = "New description."
        pl.apply_plan(self.client, self.desired, self._plan()["plan_id"])
        updated = self.client.collections["agent_connectors"][0]
        self.assertEqual(updated["description"], "New description.")
        self.assertEqual(updated["user_auth_injection_config"], {"location": "headers"})

    def test_stale_plan_is_refused(self) -> None:
        plan = self._plan()
        self.client.create("agent_config/faq", {"question": "New?", "answer": "x"})
        with self.assertRaises(PlanStaleError):
            pl.apply_plan(self.client, self.desired, plan["plan_id"])

    def test_unmanaged_items_are_kept_unless_pruned(self) -> None:
        self.client.collections["agent_config/faq"] = [
            {"id": "9", "question": "Old question?", "answer": "x"}
        ]
        plan = self._plan()
        self.assertIn("faq 'Old question?'", plan["unmanaged"])
        self.assertFalse(any(o["action"] == "delete" for o in plan["ops"]))
        self.assertEqual(self._plan(prune=True)["ops"][-1]["action"], "delete")

    def test_sections_absent_from_yaml_are_not_touched(self) -> None:
        self.client.collections["agent_config/websites"] = [
            {"id": "5", "url": "https://other.example.com"}
        ]
        del self.desired["websites"]
        ops = self._plan(prune=True)["ops"]
        self.assertFalse(any(o["kind"] == "website" for o in ops))


class ConfigTest(unittest.TestCase):
    def _write(self, folder: Path, text: str) -> Path:
        path = folder / "agent.yaml"
        path.write_text(text)
        return path

    def test_variables_must_be_declared_in_env_file(self) -> None:
        with (
            tempfile.TemporaryDirectory() as tmp,
            mock.patch.dict(os.environ, {"HOME_SECRET": "leaked"}),
        ):
            path = self._write(
                Path(tmp),
                "version: 1\nbusiness_info:\n  purchase_info: ${HOME_SECRET}\n",
            )
            with self.assertRaises(ConfigError):
                load_agent(path, set())

    def test_dotenv_keys_are_expanded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {}):
            folder = Path(tmp)
            (folder / ".env").write_text("SHOP_NOTE=hello\n")
            keys = load_dotenv(folder / ".env")
            path = self._write(
                folder, "version: 1\nbusiness_info:\n  purchase_info: ${SHOP_NOTE}\n"
            )
            doc = load_agent(path, keys)
            self.assertEqual(doc["business_info"]["purchase_info"], "hello")

    def test_skill_files_outside_the_folder_are_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(
                Path(tmp),
                "version: 1\nskills:\n  - title: x\n    description: d\n"
                "    skill_file: ../../etc/passwd\n",
            )
            with self.assertRaises(ConfigError):
                load_agent(path, set())
