# Architecture

## Layout (historical concepts kept)

```
karmanovqaauto/
  sandbox/                  synthetic target (app, store, validation, policy, schema.sql, seed, server)
  modules/
    api/clients/            catalog.py (CatalogClient), errors.py        <- was api/clients/github.py
    common/database.py      Database adapter                            <- was common/database.py
    ui/page_objects/        Selenium: base_page, sign_in_page, catalog_page  <- was ui/page_objects
    ui/playwright_pages/    Playwright page objects (primary UI layer)
    config.py               timeouts                                   <- was the empty config/config.py
  tests/
    support/                golden.py (independent expectations), observer.py (independent SQL), plugin.py, pw_plugin.py
    api/  database/  framework/  ui_selenium/  ui_playwright/  e2e/
  tools/                    mutation_runner, report/traceability builders, packaging, verification
  docs/                     contract, plan, audit, reports, learning material
```

## Test pyramid

```
            e2e                 browser -> API -> SQL, a few complete flows
        ui_playwright           real Chromium, broad UI coverage        ui_selenium: real Chrome smoke
      api over real HTTP        negative paths, boundaries, no DB delta
  database + framework          adapter on fresh SQLite files, isolation/teardown of the suite itself, tooling failure paths
```
The exact test counts per layer are generated into `QA_REPORT.md`.

## Data flow of one test

```
pytest fixture ──► tmp dir ──► sandbox.seed.create_database ──► caps.db (fresh file)
                                         │                          ▲   ▲
                    start_server(127.0.0.1:0) ◄────────────────────┘   │ read-only SQL
                          │  real HTTP                                  │
   CatalogClient ◄────────┤                              tests/support/observer.py  (independent oracle)
   Playwright / Selenium ◄┘                              tests/support/golden.py    (literal expectations)
```
The expected value of an assertion comes from `golden.py` or from the observer's own SQL, never from the code under test. The application's own query code (`sandbox/store.py`) and the adapter (`modules/common/database.py`) are separate implementations: the application is the system under test, the adapter is test-support code that is itself tested.

## Isolation rules
* One database file and one server per test; port 0 (OS-assigned); loopback only (non-loopback hosts raise `ValueError`).
* One browser context per test (Playwright) or one Chrome process per test (Selenium); always closed in `finally`/fixture teardown.
* No sleeps for synchronization: readiness is one bounded request, UI waits are `expect(...)` / `WebDriverWait` with explicit timeouts.
* No retries. The first run is the result.
* Failure and cleanup behaviour of the fixtures is itself tested (`tests/framework/test_isolation_teardown.py`).

## Controlled defects
`tools/mutation_runner.py` applies exact text patches to a throw-away copy of the project, runs the whole suite there and checks that a pre-existing assertion (not a crash) fails. The real tree is never modified.
