# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

"""Regression tests for the CLI's secret handling, approvals and go-live gate.

Every test uses an in-memory client; nothing reaches the network.
"""

from __future__ import annotations

import base64
import contextlib
import copy
import io
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

from mba import cli, config as config_module, plan as pl
from mba.client import MBAClient
from mba.config import load_agent, Scrubber
from mba.errors import (
    ApiError,
    ConfigError,
    EXIT_GATE_FAILED,
    EXIT_NEEDS_HUMAN,
    EXIT_OK,
    EXIT_PLAN_STALE,
)

ORDERS_KEY = "synthetic-orders-key/0002+x"
PLATFORM_TOKEN = "synthetic-platform-token-0001"
DOTENV = f"MBA_TOKEN={PLATFORM_TOKEN}\nMBA_ENTITY_ID=111\nORDERS_API_KEY={ORDERS_KEY}\n"
AGENT_YAML = """version: 1
settings:
  ai_audience: ALLOWLISTED_ONLY
faqs:
  - question: What are your hours?
    answer: Nine to five.
connectors:
  - name: orders
    description: Orders API.
    base_url: https://orders.example.com/api
    auth_type: API_KEY
    auth_config:
      api_key:
        headers:
          - field_name: X-API-Key
            value: ${ORDERS_API_KEY}
    tools:
      - name: get_order
        description: Looks up an order.
        user_auth_required: false
        request_definition:
          method: GET
          path: /orders/{n}
      - name: create_return
        description: Starts a return.
        user_auth_required: false
        request_definition:
          method: POST
          path: /returns
"""
SCENARIO = "turns:\n  - user: hi\n    expect:\n      contains_any: [hello]\n"


class FakeClient(MBAClient):
    """In-memory Meta Business Agent API."""

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
        self.writes: list[tuple[str, Any]] = []
        self.version_error: ApiError | None = None
        self.version: Any = None  # None: unversioned (404)
        self.lose_response_after_create = False
        self.fail_create_after: int | None = None
        self.reply = "hello there"
        self._next = 100

    def request(self, *args: Any, **kwargs: Any) -> Any:
        raise AssertionError("tests must not reach the network")

    def _id(self) -> str:
        self._next += 1
        return str(self._next)

    def get_settings(self) -> list[dict[str, Any]]:
        return [copy.deepcopy(self.settings)]

    def put_settings(self, body: dict[str, Any]) -> dict[str, Any]:
        self.writes.append(("settings", copy.deepcopy(body)))
        self.settings.update(copy.deepcopy(body))
        return copy.deepcopy(self.settings)

    def get_business_info(self) -> dict[str, Any]:
        return copy.deepcopy(self.business_info)

    def list_items(self, collection: str) -> list[dict[str, Any]]:
        return copy.deepcopy(self.collections.get(collection, []))

    def create(self, collection: str, body: dict[str, Any]) -> dict[str, Any]:
        if self.fail_create_after is not None:
            if self.fail_create_after == 0:
                raise ApiError(500, "POST", collection, "Internal error")
            self.fail_create_after -= 1
        self.writes.append(("create", collection))
        item = {**copy.deepcopy(body), "id": self._id()}
        self.collections.setdefault(collection, []).append(item)
        if self.lose_response_after_create:
            raise ConnectionError("response lost")
        return item

    def update(self, collection: str, item_id: str, body: dict[str, Any]) -> Any:
        self.writes.append(("update", collection))
        items = self.collections[collection]
        for i, it in enumerate(items):
            if it["id"] == item_id:
                items[i] = {**copy.deepcopy(body), "id": item_id}
                return items[i]
        raise KeyError(item_id)

    def delete(self, collection: str, item_id: str) -> None:
        self.writes.append(("delete", collection))
        self.collections[collection] = [
            i for i in self.collections[collection] if i["id"] != item_id
        ]

    def active_version(self) -> dict[str, Any]:
        if self.version_error:
            raise self.version_error
        if self.version is None:
            raise ApiError(404, "GET", "agent_config/versions/active", "Not Found")
        return copy.deepcopy(self.version)

    def set_active_version(
        self, version_id: str, expected_active_version_id: str | None
    ) -> dict[str, Any]:
        self.writes.append(("version", version_id))
        return {"version_id": version_id}

    def upsert_api_key(self, connector_id: str, api_key_config: dict[str, Any]) -> Any:
        self.writes.append(("upsert_api_key", copy.deepcopy(api_key_config)))
        return {"success": True}

    def upsert_oauth(self, connector_id: str, oauth_config: dict[str, Any]) -> Any:
        self.writes.append(("upsert_oauth", copy.deepcopy(oauth_config)))
        return {"success": True}

    def run_tool(self, connector_id: str, tool_id: str, tool_input: str) -> Any:
        self.writes.append(("run_tool", tool_id))
        return {"status": "ok", "output": "{}"}

    def agent_test(
        self, user_msg: str, conversation_id: str | None = None
    ) -> dict[str, Any]:
        return {"conversation_id": "c1", "agent_response": self.reply}


