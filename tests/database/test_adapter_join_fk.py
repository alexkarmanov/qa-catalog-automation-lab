"""G14: customer/item/order JOIN and foreign-key enforcement on a read-only seeded fixture."""
from __future__ import annotations

import pytest

from modules.common.database import ConstraintViolationError, Database
from tests.support import golden

pytestmark = [pytest.mark.database, pytest.mark.golden("G14")]


def test_g14_join_returns_the_exact_synthetic_tuple(db_path):
    with Database(db_path, readonly=True) as db:
        assert db.get_detailed_orders() == golden.DETAILED_ORDERS


def test_g14_join_result_is_identical_on_every_fresh_database(db_path, tmp_path):
    from sandbox.seed import create_database

    second = str(tmp_path / "second.db")
    create_database(second)
    with Database(db_path, readonly=True) as a, Database(second, readonly=True) as b:
        assert a.get_detailed_orders() == b.get_detailed_orders() == golden.DETAILED_ORDERS


@pytest.mark.parametrize(
    "customer_id,item_id", [(999, 1), (1, 999), (999, 999)], ids=["unknown-customer", "unknown-item", "both-unknown"]
)
def test_g14_foreign_keys_reject_orders_with_unknown_references(db_path, observer, customer_id, item_id):
    with Database(db_path) as db:
        with pytest.raises(ConstraintViolationError):
            db.insert_order(customer_id, item_id, "2026-02-01")
    assert observer.orders() == golden.SEED_ORDERS


def test_g14_valid_new_order_appears_in_the_join(db_path, observer):
    with Database(db_path) as db:
        order_id = db.insert_order(2, 2, "2026-02-01")
        joined = db.get_detailed_orders()
    assert order_id == 2
    assert joined[-1] == (2, "Synthetic Customer B", "Synthetic Gadget", "Seeded published item B", "2026-02-01")
    assert len(observer.orders()) == 2


def test_g14_deleting_an_ordered_item_is_blocked_by_the_foreign_key(db_path, observer):
    before = observer.items()
    with Database(db_path) as db:
        with pytest.raises(ConstraintViolationError):
            db.delete_item_by_id(1)  # item 1 is referenced by order 1
    assert observer.items() == before


def test_g14_unreferenced_item_can_be_deleted_and_the_join_is_unchanged(db_path):
    with Database(db_path) as db:
        assert db.delete_item_by_id(2) == 1
        assert db.get_detailed_orders() == golden.DETAILED_ORDERS


def test_g14_schema_references_the_right_table(db_path):
    """The 2023 schema pointed orders.product_id at orders(id); the modern schema must point at catalog_items."""
    with Database(db_path, readonly=True) as db:
        fks = {(r[2], r[3], r[4]) for r in db.conn.execute("PRAGMA foreign_key_list(orders)").fetchall()}
    assert fks == {("customers", "customer_id", "id"), ("catalog_items", "item_id", "id")}
