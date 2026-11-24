# Guided learning path

Goal: let the author understand, run, extend and explain every part of this repository without the AI conversation. Roughly 30-40 hours in total; each stage ends with the exercises in `EXERCISES.md` (answers are in the separate `ANSWER_KEY.md` - try first). You can say you *understand* a stage only after you did its exercises without peeking.

Stage 0 is a reminder: lines marked **2023** come from the original project the author wrote during a QA automation course; lines marked **2026** belong to the modernization, which was carried out with AI assistance (`DEVELOPMENT_HISTORY.md`) and must be learned before any skill is claimed.

| # | Stage | Read / run in this repository | Practice | Time | Exercises |
|--:|---|---|---|---|---|
| 1 | Python basics used here | `modules/config.py`, `tests/support/golden.py`, `sandbox/validation.py` (functions, dicts, type hints, `from __future__ import annotations`) | Explain what `validate_item` returns for 3 inputs of your own | 3 h | E01 |
| 2 | pytest: fixtures and markers | **2023** idea (fixture lifecycle), now re-implemented as the `tally` fixture in `conftest.py`; `tests/framework/test_fixture_examples.py`; `pytest.ini` markers; `tests/support/plugin.py` | Run `pytest -m check`, `pytest -m "api and negative"`; read `--strict-markers` effects | 4 h | E02, E10 |
| 3 | Requests and HTTP | `modules/api/clients/catalog.py`, `tests/api/test_http_basics.py`, `docs/API_CONTRACT.md` | Call the sandbox with `curl` while `python -m sandbox` runs; map each status code to the contract | 4 h | E03, E09 |
| 4 | SQL and the adapter | **2023** idea: `Database`; now `modules/common/database.py`, `tests/database/`, `tests/support/observer.py`, `sandbox/schema.sql` | Write the JOIN by hand in `sqlite3`; try the f-string bug on a scratch DB | 5 h | E04, E05 |
| 5 | Selenium and the Page Object | **2023** idea: `BasePage`/`SignInPage`; now `modules/ui/page_objects/`, `tests/ui_selenium/` | Break a locator, read the timeout, repair it | 4 h | E06, E11 |
| 6 | Playwright | `modules/ui/playwright_pages/pages.py`, `tests/ui_playwright/`, `tests/support/pw_plugin.py` | Run one test headed (`--headed`) and watch it; add a test | 5 h | E07, E08 |
| 7 | Cross-layer assertions | `tests/e2e/test_cross_layer.py`, `tests/support/observer.py` | For one flow write down the three independent observations | 3 h | E04 (second part), E12 |
| 8 | Reporting, mutation and CI | `tools/run_evidence.py`, `tools/mutation_runner.py`, `docs/QA_REPORT.md`, `docs/MUTATION_REPORT.md`, `.github/workflows/ci.yml` | Run one mutant, read the report, explain assertion vs infrastructure failure | 4 h | E09 (mutant), E12 (CI) |

## How to study a test
1. Read its name (what behaviour). 2. Find the literal expected value in `golden.py` or the contract. 3. Find where the independent observation comes from (observer SQL). 4. Break the application in a scratch copy and see which assertion fails (`tools/mutation_runner.py --only Mxx`). 5. Explain it aloud in two sentences - that is the interview answer.

## Honesty rule for your CV and interviews
The 2023 project is the author's own work, written during a QA automation course. The 2026 modernization (sandbox, Playwright suite, mutation checks, reports) was carried out with AI assistance and was not implemented entirely by hand. Say so accurately, and describe a technology as "used in a project" until you have shown it unaided (an unaided exercise set kept in the author's own notes). See `DEVELOPMENT_HISTORY.md` for the accurate account.
