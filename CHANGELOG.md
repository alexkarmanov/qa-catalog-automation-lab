# Changelog

## 1.0.2 - initial public snapshot
First public version of the project, prepared as a clean, independent snapshot. It contains the sandbox application, adapters, page objects, the test layers
(framework, database, API, Selenium, Playwright, cross-layer), the tooling for evidence, mutation checks, reports and publication auditing, a hash-locked dependency
set for Python 3.12 and a CI workflow that has not yet run on a hosted service. The project was originally written by the author in 2023 and modernized in 2026 with AI assistance (Claude); `docs/DEVELOPMENT_HISTORY.md` records who did what, and
`docs/LIMITATIONS.md` what is and is not verified.

Earlier, private releases (1.0 - 1.0.1) fixed audit findings in SQLite URI handling, validation and schema constraints, typed client verification, fail-closed
evidence reporting and package verification (`docs/DEVELOPMENT_DEFECTS.md`).
