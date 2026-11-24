# First hosted CI run - instructions (nothing has been run hosted)

**Status: the workflow `.github/workflows/ci.yml` has never been executed on GitHub Actions.** Nothing may be described as "CI passing" and no badge
may be added before a real run has passed. Running it needs an explicit decision by the repository owner, because it means pushing the repository (or
the publication candidate) to a GitHub repository.

## What was verified locally instead

| Check | Result |
|---|---|
| Workflow syntax against the published GitHub workflow JSON schema (`check-jsonschema --builtin-schema vendor.github-workflows`) | valid |
| Structural properties pinned by `tests/framework/test_ci_workflow.py` | gate job needs all jobs and fails on any non-success; no `continue-on-error`; artifacts uploaded with `if: always()`; hash-locked install only; maintained Python versions only |
| Every command of the workflow run by hand (macOS, Python 3.12): lint, types, full suite with JUnit/HTML/Allure/trace flags, Playwright Chromium and WebKit scenarios | see `QA_REPORT.md` |
| Linux runner, Python 3.11 and 3.13, Playwright Firefox, Selenium Chrome on Linux, `--with-deps` OS packages | **not verified** (no Linux machine or container here; Firefox could not even launch on the macOS machine) |

## Jobs

* `lint-types` - ruff and mypy on Python 3.12.
* `tests` - the complete suite on Python 3.11, 3.12 and 3.13 (Chromium through Playwright, Chrome through Selenium), JUnit, HTML, Allure results, traces and screenshots on failure.
* `browsers` - the same Playwright business scenarios (`tests/ui_playwright`, `tests/e2e`) on Chromium, Firefox and WebKit.
* `ci-gate` - fails the workflow unless every job above succeeded.

## How to run it the first time (after explicit approval)

1. Create an empty repository in the target account, for example `qa-catalog-automation-lab`.
2. Create a **private** repository first if you want a dry run; the workflow does not need a public repository.
3. Initialise a new repository from the publication candidate (`git init -b main`, `git add .`, `git commit`, `git remote add origin <URL>`, `git push -u origin main`), never from any private history.
4. Open *Actions -> ci -> Run workflow* (it has a `workflow_dispatch` trigger) or push a commit.
5. Download the `reports-*` artifacts (JUnit, HTML, Allure results, traces) and compare the totals with `QA_REPORT.md`.

## What to expect and how to react

* Python 3.11/3.13 or Firefox may fail on their first hosted run: that is the honest result, not a flaky workflow. Fix the cause or remove the entry; do not mark it `continue-on-error`.
* Action versions (`actions/checkout@v4`, `actions/setup-python@v5`, `actions/upload-artifact@v4`, `browser-actions/setup-chrome@v1`) are major-version pins that were current when this was written; bump them if a run warns about deprecation.
* After a *real* green run, record the run URL and date in `docs/QA_REPORT.md`, then (and only then) add a badge to the README.
