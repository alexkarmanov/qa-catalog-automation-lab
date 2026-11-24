"""Adapter basics (successors of the 2023 connection/all-users/by-name tests, now with real assertions)."""
from __future__ import annotations

import pytest

from modules.common.database import Database, DatabaseError
from tests.support import golden

pytestmark = [pytest.mark.database]


def test_connection_reports_version_and_enforces_foreign_keys(db_path):
    with Database(db_path) as db:
        major = int(db.sqlite_version().split(".")[0])
        assert major >= 3
        assert db.foreign_keys_enabled() is True


def test_get_all_customers_returns_exact_seed(db_path):
    with Database(db_path, readonly=True) as db:
        assert db.get_all_customers() == [(c[1], c[2], c[3]) for c in golden.SEED_CUSTOMERS]


def test_customer_address_by_name(db_path):
    with Database(db_path, readonly=True) as db:
        assert db.get_customer_address_by_name("Synthetic Customer A") == [("1 Test Street", "Testville", "T0T 0T0", "Testland")]
        assert db.get_customer_address_by_name("Nobody") == []


def test_lookup_with_quote_characters_is_a_plain_value_not_sql(db_path, observer):
    hostile = "x' OR '1'='1"
    with Database(db_path, readonly=True) as db:
        assert db.get_customer_address_by_name(hostile) == []  # historical f-string SQL would return every customer
    assert len(observer.customers()) == 2


def test_readonly_connection_refuses_writes(db_path, observer):
    before = observer.items()
    with Database(db_path, readonly=True) as db:
        with pytest.raises(DatabaseError):
            db.update_item_quantity_by_id(1, 99)
    assert observer.items() == before


def test_count_rejects_unknown_table_names(db_path):
    with Database(db_path, readonly=True) as db:
        assert db.count("catalog_items") == 3
        with pytest.raises(DatabaseError):
            db.count("catalog_items; DROP TABLE users")


def test_using_a_closed_adapter_is_a_typed_error(db_path):
    db = Database(db_path)
    with pytest.raises(DatabaseError):
        db.sqlite_version()


def test_context_manager_closes_the_connection_even_when_the_body_fails(db_path):
    db = Database(db_path)
    with pytest.raises(RuntimeError):
        with db:
            raise RuntimeError("boom")
    assert db._conn is None
