"""Independent database observer.

Uses its own plain SQL on a read-only connection. It deliberately imports nothing from ``sandbox`` or
``modules.common.database`` so that expected/actual values are never derived from the code under test.
"""
from __future__ import annotations

import os
import sqlite3
from contextlib import closing
from pathlib import PurePath
from typing import List, Optional, Tuple

ItemRow = Tuple[int, str, str, str, int, str]


class Observer:
    def __init__(self, db_path: str):
        self.db_path = db_path

    def _query(self, sql: str, params: Tuple = ()) -> List[Tuple]:
        # Own implementation (stdlib only): the absolute path is percent-encoded so '#', '?' and '%' in a
        # file name cannot change which file is opened or the access mode.
        uri = PurePath(os.path.abspath(self.db_path)).as_uri() + "?mode=ro"
        with closing(sqlite3.connect(uri, uri=True, timeout=5.0)) as conn:
            return [tuple(r) for r in conn.execute(sql, params).fetchall()]

    def items(self) -> List[ItemRow]:
        return self._query("SELECT id, sku, name, description, quantity, state FROM catalog_items ORDER BY id")  # type: ignore[return-value]

    def item(self, sku: str) -> Optional[ItemRow]:
        rows = self._query(
            "SELECT id, sku, name, description, quantity, state FROM catalog_items WHERE sku = ?", (sku,)
        )
        return rows[0] if rows else None  # type: ignore[return-value]

    def count_items(self) -> int:
        return int(self._query("SELECT count(*) FROM catalog_items")[0][0])

    def count_state(self, state: str) -> int:
        return int(self._query("SELECT count(*) FROM catalog_items WHERE state = ?", (state,))[0][0])

    def count_sessions(self) -> int:
        return int(self._query("SELECT count(*) FROM sessions")[0][0])

    def customers(self) -> List[Tuple]:
        return self._query("SELECT id, name, address, city, postal_code, country FROM customers ORDER BY id")

    def orders(self) -> List[Tuple]:
        return self._query("SELECT id, customer_id, item_id, order_date FROM orders ORDER BY id")
