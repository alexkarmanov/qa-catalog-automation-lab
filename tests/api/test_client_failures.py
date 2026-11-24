"""G15: bounded, typed client failures - never a misleading success."""
from __future__ import annotations

import time

import pytest

from modules.api.clients.catalog import CatalogClient
from modules.api.clients.errors import ApiConnectionError, ApiHttpError, ApiMalformedResponse, ApiTimeout
from modules.config import Settings

pytestmark = [pytest.mark.api, pytest.mark.negative, pytest.mark.golden("G15")]


@pytest.fixture
def raw_client(server_with_test_routes):
    with CatalogClient(server_with_test_routes.url, Settings(connect_timeout=1.0, read_timeout=0.3)) as client:
        yield client


def test_g15_slow_endpoint_raises_a_timeout_within_a_bounded_time(raw_client):
    started = time.monotonic()
    with pytest.raises(ApiTimeout):
        raw_client.request("GET", "/__test__/slow", params={"seconds": 5})
    assert time.monotonic() - started < 2.5


def test_g15_per_call_timeout_overrides_the_default(raw_client):
    started = time.monotonic()
    with pytest.raises(ApiTimeout):
        raw_client.request("GET", "/__test__/slow", params={"seconds": 5}, timeout=0.1)
    assert time.monotonic() - started < 1.5


def test_g15_invalid_json_body_is_a_malformed_response(raw_client):
    with pytest.raises(ApiMalformedResponse) as info:
        raw_client.request("GET", "/__test__/malformed")
    assert "not valid JSON" in str(info.value)
    assert info.value.body.startswith("{this is not json")


def test_g15_wrong_shape_is_a_malformed_response_for_typed_calls(raw_client, monkeypatch):
    resp = raw_client.request("GET", "/__test__/wrong-shape")
    assert resp.body == [1, 2, 3]  # raw access keeps what the server sent
    with pytest.raises(ApiMalformedResponse):
        raw_client._object(resp, "items")  # typed access refuses a non-object body


def test_g15_http_500_is_an_http_error_not_a_result(raw_client):
    resp = raw_client.request("GET", "/__test__/error500")
    assert resp.status == 500
    with pytest.raises(ApiHttpError) as info:
        raw_client._ok(resp)
    assert (info.value.status, info.value.code) == (500, "internal_error")


def test_g15_closed_port_is_a_connection_error(server_with_test_routes):
    url = server_with_test_routes.url
    server_with_test_routes.stop()
    with CatalogClient(url, Settings(connect_timeout=1.0, read_timeout=0.5)) as client:
        with pytest.raises(ApiConnectionError):
            client.health()