class CliTestBase(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.folder = Path(tmp.name)
        (self.folder / ".env").write_text(DOTENV)
        self.agent_file = self.folder / "agent.yaml"
        self.agent_file.write_text(AGENT_YAML)
        (self.folder / "evals").mkdir()
        (self.folder / "evals" / "hello.yaml").write_text(SCENARIO)
        self.env_file = self.folder / ".env"
        self.clients = {"111": FakeClient("111")}
        self.entity = "111"
        env = mock.patch.dict(os.environ, {"MBA_TOKEN": "", "MBA_ENTITY_ID": ""})
        env.start()
        self.addCleanup(env.stop)
        patcher = mock.patch.object(cli, "_client", lambda args: self.client)
        patcher.start()
        self.addCleanup(patcher.stop)

    @property
    def client(self) -> FakeClient:
        return self.clients.setdefault(self.entity, FakeClient(self.entity))

    def mba(self, *argv: str) -> tuple[int, str, str]:
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = cli.main(
                ["--file", str(self.agent_file), "--env", str(self.env_file)]
                + list(argv)
            )
        return code, stdout.getvalue(), stderr.getvalue()

    def plan_id(self, *flags: str) -> str:
        code, out, err = self.mba("--json", "plan", *flags)
        self.assertEqual(code, EXIT_OK, err)
        return json.loads(out)["plan_id"]

    def apply(self, *flags: str) -> tuple[int, str, str]:
        plan_flags = [f for f in flags if f not in ("--yes", "--widen-audience")]
        return self.mba("apply", "--plan-id", self.plan_id(*plan_flags), *flags)

    def configure_and_eval(self) -> None:
        self.assertEqual(self.apply("--yes")[0], EXIT_OK)
        code, _, err = self.mba("eval")
        self.assertEqual(code, EXIT_OK, err)

    def go_live(self) -> None:
        self.configure_and_eval()
        code, _, err = self.mba("enable", "--yes")
        self.assertEqual(code, EXIT_OK, err)


class SecretReferenceTest(unittest.TestCase):
    def _load(self, agent_yaml: str, files: dict[str, str] | None = None) -> Any:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            for name, text in (files or {}).items():
                (folder / name).parent.mkdir(parents=True, exist_ok=True)
                (folder / name).write_text(text)
            (folder / "agent.yaml").write_text(agent_yaml)
            return load_agent(
                folder / "agent.yaml",
                {"ORDERS_API_KEY": ORDERS_KEY, "MBA_TOKEN": PLATFORM_TOKEN},
            )

    def test_references_outside_auth_secrets_are_refused(self) -> None:
        cases = [
            AGENT_YAML.replace("Nine to five.", "${ORDERS_API_KEY}"),
            AGENT_YAML.replace("/api\n", "/api?k=${ORDERS_API_KEY}\n"),
            AGENT_YAML.replace("Looks up an order.", "${ORDERS_API_KEY}"),
        ]
        for text in cases:
            with self.assertRaisesRegex(ConfigError, "only allowed as a connector"):
                self._load(text)

    def test_skill_file_content_cannot_reference_secrets(self) -> None:
        text = AGENT_YAML.replace(
            "faqs:",
            "skills:\n  - title: s\n    description: d\n    skill_file: s.md\nfaqs:",
        )
        with self.assertRaisesRegex(ConfigError, "only allowed as a connector"):
            self._load(text, {"s.md": "The key is ${ORDERS_API_KEY}."})

    def test_platform_credentials_are_never_referenced(self) -> None:
        text = AGENT_YAML.replace("${ORDERS_API_KEY}", "${MBA_TOKEN}")
        with self.assertRaisesRegex(ConfigError, "platform credential"):
            self._load(text)

    def test_yaml_aliases_cannot_copy_auth_into_tool_metadata(self) -> None:
        aliased = AGENT_YAML.replace(
            "          - field_name: X-API-Key\n",
            "          - &auth_param\n            field_name: X-API-Key\n",
        ).replace(
            "          path: /orders/{n}\n",
            "          path: /orders/{n}\n          headers: *auth_param\n",
        )
        merged = AGENT_YAML.replace(
            "          - field_name: X-API-Key\n",
            "          - &auth_param\n            field_name: X-API-Key\n",
        ).replace(
            "          path: /orders/{n}\n",
            "          path: /orders/{n}\n          headers:\n            <<: *auth_param\n",
        )
        for text in (aliased, merged):
            with self.assertRaisesRegex(
                ConfigError, "YAML aliases are not allowed"
            ) as cm:
                self._load(text)
            self.assertNotIn(ORDERS_KEY, str(cm.exception))

    def test_shared_objects_are_never_resolved(self) -> None:
        param = {"field_name": "X-API-Key", "value": "${ORDERS_API_KEY}"}
        doc: dict[str, Any] = {
            "connectors": [
                {
                    "name": "c",
                    "auth_type": "API_KEY",
                    "auth_config": {"api_key": {"headers": [param]}},
                    "tools": [{"name": "t", "request_definition": {"headers": param}}],
                }
            ]
        }
        with self.assertRaisesRegex(ConfigError, "reuses another part"):
            config_module._resolve_secrets(doc, {"ORDERS_API_KEY": ORDERS_KEY}, True)
        self.assertEqual(param["value"], "${ORDERS_API_KEY}")

    def test_literal_and_short_secrets_are_refused(self) -> None:
        with self.assertRaisesRegex(ConfigError, "must be exactly"):
            self._load(AGENT_YAML.replace("${ORDERS_API_KEY}", "hunter2-literal"))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "agent.yaml"
            path.write_text(AGENT_YAML)
            with self.assertRaisesRegex(ConfigError, "shorter than 8"):
                load_agent(path, {"ORDERS_API_KEY": "short"})

    def test_oauth_client_id_may_be_literal(self) -> None:
        api_key = (
            "      api_key:\n        headers:\n          - field_name: X-API-Key\n"
            "            value: ${ORDERS_API_KEY}\n"
        )
        oauth = (
            "      oauth2_client_credentials:\n"
            "        token_url: https://auth.example.com/t\n"
            "        scopes_to_request: [read]\n"
            "        client_id: public-id\n"
            "        client_secret: ${ORDERS_API_KEY}\n"
        )
        text = AGENT_YAML.replace(
            "auth_type: API_KEY", "auth_type: OAUTH2_CLIENT_CREDENTIALS"
        ).replace(api_key, oauth)
        doc = self._load(text)
        oauth = doc["connectors"][0]["auth_config"]["oauth2_client_credentials"]
        self.assertEqual(oauth["client_id"], "public-id")
        self.assertEqual(oauth["client_secret"], ORDERS_KEY)


class ContentFileTest(unittest.TestCase):
    def _skill(self, folder: Path, ref: str) -> None:
        (folder / "agent.yaml").write_text(
            "version: 1\nskills:\n  - title: s\n    description: d\n"
            f"    skill_file: {ref}\n"
        )
        load_agent(folder / "agent.yaml", {})

    def test_only_plain_content_files_are_read(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            for name in (
                ".env.dev",
                ".envrc",
                "secrets.json",
                "id_rsa",
                "notes/.key.md",
            ):
                (folder / name).parent.mkdir(parents=True, exist_ok=True)
                (folder / name).write_text("X=1")
                with self.assertRaises(ConfigError, msg=name):
                    self._skill(folder, name)
            (folder / "ok.md").write_text("Be helpful.")
            self._skill(folder, "ok.md")

    def test_symlinks_are_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / ".env").write_text("SECRET=1")
            (folder / "skill.md").symlink_to(folder / ".env")
            (folder / "real").mkdir()
            (folder / "real" / "s.md").write_text("x")
            (folder / "linked").symlink_to(folder / "real")
            with self.assertRaisesRegex(ConfigError, "symlink"):
                self._skill(folder, "skill.md")
            with self.assertRaisesRegex(ConfigError, "symlink"):
                self._skill(folder, "linked/s.md")

    def test_faqs_file_must_be_a_list_of_entries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "faqs.yaml").write_text("KEY: value\n")
            (folder / "agent.yaml").write_text("version: 1\nfaqs_file: faqs.yaml\n")
            with self.assertRaisesRegex(ConfigError, "list of entries"):
                load_agent(folder / "agent.yaml", {})


