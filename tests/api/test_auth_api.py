"""Authentication and session behaviour over real HTTP (G01, G02)."""
from __future__ import annotations

import pytest

from modules.api.clients.catalog import CatalogClient
from modules.api.clients.errors import ApiHttpError
from tests.support import golden

pytestmark = [pytest.mark.api]


@pytest.mark.golden("G01")
@pytest.mark.negative
@pytest.mark.parametrize(
    "username,password",
    [("viewer1", "wrong-password"), ("nobody", "TESTONLY-viewer1"), ("editor1", "TESTONLY-viewer1")],
    ids=["wrong-password", "unknown-user", "other-users-password"],
)
def test_g01_invalid_login_is_rejected_without_session(anon, observer, username, password):
    resp = anon.request("POST", "/api/v1/session", {"username": username, "password": password})

    assert resp.status == 401
    assert resp.error_code == "invalid_credentials"
    assert resp.body == {"error": {"code": "invalid_credentials", "message": "Invalid username or password."}}
    assert "Set-Cookie" not in resp.headers
    assert anon.cookies == {}
    assert observer.count_sessions() == 0


@pytest.mark.golden("G01")
@pytest.mark.negative
def test_g01_protected_endpoints_reject_the_client_after_failed_login(anon):
    anon.request("POST", "/api/v1/session", {"username": "viewer1", "password": "wrong-password"})

    for path in ("/api/v1/session", "/api/v1/items", "/api/v1/items/SYN-1001"):
        resp = anon.request("GET", path)
        assert resp.status == 401, path
        assert resp.error_code == "unauthenticated", path


@pytest.mark.golden("G01")
@pytest.mark.negative
@pytest.mark.parametrize(
    "body,expected_status,expected_code",
    [
        ({"username": "viewer1"}, 400, "invalid_request"),
        ({"username": 5, "password": "x"}, 400, "invalid_request"),
        ({"username": "viewer1", "password": "x", "role": "publisher"}, 400, "invalid_request"),
        ({"username": "", "password": "x"}, 400, "invalid_request"),
    ],
    ids=["missing-password", "wrong-type", "unknown-field", "empty-username"],
)
def test_login_body_validation(anon, observer, body, expected_status, expected_code):
    resp = anon.request("POST", "/api/v1/session", body)
    assert resp.status == expected_status
    assert resp.error_code == expected_code
    assert observer.count_sessions() == 0


@pytest.mark.golden("G01")
@pytest.mark.negative
def test_login_malformed_json_is_rejected(anon, observer):
    resp = anon.request("POST", "/api/v1/session", raw_body="{not json")
    assert resp.status == 400
    assert resp.error_code == "invalid_json"
    assert observer.count_sessions() == 0


@pytest.mark.golden("G02")
@pytest.mark.parametrize("username", sorted(golden.USERS))
def test_g02_valid_login_returns_identity_and_cookie(client_factory, observer, username):
    client = client_factory()
    user = client.login(username, golden.USERS[username]["password"])

    assert user == {"username": username, "role": golden.USERS[username]["role"]}
    assert set(client.cookies) == {golden.SESSION_COOKIE}
    assert len(client.cookies[golden.SESSION_COOKIE]) >= 40
    assert client.whoami() == user
    assert observer.count_sessions() == 1


@pytest.mark.golden("G02")
def test_session_cookie_attributes(anon):
    resp = anon._session.post(  # raw access: attributes of Set-Cookie are not exposed by the typed client
        anon.base_url + "/api/v1/session",
        json={"username": "viewer1", "password": "TESTONLY-viewer1"},
        timeout=(2, 5),
    )
    header = resp.headers["Set-Cookie"]
    assert header.startswith(golden.SESSION_COOKIE + "=")
    assert "HttpOnly" in header
    assert "SameSite=Lax" in header
    assert "Path=/" in header


@pytest.mark.golden("G02")
def test_g02_logout_invalidates_session_even_when_old_cookie_is_replayed(client_factory, observer):
    client = client_factory("viewer1")
    old_cookie = client.cookies[golden.SESSION_COOKIE]
    assert client.list_items()  # authenticated before logout

    client.logout()

    assert observer.count_sessions() == 0
    assert client.request("GET", "/api/v1/items").status == 401
    replay = client_factory()
    replay.set_cookie(golden.SESSION_COOKIE, old_cookie)
    resp = replay.request("GET", "/api/v1/items")
    assert resp.status == 401
    assert resp.error_code == "unauthenticated"


@pytest.mark.golden("G02")
@pytest.mark.negative
def test_logout_without_session_is_rejected(anon):
    with pytest.raises(ApiHttpError) as info:
        anon.logout()
    assert info.value.status == 401
    assert info.value.code == "unauthenticated"


@pytest.mark.golden("G02")
def test_two_logins_create_independent_sessions(client_factory, observer):
    first = client_factory("viewer1")
    second = client_factory("viewer1")
    assert first.cookies[golden.SESSION_COOKIE] != second.cookies[golden.SESSION_COOKIE]
    first.logout()
    assert second.whoami() == {"username": "viewer1", "role": "viewer"}
    assert observer.count_sessions() == 1


def test_typed_client_raises_http_error_on_failed_login(anon):
    with pytest.raises(ApiHttpError) as info:
        anon.login("viewer1", "wrong-password")
    assert (info.value.status, info.value.code) == (401, "invalid_credentials")
    assert isinstance(anon, CatalogClient)
