# Test plan and golden expectations

Written and committed **before** any sandbox production code. Expected values below are literals, copied into `tests/support/golden.py`; no expected value is computed by the code under test. Direct SQL checks use their own SQL in `tests/support/observer.py` and never call the application's query code or the `Database` adapter.

Target: the Catalog Access & Publication Sandbox (see `API_CONTRACT.md`, `DATA_DICTIONARY.md`). Every test gets a fresh temporary database and a fresh server on a random loopback port.

## Risk-based scope

| Risk | Why it matters | Covered by |
|---|---|---|
| Unauthorized read of unpublished records | main policy of the target | G01-G03, role matrix tests |
| Unauthorized mutation, even partially applied | state corruption | G04, G06, G11 |
| Invalid data accepted or silently altered | integrity | G08-G10, parametrized boundaries |
| UI shows something the database does not hold | stale/incorrect UI | G05, G07, E2E flows |
| Test suite itself leaking state or resources | trust in the suite | G16, framework tests |
| Client hangs or reports false success on failure | automation robustness | G15 |
| Legacy CRUD concepts (apostrophes, unknown ids, duplicates, FK, rollback, JOIN) | the 2023 learning content | G13, G14 |

## Seed (literal)

Users (all test-only): `viewer1`/viewer, `viewer2`/viewer, `editor1`/editor, `publisher1`/publisher; password = `TESTONLY-<username>`.
Items: `SYN-1001` "Synthetic Widget" q12 PUBLISHED; `SYN-1002` "Synthetic Gadget" q0 PUBLISHED; `SYN-2001` "Synthetic Draft Prototype" q5 DRAFT.
Customers 1-2, order 1 as in the data dictionary.

## Golden scenarios (binding minimum)