class ScrubberTest(unittest.TestCase):
    def test_every_encoding_is_scrubbed(self) -> None:
        scrub = Scrubber([ORDERS_KEY, "abc"])
        for form in (
            ORDERS_KEY,
            "synthetic-orders-key%2F0002%2Bx",
            "synthetic-orders-key/0002%2Bx",
            json.dumps(ORDERS_KEY),
        ):
            self.assertNotIn("0002", scrub(f"url=https://x?k={form}"), form)
        self.assertEqual(scrub("abc"), "abc")

    def test_auth_header_values_are_scrubbed_in_part_and_encoded(self) -> None:
        bearer = "Bearer synthetic-bearer-token-0004"
        pair = "synthetic-user:synthetic-password-0005"
        basic = "Basic " + base64.b64encode(pair.encode()).decode()
        scrub = Scrubber([bearer, basic])
        leaks = [
            "synthetic-bearer-token-0004",
            base64.b64encode(b"synthetic-bearer-token-0004").decode().rstrip("="),
            base64.b64encode(pair.encode()).decode(),
            pair,
            "synthetic-password-0005",
            base64.urlsafe_b64encode(b"synthetic-password-0005").decode(),
        ]
        for leak in leaks:
            self.assertEqual(scrub(f"error: got {leak}!"), "error: got ***!", leak)

    def test_cli_errors_scrub_token_portions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / ".env").write_text(
                "MBA_TOKEN=x\nUPSTREAM=Bearer synthetic-bearer-token-0004\n"
            )
            (folder / "agent.yaml").write_text("version: 1\n")
            client = FakeClient()
            err = ApiError(401, "GET", "x", "token synthetic-bearer-token-0004 expired")
            stderr = io.StringIO()
            with (
                mock.patch.object(cli, "_client", lambda args: client),
                mock.patch.object(FakeClient, "put_settings", side_effect=err),
                contextlib.redirect_stdout(io.StringIO()),
                contextlib.redirect_stderr(stderr),
            ):
                code = cli.main(
                    [
                        "--file",
                        str(folder / "agent.yaml"),
                        "--env",
                        str(folder / ".env"),
                        "disable",
                        "--yes",
                    ]
                )
            self.assertEqual(code, EXIT_NEEDS_HUMAN)
            self.assertIn("token *** expired", stderr.getvalue())


