"""Independent golden expectations for the CAPS sandbox.

These literals were written from ``docs/TEST_PLAN.md`` *before* any application code existed.
They must never be computed from the code under test.
"""
from __future__ import annotations

from typing import Dict, List, Tuple

# ----- sandbox users (TEST-ONLY credentials, valid only inside the sandbox) -----------------------
USERS: Dict[str, Dict[str, str]] = {
    "viewer1": {"role": "viewer", "password": "TESTONLY-viewer1"},
    "viewer2": {"role": "viewer", "password": "TESTONLY-viewer2"},
    "editor1": {"role": "editor", "password": "TESTONLY-editor1"},
    "publisher1": {"role": "publisher", "password": "TESTONLY-publisher1"},
}

# ----- catalog items -------------------------------------------------------------------------------
ITEM_1001 = {"sku": "SYN-1001", "name": "Synthetic Widget", "description": "Seeded published item A",
             "quantity": 12, "state": "PUBLISHED"}
ITEM_1002 = {"sku": "SYN-1002", "name": "Synthetic Gadget", "description": "Seeded published item B",
             "quantity": 0, "state": "PUBLISHED"}
ITEM_2001 = {"sku": "SYN-2001", "name": "Synthetic Draft Prototype",
             "description": "Seeded draft, hidden from viewers", "quantity": 5, "state": "DRAFT"}
SEED_ITEMS = [ITEM_1001, ITEM_1002, ITEM_2001]  # database ids 1, 2, 3

VIEWER_SKUS = ["SYN-1001", "SYN-1002"]
EDITOR_SKUS = ["SYN-1001", "SYN-1002", "SYN-2001"]

NEW_ITEM = {"sku": "SYN-NEW", "name": "New Synthetic Item", "description": "Created in a test", "quantity": 7}
MISSING_SKU = "SYN-9999"

# (id, sku, name, description, quantity, state) as stored, ordered by id
SEED_CATALOG_ROWS: List[Tuple] = [
    (1, "SYN-1001", "Synthetic Widget", "Seeded published item A", 12, "PUBLISHED"),
    (2, "SYN-1002", "Synthetic Gadget", "Seeded published item B", 0, "PUBLISHED"),
    (3, "SYN-2001", "Synthetic Draft Prototype", "Seeded draft, hidden from viewers", 5, "DRAFT"),
]

SEED_CUSTOMERS: List[Tuple] = [
    (1, "Synthetic Customer A", "1 Test Street", "Testville", "T0T 0T0", "Testland"),
    (2, "Synthetic Customer B", "2 Sample Road", "Sampleton", "S1S 1S1", "Testland"),
]
SEED_ORDERS: List[Tuple] = [(1, 1, 1, "2026-01-15")]
DETAILED_ORDERS = [(1, "Synthetic Customer A", "Synthetic Widget", "Seeded published item A", "2026-01-15")]

# ----- UI literals --------------------------------------------------------------------------------
LOGIN_ERROR_TEXT = "Invalid username or password."
SIGNED_OUT_NOTICE = "You have been signed out."
LOCK_NOTE_TEXT = "Published items cannot be modified (v1 policy)."
FLASH_CREATED = "Item SYN-NEW created as DRAFT."
FLASH_PUBLISHED = "Item SYN-NEW published."
FLASH_UPDATED_2001 = "Item SYN-2001 updated."
APOSTROPHE_NAME = "O'Brien \"Prototype\"; --"

# ----- HTTP literals ------------------------------------------------------------------------------
ERROR_CODES = {
    401: "unauthenticated",
    403: "forbidden",
    404: "not_found",
}
SESSION_COOKIE = "kqa_sid"
