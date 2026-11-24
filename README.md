# Catalog QA Automation Lab

A personal Python/pytest portfolio project that tests a local catalog through the browser, REST API and SQLite. The catalog has three user roles and a draft-to-published workflow.

**Start with the [end-to-end publishing test](tests/e2e/test_cross_layer.py).** After an authorized user publishes a draft, a fresh viewer session sees the item, the REST API returns it as published, and a read-only SQL check confirms the persisted state. A separate [negative API test](tests/api/test_negative_api.py) checks both the 403 response and that the database stayed unchanged.

[Successful GitHub Actions run](https://github.com/alexkarmanov/qa-catalog-automation-lab/actions/runs/45311088885) · [Test plan](docs/TEST_PLAN.md) · [Requirements traceability](docs/TRACEABILITY.md) · [Architecture](docs/ARCHITECTURE.md)

![Viewer sees the published item in WebKit](docs/evidence/run/screenshots_webkit/e2e_03_viewer_sees_published_item.png)

## Verified results

| Check | Result |
| --- | --- |
| Full suite | 520 tests passed on Ubuntu 24.04 with Python 3.11, 3.12 and 3.13. The suite includes Selenium Chrome smoke tests. |
| Cross-browser scenarios | Playwright UI and end-to-end suites passed on Chromium, Firefox and WebKit in Linux CI. |
| Test effectiveness | The original macOS verification caught all 26 deliberately seeded defects with existing assertions. See the [mutation report](docs/MUTATION_REPORT.md). |
| Code checks and evidence | Ruff, mypy and the final CI gate passed. See the [QA report](docs/QA_REPORT.md), [reporting guide](docs/REPORTING.md) and [sample failure diagnostics](docs/evidence/diagnostics/INDEX.json). |

The hosted run verified commit `ff4c656` on November 23, 2026. The [CI workflow](.github/workflows/ci.yml) generates JUnit, HTML and browser diagnostics. Historical macOS results and current scope are documented in [Limitations](docs/LIMITATIONS.md).

## Run the end-to-end tests

Run these commands from the repository root. On Ubuntu, use `python -m playwright install --with-deps chromium` to install the system dependencies too.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --require-hashes -r requirements.lock.txt
export PLAYWRIGHT_BROWSERS_PATH="$PWD/.pw-browsers"
python -m playwright install chromium
python -m pytest tests/e2e -q
```

Run `python -m pytest` for the full suite. This also needs Google Chrome and a working Selenium driver. The test fixtures start the local Flask service and create a fresh database. Use `python -m sandbox` to explore manually with [synthetic test accounts](docs/DATA_DICTIONARY.md).

## Project background

The original project was independently written during a QA automation course in 2023, with general architectural guidance from the instructor. The 2026 modernization was carried out under the author's direction with AI assistance. The [development history](docs/DEVELOPMENT_HISTORY.md) records that contribution. The catalog is a synthetic test target for a personal portfolio.