class OutputScrubbingTest(CliTestBase):
    def test_plan_output_never_contains_secrets(self) -> None:
        for argv in (("plan",), ("--json", "plan")):
            code, out, err = self.mba(*argv)
            self.assertEqual(code, EXIT_OK, err)
            self.assertNotIn(ORDERS_KEY, out + err)
            self.assertNotIn("synthetic-orders-key", out + err)

    def test_api_errors_and_crashes_are_scrubbed(self) -> None:
        echoed = f"bad header {ORDERS_KEY} / {PLATFORM_TOKEN} / k%2F0002%2Bx"
        with mock.patch.object(
            FakeClient,
            "list_items",
            side_effect=ApiError(400, "GET", "x", echoed),
        ):
            code, out, err = self.mba("plan")
        self.assertEqual(code, 1)
        self.assertIn("bad header", err)
        self.assertNotIn("synthetic", out + err)
        with mock.patch.object(
            FakeClient, "list_items", side_effect=RuntimeError(f"url ?k={ORDERS_KEY}")
        ):
            code, out, err = self.mba("plan")
        self.assertEqual(code, 1)
        self.assertIn("RuntimeError", err)
        self.assertNotIn("synthetic", out + err)

    def test_pull_never_writes_auth_config(self) -> None:
        self.client.collections["agent_connectors"] = [
            {
                "id": "9",
                "name": "orders",
                "base_url": "https://orders.example.com/api",
                "auth_type": "API_KEY",
                "auth_config": {"api_key": {"headers": [{"value": "LIVE-VALUE-1"}]}},
            }
        ]
        out_file = self.folder / "pulled.yaml"
        code, _, err = self.mba("pull", "--out", str(out_file))
        self.assertEqual(code, EXIT_OK, err)
        text = out_file.read_text()
        self.assertNotIn("auth_config:", text.split("\n", 2)[2])
        self.assertNotIn("LIVE-VALUE-1", text)


