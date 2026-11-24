# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

from __future__ import annotations

import importlib
import inspect
import os
import re
import unittest
from collections import Counter
from collections.abc import Iterator
from functools import cache
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import mba
import yaml

SPEC_FILES = (
    "agent_eval.yaml",
    "agent_event.yaml",
    "agent_test.yaml",
    "allowlist.yaml",
    "config_versions.yaml",
    "connector_tools.yaml",
    "connectors.yaml",
    "delete_agent.yaml",
    "eligibility.yaml",
    "knowledge_business_info.yaml",
    "knowledge_fa_qs.yaml",
    "knowledge_files.yaml",
    "knowledge_websites.yaml",
    "onboarding.yaml",
    "settings.yaml",
    "skills.yaml",
)
SERVER_ORIGIN = "https://api.facebook.com"
METHODS = ("get", "put", "post", "delete", "options", "head", "patch", "trace")
REQUIRE_VALIDATOR_ENV = "MBA_REQUIRE_OPENAPI_VALIDATOR"

# Every (method, path) the `mba` client calls, relative to SERVER_ORIGIN.
CLIENT_OPERATIONS = (
    ("get", "/{entity_id}/agent_eligibility"),
    ("post", "/{entity_id}/agent_onboarding"),
    ("get", "/{entity_id}/agent_config/settings"),
    ("put", "/{entity_id}/agent_config/settings"),
    ("get", "/{entity_id}/agent_config/business_info"),
    ("put", "/{entity_id}/agent_config/business_info"),
    ("get", "/{entity_id}/agent_config/skills"),
    ("post", "/{entity_id}/agent_config/skills"),
    ("put", "/{entity_id}/agent_config/skills/{skill_id}"),
    ("delete", "/{entity_id}/agent_config/skills/{skill_id}"),
    ("get", "/{entity_id}/agent_config/faq"),
    ("post", "/{entity_id}/agent_config/faq"),
    ("put", "/{entity_id}/agent_config/faq/{faq_id}"),
    ("delete", "/{entity_id}/agent_config/faq/{faq_id}"),
    ("get", "/{entity_id}/agent_config/websites"),
    ("post", "/{entity_id}/agent_config/websites"),
    ("put", "/{entity_id}/agent_config/websites/{website_id}"),
    ("delete", "/{entity_id}/agent_config/websites/{website_id}"),
    ("get", "/{entity_id}/agent_config/files"),
    ("get", "/{entity_id}/agent_config/allowlist"),
    ("post", "/{entity_id}/agent_config/allowlist"),
    ("delete", "/{entity_id}/agent_config/allowlist/{entry_id}"),
    ("get", "/{entity_id}/agent_connectors"),
    ("post", "/{entity_id}/agent_connectors"),
    ("put", "/{entity_id}/agent_connectors/{connector_id}"),
    ("delete", "/{entity_id}/agent_connectors/{connector_id}"),
    ("get", "/{entity_id}/agent_connectors/{connector_id}/logs"),
    ("get", "/{entity_id}/agent_connectors/{connector_id}/tools"),
    ("post", "/{entity_id}/agent_connectors/{connector_id}/tools"),
    ("put", "/{entity_id}/agent_connectors/{connector_id}/tools/{tool_id}"),
    ("delete", "/{entity_id}/agent_connectors/{connector_id}/tools/{tool_id}"),
    ("post", "/{entity_id}/agent_connectors/{connector_id}/tools/{tool_id}/run"),
    ("post", "/{entity_id}/agent_connectors/{connector_id}/upsertApiKey"),
    ("post", "/{entity_id}/agent_connectors/{connector_id}/upsertOAuth"),
    ("post", "/{entity_id}/agent_test"),
    ("get", "/{entity_id}/agent-eval/cases"),
    ("get", "/{entity_id}/agent-eval/run"),
    ("post", "/{entity_id}/agent-eval/run"),
    ("get", "/{entity_id}/agent_config/versions"),
    ("get", "/{entity_id}/agent_config/versions/active"),
    ("put", "/{entity_id}/agent_config/versions/active"),
    ("post", "/{entity_id}/agent_event"),
    ("get", "/{entity_id}/agent_event/{agent_event_id}"),
)


def openapi_dir() -> Path:
    """The packaged openapi/ resources, in Buck and source layouts."""
    pkg = Path(mba.__file__)
    candidates = (
        pkg.parent.parent / "openapi",
        pkg.resolve().parent.parent / "openapi",
        Path(__file__).resolve().parent.parent / "openapi",
    )
    for directory in candidates:
        if (directory / SPEC_FILES[0]).is_file():
            return directory
    raise FileNotFoundError(
        f"openapi specs not found under {[str(c) for c in candidates]}"
    )


