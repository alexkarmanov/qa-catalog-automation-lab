"""Create and seed a sandbox database (synthetic data, test-only credentials)."""
from __future__ import annotations

import os
import sqlite3
from typing import List, Tuple

from werkzeug.security import generate_password_hash

SCHEMA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schema.sql")
# Deliberately cheap PBKDF2 (1,000 iterations): the passwords are public test-only values.
HASH_METHOD = "pbkdf2:sha256:1000"

SEED_USERS: List[Tuple[str, str, str]] = [
    ("viewer1", "viewer", "TESTONLY-viewer1"),
    ("viewer2", "viewer", "TESTONLY-viewer2"),
    ("editor1", "editor", "TESTONLY-editor1"),
    ("publisher1", "publisher", "TESTONLY-publisher1"),
]


def create_database(db_path: str) -> None:
    """Create ``db_path`` (must not exist) from schema.sql and load the synthetic seed."""
    if os.path.exists(db_path):
        raise FileExistsError("refusing to overwrite an existing database: %s" % os.path.basename(db_path))
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        with open(SCHEMA_PATH, encoding="utf-8") as handle:
            conn.executescript(handle.read())
        for username, role, password in SEED_USERS:
            conn.execute(
                "INSERT INTO users (username, role, password_hash) VALUES (?, ?, ?)",
                (username, role, generate_password_hash(password, method=HASH_METHOD)),
            )
        conn.executemany(
            "INSERT INTO catalog_items (id, sku, name, description, quantity, state) VALUES (?, ?, ?, ?, ?, ?)",
            [
                (1, "SYN-1001", "Synthetic Widget", "Seeded published item A", 12, "PUBLISHED"),
                (2, "SYN-1002", "Synthetic Gadget", "Seeded published item B", 0, "PUBLISHED"),
                (3, "SYN-2001", "Synthetic Draft Prototype", "Seeded draft, hidden from viewers", 5, "DRAFT"),
            ],
        )
        conn.executemany(
            "INSERT INTO customers (id, name, address, city, postal_code, country) VALUES (?, ?, ?, ?, ?, ?)",
            [
                (1, "Synthetic Customer A", "1 Test Street", "Testville", "T0T 0T0", "Testland"),
                (2, "Synthetic Customer B", "2 Sample Road", "Sampleton", "S1S 1S1", "Testland"),
            ],
        )
        conn.execute("INSERT INTO orders (id, customer_id, item_id, order_date) VALUES (1, 1, 1, '2026-01-15')")
        conn.commit()
    finally:
        conn.close()
