# Data dictionary - CAPS seed database (SQLite)

All data is synthetic. Schema file: `sandbox/schema.sql` (committed with the contract, before any application code). Foreign keys are enforced per connection (`PRAGMA foreign_keys = ON`). Amounts are not modelled; quantities are integers.

| Table | Column | Type | Rule |
|---|---|---|---|
| `users` | `id` | INTEGER PK | |
| | `username` | TEXT | unique, not null |
| | `role` | TEXT | `viewer` / `editor` / `publisher` |
| | `password_hash` | TEXT | Werkzeug PBKDF2 hash, low iteration count (test-only) |
| `sessions` | `token` | TEXT PK | random 256-bit token (the value of cookie `kqa_sid`) |
| | `user_id` | INTEGER | FK `users.id` |
| | `flash` | TEXT | one-shot UI message, cleared when shown |
| `catalog_items` | `id` | INTEGER PK | |
| | `sku` | TEXT | unique (database-enforced), immutable by API contract; CHECK: 2-32 characters from `A-Z 0-9 -`, not starting with `-` |
| | `name` | TEXT | CHECK: 1-80 characters after trimming space/tab/CR/LF/VT/FF |
| | `description` | TEXT | default `''`; CHECK: at most 500 characters |
| | `quantity` | INTEGER | CHECK: `typeof = 'integer'` and `0 .. 1000000` |
| | `state` | TEXT | `DRAFT` / `PUBLISHED` |
| `customers` | `id`, `name`, `address`, `city`, `postal_code`, `country` | | read-only seeded fixture |
| `orders` | `id` | INTEGER PK | read-only seeded fixture |
| | `customer_id` | INTEGER | FK `customers.id` |
| | `item_id` | INTEGER | FK `catalog_items.id` (the 2023 schema referenced `orders.id` by mistake) |
| | `order_date` | TEXT | ISO date |

## Synthetic seed (independent literal copy: `tests/support/golden.py`)

Sandbox users (**test-only credentials, not real secrets, valid only in this sandbox**):

| username | role | password |
|---|---|---|
| `viewer1` | viewer | `TESTONLY-viewer1` |
| `viewer2` | viewer | `TESTONLY-viewer2` |
| `editor1` | editor | `TESTONLY-editor1` |
| `publisher1` | publisher | `TESTONLY-publisher1` |

Catalog items: `SYN-1001` "Synthetic Widget" / "Seeded published item A" / 12 / PUBLISHED; `SYN-1002` "Synthetic Gadget" / "Seeded published item B" / 0 / PUBLISHED; `SYN-2001` "Synthetic Draft Prototype" / "Seeded draft, hidden from viewers" / 5 / DRAFT (ids 1, 2, 3).

Customers: id 1 "Synthetic Customer A", "1 Test Street", "Testville", "T0T 0T0", "Testland"; id 2 "Synthetic Customer B", "2 Sample Road", "Sampleton", "S1S 1S1", "Testland".

Orders: id 1, customer 1, item 1 (`SYN-1001`), date `2026-01-15`.

Expected join row: `(1, "Synthetic Customer A", "Synthetic Widget", "Seeded published item A", "2026-01-15")`.

## Database adapter (test support, `modules/common/database.py`)

`Database(path, readonly=False)` is a context manager that opens a connection with foreign keys on. The connection uses a percent-encoded absolute `file:` URI with an explicit `mode=ro` or `mode=rw` (`sqlite_file_uri()`), so `#`, `%`, `?`, spaces and non-ASCII characters in the path cannot change which file is opened or the access mode; a missing file is never created. Methods: `sqlite_version()`, `foreign_keys_enabled()`, `count(table)`, `get_all_customers()`, `get_customer_address_by_name(name)`, `insert_item(sku, name, description, quantity, state="DRAFT")` (returns the new id; unique-SKU conflict raises `DuplicateRecordError`; other constraint failures raise `ConstraintViolationError`), `update_item_quantity_by_id(item_id, quantity)` and `delete_item_by_id(item_id)` (both return the number of affected rows), `select_item_quantity_by_id(item_id)` (value or `None`), `insert_order(customer_id, item_id, order_date)`, `get_detailed_orders()`, and `transaction()` (commit on success, rollback on exception).
