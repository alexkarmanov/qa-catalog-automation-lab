"""Draft visibility, publication and rejected actions through the UI (G03, G05-G12)."""
from __future__ import annotations

import pytest
from playwright.sync_api import expect

from modules.ui.playwright_pages.pages import CatalogPage, ItemPage, NewItemPage
from tests.support import golden

pytestmark = [pytest.mark.ui, pytest.mark.playwright]


@pytest.mark.golden("G03")
@pytest.mark.negative
def test_g03_viewer_does_not_see_the_draft_in_the_catalog_or_by_direct_url(page, server, sign_in):
    sign_in(page, "viewer1")
    catalog = CatalogPage(page, server.url)
    expect(catalog.row("SYN-2001")).to_have_count(0)
    expect(page.get_by_text("Synthetic Draft Prototype")).to_have_count(0)

    response = page.goto(server.url + "/items/SYN-2001")

    assert response.status == 404
    item = ItemPage(page, server.url)
    expect(item.error_title).to_have_text("Not found")
    expect(page.get_by_text("Synthetic Draft Prototype")).to_have_count(0)
    missing = page.goto(server.url + "/items/" + golden.MISSING_SKU)
    assert missing.status == 404
    expect(item.error_title).to_have_text("Not found")


@pytest.mark.golden("G03")
def test_g03_editor_sees_the_draft_marked_as_draft(page, server, sign_in):
    sign_in(page, "editor1")
    catalog = CatalogPage(page, server.url)

    assert catalog.displayed_skus() == golden.EDITOR_SKUS
    expect(catalog.row("SYN-2001").locator(".col-state")).to_have_text("DRAFT")
    expect(catalog.new_item_link).to_be_visible()


@pytest.mark.golden("G04")
@pytest.mark.negative
def test_g04_viewer_has_no_create_controls_and_the_form_url_is_forbidden(page, server, sign_in, observer):
    sign_in(page, "viewer1")
    expect(CatalogPage(page, server.url).new_item_link).to_have_count(0)
    before = observer.items()

    response = page.goto(server.url + "/items/new")

    assert response.status == 403
    expect(ItemPage(page, server.url).error_title).to_have_text("Forbidden")
    page_post = page.request.post(server.url + "/items/new", form={"sku": "SYN-NEW", "name": "x", "quantity": "1"})
    assert page_post.status == 403
    assert observer.items() == before


@pytest.mark.golden("G05")
def test_g05_editor_creates_a_draft_through_the_form(page, server, sign_in, observer):
    sign_in(page, "editor1")
    CatalogPage(page, server.url).new_item_link.click()
    form = NewItemPage(page, server.url)

    form.create("SYN-NEW", "New Synthetic Item", "7", "Created in a test")

    item = ItemPage(page, server.url)
    expect(item.flash).to_have_text(golden.FLASH_CREATED)
    expect(item.state).to_have_text("DRAFT")
    expect(item.quantity).to_have_text("7")
    assert observer.item("SYN-NEW") == (4, "SYN-NEW", "New Synthetic Item", "Created in a test", 7, "DRAFT")
    catalog = CatalogPage(page, server.url).go_to()
    expect(catalog.row("SYN-NEW").locator(".col-state")).to_have_text("DRAFT")


@pytest.mark.golden("G06")
@pytest.mark.negative
def test_g06_editor_has_no_publish_button_and_a_forged_post_is_forbidden(page, server, sign_in, observer):
    sign_in(page, "editor1")
    item = ItemPage(page, server.url).go_to("SYN-2001")
    expect(item.state).to_have_text("DRAFT")
    expect(item.publish_button).to_have_count(0)
    before = observer.items()

    forged = page.request.post(server.url + "/items/SYN-2001/publish")

    assert forged.status == 403
    assert observer.items() == before
    assert observer.item("SYN-2001")[5] == "DRAFT"


