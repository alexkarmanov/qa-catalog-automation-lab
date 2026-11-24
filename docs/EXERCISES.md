# Practical exercises (answers are in `ANSWER_KEY.md`)

Work in a scratch copy (`cp -R` the repository without `.venv`) or on a branch. Run commands from the repository root with the virtualenv active. Mark each exercise done only when its check passes.

**E01 - Read a validator.** Without running anything, predict the result of `validate_item({"sku": "ab", "name": " ", "quantity": True}, "create")`: which fields fail and with which codes? Then check in a Python shell.

**E02 - Marker selection.** Run only the tests that carry both `api` and `negative`, then only the `golden("G08")` tests. Write the two commands and the number of tests selected by each.

**E03 - Write an API test.** Add `tests/api/test_exercises.py` with a test that logs in as `viewer2` and asserts that `SYN-1002` has quantity `0` (zero is valid, not missing) and state `PUBLISHED`, using the `client_factory` fixture and the golden literals.

**E04 - Prove that a rejected request made no database change.** Write a test in which `editor1` sends `PATCH /api/v1/items/SYN-2001` with `{"quantity": -3}`. Assert the exact status, the error code and the field error, and prove with `observer.items()` (before/after) that nothing changed. *Second part:* explain which of the three observations (UI, API, DB) each of your assertions covers.

**E05 - Parameterize SQL.** Write a parametrized test for `Database.insert_item` that stores these names literally: `O'Brien`, `say "hi"`, `a;b`, `100%`, `under_score`, `Ünïcode ☃`, and an 80-character name. After each insert check the stored value with the observer's SQL, not with an adapter method.

**E06 - Repair an unstable locator.** In `modules/ui/playwright_pages/pages.py`, method `CatalogPage.row`, change the attribute selector `data-sku` to `data-id` (in your scratch copy) and run `pytest tests/ui_playwright/test_login_ui.py -k g02_viewer_sees`. Read the failure: which assertion fails, what does the message contain, how long did the test wait, and where is the failure screenshot? Repair it the right way (restore the contract attribute; do not add a sleep).

**E07 - Add a Playwright test.** A viewer must not see the "New item" link on the catalog page and a direct request to `/items/new` must return 403. Write the test with `expect(...)` (no sleeps) and the `sign_in` fixture.

**E08 - Two browser sessions.** Write a test that signs in as `publisher1` in one browser context and `viewer1` in another, publishes `SYN-NEW` (created through the API first) and shows that the viewer's page *after a reload* contains the new row. Why must the second context be independent?

**E09 - Debug a seeded mutant.** Run `python tools/mutation_runner.py --only M03 --out /tmp/m03` (use a directory of your own). Read `mutation_results.json`: which test failed first, what was the assertion message, and why is that an *assertion* failure and not an *infrastructure* failure? Then find the exact line that M03 changes and explain the bug in one sentence.

**E10 - Fix a fixture leak.** Here is a leaky fixture: `@pytest.fixture def leaky(db_path): return start_server(db_path)` (no `stop`). Write a test that detects the leak (hint: remember `srv.host`/`srv.port` and check that connecting fails after teardown, as `tests/framework/test_isolation_teardown.py` does), then fix the fixture with `yield` and `try/finally`.

**E11 - Selenium page method.** Add `CatalogPage.skus()` to `modules/ui/page_objects/catalog_page.py` returning the displayed SKUs in order, and a Selenium test (in `tests/ui_selenium/`, where the `chrome` fixture is defined) using it for `editor1` (expects the three seeded SKUs including the draft).

**E12 - Interpret a failure and a CI run.** (a) Take the first-failing-assertion line of M06 in `docs/MUTATION_REPORT.md` and say what behaviour broke, which contract row it violates and which golden scenario covers it. (b) Read `.github/workflows/ci.yml`: which step would turn the job red if `ruff` found an error, and why does the workflow not hide failures with retries?

**E13 - Diagnose a timeout.** Start the sandbox with test routes in a Python shell (`start_server(db, test_routes=True)`), call `CatalogClient(..., Settings(read_timeout=0.3)).request("GET", "/__test__/slow", params={"seconds": 5})` and explain the exception you get. What is the difference between `ApiTimeout` and `ApiConnectionError`?
