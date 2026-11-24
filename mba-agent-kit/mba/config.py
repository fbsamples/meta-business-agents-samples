# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

"""Loads .env and agent.yaml into the desired-state document that plan.py diffs."""

from __future__ import annotations

import base64
import json
import os
import re
from collections.abc import Iterable, Iterator, Mapping
from pathlib import Path
from typing import Any
from urllib.parse import quote, quote_plus

import yaml

from .errors import ConfigError

ENV_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_ENV_REF_PATTERN = re.compile(r"\$\{([A-Za-z0-9_]*)\}")
_WHOLE_REF_PATTERN = re.compile(r"^\$\{([A-Za-z_][A-Za-z0-9_]*)\}$")
PLATFORM_PREFIX = "MBA_"
MIN_SECRET_LENGTH = 8
MIN_SCRUB_LENGTH = 4
MAX_CONTENT_BYTES = 1 << 20
SKILL_SUFFIXES: frozenset[str] = frozenset({".md", ".txt"})
FAQ_SUFFIXES: frozenset[str] = frozenset({".yaml", ".yml"})
SKILL_TITLE_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")
SCHEMA_PATH: Path = (
    Path(__file__).resolve().parent.parent / "schema" / "agent.schema.json"
)


class _NoAliasLoader(yaml.SafeLoader):
    """SafeLoader that refuses YAML aliases (`*name`, including `<<: *name`).

    An alias makes two places in the document the same object, so a value
    checked in one place (an auth secret) could be reused in another.
    """

    def compose_node(self, parent: Any, index: Any) -> Any:
        if self.check_event(yaml.AliasEvent):
            event = self.peek_event()
            raise ConfigError(
                f"YAML aliases are not allowed (found *{event.anchor} at line "
                f"{event.start_mark.line + 1}).",
                "Write each value out in full instead of reusing it with &anchor/*alias.",
            )
        return super().compose_node(parent, index)


def load_yaml(text: str | bytes) -> Any:
    """yaml.safe_load without aliases. Used for every YAML file the kit reads."""
    return yaml.load(text, Loader=_NoAliasLoader)  # noqa: S506 - SafeLoader subclass


def load_dotenv(path: Path) -> dict[str, str]:
    """Reads KEY=VALUE lines and returns them; os.environ is not modified.

    Only these keys may be referenced as ${NAME} from agent.yaml, so a config
    cannot pull unrelated secrets out of the user's shell environment. A key
    left blank in the file falls back to the process environment, so CI can
    inject the value while .env still declares it.
    """
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not ENV_NAME_PATTERN.match(key):
            continue
        value = value.strip().strip('"').strip("'")
        values[key] = value or os.environ.get(key, "")
    return values


def credentials(env: Mapping[str, str]) -> dict[str, str]:
    token = env.get("MBA_TOKEN") or os.environ.get("MBA_TOKEN", "")
    entity_id = env.get("MBA_ENTITY_ID") or os.environ.get("MBA_ENTITY_ID", "")
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


_AUTH_SCHEME_PATTERN = re.compile(r"^(?:Bearer|Basic|Token|Bot)\s+(\S+)$", re.I)


def _derived_secrets(secret: str) -> set[str]:
    """The secret plus the standard pieces an Authorization value carries:
    the token after its scheme, and a Basic credential's decoded pair and
    password, each also in base64 (standard and URL-safe, padded or not)."""
    derived = {secret}
    m = _AUTH_SCHEME_PATTERN.match(secret)
    if m:
        token = m.group(1)
        derived.add(token)
        try:
            pair = base64.b64decode(token, validate=True).decode()
        except ValueError:  # includes binascii.Error and UnicodeDecodeError
            pair = ""
        if ":" in pair:
            derived.update({pair, pair.split(":", 1)[1]})
    for value in list(derived):
        raw = value.encode()
        for encoded in (base64.b64encode(raw), base64.urlsafe_b64encode(raw)):
            text = encoded.decode()
            derived.update({text, text.rstrip("=")})
    return {d for d in derived if len(d) >= MIN_SCRUB_LENGTH}


class Scrubber:
    """Replaces known secret values with ***: raw, URL-encoded, JSON- and
    repr-escaped, and the derived forms of _derived_secrets. Values it was
    never given, or other encodings, are not detected."""

    def __init__(self, secrets: Iterable[str]) -> None:
        forms: set[str] = set()
        for secret in secrets:
            if len(secret) < MIN_SCRUB_LENGTH:
                continue
            for s in _derived_secrets(secret):
                forms.update(
                    {
                        s,
                        quote(s),
                        quote(s, safe=""),
                        quote_plus(s),
                        json.dumps(s)[1:-1],
                        repr(s)[1:-1],
                    }
                )
        self._forms: list[str] = sorted(forms, key=len, reverse=True)

    def __call__(self, text: str) -> str:
        for form in self._forms:
            text = text.replace(form, "***")
        return text


