"""Complete browser -> API -> database flows. Each flow compares three independent observations of the same state."""
from __future__ import annotations

import pytest
from playwright.sync_api import expect

from modules.api.clients.catalog import CatalogClient
from modules.ui.playwright_pages.pages import CatalogPage, ItemPage, LoginPage, NewItemPage
from tests.support import golden

pytestmark = [pytest.mark.e2e, pytest.mark.ui, pytest.mark.playwright]


@pytest.mark.golden("G01")
@pytest.mark.negative
def test_e2e_rejected_login_leaves_no_session_and_no_data_change(page, server, observer, evidence_shot):
    items_before = observer.items()
    login = LoginPage(page, server.url).go_to()

    login.login("publisher1", "not-the-password")

    expect(login.error).to_have_text(golden.LOGIN_ERROR_TEXT)  # UI
    cookies = {c["name"]: c["value"] for c in page.context.cookies()}
    assert golden.SESSION_COOKIE not in cookies
    with CatalogClient(server.url) as api:  # API: replaying whatever the browser holds still gives 401
        for name, value in cookies.items():
            api.set_cookie(name, value)
        assert api.request("GET", "/api/v1/session").status == 401
    assert observer.count_sessions() == 0  # DB: no authenticated session was written
    assert observer.items() == items_before  # DB: no data write at all
    evidence_shot(page, "e2e_01_rejected_login")


@pytest.mark.golden("G05")
def test_e2e_editor_creates_a_draft_ui_api_and_db_agree_and_viewers_cannot_see_it(
    page, new_session, server, sign_in, observer, client_factory, evidence_shot
):
    sign_in(page, "editor1")
    NewItemPage(page, server.url).go_to().create("SYN-NEW", "New Synthetic Item", "7", "Created in a test")
    item = ItemPage(page, server.url)
    expect(item.flash).to_have_text(golden.FLASH_CREATED)
    expect(item.state).to_have_text("DRAFT")
    evidence_shot(page, "e2e_02_editor_created_draft")

    expected_api = dict(golden.NEW_ITEM, state="DRAFT")
    assert client_factory("editor1").get_item("SYN-NEW") == expected_api  # API (editor)
    assert observer.item("SYN-NEW") == (4, "SYN-NEW", "New Synthetic Item", "Created in a test", 7, "DRAFT")  # DB
    assert observer.count_items() == 4

    viewer_page = new_session()
    sign_in(viewer_page, "viewer1")
    expect(CatalogPage(viewer_page, server.url).row("SYN-NEW")).to_have_count(0)  # UI (viewer)
    assert viewer_page.goto(server.url + "/items/SYN-NEW").status == 404
    assert client_factory("viewer1").request("GET", "/api/v1/items/SYN-NEW").status == 404  # API (viewer)


@pytest.mark.golden("G07")
def test_e2e_publish_is_visible_to_a_fresh_viewer_in_ui_api_and_db(
    page, new_session, server, sign_in, observer, client_factory, evidence_shot
):
    editor_api = client_factory("editor1")
    editor_api.create_item(golden.NEW_ITEM)  # arrange through the API: the browser flow under test is the publish
    sign_in(page, "publisher1")
    item = ItemPage(page, server.url).go_to("SYN-NEW")
    expect(item.state).to_have_text("DRAFT")

    item.publish_button.click()

    expect(item.flash).to_have_text(golden.FLASH_PUBLISHED)
    expect(item.state).to_have_text("PUBLISHED")
    assert observer.item("SYN-NEW") == (4, "SYN-NEW", "New Synthetic Item", "Created in a test", 7, "PUBLISHED")  # DB
    assert observer.count_state("PUBLISHED") == 3

    viewer_page = new_session()  # fresh browser session, never saw the draft
    sign_in(viewer_page, "viewer2")
    catalog = CatalogPage(viewer_page, server.url)
    expect(catalog.row("SYN-NEW")).to_have_count(1)  # UI
    expect(catalog.row("SYN-NEW").locator(".col-name")).to_have_text("New Synthetic Item")
    expect(catalog.row("SYN-NEW").locator(".col-quantity")).to_have_text("7")
    expect(catalog.row("SYN-NEW").locator(".col-state")).to_have_text("PUBLISHED")
    assert client_factory("viewer2").get_item("SYN-NEW") == dict(golden.NEW_ITEM, state="PUBLISHED")  # API
    evidence_shot(viewer_page, "e2e_03_viewer_sees_published_item")


@pytest.mark.golden("G04")
@pytest.mark.negative
def test_e2e_forbidden_viewer_request_from_a_browser_session_changes_nothing(page, server, sign_in, observer, evidence_shot):
    sign_in(page, "viewer1")
    before = observer.items()

    created = page.request.post(server.url + "/api/v1/items", data={"sku": "SYN-NEW", "name": "Blocked", "quantity": 1})
    published = page.request.post(server.url + "/api/v1/items/SYN-2001/publish")

    assert created.status == 403 and created.json()["error"]["code"] == "forbidden"  # API verdict
    assert published.status == 403
    CatalogPage(page, server.url).go_to()
    expect(CatalogPage(page, server.url).row("SYN-NEW")).to_have_count(0)  # UI shows nothing new
    assert observer.items() == before  # DB unchanged
    evidence_shot(page, "e2e_04_forbidden_request_no_change")
