"""G01 / G02 in a real Chromium: visible rejection, no session, logout."""
from __future__ import annotations

import re

import pytest
from playwright.sync_api import expect

from modules.ui.playwright_pages.pages import CatalogPage, LoginPage
from tests.support import golden

pytestmark = [pytest.mark.ui, pytest.mark.playwright]


@pytest.mark.golden("G01")
@pytest.mark.negative
@pytest.mark.parametrize(
    "username,password", [("viewer1", "wrong-password"), ("nobody", "x"), ("", ""), ("viewer1", "")],
    ids=["wrong-password", "unknown-user", "empty-form", "empty-password"],
)
def test_g01_invalid_login_shows_an_error_and_creates_no_session(page, server, observer, username, password):
    login = LoginPage(page, server.url).go_to()

    login.login(username, password)

    expect(login.error).to_have_text(golden.LOGIN_ERROR_TEXT)
    expect(page).to_have_url(server.url + "/login")
    assert [c for c in page.context.cookies() if c["name"] == golden.SESSION_COOKIE] == []
    assert page.request.get(server.url + "/api/v1/items").status == 401  # protected endpoint rejects this browser
    page.goto(server.url + "/catalog")
    expect(page).to_have_url(server.url + "/login")
    assert observer.count_sessions() == 0


@pytest.mark.golden("G01")
def test_g01_a_failed_attempt_does_not_block_a_following_valid_login(page, server, observer):
    login = LoginPage(page, server.url).go_to()
    login.login("viewer1", "wrong-password")
    expect(login.error).to_be_visible()

    login.login("viewer1", golden.USERS["viewer1"]["password"])

    expect(page).to_have_url(server.url + "/catalog")
    expect(CatalogPage(page, server.url).current_user).to_have_text("viewer1 (viewer)")
    assert observer.count_sessions() == 1


@pytest.mark.golden("G02")
@pytest.mark.parametrize("username", sorted(golden.USERS))
def test_g02_each_role_can_sign_in_and_sees_its_identity(page, server, sign_in, username):
    sign_in(page, username)
    expect(page).to_have_url(server.url + "/catalog")


@pytest.mark.golden("G02")
def test_g02_viewer_sees_the_published_catalog_and_logout_rejects_further_access(page, server, sign_in, observer):
    sign_in(page, "viewer1")
    catalog = CatalogPage(page, server.url)

    expect(catalog.rows).to_have_count(2)
    assert catalog.displayed_skus() == golden.VIEWER_SKUS
    expect(catalog.row("SYN-1001").locator(".col-name")).to_have_text("Synthetic Widget")
    expect(catalog.row("SYN-1001").locator(".col-quantity")).to_have_text("12")
    expect(catalog.row("SYN-1002").locator(".col-state")).to_have_text("PUBLISHED")

    catalog.logout_button.click()

    expect(page).to_have_url(re.compile(r"/login\?signed_out=1$"))
    expect(LoginPage(page, server.url).notice).to_have_text(golden.SIGNED_OUT_NOTICE)
    assert [c for c in page.context.cookies() if c["name"] == golden.SESSION_COOKIE] == []
    page.goto(server.url + "/catalog")
    expect(page).to_have_url(server.url + "/login")
    assert page.request.get(server.url + "/api/v1/items").status == 401
    assert observer.count_sessions() == 0


@pytest.mark.golden("G01")
@pytest.mark.negative
def test_anonymous_ui_pages_redirect_to_login(page, server):
    for path in ("/catalog", "/items/new", "/items/SYN-1001", "/items/SYN-2001"):
        page.goto(server.url + path)
        expect(page).to_have_url(server.url + "/login")