| ID | Scenario | Literal expectation |
|---|---|---|
| G01 | Invalid login (`viewer1` / `wrong-password`; also unknown user `nobody`) | API: 401 `invalid_credentials`, no `Set-Cookie`. UI: status 401, `[data-testid=login-error]` text exactly "Invalid username or password.", URL stays `/login`. Afterward `GET /api/v1/session` and `GET /api/v1/items` with the same client -> 401. DB: `sessions` row count 0. |
| G02 | `viewer1` signs in, reads, signs out | list -> exactly `["SYN-1001","SYN-1002"]` in that order, count 2; `GET SYN-1001` -> `{sku:"SYN-1001", name:"Synthetic Widget", description:"Seeded published item A", quantity:12, state:"PUBLISHED"}`; after logout: `GET /api/v1/items` -> 401 with the **same old cookie replayed**; `sessions` count 0. UI: rows for SYN-1001 and SYN-1002 only; `current-user` = "viewer1 (viewer)". |
| G03 | Draft visibility | anonymous list/item -> 401; `viewer1` list excludes `SYN-2001`; `GET /items/SYN-2001` as viewer -> 404 `not_found` (identical body to a missing SKU `SYN-9999`); search `q=Draft` as viewer -> `[]`; as `editor1` the list is `["SYN-1001","SYN-1002","SYN-2001"]` and `q=Draft` -> `["SYN-2001"]`. UI: viewer `/items/SYN-2001` -> 404 page "Not found"; editor sees the row with state "DRAFT". |
| G04 | `viewer1` tries POST create `{sku:"SYN-NEW",name:"Blocked",quantity:1}`, PATCH `SYN-2001`, publish `SYN-2001`, PATCH and publish a missing SKU | every call 403 `forbidden` (also for the missing SKU: role check precedes lookup); `catalog_items` snapshot before == after (exact rows). Anonymous attempts -> 401, same snapshot. |
| G05 | `editor1` creates `SYN-NEW` quantity 7 (name "New Synthetic Item", description "Created in a test") | 201, `Location: /api/v1/items/SYN-NEW`, body state `DRAFT`, quantity 7; DB: exactly one new row `(sku=SYN-NEW, name, description, 7, DRAFT)`, row count 3 -> 4; editor API and UI show it with state DRAFT; `viewer1` list unchanged and direct read -> 404. |
| G06 | `editor1` tries to publish `SYN-NEW` | 403 `forbidden`; DB state stays `DRAFT`; viewer still cannot see it. |
| G07 | `publisher1` publishes `SYN-NEW` | 200 state `PUBLISHED`; DB row state `PUBLISHED`, count of PUBLISHED rows 2 -> 3; a **fresh** viewer session (new client / new browser context) lists `["SYN-1001","SYN-1002","SYN-NEW"]` and reads SKU "SYN-NEW", name "New Synthetic Item", quantity 7; DB equals API. Second publish -> 409 `already_published`. |
| G08 | Duplicate create `SYN-1001` with changed name/quantity | 409 `duplicate_sku`; row `SYN-1001` unchanged ("Synthetic Widget", 12); row count unchanged; same via UI form (409 page, text "sku already exists"). |
| G09 | Invalid create/edit input (parametrized): quantity `-1`, `1000001`, `true`, `1.5`, `"7"`, missing quantity, empty/whitespace name, name of 81 chars, bad SKU (`lower`, `X`, 33 chars), unknown field `price`, `state` supplied, malformed JSON, JSON array | each -> 400 (`invalid_request` with the expected field code, or `invalid_json`); `catalog_items` snapshot unchanged. Boundary acceptances: quantity `0` and `1000000` -> 201; name of exactly 80 chars -> 201; SKU of exactly 2 and 32 chars -> 201. |
| G10 | `editor1` edits draft `SYN-2001` name to `O'Brien "Prototype"; --` | 200; DB value is the literal string; `SYN-1001`, `SYN-1002` rows unchanged; UI shows the literal text. |
| G11 | Edit a PUBLISHED item (`SYN-1001`) as editor and publisher | 409 `item_published`; row unchanged; UI shows the lock note and no edit form. |
| G12 | Missing target: GET/PATCH/publish `SYN-9999` as editor | 404 `not_found` each; no row `SYN-9999` exists afterwards; row count unchanged; same-shape error body as G03's hidden draft. |
| G13 | DB adapter: insert / update / delete / unknown id (fresh DB file) | insert returns id 4, count 3 -> 4; duplicate SKU raises `DuplicateRecordError` and keeps the original row; update `id=1` to 25 -> affected rows 1, value 25, other rows unchanged; update id 999 -> 0 affected, no row created; delete id 3 -> 1 affected, count 2; delete id 999 -> 0; apostrophe name `O'Brien` stored literally; negative quantity -> `ConstraintViolationError`, value unchanged; exception inside `transaction()` rolls back. |
| G14 | JOIN and foreign keys (read-only fixture) | `get_detailed_orders()` == `[(1, "Synthetic Customer A", "Synthetic Widget", "Seeded published item A", "2026-01-15")]`; inserting an order with `customer_id=999` or `item_id=999` raises `ConstraintViolationError` and leaves 1 order; `PRAGMA foreign_keys` is 1; the join result is identical on every fresh DB (no dependence on other tests). |
| G15 | Timeout and malformed responses (test-only routes, test fixture only) | slow route with client read timeout 0.3 s -> `ApiTimeout` raised in < 2.5 s; invalid JSON body -> `ApiMalformedResponse`; JSON array where an object is required -> `ApiMalformedResponse`; 500 -> `ApiHttpError(status=500)`; closed port -> `ApiConnectionError`; never a successful-looking return. Default app: `/__test__/*` -> 404. |
| G16 | Isolation and teardown | two server+DB fixtures in one test start from the original seed, a mutation in one is invisible in the other; two consecutive test runs see the original seed; a test body that fails and a fixture setup that fails both leave: server port closed, temporary DB directory removed, an unrelated foreign file in the parent directory untouched. |

## Test layers and tooling

| Layer | Location | Runs against | Notes |
|---|---|---|---|
| Framework/fixture examples | `tests/framework/` | in-memory | educational successor of the 2023 fixture tests; G16 |
| DB adapter | `tests/database/` | fresh temporary SQLite files | G13, G14 |
| REST | `tests/api/` | real localhost HTTP server | `CatalogClient` plus direct `requests`; G01-G12, G15 |
| Selenium smoke | `tests/ui_selenium/` | real headless Chrome + real localhost server | replaces the 2023 login POM tests; G01, G02 |
| Playwright | `tests/ui_playwright/` | real headless Chromium + real localhost server | broad UI coverage; G01-G12 UI aspects |
| Cross-layer | `tests/e2e/` | browser -> API -> SQL | at least three complete flows, including a rejection with no DB write |

Flask's test client is *not* used for acceptance. Waits are explicit (`WebDriverWait`, Playwright auto-waiting `expect`) and bounded; there are no sleep-based synchronizations. Retries are never used; the first-run result is the result.

## Entry and exit criteria

* Entry: contract and golden values committed; clean venv created from the pinned lock file.
* Exit: all collected tests executed with 0 failures, 0 xfail, 0 unexplained skips; Selenium and Playwright suites executed on Chromium; 23 seeded mutants (12 planned originally, 13 in v1.0, 23 in v1.0.1) each caught by a pre-existing assertion; baseline green before and after; JUnit XML and HTML produced.

## Out of scope

Inventory allocation, checkout, payment, shipping, order state machines, order UI/API, other browsers/OSes (reported as unverified), load or security testing.
