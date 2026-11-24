"""Negative paths: forbidden, invalid, conflicting and missing targets. Every rejection proves 'no DB delta' (G04, G06, G08, G09, G11, G12)."""
from __future__ import annotations

import pytest

from tests.support import golden

pytestmark = [pytest.mark.api, pytest.mark.negative]

VALID_NEW = {"sku": "SYN-NEW", "name": "Blocked", "quantity": 1}


def _all_mutation_attempts(client, sku):
    """Yield (label, response) for every mutating endpoint against ``sku``."""
    yield "create", client.request("POST", "/api/v1/items", VALID_NEW)
    yield "patch", client.request("PATCH", "/api/v1/items/" + sku, {"name": "Changed"})
    yield "publish", client.request("POST", "/api/v1/items/" + sku + "/publish")


@pytest.mark.golden("G04")
@pytest.mark.parametrize("sku", ["SYN-2001", "SYN-1001", golden.MISSING_SKU], ids=["draft", "published", "missing"])
def test_g04_viewer_mutations_are_forbidden_and_change_nothing(viewer, observer, sku):
    before = observer.items()

    for label, resp in _all_mutation_attempts(viewer, sku):
        assert resp.status == 403, label
        assert resp.error_code == "forbidden", label

    assert observer.items() == before


@pytest.mark.golden("G04")
def test_g04_anonymous_mutations_are_unauthenticated_and_change_nothing(anon, observer):
    before = observer.items()

    for label, resp in _all_mutation_attempts(anon, "SYN-2001"):
        assert resp.status == 401, label
        assert resp.error_code == "unauthenticated", label

    assert observer.items() == before
    assert observer.count_sessions() == 0


@pytest.mark.golden("G06")
def test_g06_editor_cannot_publish_and_the_draft_stays_hidden(editor, viewer, observer):
    editor.create_item(golden.NEW_ITEM)
    before = observer.items()

    resp = editor.request("POST", "/api/v1/items/SYN-NEW/publish")

    assert resp.status == 403
    assert resp.error_code == "forbidden"
    assert observer.items() == before
    assert observer.item("SYN-NEW")[5] == "DRAFT"
    assert "SYN-NEW" not in [i["sku"] for i in viewer.list_items()]
    assert viewer.request("GET", "/api/v1/items/SYN-NEW").status == 404


@pytest.mark.golden("G08")
@pytest.mark.parametrize("who", ["editor", "publisher"])
@pytest.mark.parametrize("original", [golden.ITEM_1001, golden.ITEM_1002], ids=["SYN-1001", "SYN-1002"])
def test_g08_duplicate_sku_conflicts_and_the_original_row_is_unchanged(request, observer, who, original):
    client = request.getfixturevalue(who)
    before = observer.items()
    stored_before = observer.item(original["sku"])

    resp = client.request(
        "POST", "/api/v1/items", {"sku": original["sku"], "name": "Overwritten", "description": "x", "quantity": 999}
    )

    assert resp.status == 409
    assert resp.error_code == "duplicate_sku"
    assert observer.items() == before
    assert observer.item(original["sku"]) == stored_before
    assert stored_before[2:] == (original["name"], original["description"], original["quantity"], original["state"])


@pytest.mark.golden("G08")
def test_g08_duplicate_of_a_draft_sku_also_conflicts(editor, observer):
    before = observer.items()
    resp = editor.request("POST", "/api/v1/items", {"sku": "SYN-2001", "name": "Again", "quantity": 1})
    assert (resp.status, resp.error_code) == (409, "duplicate_sku")
    assert observer.items() == before


INVALID_CREATE = [
    ({"sku": "SYN-X1", "name": "N", "quantity": -1}, "quantity", "out_of_range"),
    ({"sku": "SYN-X1", "name": "N", "quantity": 1000001}, "quantity", "out_of_range"),
    ({"sku": "SYN-X1", "name": "N", "quantity": True}, "quantity", "wrong_type"),
    ({"sku": "SYN-X1", "name": "N", "quantity": False}, "quantity", "wrong_type"),
    ({"sku": "SYN-X1", "name": "N", "quantity": 1.5}, "quantity", "wrong_type"),
    ({"sku": "SYN-X1", "name": "N", "quantity": "7"}, "quantity", "wrong_type"),
    ({"sku": "SYN-X1", "name": "N", "quantity": None}, "quantity", "wrong_type"),
    ({"sku": "SYN-X1", "name": "N"}, "quantity", "required"),
    ({"sku": "SYN-X1", "name": "", "quantity": 1}, "name", "empty"),
    ({"sku": "SYN-X1", "name": "   ", "quantity": 1}, "name", "empty"),
    ({"sku": "SYN-X1", "name": "n" * 81, "quantity": 1}, "name", "too_long"),
    ({"sku": "SYN-X1", "name": 5, "quantity": 1}, "name", "wrong_type"),
    ({"sku": "SYN-X1", "quantity": 1}, "name", "required"),
    ({"sku": "SYN-X1", "name": "N", "description": "d" * 501, "quantity": 1}, "description", "too_long"),
    ({"sku": "lower", "name": "N", "quantity": 1}, "sku", "bad_format"),
    ({"sku": "X", "name": "N", "quantity": 1}, "sku", "bad_format"),
    ({"sku": "A" * 33, "name": "N", "quantity": 1}, "sku", "bad_format"),
    ({"sku": "-LEADING", "name": "N", "quantity": 1}, "sku", "bad_format"),
    ({"sku": 123, "name": "N", "quantity": 1}, "sku", "wrong_type"),
    ({"name": "N", "quantity": 1}, "sku", "required"),
    ({"sku": "SYN-X1", "name": "N", "quantity": 1, "price": 3}, "price", "unknown_field"),
    ({"sku": "SYN-X1", "name": "N", "quantity": 1, "state": "PUBLISHED"}, "state", "unknown_field"),
]
INVALID_IDS = [
    "qty-negative", "qty-too-large", "qty-true", "qty-false", "qty-float", "qty-string", "qty-null", "qty-missing",
    "name-empty", "name-blank", "name-81", "name-int", "name-missing", "description-501", "sku-lowercase",
    "sku-1-char", "sku-33-chars", "sku-leading-hyphen", "sku-int", "sku-missing", "unknown-field", "state-supplied",
]


