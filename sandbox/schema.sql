-- Catalog Access & Publication Sandbox (CAPS) - tiny seed schema (frozen with the contract).
-- Synthetic data only. Foreign keys are enforced per connection with PRAGMA foreign_keys = ON.

CREATE TABLE users (
    id            INTEGER PRIMARY KEY,
    username      TEXT    NOT NULL UNIQUE,
    role          TEXT    NOT NULL CHECK (role IN ('viewer', 'editor', 'publisher')),
    password_hash TEXT    NOT NULL
);

CREATE TABLE sessions (
    token   TEXT    PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    flash   TEXT
);

-- Successor of the historical `products` table (same idea: id, name, description, quantity).
-- The CHECK constraints below mirror the item schema of docs/API_CONTRACT.md section 4, so a row that
-- violates the schema cannot be stored even by a direct SQL statement. Not enforced here by design:
-- roles/authorization and the "published items are immutable" policy (application rules, exercised through
-- the API; the database-adapter tests intentionally perform raw CRUD). SQLite's trim() and the application's
-- str.strip() differ for exotic Unicode whitespace; the application is the stricter gate.
CREATE TABLE catalog_items (
    id          INTEGER PRIMARY KEY,
    sku         TEXT    NOT NULL UNIQUE
                CHECK (typeof(sku) = 'text' AND length(sku) BETWEEN 2 AND 32
                       AND sku NOT GLOB '*[^A-Z0-9-]*' AND substr(sku, 1, 1) <> '-'),
    name        TEXT    NOT NULL
                CHECK (typeof(name) = 'text'
                       AND length(trim(name, ' ' || char(9) || char(10) || char(11) || char(12) || char(13))) BETWEEN 1 AND 80),
    description TEXT    NOT NULL DEFAULT '' CHECK (typeof(description) = 'text' AND length(description) <= 500),
    quantity    INTEGER NOT NULL CHECK (typeof(quantity) = 'integer' AND quantity BETWEEN 0 AND 1000000),
    state       TEXT    NOT NULL CHECK (state IN ('DRAFT', 'PUBLISHED'))
);

CREATE TABLE customers (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    address     TEXT NOT NULL,
    city        TEXT NOT NULL,
    postal_code TEXT NOT NULL,
    country     TEXT NOT NULL
);

-- The historical schema pointed product_id at orders(id) by mistake; here item_id references catalog_items(id).
CREATE TABLE orders (
    id          INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers(id),
    item_id     INTEGER NOT NULL REFERENCES catalog_items(id),
    order_date  TEXT    NOT NULL
);
