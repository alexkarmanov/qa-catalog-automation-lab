# Answer key (separate from the exercises - try first)

Code blocks marked `# verified` were executed during the project (copied into a scratch test file and run against the real suite).

## E01
`validate_item(..., "create")` reports: `sku` -> `bad_format` ("ab" is lowercase), `name` -> `empty` (whitespace only), `quantity` -> `wrong_type` (a boolean is not an integer). Nothing else is reported because `description` is optional on create.

## E02 (counts measured on the 520-test suite)
```bash
python -m pytest -m "api and negative" --collect-only -q | tail -1   # 159 selected
python -m pytest -k g08 --collect-only -q | tail -1                  # 6 selected (names containing g08)
python -m pytest -m golden --collect-only -q | tail -1               # 159 selected (every test with a golden marker)
```
The marker `golden("G08")` has an argument, and `-m` matches only the marker *name*, so a single scenario is selected with `-k` on the test names (they all start with `test_g08_`). The numbers change when tests are added; the current ones are in `QA_REPORT.md`.

## E03 (verified)
```python
import pytest
from tests.support import golden

@pytest.mark.api
def test_viewer2_reads_zero_quantity_item(client_factory):
    viewer2 = client_factory("viewer2")
    item = viewer2.get_item("SYN-1002")
    assert item["quantity"] == 0          # zero is a valid value, not "missing"
    assert item["state"] == "PUBLISHED"
    assert item == golden.ITEM_1002
```

## E04 (verified)
```python
import pytest

@pytest.mark.api
@pytest.mark.negative
def test_negative_quantity_edit_is_rejected_without_db_change(editor, observer):
    before = observer.items()
    resp = editor.request("PATCH", "/api/v1/items/SYN-2001", {"quantity": -3})
    assert resp.status == 400
    assert resp.error_code == "invalid_request"
    assert {"field": "quantity", "code": "out_of_range"} in resp.body["error"]["fields"]
    assert observer.items() == before     # exact table snapshot before == after
```
Second part: the status, the error code and the field error are the **API** observation; the snapshot comparison is the **DB** observation; the UI observation would be a form submission showing "quantity must be between 0 and 1000000" (see the Playwright G09 test). A rejection test is only convincing if the DB observation is there.

## E05 (verified)
```python
import pytest
from modules.common.database import Database

NAMES = ["O'Brien", 'say "hi"', "a;b", "100%", "under_score", "Ünïcode ☃", "n" * 80]

@pytest.mark.database
@pytest.mark.parametrize("name", NAMES, ids=["apostrophe", "quotes", "semicolon", "percent", "underscore", "unicode", "len-80"])
def test_names_are_stored_literally(db_path, observer, name):
    with Database(db_path) as db:
        db.insert_item("SYN-P1", name, "", 1)
    row = observer.item("SYN-P1")          # the observer uses its own SQL
    assert row[2] == name
```

## E06
`expect(catalog.rows).to_have_count(2)` still passes (that locator does not use `data-sku`), then `AssertionError: Locator expected to have text 'Synthetic Widget'` fails after the bounded `expect` timeout of about 5 s; the message ends with a page snapshot showing the table rows are present but the locator matched nothing. The screenshot is `artifacts/failures/tests_ui_playwright_test_login_ui.py_test_g02_viewer_sees_the_published_catalog_and_logout_rejects_further_access_chromium_.png`, written by the hook in `conftest.py`. (This was executed once during the project and the file was restored from Git.) Right fix: restore `data-sku` - the attribute names are part of the contract in `docs/API_CONTRACT.md` section 6. A `sleep` would not help: the element would never match. Lesson: when a locator breaks, compare it with the contract/DOM first; stable `data-*` attributes exist so cosmetic changes do not break tests.

## E07 (verified)
```python
import pytest
from playwright.sync_api import expect
from modules.ui.playwright_pages.pages import CatalogPage

@pytest.mark.playwright
@pytest.mark.negative
def test_viewer_has_no_new_item_link_and_form_is_forbidden(page, server, sign_in):
    sign_in(page, "viewer1")
    expect(CatalogPage(page, server.url).new_item_link).to_have_count(0)
    assert page.goto(server.url + "/items/new").status == 403
```

