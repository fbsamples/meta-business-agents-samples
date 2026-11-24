# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

"""Loads .env and agent.yaml into the desired-state document that plan.py diffs."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

import yaml

from .errors import ConfigError

_ENV_REF_PATTERN = re.compile(r"\$\{([A-Z0-9_]+)\}")
SKILL_TITLE_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")
SCHEMA_PATH: Path = (
    Path(__file__).resolve().parent.parent / "schema" / "agent.schema.json"
)


def load_dotenv(path: Path) -> set[str]:
    """Loads KEY=VALUE lines into os.environ and returns the keys the file defines.

    Only those keys may be referenced as ${NAME} from agent.yaml, so a config
    cannot pull unrelated secrets out of the user's shell environment.
    """
    keys: set[str] = set()
    if not path.exists():
        return keys
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        keys.add(key)
        os.environ.setdefault(key, value.strip().strip('"').strip("'"))
    return keys


def credentials() -> dict[str, str]:
    token = os.environ.get("MBA_TOKEN", "")
    entity_id = os.environ.get("MBA_ENTITY_ID", "")
    missing = [
        k for k, v in (("MBA_TOKEN", token), ("MBA_ENTITY_ID", entity_id)) if not v
    ]
    if missing:
        raise ConfigError(
            f"Missing {', '.join(missing)}.",
            "Copy .env.example to .env and fill it in. MBA_ENTITY_ID is the WhatsApp "
            "phone number ID (WhatsApp Manager > Account tools > Phone numbers).",
        )
    return {"token": token, "entity_id": entity_id}


def _expand_env(value: Any, allowed: set[str], problems: list[str]) -> Any:
    if isinstance(value, str):

        def sub(m: re.Match[str]) -> str:
            name = m.group(1)
            if name not in allowed or name not in os.environ:
                problems.append(name)
                return m.group(0)
            return os.environ[name]

        return _ENV_REF_PATTERN.sub(sub, value)
    if isinstance(value, dict):
        return {k: _expand_env(v, allowed, problems) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand_env(v, allowed, problems) for v in value]
    return value


def _read_local(base: Path, relative: str) -> str:
    """Reads a file referenced from agent.yaml, refusing paths outside its folder."""
    path = (base / relative).resolve()
    if not path.is_relative_to(base.resolve()):
        raise ConfigError(
            f"{relative!r} is outside the folder containing agent.yaml.",
            "Keep skill and FAQ files next to agent.yaml.",
        )
    return path.read_text()


def load_agent(
    path: Path, env_keys: set[str] | None = None, expand_secrets: bool = True
) -> dict[str, Any]:
    """Reads agent.yaml. `env_keys` are the names ${...} may reference (from .env)."""
    if not path.exists():
        raise ConfigError(
            f"{path} not found.",
            "Run `mba init --template post-purchase` or `mba pull` to create one.",
        )
    doc = yaml.safe_load(path.read_text()) or {}
    validate_schema(doc)
    base = path.parent

    for skill in doc.get("skills", []):
        if "skill_file" in skill:
            skill["skill"] = _read_local(base, skill.pop("skill_file")).strip()
        if not SKILL_TITLE_PATTERN.match(skill.get("title", "")):
            raise ConfigError(
                f"Skill title {skill.get('title')!r} is invalid.",
                "Use up to 64 lowercase letters, numbers and dashes, not starting or ending with a dash.",
            )

    if "faqs_file" in doc:
        faqs = yaml.safe_load(_read_local(base, doc.pop("faqs_file"))) or []
        doc["faqs"] = list(doc.get("faqs", [])) + faqs

    if expand_secrets:
        problems: list[str] = []
        doc = _expand_env(doc, env_keys or set(), problems)
        if problems:
            raise ConfigError(
                "agent.yaml references variables that are not set in .env: "
                f"{', '.join(sorted(set(problems)))}.",
                "Add them to .env. Never write secret values into agent.yaml.",
            )
    return doc


def schema_validation_available() -> bool:
    try:
        import jsonschema  # noqa: F401  # optional dependency
    except ImportError:
        return False
    return True


def validate_schema(doc: dict[str, Any]) -> None:
    if not schema_validation_available():
        return
    import jsonschema

    schema = json.loads(SCHEMA_PATH.read_text())
    errors = sorted(
        jsonschema.Draft7Validator(schema).iter_errors(doc), key=lambda e: list(e.path)
    )
    if errors:
        lines = [
            f"- {'/'.join(str(p) for p in e.path) or '(root)'}: {e.message}"
            for e in errors[:10]
        ]
        raise ConfigError(
            "agent.yaml does not match schema/agent.schema.json:\n" + "\n".join(lines)
        )


def dump_yaml(doc: dict[str, Any], header: str | None = None) -> str:
    text = yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=100)
    return (header + "\n" if header else "") + text
