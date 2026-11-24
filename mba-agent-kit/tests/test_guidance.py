# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

import yaml
from mba.cli import TEMPLATES

ROOT: Path = TEMPLATES.parent
GUIDANCE_NAMES: tuple[str, ...] = ("mba-start", "mba-prd-builder", "mba-onboarding")


class GuidanceTest(unittest.TestCase):
    def test_bundled_skills_have_valid_discovery_metadata(self) -> None:
        for name in GUIDANCE_NAMES:
            with self.subTest(skill=name):
                path = ROOT / "agent-guidance" / name / "SKILL.md"
                text = path.read_text()
                self.assertTrue(text.startswith("---\n"))
                metadata = yaml.safe_load(text.split("---", 2)[1])
                self.assertEqual(metadata["name"], name)
                self.assertIsInstance(metadata["description"], str)
                self.assertTrue(metadata["description"].strip())

    def test_skill_reference_files_are_present(self) -> None:
        for name in GUIDANCE_NAMES:
            folder = ROOT / "agent-guidance" / name
            for reference in set(
                re.findall(
                    r"(?:\.\./[a-z-]+/)?references/[a-z-]+\.md",
                    (folder / "SKILL.md").read_text(),
                )
            ):
                with self.subTest(skill=name, reference=reference):
                    self.assertTrue((folder / reference).is_file())

    def test_readme_explains_explicit_loading_and_source_installation(self) -> None:
        text = (ROOT / "README.md").read_text()
        self.assertIn("not automatically installed as slash commands", text)
        self.assertIn("Only source/editable installation is supported", text)
        self.assertIn("agent-guidance/mba-start/SKILL.md", text)

    def test_thread_control_uses_its_own_api_version(self) -> None:
        path = ROOT / "agent-guidance/mba-onboarding/references/thread-control.md"
        versions = re.findall(r"X-API-Version: ([0-9.]+)", path.read_text())
        self.assertEqual(versions, ["1.0.0"] * 4)

    def test_connector_auth_modes_match_the_public_spec(self) -> None:
        schema = json.loads((ROOT / "schema/agent.schema.json").read_text())
        modes = schema["properties"]["connectors"]["items"]["properties"]["auth_type"][
            "enum"
        ]
        self.assertCountEqual(modes, ["API_KEY", "OAUTH2_CLIENT_CREDENTIALS", "NONE"])
        spec = yaml.safe_load((ROOT / "openapi/connectors.yaml").read_text())
        connector = spec["components"]["schemas"]["BizAIOmniChannelConnectorRequest"]
        auth = connector["properties"]["auth_type"]
        self.assertTrue(set(modes).issubset(auth["enum"]))
        accepted_text = (
            auth["description"].split("but only", 1)[1].split("are accepted here", 1)[0]
        )
        self.assertCountEqual(modes, re.findall(r"`([^`]+)`", accepted_text))

    def test_working_ledger_examples_are_explicitly_fictional(self) -> None:
        path = ROOT / "agent-guidance/mba-prd-builder/references/capture.md"
        self.assertIn("are fictional", path.read_text())
        self.assertIn("not records of a client engagement", path.read_text())
