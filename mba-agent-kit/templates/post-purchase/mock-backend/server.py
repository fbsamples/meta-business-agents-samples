# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

"""Mock store orders API implementing the post-purchase connector contract.

Lets the agent work end to end before the business's own order API exists.
Standard library only.

    MOCK_API_KEY=<same value as ORDERS_API_KEY> python3 server.py
    cloudflared tunnel --url http://localhost:8080

cloudflared prints a public https://<random-name>.trycloudflare.com URL; set the
connector's base_url in agent.yaml to that URL + /api/v1. Keep both processes
running while you test. The URL changes every time cloudflared restarts.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any


def _d(days: int) -> str:
    return (dt.date.today() + dt.timedelta(days=days)).isoformat()


def build_orders() -> dict[str, dict[str, Any]]:
    return {
        "1001": {
            "order_number": "1001",
            "placed_at": _d(-4),
            "status": "shipped",
            "carrier": "UPS",
            "tracking_number": "1Z999AA10123456784",
            "tracking_url": "https://example.com/track/1Z999AA10123456784",
            "estimated_delivery": _d(2),
            "items": [
                {"item_id": "A1", "name": "Rain jacket (M)", "price": "89.00", "returnable": True, "return_by": _d(32)},
                {"item_id": "A2", "name": "Ceramic mug", "price": "18.00", "returnable": True, "return_by": _d(32)},
            ],
            "refunds": [],
        },
        "1002": {
            "order_number": "1002",
            "placed_at": _d(-60),
            "status": "delivered",
            "delivered_at": _d(-55),
            "carrier": "USPS",
            "tracking_number": "9400100000000000000000",
            "items": [
                {
                    "item_id": "B1",
                    "name": "Trail shoes (9)",
                    "price": "120.00",
                    "returnable": False,
                    "not_returnable_reason": "Return window closed 25 days ago",
                },
            ],
            "refunds": [
                {"refund_id": "R77", "amount": "24.00", "status": "issued", "issued_at": _d(-50), "reason": "Shipping fee refund"}
            ],
        },
        "1003": {
            "order_number": "1003",
            "placed_at": _d(-14),
            "status": "in_transit",
            "carrier": "FedEx",
            "tracking_number": "449044304137821",
            "estimated_delivery": _d(-6),
            "late": True,
            "items": [
                {"item_id": "C1", "name": "Wool socks (3 pack)", "price": "24.00", "returnable": True, "return_by": _d(30)}
            ],
            "refunds": [],
        },
    }  # fmt: skip


class Handler(BaseHTTPRequestHandler):
    orders: dict[str, dict[str, Any]] = {}
    returns: list[dict[str, Any]] = []

    def _send(self, status: int, body: object) -> None:
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _authorized(self) -> bool:
        expected = os.environ.get("MOCK_API_KEY")
        return not expected or self.headers.get("X-API-Key") == expected

    def _create_return(self, order: dict[str, Any]) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        ids = [i.strip() for i in str(body.get("item_ids", "")).split(",") if i.strip()]
        items = {i["item_id"]: i for i in order["items"]}
        bad = [i for i in ids if i not in items or not items[i]["returnable"]]
        if not ids or bad:
            return self._send(400, {"error": f"not returnable: {bad or 'no items'}"})
        ret = {
            "return_id": f"RET{len(self.returns) + 1:03d}",
            "order_number": order["order_number"],
            "item_ids": ids,
            "reason": body.get("reason"),
            "label_url": "https://example.com/labels/demo.pdf",
            "instructions": "Print the label and drop the parcel at any UPS location within 14 days.",
        }
        self.returns.append(ret)
        self._send(201, ret)

    def _route(self, method: str) -> None:
        if not self._authorized():
            return self._send(401, {"error": "invalid api key"})
        path = re.sub(r"^/api/v1", "", self.path.split("?")[0]).rstrip("/")
        if method == "GET" and path == "/orders":
            summary = [
                {k: o[k] for k in ("order_number", "placed_at", "status")}
                for o in self.orders.values()
            ]
            return self._send(200, {"orders": summary})
        m = re.fullmatch(r"/orders/(\w+)(/returns|/refunds)?", path)
        if not m or m.group(1) not in self.orders:
            return self._send(404, {"error": "order not found"})
        order, sub = self.orders[m.group(1)], m.group(2)
        if method == "GET" and not sub:
            return self._send(200, order)
        if method == "GET" and sub == "/refunds":
            refunds = {
                "order_number": order["order_number"],
                "refunds": order["refunds"],
            }
            return self._send(200, refunds)
        if method == "POST" and sub == "/returns":
            return self._create_return(order)
        self._send(405, {"error": "method not allowed"})

    def do_GET(self) -> None:
        self._route("GET")

    def do_POST(self) -> None:
        self._route("POST")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8080)
    args = ap.parse_args()
    Handler.orders = build_orders()
    print(
        f"Mock orders API on http://localhost:{args.port}/api/v1 "
        "(orders 1001 shipped, 1002 past return window, 1003 late).\n"
        f"Expose it with: cloudflared tunnel --url http://localhost:{args.port}"
    )
    HTTPServer(("127.0.0.1", args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
