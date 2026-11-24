"""KQA-002 regression: the shipped schema.sql enforces the item schema of the frozen API contract.

Expected accept/reject decisions are literals written from docs/API_CONTRACT.md section 4. The same table
is also run through the application's validator, so the two layers cannot drift apart silently. Row state
is verified with the independent Observer. Roles and the published-is-immutable rule are application
policy and are deliberately NOT database constraints (direct CRUD exercises stay possible).
"""
from __future__ import annotations

import pytest

from modules.common.database import ConstraintViolationError, Database
from sandbox import validation
from tests.support import golden

pytestmark = [pytest.mark.database, pytest.mark.negative]

OK, BAD = True, False
# (id, sku, name, description, quantity, expected_acceptable)
CASES = [
    ("sku-min-2", "AB", "n", "", 0, OK),
    ("sku-max-32", "A" * 32, "n", "", 0, OK),
    ("sku-digit-first", "1B", "n", "", 0, OK),
    ("sku-hyphen-inside", "A-B-9", "n", "", 0, OK),
    ("name-80", "SKU-NAME80", "n" * 80, "", 0, OK),
    ("desc-500", "SKU-D500", "n", "d" * 500, 0, OK),
    ("qty-0", "SKU-Q0", "n", "", 0, OK),
    ("qty-max", "SKU-QMAX", "n", "", 1_000_000, OK),
    ("sku-too-short", "x", "n", "", 1, BAD),
    ("sku-lowercase", "syn-1", "n", "", 1, BAD),
    ("sku-33", "A" * 33, "n", "", 1, BAD),
    ("sku-trailing-newline", "SYN-X\n", "n", "", 1, BAD),
    ("sku-leading-hyphen", "-AB", "n", "", 1, BAD),
    ("sku-space", "AB CD", "n", "", 1, BAD),
    ("sku-underscore", "AB_CD", "n", "", 1, BAD),
    ("sku-empty", "", "n", "", 1, BAD),
    ("name-empty", "SKU-N0", "", "", 1, BAD),
    ("name-spaces", "SKU-N1", "   ", "", 1, BAD),
    ("name-tab-newline", "SKU-N2", "\t\n", "", 1, BAD),
    ("name-81", "SKU-N81", "n" * 81, "", 1, BAD),
    ("desc-501", "SKU-D501", "n", "d" * 501, 1, BAD),
    ("qty-over-max", "SKU-QOV", "n", "", 1_000_001, BAD),
    ("qty-negative", "SKU-QNEG", "n", "", -1, BAD),
]
IDS = [c[0] for c in CASES]


@pytest.mark.parametrize("case", CASES, ids=IDS)
def test_schema_sql_accepts_or_rejects_exactly_as_the_contract_says(db_path, observer, case):
    _, sku, name, description, quantity, acceptable = case
    before = observer.items()
    with Database(db_path) as db:
        if acceptable:
            db.insert_item(sku, name, description, quantity)
        else:
            with pytest.raises(ConstraintViolationError):
                db.insert_item(sku, name, description, quantity)
    after = observer.items()
    if acceptable:
        assert len(after) == len(before) + 1
        assert observer.item(sku) == (4, sku, name, description, quantity, "DRAFT")
    else:
        assert after == before


@pytest.mark.parametrize("case", CASES, ids=IDS)
def test_application_validator_agrees_with_the_schema_table(case):
    _, sku, name, description, quantity, acceptable = case
    _, errors = validation.validate_item(
        {"sku": sku, "name": name, "description": description, "quantity": quantity}, "create"
    )
    assert (errors == []) is acceptable, errors


def test_sku_with_trailing_newline_is_a_bad_format_not_a_valid_sku():
    clean, errors = validation.validate_item({"sku": "SYN-X\n", "name": "name", "quantity": 1}, "create")
    assert errors == [{"field": "sku", "code": "bad_format"}]
    assert "sku" not in clean


@pytest.mark.parametrize("bad", ["SYN-X\n", "\nSYN-X", "SYN-X\r\n", "SYN-X\x00", "SYN‑X", "syn-x", ""])
def test_sku_pattern_uses_a_full_match(bad):
    assert validation.SKU_RE.fullmatch(bad) is None


@pytest.mark.parametrize("good", ["SYN-1001", "AB", "A" * 32, "0-9"])
def test_sku_pattern_accepts_contract_valid_values(good):
    assert validation.SKU_RE.fullmatch(good) is not None


def test_unique_sku_and_enumerated_state_remain_enforced(db_path, observer):
    before = observer.items()
    with Database(db_path) as db:
        with pytest.raises(Exception) as dup:
            db.insert_item(golden.ITEM_1001["sku"], "Other", "", 1)
        assert "Duplicate" in type(dup.value).__name__
        with pytest.raises(ConstraintViolationError):
            db.insert_item("SKU-BADSTATE", "n", "", 1, state="ARCHIVED")
    assert observer.items() == before


def test_database_level_crud_stays_independent_of_application_policy(db_path, observer):
    """Raw adapter CRUD may still change a PUBLISHED row: the immutability rule is application policy."""
    with Database(db_path) as db:
        assert db.update_item_quantity_by_id(1, 25) == 1  # item 1 is PUBLISHED in the seed
    assert observer.item("SYN-1001")[4:] == (25, "PUBLISHED")