class ApprovalTest(CliTestBase):
    def test_apply_requires_yes(self) -> None:
        code, _, _ = self.mba("apply", "--plan-id", self.plan_id())
        self.assertEqual(code, EXIT_NEEDS_HUMAN)
        self.assertEqual(self.client.writes, [])

    def test_plan_is_bound_to_the_target(self) -> None:
        plan_id = self.plan_id()
        self.entity = "222"  # identical, empty agent on another number
        code, _, _ = self.mba("apply", "--plan-id", plan_id, "--yes")
        self.assertEqual(code, EXIT_PLAN_STALE)
        self.assertEqual(self.client.writes, [])

    def test_plan_is_bound_to_secrets_and_flags(self) -> None:
        plan_id = self.plan_id()
        (self.folder / ".env").write_text(DOTENV.replace("0002", "0003"))
        self.assertEqual(
            self.mba("apply", "--plan-id", plan_id, "--yes")[0], EXIT_PLAN_STALE
        )
        plan_id = self.plan_id()
        self.assertEqual(
            self.mba("apply", "--plan-id", plan_id, "--prune", "--yes")[0],
            EXIT_PLAN_STALE,
        )
        self.assertEqual(self.client.writes, [])

    def test_plan_id_is_keyed_and_the_key_is_private(self) -> None:
        plan_id = self.plan_id()
        key_file = self.folder / ".mba" / "approval.key"
        self.assertEqual(stat.S_IMODE(key_file.stat().st_mode), 0o600)
        key_file.unlink()
        self.assertNotEqual(self.plan_id(), plan_id)
        key_file.chmod(0o644)
        code, _, err = self.mba("plan")
        self.assertEqual(code, 2)
        self.assertIn("readable only by you", err)

    def test_apply_without_a_plan_in_this_folder_is_stale(self) -> None:
        code, _, _ = self.mba("apply", "--plan-id", "0" * 16, "--yes")
        self.assertEqual(code, EXIT_PLAN_STALE)


class GoLiveGateTest(CliTestBase):
    def test_state_lives_next_to_agent_yaml(self) -> None:
        self.configure_and_eval()
        self.assertTrue((self.folder / ".mba" / "state.json").is_file())
        self.assertTrue(list((self.folder / ".mba" / "evals").glob("*.json")))

    def test_enable_after_a_passing_eval(self) -> None:
        self.go_live()
        self.assertTrue(self.client.settings["rollout"]["enabled"])

    def test_eval_of_another_agent_does_not_open_the_gate(self) -> None:
        self.configure_and_eval()
        self.entity = "222"
        self.assertEqual(self.mba("enable", "--yes")[0], EXIT_GATE_FAILED)
        self.assertEqual(self.client.writes, [])

    def test_live_change_after_the_eval_closes_the_gate(self) -> None:
        self.configure_and_eval()
        self.client.collections["agent_config/faq"].append(
            {"id": "1", "question": "Added in the console?", "answer": "x"}
        )
        self.assertEqual(self.mba("enable", "--yes")[0], EXIT_GATE_FAILED)
        self.assertFalse(self.client.settings["rollout"]["enabled"])

    def test_other_suites_and_partial_runs_do_not_open_the_gate(self) -> None:
        self.apply("--yes")
        other = self.folder / "other"
        other.mkdir()
        (other / "x.yaml").write_text(SCENARIO)
        self.assertEqual(self.mba("eval", "--dir", str(other))[0], EXIT_OK)
        self.assertEqual(self.mba("enable", "--yes")[0], EXIT_GATE_FAILED)
        self.assertEqual(self.mba("eval", "--only", "hello")[0], EXIT_OK)
        self.assertEqual(self.mba("enable", "--yes")[0], EXIT_GATE_FAILED)

    def test_unverifiable_live_version_fails_closed(self) -> None:
        self.configure_and_eval()
        self.client.version_error = ApiError(500, "GET", "versions/active", "down")
        self.assertEqual(self.mba("enable", "--yes")[0], 1)
        self.assertFalse(self.client.settings["rollout"]["enabled"])

    def test_partial_apply_closes_the_gate(self) -> None:
        self.configure_and_eval()
        self.client.settings["rollout"]["enabled"] = False
        self.agent_file.write_text(
            AGENT_YAML.replace(
                "faqs:\n",
                "faqs:\n  - question: A?\n    answer: a\n"
                "  - question: B?\n    answer: b\n",
            )
        )
        self.client.fail_create_after = 1
        code, _, _ = self.apply("--yes")
        self.assertEqual(code, 1)
        state = json.loads((self.folder / ".mba" / "state.json").read_text())
        record = state["applies"][self.client.target]
        self.assertEqual(record["status"], "failed")
        self.assertEqual(record["completed_ops"], 1)
        self.assertEqual(self.mba("enable", "--yes")[0], EXIT_GATE_FAILED)

    def test_enabling_for_everyone_needs_separate_confirmation(self) -> None:
        self.configure_and_eval()
        self.client.settings["ai_audience"] = None  # API default is EVERYONE
        self.assertEqual(self.mba("enable", "--yes")[0], EXIT_NEEDS_HUMAN)
        self.assertEqual(self.mba("enable", "--yes", "--widen-audience")[0], EXIT_OK)


