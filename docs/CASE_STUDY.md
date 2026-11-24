# Case study - modernizing a personal QA automation project (2023 to 2026)

**Situation.** In early 2023 the author wrote a small Python/pytest project while taking a QA automation course (the instructor gave general architectural guidance): an API client, a SQLite helper, a Selenium page object and 22 tests. It used live GitHub endpoints and the live GitHub login page, a database file with hard-coded personal paths, and had no README, dependency list or CI.

**Problem.** Read again as an engineer in 2026, the suite could not be trusted: results depended on the internet, the UI tests could not start (path bug), a rejected login was "proved" by the page title, tests mutated one shared database, and two tests could not fail at all.

**Approach (2026).** The historical state was frozen (tag, full history, verified backup), every file and all 22 tests were reviewed, and a decision was written down for each. Before any code was written a test plan, an API/UI contract and literal expected values were committed. Then a tiny synthetic target was built (login, roles, draft/published catalog) so that browser, REST and SQL tests exercise the same controlled system - no external calls. The modernization was done with AI assistance (Claude); [DEVELOPMENT_HISTORY.md](DEVELOPMENT_HISTORY.md) records what was done and how.

**Result.** 520 tests (REST over real HTTP, adapter tests on fresh SQLite files, isolation tests of the suite itself, Selenium smoke, Playwright suite on Chromium and WebKit, four cross-layer flows) pass from a clean install; 26 seeded defects are each caught by a pre-existing assertion; reports (JUnit XML, HTML, Allure, screenshots, traces) come from real runs. Numbers are in `QA_REPORT.md` and `MUTATION_REPORT.md`.

**Engineering ideas that carried the project.** Independent expected values, "no change" proofs for rejected requests, per-test isolation, bounded waits, evidence checks that fail closed, and a seeded-defect check that proves the tests detect defects.

**Honest limits.** One verified environment (macOS, Python 3.12), Playwright Firefox could not be run on the development machine, hosted CI has not run, and the target's security policy is deliberately simplified and synthetic. It is a personal portfolio project, not commercial experience; see `LIMITATIONS.md`.
