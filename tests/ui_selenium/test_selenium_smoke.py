"""Small real-Chrome Selenium suite that replaces the two 2023 GitHub-login UI tests (G01, G02)."""
from __future__ import annotations

import pytest

from modules.api.clients.catalog import CatalogClient
from modules.ui.page_objects.catalog_page import CatalogPage
from modules.ui.page_objects.sign_in_page import SignInPage
from tests.support import golden

pytestmark = [pytest.mark.ui, pytest.mark.selenium]


@pytest.mark.golden("G01")
@pytest.mark.negative
def test_g01_invalid_login_is_rejected(chrome, server, observer):
    page = SignInPage(chrome, server.url).go_to()

    page.try_login("viewer1", "wrong-password")

    assert page.error_text() == golden.LOGIN_ERROR_TEXT  # visible rejection, not just the page title
    assert page.current_path == "/login"
    assert chrome.get_cookie(golden.SESSION_COOKIE) is None  # no authenticated session in the browser
    assert observer.count_sessions() == 0  # nor in the database
    with CatalogClient(server.url) as client:  # and the protected endpoint refuses a client without a session
        assert client.request("GET", "/api/v1/items").status == 401
    chrome.get(server.url + "/catalog")
    assert chrome.current_url == server.url + "/login"  # the browser itself is bounced back to the login form


@pytest.mark.golden("G02")
def test_g02_viewer_sees_only_published_items_and_logout_revokes_access(chrome, server, observer):
    page = SignInPage(chrome, server.url).go_to()
    page.try_login("viewer1", golden.USERS["viewer1"]["password"])

    catalog = CatalogPage(chrome, server.url).wait_loaded()

    assert catalog.current_user() == "viewer1 (viewer)"
    assert catalog.rows() == {
        "SYN-1001": ("Synthetic Widget", "12", "PUBLISHED"),
        "SYN-1002": ("Synthetic Gadget", "0", "PUBLISHED"),
    }
    assert "SYN-2001" not in chrome.page_source  # the seeded draft is not even present in the markup
    assert observer.count_sessions() == 1
    old_cookie = chrome.get_cookie(golden.SESSION_COOKIE)["value"]

    catalog.logout()

    page.wait_url_path("/login?signed_out=1")
    assert chrome.get_cookie(golden.SESSION_COOKIE) is None
    assert observer.count_sessions() == 0
    with CatalogClient(server.url) as client:
        client.set_cookie(golden.SESSION_COOKIE, old_cookie)
        assert client.request("GET", "/api/v1/items").status == 401  # the old session is really gone
