# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

from __future__ import annotations

from typing import Any

# Exit codes are part of the CLI contract; AGENTS.md documents them.
EXIT_OK = 0
EXIT_ERROR = 1
EXIT_INVALID_CONFIG = 2
EXIT_NEEDS_HUMAN = 3
EXIT_PLAN_STALE = 4
EXIT_GATE_FAILED = 5

_HINTS = {
    401: "The token is invalid, expired, or lacks whatsapp_business_messaging. "
    "Generate a new system user token: Business Settings > System users > Generate new token.",
    403: "The Meta Business Agent Terms of Service are not accepted for this WABA, or the "
    "token's system user is not assigned the app and WABA. Accept the terms in WhatsApp "
    "Manager > Meta Business Agent.",
    404: "No agent exists for this phone number ID, or the ID is wrong. Run `mba onboard` "
    "(after checking MBA_ENTITY_ID is the phone number ID, not the WABA ID).",
    429: "Rate limited. Wait and retry.",
}


class MBAError(Exception):
    exit_code: int = EXIT_ERROR

    def __init__(self, message: str, hint: str | None = None) -> None:
        super().__init__(message)
        self.hint = hint


class ConfigError(MBAError):
    exit_code = EXIT_INVALID_CONFIG


class NeedsHumanError(MBAError):
    exit_code = EXIT_NEEDS_HUMAN


class PlanStaleError(MBAError):
    exit_code = EXIT_PLAN_STALE


class GateError(MBAError):
    exit_code = EXIT_GATE_FAILED


class ApiError(MBAError):
    def __init__(
        self, status: int, method: str, path: str, detail: str, body: Any = None
    ) -> None:
        super().__init__(
            f"{method} {path} failed with {status}: {detail}", _HINTS.get(status)
        )
        self.status = status
        self.body = body
        if status in (401, 403):
            self.exit_code = EXIT_NEEDS_HUMAN

    @classmethod
    def from_response(cls, method: str, path: str, resp: Any) -> "ApiError":
        try:
            body = resp.json()
        except ValueError:
            body = resp.text
        detail = resp.reason
        if isinstance(body, dict):
            err = body.get("error", body)
            if isinstance(err, dict):
                detail = (
                    err.get("detail")
                    or err.get("message")
                    or err.get("title")
                    or detail
                )
        return cls(resp.status_code, method, path, str(detail), body)
