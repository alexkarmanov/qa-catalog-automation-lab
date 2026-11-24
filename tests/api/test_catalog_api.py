"""Catalog reads, visibility and the happy-path create/edit/publish flow (G02, G03, G05, G07, G10)."""
from __future__ import annotations

import pytest

from modules.api.clients.errors import ApiHttpError
from tests.support import golden

pytestmark = [pytest.mark.api]


@pytest.mark.golden("G02")
def test_g02_viewer_lists_exactly_the_published_items_in_sku_order(viewer):
    items = viewer.list_items()

    assert [i["sku"] for i in items] == golden.VIEWER_SKUS
    assert items == [golden.ITEM_1001, golden.ITEM_1002]


@pytest.mark.golden("G02")
def test_g02_viewer_reads_one_published_item_with_exact_fields(viewer):
    assert viewer.get_item("SYN-1001") == golden.ITEM_1001
    assert viewer.get_item("SYN-1002") == golden.ITEM_1002


@pytest.mark.golden("G02")
def test_list_response_envelope_and_count(viewer):
    resp = viewer.request("GET", "/api/v1/items")
    assert resp.status == 200
    assert set(resp.body) == {"items", "count"}
    assert resp.body["count"] == 2


@pytest.mark.golden("G03")
@pytest.mark.negative
def test_g03_anonymous_cannot_list_or_read_anything(anon):
    for path in ("/api/v1/items", "/api/v1/items/SYN-2001", "/api/v1/items/SYN-1001", "/api/v1/items?q=Draft"):
        resp = anon.request("GET", path)
        assert resp.status == 401, path
        assert resp.error_code == "unauthenticated", path
        assert "SYN-2001" not in resp.text


@pytest.mark.golden("G03")
@pytest.mark.negative
def test_g03_viewer_list_and_search_do_not_disclose_the_seeded_draft(viewer):
    assert "SYN-2001" not in [i["sku"] for i in viewer.list_items()]
    assert viewer.list_items(q="Draft") == []
    assert viewer.list_items(q="SYN-2001") == []
    assert viewer.list_items(q="prototype") == []


@pytest.mark.golden("G03")
@pytest.mark.negative
def test_g03_viewer_direct_read_of_draft_is_indistinguishable_from_missing(viewer):
    draft = viewer.request("GET", "/api/v1/items/SYN-2001")
    missing = viewer.request("GET", "/api/v1/items/" + golden.MISSING_SKU)

    assert (draft.status, draft.body) == (404, {"error": {"code": "not_found", "message": "Not found."}})
    assert (missing.status, missing.body) == (draft.status, draft.body)


@pytest.mark.golden("G03")
def test_g03_editor_and_publisher_see_the_draft(editor, publisher):
    for client in (editor, publisher):
        assert [i["sku"] for i in client.list_items()] == golden.EDITOR_SKUS
        assert client.get_item("SYN-2001") == golden.ITEM_2001
        assert client.list_items(q="Draft") == [golden.ITEM_2001]


@pytest.mark.parametrize(
    "q,expected",
    [
        ("widget", ["SYN-1001"]),
        ("WIDGET", ["SYN-1001"]),
        ("gadget", ["SYN-1002"]),
        ("syn-10", ["SYN-1001", "SYN-1002"]),
        ("s", ["SYN-1001", "SYN-1002"]),  # single-character boundary (historical test: single char finds results)
        ("zzz-no-such-item", []),  # historical test: search without match
        ("a" * 80, []),  # maximum length is accepted
    ],
    ids=["name", "case-insensitive", "other-name", "sku-prefix", "single-char", "no-match", "max-length-80"],
)
def test_search_boundaries_for_viewer(viewer, q, expected):
    assert [i["sku"] for i in viewer.list_items(q=q)] == expected


@pytest.mark.negative
@pytest.mark.parametrize("params", [{"q": ""}, {"q": " "}, {"q": "a" * 81}, {"x": "1"}], ids=["empty", "blank", "81-chars", "unknown-key"])
def test_search_invalid_parameters_are_rejected(viewer, params):
    resp = viewer.request("GET", "/api/v1/items", params=params)
    assert resp.status == 400
    assert resp.error_code == "invalid_request"