def scrubber_for(env: Mapping[str, str]) -> Scrubber:
    """Every value .env provides is treated as secret, plus the platform token."""
    values = [v for k, v in env.items() if k != "MBA_ENTITY_ID"]
    values.append(os.environ.get("MBA_TOKEN", ""))
    return Scrubber(values)


def _secret_leaves(doc: dict[str, Any]) -> Iterator[tuple[dict[str, Any], str, str]]:
    """The only places ${NAME} may appear: typed credential fields of auth_config.

    OAuth client_id is public, so it may also be written literally.
    """
    for i, conn in enumerate(doc.get("connectors") or []):
        auth = conn.get("auth_config") if isinstance(conn, dict) else None
        if not isinstance(auth, dict):
            continue
        api_key = auth.get("api_key")
        if isinstance(api_key, dict):
            for group in ("headers", "query_params", "body_params"):
                for j, param in enumerate(api_key.get(group) or []):
                    if isinstance(param, dict) and "value" in param:
                        where = (
                            f"connectors[{i}].auth_config.api_key.{group}[{j}].value"
                        )
                        yield param, "value", where
        oauth = auth.get("oauth2_client_credentials")
        if isinstance(oauth, dict):
            for field in ("client_id", "client_secret"):
                if field in oauth:
                    where = (
                        f"connectors[{i}].auth_config.oauth2_client_credentials.{field}"
                    )
                    yield oauth, field, where


def secret_detector(env: Mapping[str, str]) -> Scrubber:
    """Matches secret material that must never be sent as agent content."""
    values = [v for k, v in env.items() if k != "MBA_ENTITY_ID"]
    values.append(os.environ.get("MBA_TOKEN", ""))
    return Scrubber(v for v in values if len(v) >= MIN_SECRET_LENGTH)


def contains_secret(text: str, detector: Scrubber) -> bool:
    return detector(text) != text


def _stray_refs(
    value: Any,
    where: str,
    leaves: set[str],
    detector: Scrubber,
    problems: list[str],
    seen: set[int],
) -> None:
    """Flags ${...} and secret values anywhere except the auth leaves, which
    are identified by their full path, never by object identity."""
    if isinstance(value, (dict, list)):
        if id(value) in seen:
            problems.append(f"{where}: reuses another part of the document")
            return
        seen.add(id(value))
    if isinstance(value, dict):
        for k, v in value.items():
            path = f"{where}.{k}" if where else str(k)
            if path in leaves:
                continue
            _stray_refs(v, path, leaves, detector, problems, seen)
    elif isinstance(value, list):
        for i, v in enumerate(value):
            _stray_refs(v, f"{where}[{i}]", leaves, detector, problems, seen)
    elif isinstance(value, str):
        if _ENV_REF_PATTERN.search(value):
            problems.append(
                f"{where}: ${{...}} is only allowed as a connector auth_config secret value"
            )
        if contains_secret(value, detector):
            problems.append(f"{where}: contains the value of a secret from .env")


def _resolve_secrets(doc: dict[str, Any], env: Mapping[str, str], expand: bool) -> None:
    leaves = list(_secret_leaves(doc))
    problems: list[str] = []
    leaf_paths = {where for _, _, where in leaves}
    _stray_refs(doc, "", leaf_paths, secret_detector(env), problems, set())
    if problems:
        # Resolve nothing while any part of the document is in doubt.
        leaves = []
    for container, key, where in leaves:
        value = container[key]
        public = key == "client_id"
        m = _WHOLE_REF_PATTERN.match(value) if isinstance(value, str) else None
        if not m:
            if not (public and isinstance(value, str) and value):
                problems.append(
                    f"{where}: must be exactly ${{ENV_VAR}}; put the secret in .env"
                )
            continue
        name = m.group(1)
        if name.startswith(PLATFORM_PREFIX):
            problems.append(f"{where}: {name} is a platform credential")
        elif not env.get(name):
            problems.append(f"{where}: {name} is not set in .env")
        elif not public and len(env[name]) < MIN_SECRET_LENGTH:
            problems.append(
                f"{where}: the value of {name} is shorter than "
                f"{MIN_SECRET_LENGTH} characters; use a longer, random secret"
            )
        elif expand:
            container[key] = env[name]
    if problems:
        raise ConfigError(
            "agent.yaml secret references are invalid:\n"
            + "\n".join(f"- {p}" for p in problems),
            "Reference secrets only as auth_config values like ${ORDERS_API_KEY}, "
            "declared in .env. MBA_* variables can never be referenced.",
        )


