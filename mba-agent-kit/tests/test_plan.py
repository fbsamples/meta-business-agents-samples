# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

from __future__ import annotations

import copy
import shutil
import tempfile
import unittest
from pathlib import Path
from typing import Any

from mba import plan as pl
from mba.cli import TEMPLATES
from mba.client import MBAClient
from mba.config import load_agent, load_dotenv
from mba.errors import ApiError, ConfigError, PlanStaleError
from mba.evals import State

ENV: dict[str, str] = {"ORDERS_API_KEY": "secret-key-value"}


class FakeClient(MBAClient):
    """In-memory stand-in for MBAClient with the same collection semantics."""

    def __init__(self, entity_id: str = "111") -> None:
        super().__init__(
            token="test", entity_id=entity_id, base_url="https://api.invalid"
        )
        self.settings: dict[str, Any] = {
            "agent_id": "a1",
            "ai_audience": "ALLOWLISTED_ONLY",
            "rollout": {"enabled": False},
        }
        self.business_info: dict[str, Any] = {}
        self.collections: dict[str, list[dict[str, Any]]] = {}
        self.rotations: list[tuple[str, str, dict[str, Any]]] = []
        self._next = 100

    def request(self, *args: Any, **kwargs: Any) -> Any:
        raise AssertionError("tests must not reach the network")

    def _id(self) -> str:
        self._next += 1
        return str(self._next)

    def get_settings(self) -> list[dict[str, Any]]:
        return [copy.deepcopy(self.settings)]

    def put_settings(self, body: dict[str, Any]) -> dict[str, Any]:
        self.settings.update(copy.deepcopy(body))
        return copy.deepcopy(self.settings)

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

    def active_version(self) -> dict[str, Any]:
        raise ApiError(404, "GET", "agent_config/versions/active", "Not Found")

    def upsert_api_key(self, connector_id: str, api_key_config: dict[str, Any]) -> Any:
        self.rotations.append(("api_key", connector_id, copy.deepcopy(api_key_config)))
        return {"success": True}

    def upsert_oauth(self, connector_id: str, oauth_config: dict[str, Any]) -> Any:
        self.rotations.append(("oauth", connector_id, copy.deepcopy(oauth_config)))
        return {"success": True}


def copy_template(dest: Path) -> Path:
    """A real-file copy of the template (Buck may provide resources as symlinks)."""
    shutil.copytree(TEMPLATES / "post-purchase", dest / "kit")
    return dest / "kit" / "agent.yaml"


def no_gate() -> None:
    raise AssertionError("the gate should not be needed")