@pytest.mark.golden("G09")
@pytest.mark.parametrize("payload,field,code", INVALID_CREATE, ids=INVALID_IDS)
def test_g09_invalid_create_is_rejected_with_a_field_error_and_no_db_delta(editor, observer, payload, field, code):
    before = observer.items()

    resp = editor.request("POST", "/api/v1/items", payload)

    assert resp.status == 400
    assert resp.error_code == "invalid_request"
    assert {"field": field, "code": code} in resp.body["error"]["fields"]
    assert observer.items() == before


@pytest.mark.golden("G09")
@pytest.mark.parametrize(
    "raw",
    ["{not json", "", "[]", '"text"', "null", '{"sku": "SYN-X1", "name": "N", "quantity": 1', "ÿþ"],
    ids=["garbage", "empty-body", "array", "string", "null", "truncated", "non-json-chars"],
)
def test_g09_malformed_json_is_rejected_with_no_db_delta(editor, observer, raw):
    before = observer.items()
    resp = editor.request("POST", "/api/v1/items", raw_body=raw)
    assert resp.status == 400
    assert resp.error_code == "invalid_json"
    assert observer.items() == before


@pytest.mark.golden("G09")
@pytest.mark.parametrize(
    "payload,field,code",
    [
        ({}, "body", "empty"),
        ({"sku": "SYN-OTHER"}, "sku", "immutable_field"),
        ({"state": "PUBLISHED"}, "state", "unknown_field"),
        ({"quantity": -5}, "quantity", "out_of_range"),
        ({"quantity": True}, "quantity", "wrong_type"),
        ({"name": ""}, "name", "empty"),
    ],
    ids=["empty-object", "sku-immutable", "state-not-allowed", "negative", "boolean", "empty-name"],
)
def test_g09_invalid_edit_is_rejected_with_no_db_delta(editor, observer, payload, field, code):
    before = observer.items()
    resp = editor.request("PATCH", "/api/v1/items/SYN-2001", payload)
    assert resp.status == 400
    assert {"field": field, "code": code} in resp.body["error"]["fields"]
    assert observer.items() == before


@pytest.mark.golden("G09")
@pytest.mark.parametrize(
    "payload",
    [
        {"sku": "AB", "name": "n" * 80, "quantity": 0},
        {"sku": "A" * 32, "name": "N", "quantity": 1000000},
        {"sku": "SYN-B1", "name": "N", "description": "d" * 500, "quantity": 1},
    ],
    ids=["sku-2-name-80-qty-0", "sku-32-qty-max", "description-500"],
)
def test_g09_boundary_values_are_accepted(editor, observer, payload):
    resp = editor.request("POST", "/api/v1/items", payload)
    assert resp.status == 201
    assert observer.count_items() == 4
    row = observer.item(payload["sku"])
    assert row[1:3] == (payload["sku"], payload["name"]) and row[4] == payload["quantity"] and row[5] == "DRAFT"


@pytest.mark.golden("G11")
@pytest.mark.parametrize("who", ["editor", "publisher"])
@pytest.mark.parametrize("payload", [{"name": "Hacked"}, {"quantity": 1}], ids=["name", "quantity"])
def test_g11_editing_a_published_item_is_rejected_and_unchanged(request, observer, who, payload):
    client = request.getfixturevalue(who)
    before = observer.items()

    resp = client.request("PATCH", "/api/v1/items/SYN-1001", payload)

    assert resp.status == 409
    assert resp.error_code == "item_published"
    assert observer.items() == before


@pytest.mark.golden("G11")
def test_g11_a_draft_published_by_the_publisher_becomes_immutable(editor, publisher, observer):
    editor.create_item(golden.NEW_ITEM)
    publisher.publish_item("SYN-NEW")
    before = observer.items()

    resp = editor.request("PATCH", "/api/v1/items/SYN-NEW", {"quantity": 8})

    assert (resp.status, resp.error_code) == (409, "item_published")
    assert observer.items() == before


@pytest.mark.golden("G12")
@pytest.mark.parametrize("who", ["editor", "publisher"])
def test_g12_missing_target_gives_404_and_creates_no_phantom_row(request, observer, who):
    client = request.getfixturevalue(who)
    before = observer.items()
    sku = golden.MISSING_SKU

    get = client.request("GET", "/api/v1/items/" + sku)
    patch = client.request("PATCH", "/api/v1/items/" + sku, {"name": "Ghost"})

    for resp in (get, patch):
        assert resp.status == 404
        assert resp.body == {"error": {"code": "not_found", "message": "Not found."}}
    assert observer.items() == before
    assert observer.item(sku) is None


@pytest.mark.golden("G12")
def test_g12_publishing_a_missing_sku_is_404_for_the_publisher(publisher, observer):
    before = observer.items()
    resp = publisher.request("POST", "/api/v1/items/" + golden.MISSING_SKU + "/publish")
    assert (resp.status, resp.error_code) == (404, "not_found")
    assert observer.items() == before


@pytest.mark.golden("G12")
def test_malformed_sku_in_path_is_not_found_not_an_error(editor):
    for sku in ("lower-case", "x", "A" * 40, "SYN%201001"):
        assert editor.request("GET", "/api/v1/items/" + sku).status == 404
