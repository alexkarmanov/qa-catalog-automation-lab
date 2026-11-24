"""KQA-002: request-validation edge cases at the HTTP boundary, with independent no-DB-delta proofs.

Content-Type contract (documented, pinned here): the sandbox parses the request body as JSON whatever media
type the client declares. It does NOT enforce ``Content-Type: application/json`` and therefore offers no
CSRF protection through that header; the only mitigation in scope is ``SameSite=Lax`` on the session cookie.
"""
from __future__ import annotations

import pytest
import requests

from tests.support import golden

pytestmark = [pytest.mark.api, pytest.mark.negative]


def _create(editor, sku, **extra):
    payload = {"sku": sku, "name": "Boundary", "quantity": 1}
    payload.update(extra)
    return editor.request("POST", "/api/v1/items", payload)


@pytest.mark.parametrize("sku", ["SYN-X\n", "SYN-X\r\n", "\nSYN-X", "SYN-X "], ids=["lf", "crlf", "leading-lf", "space"])
def test_create_rejects_whitespace_decorated_sku_and_changes_nothing(editor, observer, sku):
    before = observer.items()
    resp = _create(editor, sku)
    assert resp.status == 400
    assert resp.error_code == "invalid_request"
    assert resp.body["error"]["fields"] == [{"field": "sku", "code": "bad_format"}]
    assert observer.items() == before


@pytest.mark.parametrize("sku", ["AB", "A" * 32])
def test_create_accepts_sku_length_boundaries(editor, observer, sku):
    assert _create(editor, sku).status == 201
    assert observer.item(sku) is not None


@pytest.mark.parametrize("encoded", ["SYN-1001%0A", "%0ASYN-1001", "SYN-1001%20"])
def test_path_sku_with_trailing_or_leading_whitespace_is_not_found(editor, encoded):
    resp = editor.request("GET", "/api/v1/items/" + encoded)
    assert resp.status == 404
    assert resp.error_code == "not_found"


def test_edit_and_publish_with_newline_sku_are_not_found_and_change_nothing(publisher, observer):
    before = observer.items()
    assert publisher.request("PATCH", "/api/v1/items/SYN-2001%0A", {"name": "X"}).status == 404
    assert publisher.request("POST", "/api/v1/items/SYN-2001%0A/publish").status == 404
    assert observer.items() == before


def _post_raw(server, cookie, body, content_type):
    headers = {} if content_type is None else {"Content-Type": content_type}
    return requests.post(
        server.url + "/api/v1/items", data=body, headers=headers, cookies={"kqa_sid": cookie}, timeout=5
    )


@pytest.mark.parametrize("content_type", ["text/plain", "application/x-www-form-urlencoded", None],
                         ids=["text-plain", "form-urlencoded", "absent"])
def test_json_body_is_parsed_whatever_media_type_is_declared(server, editor, observer, content_type):
    """Pins the documented leniency: no Content-Type enforcement exists, so none is claimed."""
    cookie = editor.cookies["kqa_sid"]
    resp = _post_raw(server, cookie, b'{"sku": "SYN-CT", "name": "Typed", "quantity": 2}', content_type)
    assert resp.status_code == 201
    assert observer.item("SYN-CT")[1:] == ("SYN-CT", "Typed", "", 2, "DRAFT")


@pytest.mark.parametrize("body", [b"sku=SYN-CT&name=Typed&quantity=2", b"", b"\xff\xfe"], ids=["form-body", "empty", "not-utf8"])
def test_non_json_bodies_are_rejected_regardless_of_content_type(server, editor, observer, body):
    before = observer.items()
    resp = _post_raw(server, editor.cookies["kqa_sid"], body, "application/json")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "invalid_json"
    assert observer.items() == before


def test_seed_item_is_untouched_by_all_of_the_above(observer):
    assert observer.items() == golden.SEED_CATALOG_ROWS