class PlanTest(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.agent_file = copy_template(Path(tmp.name))
        self.desired: dict[str, Any] = load_agent(self.agent_file, ENV)
        self.client = FakeClient()
        self.state = State(self.agent_file.parent / ".mba")
        self.binding = pl.Binding(
            key=b"k" * 32, target=self.client.target, origin=str(self.agent_file)
        )

    def _plan(self, prune: bool = False) -> dict[str, Any]:
        return pl.compute_plan(
            self.desired,
            pl.fetch_remote(self.client, self.desired),
            self.binding,
            prune,
        )

    def _apply(self, **kwargs: Any) -> list[dict[str, Any]]:
        plan_id = self._plan(kwargs.get("prune", False))["plan_id"]
        return pl.apply_plan(
            self.client,
            self.desired,
            plan_id,
            self.binding,
            self.state,
            gate=no_gate,
            **kwargs,
        )

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
        self.assertEqual(header["value"], "secret-key-value")

    def test_first_apply_creates_everything_then_converges(self) -> None:
        kinds = {(o["action"], o["kind"]) for o in self._plan()["ops"]}
        self.assertIn(("create", "connector"), kinds)
        self.assertIn(("create", "tool"), kinds)
        self._apply()
        connector_id = self.client.collections["agent_connectors"][0]["id"]
        tools = self.client.collections[f"agent_connectors/{connector_id}/tools"]
        self.assertEqual(len(tools), 4)
        self.assertEqual(self._plan()["ops"], [])
        record = self.state.read()["applies"][self.client.target]
        self.assertEqual(record["status"], "complete")

    def test_server_defaults_do_not_cause_diffs(self) -> None:
        self._apply()
        for item in self.client.collections["agent_config/skills"]:
            item["status"] = "active"
            item["created_at"] = 1
        self.assertEqual(self._plan()["ops"], [])

    def test_masked_live_credentials_do_not_cause_diffs(self) -> None:
        self._apply()
        conn = self.client.collections["agent_connectors"][0]
        conn["auth_config"]["api_key"]["headers"][0]["value"] = "****"
        self.assertEqual(self._plan()["ops"], [])

    def test_edit_is_an_update_and_secrets_are_redacted(self) -> None:
        self._apply()
        self.desired["faqs"][0]["answer"] = "Two days."
        plan = self._plan()
        self.assertEqual(
            [(o["action"], o["kind"]) for o in plan["ops"]], [("update", "faq")]
        )
        remote = pl.fetch_remote(self.client, self.desired)
        self.assertNotIn("secret-key-value", str(pl.redact(remote)))

    def test_connector_update_keeps_live_fields_not_in_yaml(self) -> None:
        self._apply()
        conn = self.client.collections["agent_connectors"][0]
        conn["user_auth_injection_config"] = {"location": "headers"}
        conn["auth_config"] = {"api_key": {"headers": [{"value": "****"}]}}
        self.desired["connectors"][0]["description"] = "New description."
        self._apply()
        updated = self.client.collections["agent_connectors"][0]
        self.assertEqual(updated["description"], "New description.")
        self.assertEqual(updated["user_auth_injection_config"], {"location": "headers"})
        header = updated["auth_config"]["api_key"]["headers"][0]
        self.assertEqual(header["value"], "secret-key-value")

    def test_connector_update_without_auth_config_is_refused(self) -> None:
        self._apply()
        del self.desired["connectors"][0]["auth_config"]
        self.desired["connectors"][0]["description"] = "New description."
        with self.assertRaisesRegex(ConfigError, "needs auth_config"):
            self._plan()

    def test_stale_plan_is_refused(self) -> None:
        plan = self._plan()
        self.client.create("agent_config/faq", {"question": "New?", "answer": "x"})
        with self.assertRaises(PlanStaleError):
            pl.apply_plan(
                self.client,
                self.desired,
                plan["plan_id"],
                self.binding,
                self.state,
                gate=no_gate,
            )
        self.assertEqual(self.state.read(), {})

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

    def test_snapshot_never_exports_auth_config(self) -> None:
        self._apply()
        doc = pl.snapshot(self.client)
        self.assertNotIn("auth_config", doc["connectors"][0])
        self.assertNotIn("secret-key-value", str(doc))


class ConfigTest(unittest.TestCase):
    def _write(self, folder: Path, text: str) -> Path:
        path = folder / "agent.yaml"
        path.write_text(text)
        return path

    def _connector(self, value: str) -> str:
        return (
            "version: 1\nconnectors:\n  - name: c\n    base_url: https://x.example\n"
            "    auth_type: API_KEY\n    auth_config:\n      api_key:\n"
            "        headers:\n          - field_name: X-API-Key\n"
            f"            value: {value}\n"
        )

    def test_variables_must_be_declared_in_env_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(Path(tmp), self._connector("${HOME_SECRET}"))
            with self.assertRaisesRegex(ConfigError, "not set in .env"):
                load_agent(path, {})

    def test_dotenv_values_win_over_the_shell_and_are_expanded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / ".env").write_text("SHOP_KEY=from-dotenv-file\nBLANK=\n")
            env = load_dotenv(folder / ".env")
            path = self._write(folder, self._connector("${SHOP_KEY}"))
            doc = load_agent(path, env)
            header = doc["connectors"][0]["auth_config"]["api_key"]["headers"][0]
            self.assertEqual(header["value"], "from-dotenv-file")
            self.assertEqual(env["BLANK"], "")

    def test_skill_files_outside_the_folder_are_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(
                Path(tmp),
                "version: 1\nskills:\n  - title: x\n    description: d\n"
                "    skill_file: ../../etc/passwd.md\n",
            )
            with self.assertRaises(ConfigError):
                load_agent(path, {})