@pytest.mark.golden("G05")
def test_g05_editor_creates_a_draft_that_only_editors_can_see(editor, viewer, observer):
    before = observer.items()
    assert len(before) == 3

    resp = editor.request("POST", "/api/v1/items", golden.NEW_ITEM)

    assert resp.status == 201
    assert resp.headers["Location"] == "/api/v1/items/SYN-NEW"
    expected = dict(golden.NEW_ITEM, state="DRAFT")
    assert resp.body == expected
    assert observer.count_items() == 4
    assert observer.items()[:3] == before  # existing rows untouched
    assert observer.item("SYN-NEW") == (4, "SYN-NEW", "New Synthetic Item", "Created in a test", 7, "DRAFT")
    assert editor.get_item("SYN-NEW") == expected
    assert "SYN-NEW" not in [i["sku"] for i in viewer.list_items()]
    missing = viewer.request("GET", "/api/v1/items/SYN-NEW")
    assert missing.status == 404


@pytest.mark.golden("G05")
def test_publisher_can_also_create_drafts_and_description_defaults_to_empty(publisher, observer):
    created = publisher.create_item({"sku": "SYN-PUB", "name": "  Padded Name  ", "quantity": 0})
    assert created == {"sku": "SYN-PUB", "name": "Padded Name", "description": "", "quantity": 0, "state": "DRAFT"}
    assert observer.item("SYN-PUB") == (4, "SYN-PUB", "Padded Name", "", 0, "DRAFT")


@pytest.mark.golden("G07")
def test_g07_publisher_publishes_and_a_fresh_viewer_session_sees_the_same_values(
    editor, publisher, client_factory, observer
):
    editor.create_item(golden.NEW_ITEM)
    assert observer.count_state("PUBLISHED") == 2

    published = publisher.publish_item("SYN-NEW")

    expected = dict(golden.NEW_ITEM, state="PUBLISHED")
    assert published == expected
    assert observer.count_state("PUBLISHED") == 3
    assert observer.item("SYN-NEW") == (4, "SYN-NEW", "New Synthetic Item", "Created in a test", 7, "PUBLISHED")
    fresh_viewer = client_factory("viewer2")  # a different, brand-new session
    assert [i["sku"] for i in fresh_viewer.list_items()] == ["SYN-1001", "SYN-1002", "SYN-NEW"]
    assert fresh_viewer.get_item("SYN-NEW") == expected


@pytest.mark.golden("G07")
@pytest.mark.negative
def test_g07_second_publish_conflicts(editor, publisher, observer):
    editor.create_item(golden.NEW_ITEM)
    publisher.publish_item("SYN-NEW")
    before = observer.items()

    with pytest.raises(ApiHttpError) as info:
        publisher.publish_item("SYN-NEW")

    assert (info.value.status, info.value.code) == (409, "already_published")
    assert observer.items() == before


@pytest.mark.golden("G10")
def test_g10_edit_draft_with_apostrophe_persists_the_literal_value(editor, observer):
    before = observer.items()

    updated = editor.edit_item("SYN-2001", {"name": golden.APOSTROPHE_NAME})

    assert updated["name"] == golden.APOSTROPHE_NAME
    after = observer.items()
    assert after[2] == (3, "SYN-2001", golden.APOSTROPHE_NAME, "Seeded draft, hidden from viewers", 5, "DRAFT")
    assert after[:2] == before[:2]  # unrelated rows unchanged
    assert editor.get_item("SYN-2001")["name"] == golden.APOSTROPHE_NAME


@pytest.mark.golden("G10")
def test_edit_changes_only_the_requested_fields(editor, observer):
    editor.edit_item("SYN-2001", {"quantity": 9})
    assert observer.item("SYN-2001") == (3, "SYN-2001", "Synthetic Draft Prototype", "Seeded draft, hidden from viewers", 9, "DRAFT")
    editor.edit_item("SYN-2001", {"description": "new text"})
    assert observer.item("SYN-2001") == (3, "SYN-2001", "Synthetic Draft Prototype", "new text", 9, "DRAFT")