FileId = tuple[int, int]


def file_ids(paths: Iterable[Path]) -> frozenset[FileId]:
    """Filesystem identities (device, inode) of existing files, so hard links
    and other names for the same file are recognized."""
    ids = set()
    for p in paths:
        try:
            st = os.stat(p)
        except OSError:
            continue
        ids.add((st.st_dev, st.st_ino))
    return frozenset(ids)


def read_content(
    base: Path,
    relative: Any,
    suffixes: frozenset[str],
    forbidden: frozenset[FileId] = frozenset(),
) -> str:
    """Reads a skill or FAQ file referenced from agent.yaml.

    It must be a regular, non-hidden file with an allowed extension, inside
    the agent.yaml folder, with no symlink anywhere on its path, and not the
    credentials file (`forbidden`) under any name.
    """
    if not isinstance(relative, str) or not relative:
        raise ConfigError(f"Invalid content file reference {relative!r}.")
    rel = Path(relative)
    hint = "Keep skill (.md, .txt) and FAQ (.yaml) files in the agent.yaml folder."
    if rel.is_absolute() or ".." in rel.parts:
        raise ConfigError(f"{relative!r} is outside the agent.yaml folder.", hint)
    if any(part.startswith(".") for part in rel.parts):
        raise ConfigError(f"{relative!r} is a hidden file or folder.", hint)
    if rel.suffix.lower() not in suffixes:
        raise ConfigError(
            f"{relative!r} must have one of these extensions: "
            f"{', '.join(sorted(suffixes))}.",
            hint,
        )
    path = base
    for part in rel.parts:
        path = path / part
        if path.is_symlink():
            raise ConfigError(f"{relative!r} goes through a symlink.", hint)
    if not path.is_file() or not path.resolve().is_relative_to(base.resolve()):
        raise ConfigError(f"{relative!r} is not a regular file in the folder.", hint)
    st = path.stat()
    if (st.st_dev, st.st_ino) in forbidden:
        raise ConfigError(f"{relative!r} is the credentials file.", hint)
    if st.st_size > MAX_CONTENT_BYTES:
        raise ConfigError(f"{relative!r} is larger than 1 MiB.")
    return path.read_text(encoding="utf-8")


def _load_faqs(
    base: Path, relative: Any, forbidden: frozenset[FileId]
) -> list[dict[str, Any]]:
    faqs = load_yaml(read_content(base, relative, FAQ_SUFFIXES, forbidden)) or []
    if not isinstance(faqs, list) or not all(
        isinstance(f, dict)
        and isinstance(f.get("question"), str)
        and isinstance(f.get("answer"), str)
        for f in faqs
    ):
        raise ConfigError(
            f"{relative!r} must be a list of entries with string question and answer."
        )
    return faqs


def load_agent(
    path: Path,
    env: Mapping[str, str] | None = None,
    expand_secrets: bool = True,
    credential_files: Iterable[Path] = (),
) -> dict[str, Any]:
    """Reads agent.yaml. `env` holds the .env values ${...} may reference;
    `credential_files` (the .env in use) can never be read as content."""
    forbidden = file_ids(credential_files)
    if not path.exists():
        raise ConfigError(
            f"{path} not found.",
            "Run `mba init --template post-purchase` or `mba pull` to create one.",
        )
    doc = load_yaml(path.read_text()) or {}
    if not isinstance(doc, dict):
        raise ConfigError(f"{path} must be a YAML mapping.")
    validate_schema(doc)
    base = path.parent

    for skill in doc.get("skills", []):
        if "skill_file" in skill:
            content = read_content(
                base, skill.pop("skill_file"), SKILL_SUFFIXES, forbidden
            )
            skill["skill"] = content.strip()
        if not SKILL_TITLE_PATTERN.match(skill.get("title", "")):
            raise ConfigError(
                f"Skill title {skill.get('title')!r} is invalid.",
                "Use up to 64 lowercase letters, numbers and dashes, not starting or ending with a dash.",
            )

    if "faqs_file" in doc:
        faqs = _load_faqs(base, doc.pop("faqs_file"), forbidden)
        doc["faqs"] = list(doc.get("faqs", [])) + faqs

    _resolve_secrets(doc, env or {}, expand_secrets)
    return doc


def schema_validation_available() -> bool:
    try:
        import jsonschema  # noqa: F401  # optional dependency
    except ImportError:
        return False
    return True


def validate_schema(doc: dict[str, Any]) -> None:
    if not schema_validation_available():
        raise ConfigError(
            "jsonschema is not installed, so agent.yaml cannot be validated.",
            'Install the kit with its dependencies: pip install -e ".".',
        )
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