@pytest.mark.golden("G07")
def test_g07_publisher_publishes_and_a_fresh_viewer_session_sees_it(page, new_session, server, sign_in, observer):
    sign_in(page, "editor1")
    NewItemPage(page, server.url).go_to().create("SYN-NEW", "New Synthetic Item", "7", "Created in a test")
    expect(ItemPage(page, server.url).flash).to_have_text(golden.FLASH_CREATED)

    publisher_page = new_session()
    sign_in(publisher_page, "publisher1")
    item = ItemPage(publisher_page, server.url).go_to("SYN-NEW")
    expect(item.publish_button).to_be_visible()
    item.publish_button.click()
    expect(item.flash).to_have_text(golden.FLASH_PUBLISHED)
    expect(item.state).to_have_text("PUBLISHED")
    expect(item.lock_note).to_have_text(golden.LOCK_NOTE_TEXT)
    assert observer.item("SYN-NEW") == (4, "SYN-NEW", "New Synthetic Item", "Created in a test", 7, "PUBLISHED")

    viewer_page = new_session()
    sign_in(viewer_page, "viewer2")
    catalog = CatalogPage(viewer_page, server.url)
    expect(catalog.rows).to_have_count(3)
    assert catalog.displayed_skus() == ["SYN-1001", "SYN-1002", "SYN-NEW"]
    expect(catalog.row("SYN-NEW").locator(".col-name")).to_have_text("New Synthetic Item")
    expect(catalog.row("SYN-NEW").locator(".col-quantity")).to_have_text("7")


@pytest.mark.golden("G08")
@pytest.mark.negative
def test_g08_duplicate_sku_is_rejected_by_the_form_and_the_original_is_unchanged(page, server, sign_in, observer):
    sign_in(page, "editor1")
    before = observer.items()

    NewItemPage(page, server.url).go_to().create("SYN-1001", "Overwritten", "999", "x")

    expect(NewItemPage(page, server.url).errors).to_contain_text("sku already exists")
    assert observer.items() == before


@pytest.mark.golden("G09")
@pytest.mark.negative
@pytest.mark.parametrize(
    "sku,name,quantity,message",
    [
        ("SYN-X1", "N", "-1", "quantity must be between 0 and 1000000"),
        ("SYN-X1", "N", "1000001", "quantity must be between 0 and 1000000"),
        ("SYN-X1", "N", "abc", "quantity has the wrong type"),
        ("SYN-X1", "N", "1.5", "quantity has the wrong type"),
        ("SYN-X1", "N", "", "quantity is required"),
        ("SYN-X1", "   ", "1", "name must not be empty"),
        ("lower", "N", "1", "sku has an invalid format"),
    ],
    ids=["negative", "too-large", "text", "decimal", "missing", "blank-name", "bad-sku"],
)
def test_g09_invalid_form_input_shows_the_problem_and_writes_nothing(page, server, sign_in, observer, sku, name, quantity, message):
    sign_in(page, "editor1")
    before = observer.items()

    NewItemPage(page, server.url).go_to().create(sku, name, quantity)

    expect(NewItemPage(page, server.url).errors).to_contain_text(message)
    assert observer.items() == before


@pytest.mark.golden("G10")
def test_g10_editing_a_draft_with_quotes_shows_and_stores_the_literal_text(page, server, sign_in, observer):
    sign_in(page, "editor1")
    item = ItemPage(page, server.url).go_to("SYN-2001")
    before = observer.items()

    item.edit_name.fill(golden.APOSTROPHE_NAME)
    item.edit_submit.click()

    expect(item.flash).to_have_text(golden.FLASH_UPDATED_2001)
    expect(item.name).to_have_text(golden.APOSTROPHE_NAME)
    after = observer.items()
    assert after[2][2] == golden.APOSTROPHE_NAME
    assert after[:2] == before[:2]


@pytest.mark.golden("G11")
@pytest.mark.negative
@pytest.mark.parametrize("username", ["editor1", "publisher1"])
def test_g11_a_published_item_shows_a_lock_note_and_cannot_be_edited(page, server, sign_in, observer, username):
    sign_in(page, username)
    item = ItemPage(page, server.url).go_to("SYN-1001")
    expect(item.state).to_have_text("PUBLISHED")
    expect(item.lock_note).to_have_text(golden.LOCK_NOTE_TEXT)
    expect(item.edit_form).to_have_count(0)
    before = observer.items()

    forged = page.request.post(server.url + "/items/SYN-1001/edit", form={"name": "Hacked", "quantity": "1"})

    assert forged.status == 409
    assert observer.items() == before


@pytest.mark.golden("G12")
@pytest.mark.negative
def test_g12_missing_item_page_is_a_clear_404_and_publish_forgery_creates_nothing(page, server, sign_in, observer):
    sign_in(page, "publisher1")
    before = observer.items()

    response = page.goto(server.url + "/items/" + golden.MISSING_SKU)
    assert response.status == 404
    expect(ItemPage(page, server.url).error_title).to_have_text("Not found")
    forged = page.request.post(server.url + "/items/%s/publish" % golden.MISSING_SKU)

    assert forged.status == 404
    assert observer.items() == before
