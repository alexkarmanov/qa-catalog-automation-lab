"""SQLite adapter (modernized successor of the 2023 ``modules/common/database.py``).

What changed relative to the historical class (see docs/LEGACY_AUDIT.md, LEG-05/LEG-09/LEG-11):
the database path is injected instead of hard-coded, values are bound as SQL parameters (never
interpolated), the connection lifetime is explicit (context manager), foreign keys are enforced,
``INSERT OR REPLACE`` is gone (a duplicate raises), and UPDATE/DELETE report affected rows.
"""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import PurePath
from types import TracebackType
from typing import Iterator, List, Optional, Tuple, Type

_KNOWN_TABLES = frozenset({"users", "sessions", "catalog_items", "customers", "orders"})


def sqlite_file_uri(path: str, readonly: bool) -> str:
    """Return a SQLite ``file:`` URI for ``path`` with an explicit access mode.

    The absolute path is percent-encoded as a whole (``#`` would otherwise start a fragment, ``?`` a query,
    ``%`` an escape), so the URI names exactly the file the caller passed. ``mode=rw`` never creates a file
    and ``mode=ro`` opens it read-only; SQLite's default ``rwc`` is never used.
    """
    base = PurePath(os.path.abspath(path)).as_uri()
    return "%s?mode=%s" % (base, "ro" if readonly else "rw")


class DatabaseError(Exception):
    """Base class for adapter failures."""


class DuplicateRecordError(DatabaseError):
    """A UNIQUE constraint rejected the statement (for example a duplicate SKU)."""


class ConstraintViolationError(DatabaseError):
    """A CHECK, NOT NULL or FOREIGN KEY constraint rejected the statement."""


class Database:
    def __init__(self, path: str, readonly: bool = False):
        self.path = path
        self.readonly = readonly
        self._conn: Optional[sqlite3.Connection] = None

    # -- lifetime ------------------------------------------------------------------------------------
    def __enter__(self) -> "Database":
        uri = sqlite_file_uri(self.path, self.readonly)
        conn = sqlite3.connect(uri, uri=True, timeout=5.0, isolation_level=None)  # explicit transactions
        conn.execute("PRAGMA foreign_keys = ON")
        self._conn = conn
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc: Optional[BaseException],
        tb: Optional[TracebackType],
    ) -> None:
        self.close()

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            raise DatabaseError("the database is not open; use 'with Database(path) as db'")
        return self._conn

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """Commit on success, roll back if the body raises."""
        self.conn.execute("BEGIN")
        try:
            yield
        except BaseException:
            self.conn.execute("ROLLBACK")
            raise
        self.conn.execute("COMMIT")

    def _execute(self, sql: str, params: Tuple = ()) -> sqlite3.Cursor:
        try:
            return self.conn.execute(sql, params)
        except sqlite3.IntegrityError as exc:
            if "UNIQUE" in str(exc).upper():
                raise DuplicateRecordError(str(exc)) from exc
            raise ConstraintViolationError(str(exc)) from exc
        except sqlite3.DatabaseError as exc:
            raise DatabaseError(str(exc)) from exc

    def _write(self, sql: str, params: Tuple = ()) -> sqlite3.Cursor:
        """Run one statement; commit it unless the caller opened a transaction."""
        if self.conn.in_transaction:
            return self._execute(sql, params)
        with self.transaction():
            return self._execute(sql, params)

    # -- information -----------------------------------------------------------------------------------
    def sqlite_version(self) -> str:
        return str(self._execute("SELECT sqlite_version()").fetchone()[0])

    def foreign_keys_enabled(self) -> bool:
        return bool(self._execute("PRAGMA foreign_keys").fetchone()[0])

    def count(self, table: str) -> int:
        if table not in _KNOWN_TABLES:  # table names cannot be bound as parameters: whitelist instead
            raise DatabaseError("unknown table %r" % table)
        return int(self._execute("SELECT count(*) FROM %s" % table).fetchone()[0])

    # -- customers (read-only fixture) ----------------------------------------------------------------
    def get_all_customers(self) -> List[Tuple[str, str, str]]:
        return [tuple(r) for r in self._execute("SELECT name, address, city FROM customers ORDER BY id").fetchall()]

    def get_customer_address_by_name(self, name: str) -> List[Tuple[str, str, str, str]]:
        rows = self._execute(
            "SELECT address, city, postal_code, country FROM customers WHERE name = ? ORDER BY id", (name,)
        ).fetchall()
        return [tuple(r) for r in rows]

    # -- catalog items (CRUD concepts from 2023) ---------------------------------------------------------
    def insert_item(self, sku: str, name: str, description: str, quantity: int, state: str = "DRAFT") -> int:
        cur = self._write(
            "INSERT INTO catalog_items (sku, name, description, quantity, state) VALUES (?, ?, ?, ?, ?)",
            (sku, name, description, quantity, state),
        )
        assert cur.lastrowid is not None
        return int(cur.lastrowid)

    def update_item_quantity_by_id(self, item_id: int, quantity: int) -> int:
        return self._write("UPDATE catalog_items SET quantity = ? WHERE id = ?", (quantity, item_id)).rowcount

    def select_item_quantity_by_id(self, item_id: int) -> Optional[int]:
        row = self._execute("SELECT quantity FROM catalog_items WHERE id = ?", (item_id,)).fetchone()
        return None if row is None else int(row[0])

    def delete_item_by_id(self, item_id: int) -> int:
        return self._write("DELETE FROM catalog_items WHERE id = ?", (item_id,)).rowcount

    # -- orders ---------------------------------------------------------------------------------------------
    def insert_order(self, customer_id: int, item_id: int, order_date: str) -> int:
        cur = self._write(
            "INSERT INTO orders (customer_id, item_id, order_date) VALUES (?, ?, ?)",
            (customer_id, item_id, order_date),
        )
        assert cur.lastrowid is not None
        return int(cur.lastrowid)

    def get_detailed_orders(self) -> List[Tuple[int, str, str, str, str]]:
        rows = self._execute(
            "SELECT orders.id, customers.name, catalog_items.name, catalog_items.description, orders.order_date "
            "FROM orders "
            "JOIN customers ON orders.customer_id = customers.id "
            "JOIN catalog_items ON orders.item_id = catalog_items.id "
            "ORDER BY orders.id"
        ).fetchall()
        return [tuple(r) for r in rows]
