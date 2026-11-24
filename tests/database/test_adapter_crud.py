"""G13: insert / update / delete / unknown id / duplicates / rollback, verified independently with the Observer."""
from __future__ import annotations

import pytest

from modules.common.database import ConstraintViolationError, Database, DuplicateRecordError
from tests.support import golden

pytestmark = [pytest.mark.database, pytest.mark.golden("G13")]


def test_g13_insert_returns_new_id_and_adds_exactly_one_row(db_path, observer):
    before = observer.items()
    with Database(db_path) as db:
        new_id = db.insert_item("SYN-DB1", "Adapter Item", "inserted by adapter", 30)
    assert new_id == 4
    after = observer.items()
    assert after[:3] == before
    assert len(after) == 4
    assert after[3] == (4, "SYN-DB1", "Adapter Item", "inserted by adapter", 30, "DRAFT")


def test_g13_apostrophes_and_sql_metacharacters_are_stored_literally(db_path, observer):
    name = "O'Brien's \"kit\"; DROP TABLE catalog_items; --"
    with Database(db_path) as db:
        db.insert_item("SYN-DB2", name, "it's fine", 1)
    assert observer.item("SYN-DB2") == (4, "SYN-DB2", name, "it's fine", 1, "DRAFT")
    assert observer.count_items() == 4  # the table still exists and nothing else changed


def test_g13_duplicate_sku_raises_and_keeps_the_original_row(db_path, observer):
    before = observer.items()
    with Database(db_path) as db:
        with pytest.raises(DuplicateRecordError):
            db.insert_item("SYN-1001", "Overwritten", "x", 999)  # the 2023 'INSERT OR REPLACE' would have replaced it
    assert observer.items() == before


def test_g13_update_known_id_reports_one_affected_row_and_changes_only_that_value(db_path, observer):
    before = observer.items()
    with Database(db_path) as db:
        affected = db.update_item_quantity_by_id(1, 25)
        assert db.select_item_quantity_by_id(1) == 25
    assert affected == 1
    after = observer.items()
    assert after[0] == (1, "SYN-1001", "Synthetic Widget", "Seeded published item A", 25, "PUBLISHED")
    assert after[1:] == before[1:]


def test_g13_update_unknown_id_affects_nothing_and_creates_no_row(db_path, observer):
    before = observer.items()
    with Database(db_path) as db:
        assert db.update_item_quantity_by_id(999, 5) == 0
        assert db.select_item_quantity_by_id(999) is None
    assert observer.items() == before


def test_g13_delete_known_id_removes_exactly_one_row(db_path, observer):
    with Database(db_path) as db:
        assert db.delete_item_by_id(3) == 1
        assert db.select_item_quantity_by_id(3) is None
    assert [r[1] for r in observer.items()] == ["SYN-1001", "SYN-1002"]


def test_g13_delete_unknown_id_affects_nothing(db_path, observer):
    before = observer.items()
    with Database(db_path) as db:
        assert db.delete_item_by_id(999) == 0
    assert observer.items() == before


def test_g13_insert_then_delete_round_trip_leaves_the_seed_intact(db_path, observer):
    with Database(db_path) as db:
        new_id = db.insert_item("SYN-TMP", "temporary", "", 1)
        assert db.delete_item_by_id(new_id) == 1
    assert observer.items() == golden.SEED_CATALOG_ROWS


@pytest.mark.parametrize("bad", [-1, "many", None], ids=["negative", "text", "null"])
def test_g13_constraint_violations_are_typed_and_change_nothing(db_path, observer, bad):
    before = observer.items()
    with Database(db_path) as db:
        with pytest.raises(ConstraintViolationError):
            db.update_item_quantity_by_id(1, bad)
    assert observer.items() == before


def test_g13_failed_transaction_rolls_back_everything(db_path, observer):
    before = observer.items()
    with Database(db_path) as db:
        with pytest.raises(RuntimeError):
            with db.transaction():
                db.insert_item("SYN-RB1", "first", "", 1)
                db.update_item_quantity_by_id(1, 77)
                raise RuntimeError("abort")
    assert observer.items() == before


def test_g13_successful_transaction_commits_all_statements(db_path, observer):
    with Database(db_path) as db:
        with db.transaction():
            db.insert_item("SYN-TX1", "one", "", 1)
            db.insert_item("SYN-TX2", "two", "", 2)
    assert [r[1] for r in observer.items()][-2:] == ["SYN-TX1", "SYN-TX2"]


def test_g13_constraint_violation_inside_a_transaction_rolls_back_earlier_statements(db_path, observer):
    before = observer.items()
    with Database(db_path) as db:
        with pytest.raises(DuplicateRecordError):
            with db.transaction():
                db.insert_item("SYN-TX3", "ok", "", 1)
                db.insert_item("SYN-1001", "duplicate", "", 1)
    assert observer.items() == before
