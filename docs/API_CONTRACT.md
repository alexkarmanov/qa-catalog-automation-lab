# API and UI contract - Catalog Access & Publication Sandbox (CAPS) v1

Status: **frozen before implementation** (committed ahead of any `sandbox/` code). Any change after that is a documented contract change in `CHANGELOG.md`.

CAPS is a deliberately simplified *synthetic* policy used as a local test target. It is not a security product, it was not penetration-tested and it makes no security claim. It binds to loopback only, on a random free port, and makes no external calls.

## 1. Roles and permissions (binding matrix)

| Action | anonymous | viewer | editor | publisher |
|---|:-:|:-:|:-:|:-:|
| Sign in / health check | yes | yes | yes | yes |
| Who am I / sign out | 401 | yes | yes | yes |
| List or search items | 401 | PUBLISHED only | all states | all states |
| Read one PUBLISHED item | 401 | yes | yes | yes |
| Read one DRAFT item | 401 | 404 (indistinguishable from missing) | yes | yes |
| Create a DRAFT | 401 | 403 | yes | yes |
| Edit a DRAFT | 401 | 403 | yes | yes |
| Edit a PUBLISHED item | 401 | 403 | 409 `item_published` | 409 `item_published` |
| Publish a DRAFT | 401 | 403 | 403 | yes |
| Delete an item | not offered in v1 (no route; CRUD *delete* is exercised only at the database-adapter level) |

Visible catalog changes appear only after the publish is **committed**. v1 policy: a published item is immutable (reject, do not silently edit).

## 2. Check order (precedence) - frozen

1. Authentication -> **401** `unauthenticated` (HTML pages: **302** to `/login`).
2. Role permission -> **403** `forbidden` (applies before looking at the item, so a viewer learns nothing about existence).
3. Request body syntax and schema -> **400** (`invalid_json` / `invalid_request`). Validation is stateless and runs before lookup. 422 is *not* used.
4. Existence and visibility -> **404** `not_found` (a DRAFT is "missing" for a viewer).
5. State / conflict -> **409** (`duplicate_sku`, `item_published`, `already_published`).
6. Success -> 200 / 201 / 204.

Unknown routes return JSON 404 `not_found` under `/api/`; wrong methods return JSON 405 `method_not_allowed`.

## 3. Common rules

* Base URL `http://127.0.0.1:<port>` (random port).
* Clients should send JSON with `Content-Type: application/json`, but the sandbox **does not enforce the declared media type** (v1.0.1 clarification, pinned by `tests/api/test_request_validation_contract.py`): the raw body is parsed as JSON whatever type is stated, and no 415 is defined. A body that is not valid UTF-8 JSON, or not a JSON object, is **400 `invalid_json`**.
* Every JSON response carries `Content-Type: application/json`, `Cache-Control: no-store`, `X-Content-Type-Options: nosniff`.
* Error body shape: `{"error": {"code": "<code>", "message": "<text>", "fields": [{"field": "<name>", "code": "<code>"}]}}` (`fields` only for 400 `invalid_request`).
* Session: cookie `kqa_sid` (random 256-bit token from `secrets`), `HttpOnly`, `SameSite=Lax`, `Path=/`, **no expiry in v1**. The session row lives server-side; **logout deletes it**, so a replayed old cookie is rejected with 401.
* Passwords are stored as Werkzeug PBKDF2 hashes with a deliberately low iteration count (test-only data). Sandbox credentials are marked test-only and are listed in `DATA_DICTIONARY.md`.
* **Out of scope (explicit):** CSRF tokens (the only mitigation is `SameSite=Lax` on the session cookie; because the JSON content type is **not** enforced it is not a mitigation), rate limiting, HTTPS, password policy, session expiry, audit logging, account management. No security certification or penetration test is claimed.

## 4. Item schema

| Field | Type | Rules |
|---|---|---|
| `sku` | string | immutable, unique (enforced by the database), **full match** of `[A-Z0-9][A-Z0-9-]{1,31}` (2-32 chars). A trailing newline is not allowed (`"SYN-X\n"` is `bad_format`); the same full-match rule is used for request bodies and for path segments |
| `name` | string | after trimming: 1-80 characters; empty or whitespace-only rejected |
| `description` | string | optional on create (default `""`), 0-500 characters |
| `quantity` | integer | 0 .. 1,000,000 inclusive; **booleans are not integers**; floats and numeric strings rejected |
| `state` | enum | `DRAFT` or `PUBLISHED`; server-controlled, never accepted from clients |

Unknown fields -> 400 (`unknown_field`). Changing `sku` in an edit -> 400 (`immutable_field`). Field error codes: `required`, `wrong_type`, `empty`, `too_long`, `out_of_range`, `bad_format`, `unknown_field`, `immutable_field`.

## 5. REST endpoints