## E08
```python
import pytest
from playwright.sync_api import expect
from modules.ui.playwright_pages.pages import CatalogPage, ItemPage
from tests.support import golden

@pytest.mark.playwright
def test_viewer_context_sees_new_row_after_reload(page, new_session, server, sign_in, client_factory):
    client_factory("editor1").create_item(golden.NEW_ITEM)
    viewer_page = new_session()
    sign_in(viewer_page, "viewer1")
    sign_in(page, "publisher1")
    item = ItemPage(page, server.url).go_to("SYN-NEW")
    item.publish_button.click()
    expect(item.state).to_have_text("PUBLISHED")
    viewer_page.reload()
    expect(CatalogPage(viewer_page, server.url).row("SYN-NEW")).to_have_count(1)
```
The second context must be independent (own cookies) - otherwise the "viewer" would simply be the publisher and the test would prove nothing about what a different user sees.

## E09
`python tools/mutation_runner.py --only M03 --out ...` shows M03 = "editor can publish": `sandbox/policy.py` line `PUBLISH_ROLES = frozenset({"publisher"})` becomes `frozenset({"editor", "publisher"})`. The first failing test is `test_g06_editor_cannot_publish_and_the_draft_stays_hidden`, the assertion `assert resp.status == 403` fails (the server answered 200). It is an *assertion* failure because the test ran to its assertion and the observed value differed from the literal expectation; an *infrastructure* failure would be an error in a fixture or collection (for example the server not starting), which is never counted as detection.

## E10 (verified)
```python
import socket
import pytest
from sandbox.server import start_server

def closed(host, port):
    with socket.socket() as s:
        s.settimeout(1.0)
        return s.connect_ex((host, port)) != 0

@pytest.fixture
def good(db_path):
    srv = start_server(db_path)
    try:
        yield srv
    finally:
        srv.stop()

def test_detects_a_leak(db_path):
    srv = start_server(db_path)                 # simulates the leaky fixture body
    host, port = srv.host, srv.port
    assert not closed(host, port)               # still open -> this is the leak
    srv.stop()
    assert closed(host, port)
```
The fixed fixture is `good` (yield inside `try`, stop in `finally`) - the same shape as `server` in `tests/support/plugin.py`.

## E11 (verified)
```python
# modules/ui/page_objects/catalog_page.py
    def skus(self):
        return [row.get_attribute("data-sku") for row in self.driver.find_elements(*ROWS)]
```
Put the test in `tests/ui_selenium/` (the `chrome` fixture lives in that folder's `conftest.py`).
```python
import pytest
from modules.ui.page_objects.catalog_page import CatalogPage
from modules.ui.page_objects.sign_in_page import SignInPage

@pytest.mark.selenium
def test_editor_sees_three_skus(chrome, server):
    SignInPage(chrome, server.url).go_to().try_login("editor1", "TESTONLY-editor1")
    page = CatalogPage(chrome, server.url).wait_loaded()
    assert page.skus() == ["SYN-1001", "SYN-1002", "SYN-2001"]
```

## E12
(a) M06 is "duplicate SKU overwrites the original": `INSERT` became `INSERT OR REPLACE`. The assertion that failed in the G08 test is `assert resp.status == 409` (the server answered 201). It violates the contract row "POST /api/v1/items ... 409 `duplicate_sku` (existing row unchanged)" and golden scenario G08. (b) The `Lint` step (`ruff check .`) fails the job on any finding because the step's exit code is non-zero and later steps do not run; the workflow has no `continue-on-error` and no rerun plugin, so a flaky or failing test is reported, never hidden.

## E13
`ApiTimeout`: the server accepted the connection but did not send the response within the read timeout (0.3 s). `ApiConnectionError`: the TCP connection itself could not be established (refused/reset) - for example the server was stopped. Diagnosis differs: a timeout means a slow or stuck handler (look at server logs, the slow query), a connection error means the service is down or the URL/port is wrong.