@cache
def load_spec(name: str) -> dict[str, Any]:
    with open(openapi_dir() / name, encoding="utf-8") as f:
        spec = yaml.safe_load(f)
    if not isinstance(spec, dict):
        raise TypeError(f"{name}: top level is not a mapping")
    return spec


def operations(
    spec: dict[str, Any],
) -> Iterator[tuple[str, str, dict[str, Any], dict[str, Any]]]:
    for path, item in spec["paths"].items():
        for method in METHODS:
            if method in item:
                yield path, method, item, item[method]


def walk_refs(node: object, where: str = "#") -> Iterator[tuple[str, object]]:
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "$ref":
                yield where, value
            else:
                yield from walk_refs(value, f"{where}/{key}")
    elif isinstance(node, list):
        for i, value in enumerate(node):
            yield from walk_refs(value, f"{where}/{i}")


def resolve_pointer(spec: dict[str, Any], ref: str) -> bool:
    node: object = spec
    for token in ref[2:].split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        if not isinstance(node, dict) or token not in node:
            return False
        node = node[token]
    return True


def deref(spec: dict[str, Any], node: dict[str, Any]) -> dict[str, Any]:
    ref = node.get("$ref")
    if not isinstance(ref, str):
        return node
    target: Any = spec
    for token in ref[2:].split("/"):
        target = target[token.replace("~1", "/").replace("~0", "~")]
    return target


