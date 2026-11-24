# SPEC - karmanovqaauto 1.0 (Reproducible UI, API & Database Test Automation)

## Purpose
Modernize the author's 2023 Python QA automation project into a maintainable, reproducible test-automation portfolio that is honest about its origin and history. It is a **personal portfolio project**, not commercial experience, a security product or a new test runner.

## Requirements (R-IDs are traced to tests in `TRACEABILITY.md`)

| ID | Requirement |
|---|---|
| R-01 | The historical baseline is preserved (tag, full history, private verified backup) and the modern branch descends from it. |
| R-02 | Every historical source file and all 22 historical test functions have a recorded decision (preserved/replaced/retired) with a reason. |
| R-03 | No automated test contacts a live third-party service; the target is a local synthetic sandbox bound to loopback on a random free port. |
| R-04 | A failing login is shown as a meaningful rejection (visible message, no session, protected endpoint refuses) - not by page title. |
| R-05 | Role-dependent catalog visibility: anonymous sees nothing; viewer sees PUBLISHED only; editor/publisher also see DRAFTs. |
| R-06 | Unauthorized or invalid mutations are rejected with the frozen status/error code and cause no database change. |
| R-07 | Only a publisher can publish a valid draft; published items are immutable in v1; the change is visible only after the committed publish. |
| R-08 | SKU uniqueness is enforced by the database; duplicates are a 409 conflict and never overwrite. |
| R-09 | Strict input schema: bad types, booleans as integers, out-of-range numbers, empty names, unknown fields and malformed JSON are rejected. |
| R-10 | The database adapter keeps the 2023 CRUD concepts safely: parameterized values (apostrophes), affected-row counts, no silent replace, foreign keys, rollback, JOIN. |
| R-11 | The REST client has bounded timeouts and typed failures; a timeout or malformed response never looks like success. |
| R-12 | Every test has an isolated database and server; failed set-up or failed body still releases the owned resources and leaves foreign files alone. |
| R-13 | Real browsers: Playwright (Chromium) is the primary E2E layer and a small Selenium 4 suite replaces the historical login Page Object test. |
| R-14 | At least three complete browser -> API -> database flows, including a rejection with no database write. |
| R-15 | At least eight seeded defects are detected by pre-existing assertions; baseline is green before and after. |
| R-16 | JUnit XML, a readable HTML report, real screenshots and (optionally) Allure results are produced from actual runs. |
| R-17 | A clean extracted copy installs from the pinned manifest and passes; CI workflow configuration mirrors the local commands (not executed on a hosted service). |
| R-18 | Historical (2023) and modern (2026) work and results are kept separate; the AI involvement in the modernization is documented (`docs/DEVELOPMENT_HISTORY.md`). |

## Out of scope
Inventory allocation, checkout/payment/shipping, an order state machine or order UI/API, load/security/penetration testing, other browsers and operating systems (reported as unverified), a custom test runner or DSL, a release-gate engine, hosted CI execution, publication.

## Environment decision
Target runtime: Python 3.11+ per the brief. **Only Python 3.9.6 (macOS system interpreter, LibreSSL 2.8.3) was available**, so every claim in this repository is verified on 3.9.6 only; code is written to stay compatible with 3.9 (`from __future__ import annotations`, no `X | Y` runtime types). Compatibility with 3.11/3.12 is *expected but unverified*; the CI workflow lists 3.12 as an additional unverified matrix entry. See `LIMITATIONS.md`.

Sandbox framework: **Flask 3.1.3** with Werkzeug's development server. Why: server-rendered HTML and JSON with a few routes, signed form handling and standard password-hash primitives out of the box, one small maintained dependency set, and it runs in a thread for per-test servers. No separate frontend framework.