class ExposureGuardTest(CliTestBase):
    def test_config_changes_are_refused_while_live(self) -> None:
        self.go_live()
        self.agent_file.write_text(AGENT_YAML.replace("Nine to five.", "Ten to six."))
        before = list(self.client.writes)
        self.assertEqual(self.apply("--yes")[0], EXIT_GATE_FAILED)
        self.assertEqual(self.client.writes, before)

    def test_widening_needs_confirmation_and_a_live_eval(self) -> None:
        self.go_live()
        widened = AGENT_YAML.replace("ALLOWLISTED_ONLY", "EVERYONE")
        self.agent_file.write_text(widened)
        self.assertEqual(self.apply("--yes")[0], EXIT_NEEDS_HUMAN)
        self.assertEqual(self.apply("--yes", "--widen-audience")[0], EXIT_OK)
        self.assertEqual(self.client.settings["ai_audience"], "EVERYONE")

    def test_live_widening_without_a_current_eval_is_refused(self) -> None:
        self.go_live()
        self.client.collections["agent_config/faq"].append(
            {"id": "1", "question": "Changed elsewhere?", "answer": "x"}
        )
        self.agent_file.write_text(
            AGENT_YAML.replace(
                "connectors:", 'allowlist:\n  - "+15555550199"\nconnectors:'
            )
        )
        self.assertEqual(self.apply("--yes", "--widen-audience")[0], EXIT_GATE_FAILED)
        self.assertEqual(self.client.list_items("agent_config/allowlist"), [])

    def test_setup_while_disabled_needs_no_widening_flag(self) -> None:
        self.agent_file.write_text(
            AGENT_YAML.replace("ALLOWLISTED_ONLY", "EVERYONE").replace(
                "connectors:", 'allowlist:\n  - "+15555550199"\nconnectors:'
            )
        )
        self.client.settings["ai_audience"] = "ALLOWLISTED_ONLY"
        self.assertEqual(self.apply("--yes")[0], EXIT_OK)
        self.assertEqual(len(self.client.list_items("agent_config/allowlist")), 1)
        self.assertEqual(self.mba("eval")[0], EXIT_OK)
        self.assertEqual(self.mba("enable", "--yes")[0], EXIT_NEEDS_HUMAN)

    def test_narrowing_is_allowed_while_live(self) -> None:
        self.go_live()
        self.client.settings["ai_audience"] = "EVERYONE"
        self.assertEqual(self.apply("--yes")[0], EXIT_OK)
        self.assertEqual(self.client.settings["ai_audience"], "ALLOWLISTED_ONLY")

    def test_rotation_is_explicit_and_disabled_only(self) -> None:
        self.configure_and_eval()
        code, out, _ = self.mba("--json", "plan")
        self.assertEqual(json.loads(out)["ops"], [])  # no perpetual credential diff
        code, out, err = self.apply("--rotate-credentials", "orders", "--yes")
        self.assertEqual(code, EXIT_OK, err)
        rotation = [w for w in self.client.writes if w[0] == "upsert_api_key"]
        self.assertEqual(rotation[0][1]["headers"][0]["value"], ORDERS_KEY)
        self.assertNotIn(ORDERS_KEY, out)
        self.client.settings["rollout"]["enabled"] = True
        code, _, _ = self.apply("--rotate-credentials", "orders", "--yes")
        self.assertEqual(code, EXIT_GATE_FAILED)

    def test_rollback_is_refused_while_live(self) -> None:
        self.go_live()
        self.assertEqual(self.mba("rollback", "v1", "--yes")[0], EXIT_GATE_FAILED)
        self.assertNotIn(("version", "v1"), self.client.writes)

    def test_mutating_tools_need_yes(self) -> None:
        self.apply("--yes")
        self.assertEqual(self.mba("run-tool", "orders", "get_order")[0], EXIT_OK)
        self.assertEqual(
            self.mba("run-tool", "orders", "create_return")[0], EXIT_NEEDS_HUMAN
        )
        self.assertEqual(
            [w for w in self.client.writes if w[0] == "run_tool"], [("run_tool", "103")]
        )
        self.assertEqual(
            self.mba("run-tool", "orders", "create_return", "--yes")[0], EXIT_OK
        )


class PlanUnitTest(unittest.TestCase):
    def test_same_plan_on_two_targets_has_different_ids(self) -> None:
        desired: dict[str, Any] = {"faqs": [{"question": "Q?", "answer": "A"}]}
        remote: dict[str, Any] = {"faqs": []}
        ids = {
            pl.compute_plan(desired, remote, pl.Binding(b"k" * 32, t, "/a"))["plan_id"]
            for t in ("https://api.invalid/111", "https://api.invalid/222")
        }
        other_key = pl.compute_plan(
            desired, remote, pl.Binding(b"j" * 32, "https://api.invalid/111", "/a")
        )["plan_id"]
        self.assertEqual(len(ids), 2)
        self.assertNotIn(other_key, ids)