class OpenApiSpecTest(unittest.TestCase):
    def test_known_files_are_packaged(self) -> None:
        self.assertEqual(
            sorted(p.name for p in openapi_dir().glob("*.yaml")), sorted(SPEC_FILES)
        )
        self.assertEqual(len(SPEC_FILES), 16)

    def test_document_basics(self) -> None:
        for name in SPEC_FILES:
            with self.subTest(spec=name):
                spec = load_spec(name)
                self.assertRegex(str(spec.get("openapi")), r"^3\.1\.\d+$")
                self.assertIsInstance(spec.get("info", {}).get("title"), str)
                self.assertEqual(spec.get("servers"), [{"url": SERVER_ORIGIN}])
                origin = urlsplit(spec["servers"][0]["url"])
                self.assertEqual(
                    (origin.path, origin.query, origin.fragment), ("", "", "")
                )
                self.assertTrue(spec.get("paths"))
                schemes = spec.get("components", {}).get("securitySchemes", {})
                for requirement in spec.get("security", []):
                    for scheme in requirement:
                        self.assertIn(scheme, schemes)

    def test_paths_are_full_resource_paths(self) -> None:
        for name in SPEC_FILES:
            for path in load_spec(name)["paths"]:
                with self.subTest(spec=name, path=path):
                    self.assertTrue(path.startswith("/{entity_id}/"), path)
                    self.assertNotRegex(path, r"//|/$|\s")
                    self.assertRegex(path, r"^(/(\{[a-z_]+\}|[A-Za-z0-9_-]+))+$")

    def test_path_parameters_match_template(self) -> None:
        for name in SPEC_FILES:
            spec = load_spec(name)
            for path, method, item, op in operations(spec):
                with self.subTest(spec=name, op=f"{method.upper()} {path}"):
                    template = re.findall(r"\{([^}]+)\}", path)
                    self.assertEqual(len(template), len(set(template)))
                    params = {}
                    for raw in item.get("parameters", []) + op.get("parameters", []):
                        param = deref(spec, raw)
                        params[(param["name"], param["in"])] = param
                    declared = [n for (n, loc) in params if loc == "path"]
                    self.assertCountEqual(declared, template)
                    for n in declared:
                        self.assertIs(params[(n, "path")].get("required"), True, n)
                    own = [
                        (deref(spec, p)["name"], deref(spec, p)["in"])
                        for p in op.get("parameters", [])
                    ]
                    self.assertEqual(len(own), len(set(own)), "duplicate parameter")

    def test_operation_ids_unique(self) -> None:
        ids = Counter(
            op.get("operationId")
            for name in SPEC_FILES
            for *_, op in operations(load_spec(name))
        )
        self.assertNotIn(None, ids)
        self.assertEqual([i for i, n in ids.items() if n > 1], [])

    def test_no_duplicate_operations_across_files(self) -> None:
        ops = Counter(
            (method, re.sub(r"\{[^}]+\}", "{}", path))
            for name in SPEC_FILES
            for path, method, _, _ in operations(load_spec(name))
        )
        self.assertEqual([o for o, n in ops.items() if n > 1], [])

    def test_responses(self) -> None:
        for name in SPEC_FILES:
            for path, method, _, op in operations(load_spec(name)):
                with self.subTest(spec=name, op=f"{method.upper()} {path}"):
                    self.assertTrue(op.get("responses"))
                    for code in op["responses"]:
                        self.assertIsInstance(
                            code, str, f"unquoted response code {code}"
                        )
                        self.assertRegex(
                            str(code), r"^([1-5][0-9]{2}|[1-5]XX|default)$"
                        )

    def test_all_mapping_keys_are_strings(self) -> None:
        def non_string_keys(node: object, where: str) -> Iterator[str]:
            if isinstance(node, dict):
                for key, value in node.items():
                    if not isinstance(key, str):
                        yield f"{where}/{key!r}"
                    yield from non_string_keys(value, f"{where}/{key}")
            elif isinstance(node, list):
                for i, value in enumerate(node):
                    yield from non_string_keys(value, f"{where}/{i}")

        for name in SPEC_FILES:
            with self.subTest(spec=name):
                self.assertEqual(list(non_string_keys(load_spec(name), "#")), [])

    def test_refs_are_local_and_resolve(self) -> None:
        for name in SPEC_FILES:
            spec = load_spec(name)
            for where, ref in walk_refs(spec):
                with self.subTest(spec=name, at=where):
                    self.assertIsInstance(ref, str)
                    assert isinstance(ref, str)
                    self.assertTrue(ref.startswith("#/"), ref)
                    self.assertTrue(resolve_pointer(spec, ref), ref)

    def test_client_operations_are_specified(self) -> None:
        specified = {
            (method, path)
            for name in SPEC_FILES
            for path, method, _, _ in operations(load_spec(name))
        }
        normalized = {(m, re.sub(r"\{[^}]+\}", "{}", p)) for m, p in specified}
        for method, path in CLIENT_OPERATIONS:
            with self.subTest(op=f"{method.upper()} {path}"):
                self.assertIn((method, re.sub(r"\{[^}]+\}", "{}", path)), normalized)

    def test_config_versions_public_contract(self) -> None:
        spec = load_spec("config_versions.yaml")
        base = "/{entity_id}/agent_config/versions"
        self.assertEqual(
            {(method, path) for path, method, _, _ in operations(spec)},
            {
                ("get", base),
                ("get", f"{base}/active"),
                ("get", f"{base}/{{version_id}}"),
                ("put", f"{base}/active"),
            },
        )
        self.assertEqual(
            set(spec["components"]["schemas"]),
            {
                "BizAIOmniChannelConfigVersionSummaryResponse",
                "BizAIOmniChannelConfigVersionResponse",
                "BizAIOmniChannelConfigVersionKnowledgeResponse",
                "BizAIOmniChannelSetActiveConfigVersionRequest",
                "StandardError",
            },
        )

    def test_every_config_versions_schema_is_reachable(self) -> None:
        spec = load_spec("config_versions.yaml")
        prefix = "#/components/schemas/"
        reached: set[str] = set()
        queue = [ref for _, ref in walk_refs(spec["paths"])]
        while queue:
            ref = queue.pop()
            assert isinstance(ref, str)
            name = ref.removeprefix(prefix)
            if name in reached:
                continue
            reached.add(name)
            queue += [r for _, r in walk_refs(spec["components"]["schemas"][name])]
        self.assertEqual(reached, set(spec["components"]["schemas"]))

    def test_client_versioning_paths_match_public_contract(self) -> None:
        source = inspect.getsource(importlib.import_module("mba.client"))
        literals = set(
            re.findall(r"""f?["'](agent_config/versions[^"']*)["']""", source)
        )
        self.assertEqual(
            literals, {"agent_config/versions", "agent_config/versions/active"}
        )

    def test_standards_validator(self) -> None:
        try:
            validator = importlib.import_module("openapi_spec_validator")
        except ImportError:
            if os.environ.get(REQUIRE_VALIDATOR_ENV) == "1":
                self.fail(
                    f"{REQUIRE_VALIDATOR_ENV}=1 but openapi-spec-validator is not installed"
                )
            self.skipTest(
                f"openapi-spec-validator not installed; set {REQUIRE_VALIDATOR_ENV}=1 to make this a hard gate"
            )
        for name in SPEC_FILES:
            with self.subTest(spec=name):
                validator.validate(load_spec(name))
