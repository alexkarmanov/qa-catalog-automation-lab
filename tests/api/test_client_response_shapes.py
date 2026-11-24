"""KQA-003 regression: typed client operations verify response shapes and never return a malformed success.

Two controlled sources of responses (no sandbox involved, nothing external): synthetic ``ApiResponse``
objects injected through ``request`` and a scripted loopback stub server speaking real HTTP. Raw access via
``request()`` is intentionally unchanged and is asserted as such.
"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Dict, Iterator, Tuple

import pytest

from modules.api.clients.catalog import ApiResponse, CatalogClient
from modules.api.clients.errors import ApiHttpError, ApiMalformedResponse
from tests.support import golden

pytestmark = [pytest.mark.api, pytest.mark.negative]

ITEM = dict(golden.ITEM_1001)
USER = {"username": "viewer1", "role": "viewer"}


def _resp(status: int, body: Any) -> ApiResponse:
    text = body if isinstance(body, str) else json.dumps(body)
    return ApiResponse(status, {"Content-Type": "application/json"}, body, text)


def _client_returning(resp: ApiResponse) -> CatalogClient:
    client = CatalogClient("http://127.0.0.1:9")
    client.request = lambda *a, **k: resp  # type: ignore[assignment]
    return client


# (label, call, status, body) - every row must be a controlled ApiMalformedResponse
MALFORMED_SUCCESS = [
    ("list-items-null", lambda c: c.list_items(), 200, {"items": None, "count": 0}),
    ("list-items-string", lambda c: c.list_items(), 200, {"items": "not a list", "count": 0}),
    ("list-items-int-element", lambda c: c.list_items(), 200, {"items": [123], "count": 1}),
    ("list-item-missing-fields", lambda c: c.list_items(), 200, {"items": [{"sku": "only"}], "count": 1}),
    ("list-missing-count", lambda c: c.list_items(), 200, {"items": []}),
    ("list-count-mismatch", lambda c: c.list_items(), 200, {"items": [ITEM], "count": 2}),
    ("list-count-bool", lambda c: c.list_items(), 200, {"items": [], "count": False}),
    ("list-count-string", lambda c: c.list_items(), 200, {"items": [], "count": "0"}),
    ("list-extra-key", lambda c: c.list_items(), 200, {"items": [], "count": 0, "extra": 1}),
    ("list-item-bad-state", lambda c: c.list_items(), 200, {"items": [dict(ITEM, state="ARCHIVED")], "count": 1}),
    ("list-is-array", lambda c: c.list_items(), 200, [ITEM]),
    ("get-item-null-name", lambda c: c.get_item("SYN-1001"), 200, dict(ITEM, name=None)),
    ("get-item-quantity-string", lambda c: c.get_item("SYN-1001"), 200, dict(ITEM, quantity="12")),
    ("get-item-quantity-bool", lambda c: c.get_item("SYN-1001"), 200, dict(ITEM, quantity=True)),
    ("get-item-quantity-float", lambda c: c.get_item("SYN-1001"), 200, dict(ITEM, quantity=1.5)),
    ("get-item-extra-field", lambda c: c.get_item("SYN-1001"), 200, dict(ITEM, price=1)),
    ("get-item-missing-state", lambda c: c.get_item("SYN-1001"), 200, {k: v for k, v in ITEM.items() if k != "state"}),
    ("get-item-lowercase-state", lambda c: c.get_item("SYN-1001"), 200, dict(ITEM, state="published")),
    ("get-item-empty-object", lambda c: c.get_item("SYN-1001"), 200, {}),
    ("create-item-wrong-type", lambda c: c.create_item({}), 201, dict(ITEM, description=5)),
    ("edit-item-list", lambda c: c.edit_item("SYN-1001", {"name": "x"}), 200, [1]),
    ("publish-item-null", lambda c: c.publish_item("SYN-1001"), 200, {"sku": None}),
    ("login-user-string", lambda c: c.login("a", "b"), 200, {"user": "viewer1"}),
    ("login-user-bad-role", lambda c: c.login("a", "b"), 200, {"user": {"username": "x", "role": "root"}}),
    ("login-user-missing", lambda c: c.login("a", "b"), 200, {}),
    ("whoami-role-int", lambda c: c.whoami(), 200, {"user": {"username": "x", "role": 1}}),
    ("health-null", lambda c: c.health(), 200, {"status": None}),
    ("health-array", lambda c: c.health(), 200, ["ok"]),
]


@pytest.mark.parametrize("label,call,status,body", MALFORMED_SUCCESS, ids=[m[0] for m in MALFORMED_SUCCESS])
def test_malformed_success_bodies_are_a_typed_failure_never_a_result(label, call, status, body):
    client = _client_returning(_resp(status, body))
    with pytest.raises(ApiMalformedResponse):
        call(client)


VALID = [
    ("health", lambda c: c.health(), 200, {"status": "ok"}, {"status": "ok"}),
    ("login", lambda c: c.login("viewer1", "x"), 200, {"user": USER}, USER),
    ("whoami", lambda c: c.whoami(), 200, {"user": USER}, USER),
    ("list-empty", lambda c: c.list_items(), 200, {"items": [], "count": 0}, []),
    ("list-two", lambda c: c.list_items(), 200, {"items": [ITEM, golden.ITEM_1002], "count": 2}, [ITEM, golden.ITEM_1002]),
    ("get", lambda c: c.get_item("SYN-1001"), 200, ITEM, ITEM),
    ("create", lambda c: c.create_item({}), 201, dict(ITEM, state="DRAFT"), dict(ITEM, state="DRAFT")),
    ("edit", lambda c: c.edit_item("SYN-1001", {"name": "n"}), 200, ITEM, ITEM),
    ("publish", lambda c: c.publish_item("SYN-1001"), 200, ITEM, ITEM),
]


@pytest.mark.parametrize("label,call,status,body,expected", VALID, ids=[v[0] for v in VALID])
def test_well_formed_bodies_are_returned_unchanged(label, call, status, body, expected):
    assert call(_client_returning(_resp(status, body))) == expected


# (label, status, body) for a *failing* answer to a typed call -> ApiHttpError with the real status
ERROR_ENVELOPES = [
    ("string-error", 500, {"error": "wrong shape"}, None, False),
    ("error-is-list", 500, {"error": ["x"]}, None, False),
    ("code-not-string", 500, {"error": {"code": 5, "message": "m"}}, None, False),
    ("message-missing", 409, {"error": {"code": "duplicate_sku"}}, None, False),
    ("message-not-string", 409, {"error": {"code": "duplicate_sku", "message": 3}}, None, False),
    ("body-is-array", 502, [1, 2], None, False),
    ("body-is-null", 503, None, None, False),
    ("no-error-key", 500, {"detail": "x"}, None, False),
    ("valid-envelope", 409, {"error": {"code": "duplicate_sku", "message": "dup"}}, "duplicate_sku", True),
]


@pytest.mark.parametrize("label,status,body,code,valid", ERROR_ENVELOPES, ids=[e[0] for e in ERROR_ENVELOPES])
def test_error_envelopes_always_become_an_http_error_with_the_real_status(label, status, body, code, valid):
    client = _client_returning(_resp(status, body))
    for call in (lambda: client.list_items(), lambda: client.get_item("SYN-1001"), lambda: client.login("a", "b"),
                 lambda: client.create_item({})):
        with pytest.raises(ApiHttpError) as info:
            call()
        assert info.value.status == status
        assert info.value.code == code
        assert info.value.envelope_valid is valid
        assert info.value.payload == body


def test_unexpected_success_status_is_also_an_http_error():
    client = _client_returning(_resp(200, dict(ITEM)))
    with pytest.raises(ApiHttpError) as info:
        client.create_item({})  # create expects 201
    assert info.value.status == 200


def test_raw_request_still_returns_whatever_the_server_sent():
    resp = _resp(500, {"error": "wrong shape"})
    client = _client_returning(resp)
    assert client.request("GET", "/api/v1/items") is resp  # no validation on the raw path, by design


# ---- real HTTP against a scripted loopback stub (no sandbox, no external host) -----------------------------
class _Stub:
    def __init__(self) -> None:
        self.script: Dict[Tuple[str, str], Tuple[int, str, str]] = {}


@pytest.fixture
def stub() -> Iterator[Tuple[_Stub, str]]:
    state = _Stub()

    class Handler(BaseHTTPRequestHandler):
        def _answer(self) -> None:
            path = self.path.split("?")[0]
            status, ctype, body = state.script.get((self.command, path), (404, "application/json", "{}"))
            data = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        do_GET = do_POST = do_PATCH = do_DELETE = _answer  # noqa: N815

        def log_message(self, *_a: Any) -> None:
            return

    httpd = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield state, "http://127.0.0.1:%d" % httpd.server_port
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(5)


@pytest.fixture
def stubbed_client(stub: Tuple[_Stub, str]) -> Iterator[Tuple[_Stub, CatalogClient]]:
    state, url = stub
    with CatalogClient(url) as client:
        yield state, client


@pytest.mark.parametrize("body", ['{"items": null, "count": 0}', '{"items": "not a list", "count": 0}',
                                  '{"items": [123], "count": 1}', '{"items": [{"sku": "only"}], "count": 1}'])
def test_http_malformed_item_lists_are_rejected(stubbed_client, body):
    state, client = stubbed_client
    state.script[("GET", "/api/v1/items")] = (200, "application/json", body)
    with pytest.raises(ApiMalformedResponse):
        client.list_items()
    assert client.request("GET", "/api/v1/items").text == body  # raw access intact


def test_http_500_with_a_string_error_is_a_controlled_http_error(stubbed_client):
    state, client = stubbed_client
    state.script[("GET", "/api/v1/items")] = (500, "application/json", '{"error": "wrong shape"}')
    with pytest.raises(ApiHttpError) as info:
        client.list_items()
    assert (info.value.status, info.value.code, info.value.envelope_valid) == (500, None, False)
    assert info.value.payload == {"error": "wrong shape"}


def test_http_html_error_page_is_a_typed_malformed_response(stubbed_client):
    state, client = stubbed_client
    state.script[("GET", "/api/v1/items/SYN-1001")] = (502, "text/html", "<html>Bad gateway</html>")
    with pytest.raises(ApiMalformedResponse):
        client.get_item("SYN-1001")


def test_http_well_formed_answers_pass_through(stubbed_client):
    state, client = stubbed_client
    state.script[("GET", "/api/v1/items")] = (200, "application/json", json.dumps({"items": [ITEM], "count": 1}))
    assert client.list_items() == [ITEM]