class CredentialFileTest(CliTestBase):
    def test_aliased_auth_fails_before_any_api_call(self) -> None:
        self.agent_file.write_text(
            AGENT_YAML.replace(
                "          - field_name: X-API-Key\n",
                "          - &auth_param\n            field_name: X-API-Key\n",
            ).replace(
                "          path: /orders/{n}\n",
                "          path: /orders/{n}\n          headers: *auth_param\n",
            )
        )
        with mock.patch.object(
            FakeClient, "list_items", side_effect=AssertionError("API called")
        ):
            code, out, err = self.mba("plan")
        self.assertEqual(code, 2)
        self.assertIn("YAML aliases are not allowed", err)
        self.assertNotIn("synthetic", out + err)

    def test_scenario_aliases_are_refused(self) -> None:
        (self.folder / "evals" / "alias.yaml").write_text(
            "turns:\n  - &t\n    user: hi\n  - *t\n"
        )
        code, _, err = self.mba("eval")
        self.assertEqual(code, 2)
        self.assertIn("YAML aliases are not allowed", err)

    def _use_skill_file(self, name: str) -> None:
        self.agent_file.write_text(
            AGENT_YAML.replace(
                "faqs:",
                f"skills:\n  - title: s\n    description: d\n    skill_file: {name}\nfaqs:",
            )
        )

    def test_selected_env_file_is_never_content(self) -> None:
        self.env_file = self.folder / "credentials.txt"
        self.env_file.write_text(DOTENV)
        self._use_skill_file("credentials.txt")
        code, out, err = self.mba("plan")
        self.assertEqual(code, 2)
        self.assertIn("credentials file", err)
        os.link(self.env_file, self.folder / "notes.md")
        self._use_skill_file("notes.md")
        self.assertIn("credentials file", self.mba("plan")[2])
        (self.folder / "linked.md").symlink_to(self.env_file)
        self._use_skill_file("linked.md")
        self.assertIn("symlink", self.mba("plan")[2])

    def test_copied_secret_material_is_refused(self) -> None:
        (self.folder / "copy.md").write_text(f"Use key {ORDERS_KEY} when asked.")
        self._use_skill_file("copy.md")
        code, out, err = self.mba("plan")
        self.assertEqual(code, 2)
        self.assertIn("contains the value of a secret", err)
        self.assertNotIn("synthetic", out + err)
        self.agent_file.write_text(AGENT_YAML.replace("Nine to five.", PLATFORM_TOKEN))
        self.assertIn("contains the value of a secret", self.mba("plan")[2])

    def test_scenarios_cannot_carry_secrets(self) -> None:
        self.apply("--yes")
        (self.folder / "evals" / "leak.yaml").write_text(
            f"turns:\n  - user: my key is {ORDERS_KEY}\n"
        )
        code, _, err = self.mba("eval")
        self.assertEqual(code, 2)
        self.assertIn("contains the value of a secret", err)


