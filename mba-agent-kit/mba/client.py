# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

"""Thin HTTP client for the Meta Business Agent Platform API (X-API-Version 2.0.0).

Endpoint shapes follow the OpenAPI specs in ../openapi/. Every path is relative to
https://api.facebook.com/{entity_id}/, where entity_id is the WhatsApp Business
phone number ID (or Instagram business account ID).
"""

from __future__ import annotations

from typing import Any

import requests

from .errors import ApiError

BASE_URL = "https://api.facebook.com"
API_VERSION = "2.0.0"


class MBAClient:
    def __init__(
        self,
        token: str,
        entity_id: str,
        base_url: str = BASE_URL,
        timeout: float = 60.0,
    ) -> None:
        self._entity_id = entity_id
        self._base = f"{base_url.rstrip('/')}/{entity_id}"
        self._timeout = timeout
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {token}",
                "X-API-Version": API_VERSION,
                "Content-Type": "application/json",
                "User-Agent": "mba-agent-kit/0.1",
            }
        )

    @property
    def entity_id(self) -> str:
        return self._entity_id

    def request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        url = f"{self._base}/{path.lstrip('/')}"
        resp = self._session.request(
            method, url, json=body, params=params, timeout=self._timeout
        )
        if resp.status_code >= 400:
            raise ApiError.from_response(method, path, resp)
        if resp.status_code == 204 or not resp.content:
            return None
        return resp.json()

    # Onboarding

    def get_eligibility(self) -> dict[str, Any]:
        return self.request("GET", "agent_eligibility")

    def onboard(self) -> dict[str, Any]:
        return self.request("POST", "agent_onboarding", body={})

    # Settings

    def get_settings(self) -> list[dict[str, Any]]:
        return self.request("GET", "agent_config/settings") or []

    def put_settings(self, body: dict[str, Any]) -> dict[str, Any]:
        return self.request("PUT", "agent_config/settings", body=body)

    # Knowledge

    def get_business_info(self) -> dict[str, Any]:
        return self.request("GET", "agent_config/business_info") or {}

    def put_business_info(self, body: dict[str, Any]) -> dict[str, Any]:
        return self.request("PUT", "agent_config/business_info", body=body)

    def list_items(self, collection: str) -> list[dict[str, Any]]:
        return self.request("GET", collection) or []

    def create(self, collection: str, body: dict[str, Any]) -> dict[str, Any]:
        return self.request("POST", collection, body=body)

    def update(self, collection: str, item_id: str, body: dict[str, Any]) -> Any:
        return self.request("PUT", f"{collection}/{item_id}", body=body)

    def delete(self, collection: str, item_id: str) -> Any:
        return self.request("DELETE", f"{collection}/{item_id}")

    # Connectors

    def connector_logs(self, connector_id: str, **params: Any) -> dict[str, Any]:
        return self.request(
            "GET", f"agent_connectors/{connector_id}/logs", params=params
        )

    def run_tool(self, connector_id: str, tool_id: str, tool_input: str) -> Any:
        return self.request(
            "POST",
            f"agent_connectors/{connector_id}/tools/{tool_id}/run",
            body={"input": tool_input},
        )

    # Testing and evals

    def agent_test(
        self, user_msg: str, conversation_id: str | None = None
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"user_msg": user_msg}
        if conversation_id:
            body["conversation_id"] = conversation_id
        return self.request("POST", "agent_test", body=body)

    def eval_cases(self) -> dict[str, Any]:
        return self.request("GET", "agent-eval/cases")

    def eval_run(self, case_ids: list[str]) -> dict[str, Any]:
        return self.request(
            "POST",
            "agent-eval/run",
            body={},
            params={"eval_case_ids": ",".join(case_ids)},
        )

    def eval_status(self, job_id: str) -> dict[str, Any]:
        return self.request("GET", "agent-eval/run", params={"job_id": job_id})

    # Configuration versions

    def list_versions(self, limit: int = 20) -> dict[str, Any]:
        return self.request("GET", "agent_config/versions", params={"limit": limit})

    def active_version(self) -> dict[str, Any]:
        return self.request("GET", "agent_config/versions/active")

    def set_active_version(
        self, version_id: str, expected_active_version_id: str | None
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"version_id": version_id, "reason": "deploy"}
        if expected_active_version_id:
            body["expected_active_version_id"] = expected_active_version_id
        return self.request("PUT", "agent_config/versions/active", body=body)

    # Business events (e.g. order shipped)

    def send_event(self, to: str, event_type: str, payload: str) -> dict[str, Any]:
        return self.request(
            "POST",
            "agent_event",
            body={"to": to, "event": {"type": event_type, "payload": payload}},
        )

    def get_event(self, agent_event_id: str) -> dict[str, Any]:
        return self.request("GET", f"agent_event/{agent_event_id}")
