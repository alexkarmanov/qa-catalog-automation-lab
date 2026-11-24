# Handover - how to operate and extend the project

All commands run from the repository root with the virtualenv active and `PLAYWRIGHT_BROWSERS_PATH` set as in the README. The reference environment is Python 3.12 with the hash-locked `requirements.lock.txt`.

## 1. Reproduce the results
```bash
python -m pytest -p no:cacheprovider --junitxml=artifacts/junit.xml --html=artifacts/report.html --self-contained-html
python tools/run_evidence.py --out artifacts/evidence_run      # first run, reversed/shuffled order, per-layer processes, Playwright Chromium/WebKit(/Firefox), xdist, coverage
python tools/mutation_runner.py                                 # 26 seeded defects on throw-away copies (about 15 minutes); run BEFORE build_reports
python tools/build_reports.py --evidence artifacts/evidence_run # fail-closed: validates everything first, then replaces QA_REPORT, TRACEABILITY, MUTATION_REPORT and evidence/run;
                                                                # on a problem it replaces nothing, marks the old reports STALE and writes docs/REPORT_GENERATION_FAILED.md
python tools/ci_check.py                                        # ruff + mypy + pytest, exit 1 if any step fails
```

## 2. Add a test
1. Decide the behaviour and write the **literal expected value first** (add it to `tests/support/golden.py` or the contract).
2. Pick the lowest layer that can see it: `tests/database` (adapter), `tests/api` (REST), `tests/ui_playwright` (user-visible), `tests/e2e` (needs all three observations).
3. Use the fixtures: `db_path`, `server`, `client_factory` / `anon` / `viewer` / `editor` / `publisher`, `observer` (independent SQL), `page` + `sign_in` + `new_session` (Playwright), `chrome` (Selenium, in `tests/ui_selenium`).
4. For a rejection test always compare `observer.items()` before and after.
5. Add markers (`api`, `negative`, `golden("Gnn")`...). Run `python -m pytest <your file> -q`, then the whole suite, then `python tools/mutation_runner.py --only <id>` if your test is meant to catch a defect.

## 3. Diagnose
| Symptom | What to do |
|---|---|
| **Timeout** (`ApiTimeout`, Playwright `expect` timeout, `TimeoutException`) | `ApiTimeout`: the server accepted but did not answer in `Settings.read_timeout`; reproduce with `curl -m 5` against `python -m sandbox`; look for a stuck handler. Browser: open the failure screenshot in `artifacts/failures/`, re-run the one test with `--headed`; confirm the locator against the DOM. Never fix with `sleep`; change the wait only with a reason. |
| **Database error** (`DatabaseError`, `ConstraintViolationError`, `DuplicateRecordError`, "database is locked") | Read the typed class: duplicate = UNIQUE, constraint = CHECK/NOT NULL/FK. Open a copy of the file with `sqlite3 "file:<db>?mode=ro"` and inspect `.schema`. "Locked" means two writers; the sandbox uses short per-request connections and a 5 s busy timeout - look for a connection left open in a test. |
| **Stale selector / broken locator** | Compare with `docs/API_CONTRACT.md` section 6 (`data-testid`, ids, `data-sku`). Fix the page object, not every test. See exercise E06. |
| **Fixture leak** (port still open, temp directory left, process left) | `tests/framework/test_isolation_teardown.py` shows the checks. Every fixture needs `try/finally`; run `pgrep -f chromedriver` after a run; `python tools/run_evidence.py` reports leftover driver processes. |
| **CI failure** | `python tools/ci_check.py` reproduces the job locally: it names the failing step and exit code. Lint/type failures are fixed in code (`ruff check . --fix`, `mypy`). A test failure: open `artifacts/junit.xml` or the HTML report. Never add reruns to hide it. |
| **Browser missing** | Playwright prints "Executable doesn't exist ... run playwright install" -> `python -m playwright install chromium` with the same `PLAYWRIGHT_BROWSERS_PATH`. Selenium: install Google Chrome; Selenium Manager fetches the driver. |

## 4. Safe working rules
* Do not commit `artifacts/`, `.venv/`, `.pw-browsers/` or any `*.db` (they are ignored).