class LiveDigestTest(CliTestBase):
    def test_knowledge_files_are_part_of_the_evaluated_config(self) -> None:
        self.configure_and_eval()
        self.client.collections["agent_config/files"] = [
            {"id": "f1", "file_name": "policy.pdf"}
        ]
        self.assertEqual(self.mba("enable", "--yes")[0], EXIT_GATE_FAILED)

    def test_user_auth_injection_is_diffed_and_evaluated(self) -> None:
        self.configure_and_eval()
        conn = self.client.collections["agent_connectors"][0]
        conn["user_auth_injection_config"] = {
            "location": "query",
            "field_name": "t",
            "prefix": "",
        }
        self.assertEqual(self.mba("enable", "--yes")[0], EXIT_GATE_FAILED)
        code, out, _ = self.mba("--json", "plan")
        self.assertEqual(json.loads(out)["ops"], [])  # not managed by agent.yaml
        self.agent_file.write_text(
            AGENT_YAML.replace(
                "    auth_type: API_KEY\n",
                "    auth_type: API_KEY\n    user_auth_injection_config:\n"
                "      location: headers\n      field_name: X-User-Token\n"
                "      prefix: ''\n",
            )
        )
        code, out, _ = self.mba("--json", "plan")
        ops = json.loads(out)["ops"]
        self.assertEqual(
            [(o["action"], o["kind"], list(o["changes"])) for o in ops],
            [("update", "connector", ["user_auth_injection_config"])],
        )

    def test_requires_certificate_is_never_silently_ignored(self) -> None:
        self.apply("--yes")
        self.agent_file.write_text(
            AGENT_YAML.replace(
                "    auth_type: API_KEY\n",
                "    auth_type: API_KEY\n    requires_certificate: true\n",
            )
        )
        code, _, err = self.mba("plan")
        self.assertEqual(code, 2)
        self.assertIn("requires_certificate", err)
        conn = self.client.collections["agent_connectors"][0]
        conn["mtls_config"] = {"has_certificate": True, "fingerprint": "AA"}
        self.assertEqual(self.mba("plan")[0], EXIT_OK)

    def test_versioned_numbers_are_refused(self) -> None:
        self.assertEqual(self.apply("--yes")[0], EXIT_OK)
        details = [
            {"version_id": "v1", "knowledge": []},
            {
                "version_id": "v2",
                "created_at": 1,
                "is_active": True,
                "knowledge": [
                    {
                        "knowledge_type": "faq",
                        "knowledge_version_id": "k1",
                        "created_at": 1,
                    }
                ],
            },
        ]
        for version in details:
            with self.subTest(version=version["version_id"]):
                self.client.version = version
                code, _, err = self.mba("eval")
                self.assertEqual(code, EXIT_GATE_FAILED)
                self.assertIn("versioned configuration", err)
                self.assertEqual(self.mba("enable", "--yes")[0], EXIT_GATE_FAILED)
                self.assertFalse(self.client.settings["rollout"]["enabled"])

    def test_version_activated_after_a_passing_eval_blocks_enable(self) -> None:
        self.configure_and_eval()
        self.client.version = {"version_id": "v1", "knowledge": []}
        code, _, err = self.mba("enable", "--yes")
        self.assertEqual(code, EXIT_GATE_FAILED)
        self.assertIn("versioned configuration", err)
        self.assertFalse(self.client.settings["rollout"]["enabled"])

    def test_live_widening_on_a_versioned_number_is_refused(self) -> None:
        self.go_live()
        self.client.version = {"version_id": "v1", "knowledge": []}
        self.agent_file.write_text(AGENT_YAML.replace("ALLOWLISTED_ONLY", "EVERYONE"))
        self.assertEqual(self.apply("--yes", "--widen-audience")[0], EXIT_GATE_FAILED)
        self.assertEqual(self.client.settings["ai_audience"], "ALLOWLISTED_ONLY")

    def test_malformed_active_version_fails_closed(self) -> None:
        self.configure_and_eval()
        for malformed in ([], {"version_id": 5}, {"knowledge": []}):
            with self.subTest(malformed=malformed):
                self.client.version = malformed
                code, _, err = self.mba("enable", "--yes")
                self.assertEqual(code, EXIT_GATE_FAILED)
                self.assertIn("Unexpected response", err)
        self.assertFalse(self.client.settings["rollout"]["enabled"])


class ReconcileTest(CliTestBase):
    def _lost_final_response(self) -> None:
        """An apply whose single write landed but whose response was lost."""
        self.configure_and_eval()
        self.agent_file.write_text(
            AGENT_YAML.replace("faqs:\n", "faqs:\n  - question: New?\n    answer: n\n")
        )
        self.client.lose_response_after_create = True
        self.assertEqual(self.apply("--yes")[0], 1)
        self.client.lose_response_after_create = False
        self.assertEqual(self.mba("enable", "--yes")[0], EXIT_GATE_FAILED)

    def test_converged_no_op_apply_settles_a_lost_apply(self) -> None:
        self._lost_final_response()
        code, out, _ = self.mba("--json", "plan")
        self.assertEqual(json.loads(out)["ops"], [])
        self.assertEqual(self.apply("--yes")[0], EXIT_OK)
        state = json.loads((self.folder / ".mba" / "state.json").read_text())
        record = state["applies"][self.client.target]
        self.assertEqual((record["status"], record["reconciled"]), ("complete", True))
        # The eval from before the lost apply is stale; a fresh one opens the gate.
        self.assertEqual(self.mba("enable", "--yes")[0], EXIT_GATE_FAILED)
        self.assertEqual(self.mba("eval")[0], EXIT_OK)
        self.assertEqual(self.mba("enable", "--yes")[0], EXIT_OK)

    def test_reconciling_another_agent_does_not_settle_this_one(self) -> None:
        self._lost_final_response()
        self.entity = "222"
        self.assertEqual(self.apply("--yes")[0], EXIT_OK)  # creates on 222
        self.assertEqual(self.apply("--yes")[0], EXIT_OK)  # no-op on 222
        self.entity = "111"
        self.assertEqual(self.mba("eval")[0], EXIT_OK)
        self.assertEqual(self.mba("enable", "--yes")[0], EXIT_GATE_FAILED)
