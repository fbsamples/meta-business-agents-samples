# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

from __future__ import annotations

import copy
import importlib.util
import io
import json
import sys
import unittest
from http.client import parse_headers
from pathlib import Path
from typing import Any

import mba

SERVER_RELPATH = Path("templates/post-purchase/mock-backend/server.py")
KEY = "synthetic-demo-key"
ALICE = "+15550001001"
BOB = "+15550002002"
ALICE_Q = "customer_phone=%2B15550001001"
BOB_Q = "customer_phone=%2B15550002002"


def kit_root(marker: Path) -> Path:
    """The kit directory holding the packaged resources, in Buck and source layouts."""
    pkg = Path(mba.__file__)
    candidates = (
        pkg.parent.parent,
        pkg.resolve().parent.parent,
        Path(__file__).resolve().parent.parent,
    )
    for root in candidates:
        if (root / marker).is_file():
            return root
    raise FileNotFoundError(f"{marker} not found under {[str(c) for c in candidates]}")


def load_server() -> Any:
    path = kit_root(SERVER_RELPATH) / SERVER_RELPATH
    spec = importlib.util.spec_from_file_location("mba_mock_backend_server", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


server: Any = None


def setUpModule() -> None:
    global server
    server = load_server()


class StallingStream(io.BytesIO):
    """Like a socket with a read timeout: reading past the sent bytes times out."""

    def read(self, size: int | None = -1) -> bytes:
        remaining = len(self.getbuffer()) - self.tell()
        if size is not None and size > remaining:
            raise TimeoutError("timed out")
        return super().read(size)


class FakeConnection:
    """A socket stand-in: the handler reads `raw` and writes into `sent`."""

    def __init__(self, raw: bytes) -> None:
        self._rfile: io.BytesIO = StallingStream(raw)
        self.sent = bytearray()
        self.timeouts: list[float | None] = []

    def makefile(self, mode: str, *args: object) -> io.BytesIO:
        return self._rfile

    def settimeout(self, value: float | None) -> None:
        self.timeouts.append(value)

    def sendall(self, data: bytes) -> None:
        self.sent += data


class MockBackendTest(unittest.TestCase):
    def setUp(self) -> None:
        self.store = server.Store()

    def call(
        self,
        method: str,
        target: str,
        body: Any = None,
        *,
        key: str | None = KEY,
        raw_body: bytes | None = None,
        extra_headers: str = "",
    ) -> tuple[int, dict[str, Any]]:
        data = raw_body if raw_body is not None else b""
        if body is not None:
            data = json.dumps(body).encode()
        lines = []
        if key is not None:
            lines.append(f"X-API-Key: {key}")
        if method == "POST":
            lines += ["Content-Type: application/json", f"Content-Length: {len(data)}"]
        head = "".join(f"{line}\r\n" for line in lines) + extra_headers + "\r\n"
        headers = parse_headers(io.BytesIO(head.encode("latin-1")))
        return server.handle(self.store, KEY, method, target, headers, io.BytesIO(data))

    def post_return(
        self, order: str, phone: str = ALICE, **fields: Any
    ) -> tuple[int, dict[str, Any]]:
        body = {
            "item_ids": "A1",
            "reason": "too small",
            "customer_phone": phone,
            **fields,
        }
        return self.call("POST", f"/api/v1/orders/{order}/returns", body)


class AuthTest(MockBackendTest):
    def test_missing_key(self) -> None:
        status, body = self.call("GET", f"/api/v1/orders?{ALICE_Q}", key=None)
        self.assertEqual((status, body), (401, {"error": "invalid api key"}))

    def test_wrong_key(self) -> None:
        status, _ = self.call("GET", f"/api/v1/orders?{ALICE_Q}", key="wrong")
        self.assertEqual(status, 401)

    def test_duplicate_key_header(self) -> None:
        status, _ = self.call(
            "GET", f"/api/v1/orders?{ALICE_Q}", extra_headers=f"X-API-Key: {KEY}\r\n"
        )
        self.assertEqual(status, 401)

    def test_server_without_key_fails_closed(self) -> None:
        headers = parse_headers(io.BytesIO(b"X-API-Key: \r\n\r\n"))
        status, _ = server.handle(
            self.store, "", "GET", f"/api/v1/orders?{ALICE_Q}", headers, io.BytesIO()
        )
        self.assertEqual(status, 401)

    def test_auth_checked_before_routing(self) -> None:
        status, _ = self.call("GET", "/nope", key="wrong")
        self.assertEqual(status, 401)


class PhoneTest(MockBackendTest):
    def test_percent_encoded_plus(self) -> None:
        status, body = self.call("GET", f"/api/v1/orders?{ALICE_Q}")
        self.assertEqual(status, 200)
        self.assertEqual([o["order_number"] for o in body["orders"]], ["1001", "1003"])

    def test_literal_plus_is_not_a_space(self) -> None:
        status, body = self.call("GET", f"/api/v1/orders/1001?customer_phone={ALICE}")
        self.assertEqual(status, 200)
        self.assertEqual(body["order_number"], "1001")
        self.assertNotIn("owner_phone", body)

    def test_missing_phone(self) -> None:
        status, body = self.call("GET", "/api/v1/orders")
        self.assertEqual((status, body), (400, {"error": "customer_phone is required"}))

    def test_duplicate_query_phone(self) -> None:
        for second in (ALICE_Q, BOB_Q):
            with self.subTest(second=second):
                status, _ = self.call("GET", f"/api/v1/orders/1001?{ALICE_Q}&{second}")
                self.assertEqual(status, 400)

    def test_invalid_phone(self) -> None:
        for value in (
            "15550001001",
            "%2B1555",
            "%20%2B15550001001",
            "%2B1555000100x",
            "%FF",
            "%2B1555000100%",
            "%2B1555000100%2",
            "%zz15550001001",
        ):
            with self.subTest(value=value):
                status, _ = self.call("GET", f"/api/v1/orders?customer_phone={value}")
                self.assertEqual(status, 400)

    def test_return_phone_in_query_and_body_is_ambiguous(self) -> None:
        before = copy.deepcopy(self.store.orders)
        body = {"item_ids": "A1", "reason": "too small", "customer_phone": ALICE}
        status, _ = self.call("POST", f"/api/v1/orders/1001/returns?{ALICE_Q}", body)
        self.assertEqual(status, 400)
        self.assertEqual(self.store.orders, before)

    def test_return_duplicate_body_phone_key(self) -> None:
        raw = f'{{"item_ids": "A1", "reason": "x", "customer_phone": "{BOB}", "customer_phone": "{ALICE}"}}'
        status, body = self.call(
            "POST", "/api/v1/orders/1001/returns", raw_body=raw.encode()
        )
        self.assertEqual(status, 400)
        self.assertIn("duplicate", body["error"])
        self.assertEqual(self.store.returns, [])

    def test_return_without_body_phone(self) -> None:
        status, body = self.call(
            "POST", "/api/v1/orders/1001/returns", {"item_ids": "A1", "reason": "x"}
        )
        self.assertEqual((status, body), (400, {"error": "customer_phone is required"}))

    def test_return_non_string_phone(self) -> None:
        status, _ = self.post_return("1001", customer_phone=15550001001)
        self.assertEqual(status, 400)


class OwnershipTest(MockBackendTest):
    def test_list_is_scoped(self) -> None:
        _, alice = self.call("GET", f"/api/v1/orders?{ALICE_Q}")
        _, bob = self.call("GET", f"/api/v1/orders?{BOB_Q}")
        _, nobody = self.call("GET", "/api/v1/orders?customer_phone=%2B15559999999")
        self.assertEqual([o["order_number"] for o in alice["orders"]], ["1001", "1003"])
        self.assertEqual([o["order_number"] for o in bob["orders"]], ["1002"])
        self.assertEqual(nobody, {"orders": []})
        self.assertNotIn("owner_phone", json.dumps(alice))

    def test_lookup_other_customer(self) -> None:
        status, body = self.call("GET", f"/api/v1/orders/1002?{ALICE_Q}")
        self.assertEqual((status, body), (404, {"error": "order not found"}))

    def test_refunds_other_customer(self) -> None:
        status, _ = self.call("GET", f"/api/v1/orders/1002/refunds?{ALICE_Q}")
        self.assertEqual(status, 404)
        status, body = self.call("GET", f"/api/v1/orders/1002/refunds?{BOB_Q}")
        self.assertEqual(status, 200)
        self.assertEqual(body["refunds"][0]["refund_id"], "R77")

    def test_return_other_customer_does_not_mutate(self) -> None:
        before = copy.deepcopy(self.store.orders)
        status, body = self.post_return("1001", phone=BOB)
        self.assertEqual((status, body), (404, {"error": "order not found"}))
        self.assertEqual(self.store.orders, before)
        self.assertEqual(self.store.returns, [])

    def test_unknown_order_matches_unowned(self) -> None:
        self.assertEqual(
            self.call("GET", f"/api/v1/orders/9999?{ALICE_Q}"),
            self.call("GET", f"/api/v1/orders/1002?{ALICE_Q}"),
        )


class ReturnTest(MockBackendTest):
    def test_success_body(self) -> None:
        status, body = self.post_return(
            "1001", item_ids="A1, A2,A1", reason=" too small "
        )
        self.assertEqual(status, 201)
        self.assertEqual(
            body,
            {
                "return_id": "RET001",
                "order_number": "1001",
                "item_ids": ["A1", "A2"],
                "reason": "too small",
                "label_url": "https://example.com/labels/demo.pdf",
                "instructions": "Print the label and drop the parcel at any UPS location within 14 days.",
            },
        )
        self.assertEqual(self.store.returns, [body])
        self.assertEqual(
            [i["return_id"] for i in self.store.orders["1001"]["items"]],
            ["RET001", "RET001"],
        )

    def test_list_item_ids(self) -> None:
        status, body = self.post_return("1001", item_ids=["A2"])
        self.assertEqual(status, 201)
        self.assertEqual(body["item_ids"], ["A2"])

    def test_second_return_conflicts(self) -> None:
        self.assertEqual(self.post_return("1001")[0], 201)
        status, _ = self.post_return("1001")
        self.assertEqual(status, 409)
        self.assertEqual(len(self.store.returns), 1)

    def test_not_returnable(self) -> None:
        status, body = self.post_return("1002", phone=BOB, item_ids="B1")
        self.assertEqual((status, body), (400, {"error": "not returnable: B1"}))

    def test_unknown_item(self) -> None:
        status, body = self.post_return("1001", item_ids="A1,Z9")
        self.assertEqual(status, 400)
        self.assertIn("Z9", body["error"])
        self.assertEqual(self.store.returns, [])

    def test_invalid_fields(self) -> None:
        cases: list[dict[str, Any]] = [
            {"item_ids": ""},
            {"item_ids": 7},
            {"item_ids": [1]},
            {"item_ids": "<script>"},
            {"item_ids": ",".join(f"I{n}" for n in range(21))},
            {"reason": ""},
            {"reason": ["x"]},
            {"reason": "x" * 501},
        ]
        for fields in cases:
            with self.subTest(fields=fields):
                status, body = self.post_return("1001", **fields)
                self.assertEqual(status, 400)
                self.assertLess(len(body["error"]), 200)
        self.assertEqual(self.store.returns, [])


class BodyTest(MockBackendTest):
    def test_malformed_json(self) -> None:
        for raw in (b"{", b"not json", b"\xff\xfe", b'{"reason": NaN}', b"[" * 5000):
            with self.subTest(raw=raw[:10]):
                status, body = self.call(
                    "POST", "/api/v1/orders/1001/returns", raw_body=raw
                )
                self.assertEqual(status, 400)
                self.assertIn("valid JSON", body["error"])

    def test_non_object_json(self) -> None:
        for value in ([], "x", 1, None):
            with self.subTest(value=value):
                raw = json.dumps(value).encode()
                status, body = self.call(
                    "POST", "/api/v1/orders/1001/returns", raw_body=raw
                )
                self.assertEqual(
                    (status, body),
                    (400, {"error": "request body must be a JSON object"}),
                )

    def test_oversized_body_is_not_read(self) -> None:
        head = f"X-API-Key: {KEY}\r\nContent-Type: application/json\r\nContent-Length: {16 * 1024 + 1}\r\n\r\n"
        headers = parse_headers(io.BytesIO(head.encode()))
        rfile = io.BytesIO(b"x" * (16 * 1024 + 1))
        status, _ = server.handle(
            self.store, KEY, "POST", "/api/v1/orders/1001/returns", headers, rfile
        )
        self.assertEqual(status, 413)
        self.assertEqual(rfile.tell(), 0)

    def test_content_length_problems(self) -> None:
        cases = {
            "": 411,
            "Content-Length: -1\r\n": 400,
            "Content-Length: 12abc\r\n": 400,
            "Content-Length: 2\r\nContent-Length: 2\r\n": 400,
            "Content-Length: 50\r\n": 400,
            "Transfer-Encoding: chunked\r\n": 411,
        }
        for extra, expected in cases.items():
            with self.subTest(extra=extra):
                head = (
                    f"X-API-Key: {KEY}\r\nContent-Type: application/json\r\n{extra}\r\n"
                )
                headers = parse_headers(io.BytesIO(head.encode()))
                status, _ = server.handle(
                    self.store,
                    KEY,
                    "POST",
                    "/api/v1/orders/1001/returns",
                    headers,
                    io.BytesIO(b"{}"),
                )
                self.assertEqual(status, expected)

    def test_wrong_content_type(self) -> None:
        for content_type, expected in (
            ("Content-Type: text/plain\r\n", 415),
            ("", 415),
            ("Content-Type: application/json\r\nContent-Type: text/plain\r\n", 400),
        ):
            with self.subTest(content_type=content_type):
                head = f"X-API-Key: {KEY}\r\n{content_type}Content-Length: 2\r\n\r\n"
                headers = parse_headers(io.BytesIO(head.encode()))
                status, _ = server.handle(
                    self.store,
                    KEY,
                    "POST",
                    "/api/v1/orders/1001/returns",
                    headers,
                    io.BytesIO(b"{}"),
                )
                self.assertEqual(status, expected)

    def test_body_read_timeout(self) -> None:
        head = f"X-API-Key: {KEY}\r\nContent-Type: application/json\r\nContent-Length: 10\r\n\r\n"
        headers = parse_headers(io.BytesIO(head.encode()))
        status, body = server.handle(
            self.store,
            KEY,
            "POST",
            "/api/v1/orders/1001/returns",
            headers,
            StallingStream(b"{}"),
        )
        self.assertEqual(
            (status, body), (408, {"error": "timed out reading the request body"})
        )
        self.assertEqual(self.store.returns, [])


class RoutingTest(MockBackendTest):
    def test_order_number_injection(self) -> None:
        for order in (
            "1001%2F..%2F1002",
            "..",
            "%2E%2E",
            "1001%00",
            "a" * 33,
            "%E2%82%AC",
            "%zz",
            "100%",
            "10%2",
            "%C3",
        ):
            with self.subTest(order=order):
                status, _ = self.call("GET", f"/api/v1/orders/{order}?{ALICE_Q}")
                self.assertEqual(status, 400)

    def test_traversal_segments_do_not_route(self) -> None:
        for target in (
            "/api/v1/orders/1001/../1002",
            "/api/v1/orders//1002",
            "/orders/1001",
            "/api/v1x/orders",
        ):
            with self.subTest(target=target):
                status, _ = self.call("GET", f"{target}?{ALICE_Q}")
                self.assertEqual(status, 404)

    def test_encoded_order_number_is_decoded(self) -> None:
        status, body = self.call("GET", f"/api/v1/orders/%31001?{ALICE_Q}")
        self.assertEqual(status, 200)
        self.assertEqual(body["order_number"], "1001")

    def test_wrong_method(self) -> None:
        self.assertEqual(self.call("POST", f"/api/v1/orders?{ALICE_Q}", {})[0], 405)
        self.assertEqual(
            self.call("GET", f"/api/v1/orders/1001/returns?{ALICE_Q}")[0], 405
        )
        self.assertEqual(self.call("DELETE", f"/api/v1/orders/1001?{ALICE_Q}")[0], 405)


class HttpHandlerTest(MockBackendTest):
    def roundtrip(self, request: bytes) -> tuple[int, dict[str, str], dict[str, Any]]:
        conn = FakeConnection(request)
        handler = server.make_handler(self.store, KEY)
        quiet = type("QuietHandler", (handler,), {"log_message": lambda *args: None})
        quiet(conn, ("127.0.0.1", 0), None)
        head, _, payload = bytes(conn.sent).partition(b"\r\n\r\n")
        status_line, *header_lines = head.decode("latin-1").split("\r\n")
        headers = dict(line.split(": ", 1) for line in header_lines)
        return int(status_line.split()[1]), headers, json.loads(payload)

    def test_get_over_http(self) -> None:
        request = f"GET /api/v1/orders/1001?{ALICE_Q} HTTP/1.1\r\nHost: x\r\nX-API-Key: {KEY}\r\n\r\n"
        status, headers, body = self.roundtrip(request.encode())
        self.assertEqual(status, 200)
        self.assertEqual(headers["Content-Type"], "application/json")
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertEqual(body["order_number"], "1001")

    def test_post_over_http(self) -> None:
        data = json.dumps(
            {"item_ids": "C1", "reason": "late", "customer_phone": ALICE}
        ).encode()
        request = (
            f"POST /api/v1/orders/1003/returns HTTP/1.1\r\nHost: x\r\nX-API-Key: {KEY}\r\n"
            f"Content-Type: application/json; charset=utf-8\r\nContent-Length: {len(data)}\r\n\r\n"
        ).encode() + data
        status, _, body = self.roundtrip(request)
        self.assertEqual(status, 201)
        self.assertEqual(body["item_ids"], ["C1"])

    def test_truncated_body_times_out_over_http(self) -> None:
        conn = FakeConnection(
            (
                f"POST /api/v1/orders/1001/returns HTTP/1.1\r\nHost: x\r\nX-API-Key: {KEY}\r\n"
                "Content-Type: application/json\r\nContent-Length: 100\r\n\r\n{"
            ).encode()
        )
        handler = server.make_handler(self.store, KEY)
        quiet = type("QuietHandler", (handler,), {"log_message": lambda *args: None})
        quiet(conn, ("127.0.0.1", 0), None)
        self.assertEqual(conn.timeouts, [server.SOCKET_TIMEOUT_SECONDS])
        self.assertTrue(bytes(conn.sent).startswith(b"HTTP/1.0 408 "))
        self.assertEqual(self.store.returns, [])

    def test_unauthorized_over_http(self) -> None:
        status, _, body = self.roundtrip(
            f"GET /api/v1/orders?{ALICE_Q} HTTP/1.1\r\nHost: x\r\n\r\n".encode()
        )
        self.assertEqual((status, body), (401, {"error": "invalid api key"}))


class BindTest(unittest.TestCase):
    def test_loopback_detection(self) -> None:
        for host in ("127.0.0.1", "::1", "localhost", "127.0.0.2"):
            self.assertTrue(server._is_loopback(host), host)
        for host in ("0.0.0.0", "::", "192.168.1.5", "example.com"):
            self.assertFalse(server._is_loopback(host), host)