| Method and path | Auth | Success | Failures |
|---|---|---|---|
| `GET /api/v1/health` | none | 200 `{"status": "ok"}` | - |
| `POST /api/v1/session` body `{"username","password"}` (both strings, 1-64 / 1-128 chars, no other keys) | none | 200 `{"user": {"username","role"}}` + `Set-Cookie: kqa_sid` | 400 `invalid_request`/`invalid_json`; 401 `invalid_credentials` (same body for unknown user and wrong password; **no cookie**, no session row) |
| `GET /api/v1/session` | any role | 200 `{"user": {"username","role"}}` | 401 |
| `DELETE /api/v1/session` | any role | 204, cookie cleared, session row deleted | 401 |
| `GET /api/v1/items[?q=<1-80 chars>]` | viewer+ | 200 `{"items": [item...], "count": n}` sorted by `sku` ascending; `q` = case-insensitive substring of `sku` or `name`, applied **after** the visibility filter | 401; 400 `invalid_request` for empty or >80-char `q` or unknown query keys |
| `GET /api/v1/items/{sku}` | viewer+ | 200 item | 401; 404 (missing, malformed SKU, or DRAFT seen by a viewer) |
| `POST /api/v1/items` body `{sku,name,description?,quantity}` | editor, publisher | 201 item (`state` = `DRAFT`), header `Location: /api/v1/items/{sku}` | 401; 403 (viewer); 400; 409 `duplicate_sku` (existing row unchanged) |
| `PATCH /api/v1/items/{sku}` body: non-empty subset of `{name, description, quantity}` | editor, publisher | 200 item | 401; 403 (viewer); 400 (empty object, unknown or immutable field, bad values); 404; 409 `item_published` |
| `POST /api/v1/items/{sku}/publish` (empty body or `{}`) | publisher | 200 item (`state` = `PUBLISHED`) | 401; 403 (viewer, editor); 404; 409 `already_published` |

"Valid draft" for publication means "a stored row that satisfies the item schema". Creation-time validation guarantees this for rows written through the API, and since v1.0.1 the `CHECK` constraints of `sandbox/schema.sql` mirror the item schema (SKU format and length, name 1-80 characters after trimming ASCII whitespace, description at most 500 characters, integer quantity 0 .. 1,000,000, state enum), so even direct SQL cannot store a row that violates it. Roles, authorization and the published-is-immutable rule are application policy and deliberately are **not** database constraints (the database-adapter tests perform raw CRUD). SQLite `trim()` and Python `str.strip()` differ for exotic Unicode whitespace; the application is the stricter gate, the database a backstop. v1 therefore has no extra publication rule.

Test-only routes (`/__test__/slow`, `/__test__/malformed`, `/__test__/wrong-shape`, `/__test__/error500`) exist **only** when the application factory is called with `test_routes=True`. They are off by default and a test proves that the default application answers 404 for them.

## 6. Server-rendered UI (no JavaScript framework)

| Path | Behaviour |
|---|---|
| `GET /` | 302 to `/catalog` |
| `GET /login` | form: `#username`, `#password`, `#login-submit`; with `?signed_out=1` shows `[data-testid=login-notice]` "You have been signed out." |
| `POST /login` (form) | success: 303 to `/catalog` + cookie; failure: **401**, page re-rendered with `[data-testid=login-error]` = "Invalid username or password.", **no cookie**, no session row |
| `POST /logout` | session deleted, 303 to `/login?signed_out=1` |
| `GET /catalog` | anonymous -> 302 `/login`; shows `[data-testid=current-user]` ("username (role)"), `[data-testid=catalog-table]` with rows `tr[data-sku="<SKU>"]` having `.col-sku .col-name .col-quantity .col-state`; editor/publisher also see `[data-testid=new-item-link]`; button `[data-testid=logout]` |
| `GET /items/new`, `POST /items/new` (form: `sku name description quantity`) | editor/publisher only; viewer -> 403 page; success 303 to `/items/<sku>` with flash "Item <SKU> created as DRAFT."; invalid -> 400 page with `[data-testid=form-error]` (one `li` per problem, text `<field> <message>`); duplicate -> 409 page with "sku already exists" |
| `GET /items/<sku>` | detail: `[data-testid=item-state]`, name, quantity; editor/publisher on a DRAFT get `[data-testid=edit-form]`; publisher on a DRAFT gets `[data-testid=publish-button]`; on PUBLISHED shows `[data-testid=published-lock-note]` "Published items cannot be modified (v1 policy)."; viewer on a DRAFT -> 404 page; flash in `[data-testid=flash]` |
| `POST /items/<sku>/edit` (form: `name description quantity`) | success 303 with flash "Item <SKU> updated."; 400/403/404/409 as for the API |
| `POST /items/<sku>/publish` | success 303 with flash "Item <SKU> published."; 403 for editor/viewer; 404; 409 |
| any error page | `[data-testid=error-title]` shows `Forbidden` (403) / `Not found` (404) / `Conflict` (409) / `Bad request` (400) / (the 401 login page uses `login-error` instead) |

Field messages used by UI error lists (and mirrored by the field codes): `required` "is required"; `wrong_type` "has the wrong type"; `empty` "must not be empty"; `too_long` "is too long"; `out_of_range` "must be between 0 and 1000000"; `bad_format` "has an invalid format"; `unknown_field` "is not allowed"; `immutable_field` "cannot be changed".

## 7. Typed client behaviour (`modules/api/clients/catalog.py`, v1.0.1)

* `CatalogClient.request()` is the raw path: it returns whatever status/body the server sent, so tests can assert negative statuses. It still raises `ApiTimeout`, `ApiConnectionError` and, for a body that is not JSON when JSON was expected, `ApiMalformedResponse`.
* The convenience operations (`health`, `login`, `whoami`, `list_items`, `get_item`, `create_item`, `edit_item`, `publish_item`) verify the response shape before returning it: the expected object, exact field set, field types (a boolean is not an integer), the `state` and `role` enums, and for lists the `{items, count}` envelope with `count == len(items)` and every element a valid item. Any mismatch raises `ApiMalformedResponse`; nothing malformed is returned as a success.
* An unexpected status always raises `ApiHttpError` carrying the real status. If the body is a well-formed error envelope (`{"error": {"code": str, "message": str}}`) its `code` and message are exposed; otherwise `code` is `None`, `envelope_valid` is `False` and the raw body is in `payload`. A malformed envelope never hides the status and never raises `AttributeError`.
