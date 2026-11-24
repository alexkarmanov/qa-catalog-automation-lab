"""Basic HTTP contract checks (successors of the three 2023 ``test_http.py`` tests)."""
from __future__ import annotations

import pytest

from tests.support import golden

pytestmark = [pytest.mark.api, pytest.mark.http]


def test_health_endpoint_contract(anon):
    resp = anon.request("GET", "/api/v1/health")
    assert resp.status == 200
    assert resp.body == {"status": "ok"}
    assert resp.headers["Content-Type"] == "application/json"


def test_item_response_headers_and_body(viewer):
    resp = viewer.request("GET", "/api/v1/items/SYN-1001")
    assert resp.status == 200
    assert resp.body == golden.ITEM_1001
    assert resp.headers["Content-Type"] == "application/json"
    assert resp.headers["Cache-Control"] == "no-store"
    assert resp.headers["X-Content-Type-Options"] == "nosniff"


@pytest.mark.negative
def test_unknown_route_and_missing_item_return_404(viewer):
    unknown = viewer.request("GET", "/api/v1/nothing-here")
    missing = viewer.request("GET", "/api/v1/items/" + golden.MISSING_SKU)
    for resp in (unknown, missing):
        assert resp.status == 404
        assert resp.error_code == "not_found"
        assert resp.headers["Content-Type"] == "application/json"


@pytest.mark.negative
@pytest.mark.parametrize(
    "method,path",
    [("PUT", "/api/v1/items/SYN-1001"), ("DELETE", "/api/v1/items/SYN-1001"), ("POST", "/api/v1/health"), ("GET", "/api/v1/items/SYN-1001/publish")],
)
def test_unsupported_methods_return_json_405_and_change_nothing(publisher, observer, method, path):
    before = observer.items()
    resp = publisher.request(method, path)
    assert resp.status == 405
    assert resp.error_code == "method_not_allowed"
    assert observer.items() == before


@pytest.mark.negative
def test_test_only_routes_are_absent_from_the_default_application(anon):
    for path in ("/__test__/slow", "/__test__/malformed", "/__test__/wrong-shape", "/__test__/error500"):
        assert anon.request("GET", path, expect_json=False).status == 404, path
