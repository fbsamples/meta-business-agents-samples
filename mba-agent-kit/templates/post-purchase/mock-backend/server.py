# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

"""Mock store orders API implementing the post-purchase connector contract.

Lets the agent work end to end before the business's own order API exists.
Standard library only. Serves synthetic demo data only: never load real orders
or real customer data into it.

Usage::

    MOCK_API_KEY=<value of ORDERS_API_KEY> python3 server.py
    cloudflared tunnel --url http://localhost:8080

MOCK_API_KEY is required; the server exits if it is not set. Every request must
send it, exactly once, in the X-API-Key header; anything else gets 401.

The server binds to 127.0.0.1 by default. cloudflared reaches it there, so the
default is all a tunnel needs; binding any other address requires
--allow-non-loopback.

Contract (base path /api/v1, JSON responses, errors as {"error": "..."}):

    GET  /api/v1/orders?customer_phone=<E.164>
    GET  /api/v1/orders/{order_number}?customer_phone=<E.164>
    GET  /api/v1/orders/{order_number}/refunds?customer_phone=<E.164>
    POST /api/v1/orders/{order_number}/returns
         Content-Type: application/json
         {"item_ids": "A1,A2", "reason": "...", "customer_phone": "<E.164>"}

- customer_phone identifies the customer (the connector binds it with the
  WHATSAPP_PHONE_NUMBER macro). It goes in the query string for GET and in the
  JSON body for POST, exactly once: a second copy, in the same place or the
  other one, is rejected with 400. Percent-encoding is decoded (%2B is "+"); a
  literal "+" stays "+".
- A customer sees and changes only their own orders. Another customer's order
  answers 404, as if it did not exist, and is never modified.
- POST bodies need Content-Length and at most 16 KiB; invalid JSON, a non-object
  body or wrong field types get 400. A client that stalls for 10 seconds
  mid-request is dropped (408 if it stalled while sending the body).

Security notes (demo only, not production code):
- customer_phone scopes results to a customer; it does not authenticate them.
  Authentication is the shared demo key in MOCK_API_KEY / X-API-Key.
- Never expose this server with real customer data.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hmac
import ipaddress
import json
import os
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from email.message import Message
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, BinaryIO
from urllib.parse import unquote

API_PREFIX = "/api/v1"
MAX_BODY_BYTES = 16 * 1024
MAX_ITEMS_PER_RETURN = 20
MAX_REASON_CHARS = 500
SOCKET_TIMEOUT_SECONDS = 10
PHONE_PATTERN = r"\+[1-9][0-9]{6,14}"
ID_PATTERN = r"[A-Za-z0-9_-]{1,32}"

# Synthetic demo phone numbers that own the orders. In a real integration the
# WHATSAPP_PHONE_NUMBER macro provides the caller's E.164 number.
DEMO_PHONE_ALICE = "+15550001001"
DEMO_PHONE_BOB = "+15550002002"


class RequestError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


def _d(days: int) -> str:
    return (dt.date.today() + dt.timedelta(days=days)).isoformat()


def build_orders() -> dict[str, dict[str, Any]]:
    return {
        "1001": {
            "owner_phone": DEMO_PHONE_ALICE,
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
            "owner_phone": DEMO_PHONE_BOB,
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
            "owner_phone": DEMO_PHONE_ALICE,
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


@dataclass
class Store:
    orders: dict[str, dict[str, Any]] = field(default_factory=build_orders)
    returns: list[dict[str, Any]] = field(default_factory=list)


def _fullmatch(pattern: str, value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(pattern, value) is not None


def _decode(component: str) -> str:
    try:
        return unquote(component, errors="strict")
    except UnicodeDecodeError:
        raise RequestError(400, "invalid percent-encoding in URL") from None


def parse_query(query: str) -> dict[str, list[str]]:
    """Percent-decode a query string. "+" is kept literally, never read as a space."""
    values: dict[str, list[str]] = {}
    for part in query.split("&"):
        if not part:
            continue
        name, _, value = part.partition("=")
        values.setdefault(_decode(name), []).append(_decode(value))
    return values


def parse_path(path: str) -> list[str]:
    """Split a request path under API_PREFIX into percent-decoded segments."""
    if path != API_PREFIX and not path.startswith(API_PREFIX + "/"):
        raise RequestError(404, "not found")
    rest = path[len(API_PREFIX) :].strip("/")
    raw = rest.split("/") if rest else []
    if any(not segment for segment in raw):
        raise RequestError(404, "not found")
    return [_decode(segment) for segment in raw]


def check_api_key(headers: Message, expected: str) -> None:
    supplied = headers.get_all("X-API-Key") or []
    if not expected or len(supplied) != 1:
        raise RequestError(401, "invalid api key")
    if not hmac.compare_digest(supplied[0].encode(), expected.encode()):
        raise RequestError(401, "invalid api key")


def _content_length(headers: Message) -> int:
    if headers.get("Transfer-Encoding"):
        raise RequestError(
            411, "Content-Length is required; chunked bodies are not supported"
        )
    lengths = headers.get_all("Content-Length") or []
    if not lengths:
        raise RequestError(411, "Content-Length is required")
    raw = lengths[0].strip()
    if len(lengths) != 1 or not (raw.isascii() and raw.isdigit()):
        raise RequestError(400, "invalid Content-Length")
    length = int(raw)
    if length > MAX_BODY_BYTES:
        raise RequestError(413, f"request body exceeds {MAX_BODY_BYTES} bytes")
    return length


def _require_json_content_type(headers: Message) -> None:
    content_types = headers.get_all("Content-Type") or []
    if len(content_types) > 1:
        raise RequestError(400, "Content-Type must be sent exactly once")
    media_type = content_types[0].split(";", 1)[0] if content_types else ""
    if media_type.strip().lower() != "application/json":
        raise RequestError(415, "Content-Type must be application/json")


def read_json_body(headers: Message, rfile: BinaryIO) -> dict[str, Any]:
    length = _content_length(headers)
    _require_json_content_type(headers)
    try:
        data = rfile.read(length)
    except TimeoutError:
        raise RequestError(408, "timed out reading the request body") from None
    if len(data) != length:
        raise RequestError(400, "request body is shorter than Content-Length")
    try:
        body = json.loads(
            data.decode("utf-8"),
            object_pairs_hook=_unique_keys,
            parse_constant=_reject_constant,
        )
    except (ValueError, RecursionError):
        raise RequestError(
            400, "request body must be valid JSON without duplicate keys"
        ) from None
    if not isinstance(body, dict):
        raise RequestError(400, "request body must be a JSON object")
    return body


def _unique_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = dict(pairs)
    if len(result) != len(pairs):
        raise ValueError("duplicate key")
    return result


def _reject_constant(name: str) -> None:
    raise ValueError(name)


def _phone(value: object) -> str:
    if isinstance(value, str) and _fullmatch(PHONE_PATTERN, value):
        return value
    raise RequestError(
        400, "customer_phone must be an E.164 number such as +15550001001"
    )


def _query_phone(query: dict[str, list[str]]) -> str:
    values = query.get("customer_phone", [])
    if not values:
        raise RequestError(400, "customer_phone is required")
    if len(values) > 1:
        raise RequestError(400, "customer_phone must be sent exactly once")
    return _phone(values[0])


def _body_phone(query: dict[str, list[str]], body: dict[str, Any]) -> str:
    if "customer_phone" in query:
        raise RequestError(
            400, "customer_phone must be sent exactly once, in the JSON body"
        )
    if "customer_phone" not in body:
        raise RequestError(400, "customer_phone is required")
    return _phone(body["customer_phone"])


def _owned_order(store: Store, order_number: str, customer: str) -> dict[str, Any]:
    order = store.orders.get(order_number)
    # Another customer's order is reported as missing so its existence does not leak.
    if order is None or order["owner_phone"] != customer:
        raise RequestError(404, "order not found")
    return order


def _public(order: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in order.items() if k != "owner_phone"}


def _list_orders(store: Store, customer: str) -> dict[str, Any]:
    owned = [o for _, o in sorted(store.orders.items()) if o["owner_phone"] == customer]
    keys = ("order_number", "placed_at", "status")
    return {"orders": [{k: o[k] for k in keys} for o in owned]}


def _item_ids(value: object) -> list[str]:
    if isinstance(value, str):
        ids = [i.strip() for i in value.split(",") if i.strip()]
    elif isinstance(value, list) and all(isinstance(i, str) for i in value):
        ids = [i.strip() for i in value if i.strip()]
    else:
        raise RequestError(
            400, "item_ids must be a comma-separated string or a list of strings"
        )
    if not ids:
        raise RequestError(400, "item_ids is required")
    if len(ids) > MAX_ITEMS_PER_RETURN:
        raise RequestError(400, f"at most {MAX_ITEMS_PER_RETURN} item_ids per return")
    if not all(_fullmatch(ID_PATTERN, i) for i in ids):
        raise RequestError(400, "item_ids contains an invalid item id")
    return list(dict.fromkeys(ids))


def _reason(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RequestError(400, "reason is required and must be a string")
    if len(value) > MAX_REASON_CHARS:
        raise RequestError(400, f"reason must be at most {MAX_REASON_CHARS} characters")
    return value.strip()


def _create_return(
    order: dict[str, Any], body: dict[str, Any], store: Store
) -> dict[str, Any]:
    ids = _item_ids(body.get("item_ids"))
    reason = _reason(body.get("reason"))
    items = {i["item_id"]: i for i in order["items"]}
    unknown = [i for i in ids if i not in items]
    if unknown:
        raise RequestError(400, f"unknown item ids on this order: {', '.join(unknown)}")
    blocked = [i for i in ids if not items[i]["returnable"]]
    if blocked:
        raise RequestError(400, f"not returnable: {', '.join(blocked)}")
    started = [i for i in ids if items[i].get("return_id")]
    if started:
        raise RequestError(409, f"a return already exists for: {', '.join(started)}")
    ret = {
        "return_id": f"RET{len(store.returns) + 1:03d}",
        "order_number": order["order_number"],
        "item_ids": ids,
        "reason": reason,
        "label_url": "https://example.com/labels/demo.pdf",
        "instructions": "Print the label and drop the parcel at any UPS location within 14 days.",
    }
    for i in ids:
        items[i]["return_id"] = ret["return_id"]
    store.returns.append(ret)
    return ret


def _route(
    store: Store,
    method: str,
    segments: list[str],
    query: dict[str, list[str]],
    body: Callable[[], dict[str, Any]],
) -> tuple[int, dict[str, Any]]:
    if not segments or segments[0] != "orders" or len(segments) > 3:
        raise RequestError(404, "not found")
    sub = segments[2] if len(segments) == 3 else None
    if sub not in (None, "returns", "refunds"):
        raise RequestError(404, "not found")
    allowed = "POST" if sub == "returns" else "GET"
    if method != allowed:
        raise RequestError(405, "method not allowed")
    if len(segments) == 1:
        return 200, _list_orders(store, _query_phone(query))
    order_number = segments[1]
    if not _fullmatch(ID_PATTERN, order_number):
        raise RequestError(400, "invalid order_number")
    if sub == "returns":
        payload = body()
        order = _owned_order(store, order_number, _body_phone(query, payload))
        return 201, _create_return(order, payload, store)
    order = _owned_order(store, order_number, _query_phone(query))
    if sub == "refunds":
        return 200, {"order_number": order["order_number"], "refunds": order["refunds"]}
    return 200, _public(order)


def handle(
    store: Store,
    api_key: str,
    method: str,
    target: str,
    headers: Message,
    rfile: BinaryIO,
) -> tuple[int, dict[str, Any]]:
    """Answer one request without touching the network: (status, JSON body)."""
    try:
        check_api_key(headers, api_key)
        path, _, query = target.split("#", 1)[0].partition("?")
        return _route(
            store,
            method,
            parse_path(path),
            parse_query(query),
            lambda: read_json_body(headers, rfile),
        )
    except RequestError as e:
        return e.status, {"error": e.message}


class Handler(BaseHTTPRequestHandler):
    server_version = "mba-mock-orders/1"
    sys_version = ""
    # A client that stalls mid-request (e.g. a body shorter than its
    # Content-Length) is dropped instead of holding the single-threaded server.
    timeout = SOCKET_TIMEOUT_SECONDS
    store: Store
    api_key: str = ""

    def _dispatch(self) -> None:
        status, body = handle(
            self.store, self.api_key, self.command, self.path, self.headers, self.rfile
        )
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    do_GET = _dispatch
    do_POST = _dispatch
    do_PUT = _dispatch
    do_PATCH = _dispatch
    do_DELETE = _dispatch

    def log_request(self, code: int | str = "-", size: int | str = "-") -> None:
        # Keep customer_phone out of the log: log the path without its query string.
        self.log_message("%s %s %s", self.command, self.path.split("?", 1)[0], code)


def make_handler(store: Store, api_key: str) -> type[Handler]:
    return type("ConfiguredHandler", (Handler,), {"store": store, "api_key": api_key})


def _is_loopback(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Synthetic mock orders API for the post-purchase template."
    )
    ap.add_argument(
        "--host", default="127.0.0.1", help="address to bind (default 127.0.0.1)"
    )
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument(
        "--allow-non-loopback",
        action="store_true",
        help="allow binding an address other than loopback (not needed for cloudflared)",
    )
    args = ap.parse_args()
    api_key = os.environ.get("MOCK_API_KEY", "")
    if not api_key.strip():
        sys.exit(
            "Error: MOCK_API_KEY environment variable must be set.\n"
            "Example: MOCK_API_KEY=<value of ORDERS_API_KEY> python3 server.py"
        )
    if not _is_loopback(args.host) and not args.allow_non_loopback:
        sys.exit(
            f"Error: refusing to bind {args.host}; pass --allow-non-loopback to do so."
        )
    handler = make_handler(Store(), api_key)
    print(
        f"Mock orders API (synthetic data only) on http://{args.host}:{args.port}{API_PREFIX} "
        "(orders 1001 shipped, 1002 past return window, 1003 late).\n"
        f"Expose it with: cloudflared tunnel --url http://localhost:{args.port}"
    )
    HTTPServer((args.host, args.port), handler).serve_forever()


if __name__ == "__main__":
    main()
