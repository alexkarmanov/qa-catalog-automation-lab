# Reporting - what is produced, how, and what each report proves

Every report below is generated from a real run. Nothing is hand-edited, no badge or screenshot is fabricated, and any report that fails its
consistency or privacy checks is not published (`tools/build_reports.py`, `tools/allure_report.py` and `tools/diagnostics_demo.py` exit non-zero instead).

| Report | Produced by | Where | What it shows |
|---|---|---|---|
| JUnit XML | `pytest --junitxml` (first run) | `docs/evidence/run/junit_first_run.xml` | one machine-readable result per test, with layer, golden scenario and markers as properties |
| pytest-html | `pytest --html --self-contained-html` | `artifacts/report.html` (generated locally or by CI) | readable single-file result list; failing browser tests embed a screenshot |
| Allure | `allure-pytest` results + `tools/allure_report.py` | `artifacts/allure-report/index.html` (generated locally) | Overview, Suites, Behaviors (layer -> golden scenario), Categories and an Environment widget with the real versions |
| Coverage | `pytest --cov --cov-branch` | `docs/QA_REPORT.md` section 4 | line and branch coverage of the target and of the test support code (a diagnostic, not an acceptance criterion) |
| Screenshots | the e2e tests and each browser run | `docs/evidence/run/screenshots*/` | the same four business scenarios captured by Chromium and WebKit (and Firefox where it can run) |
| Failure diagnostics | `tools/diagnostics_demo.py` | `docs/evidence/diagnostics/` | what a *failing* browser run leaves behind: failure screenshots, Playwright traces, the failing JUnit file and the Allure run summary |
| Mutation report | `tools/mutation_runner.py` | `docs/MUTATION_REPORT.md` | 26 seeded defects, each caught by an existing assertion, between two green baselines |
| Traceability | `tools/build_reports.py` | `docs/TRACEABILITY.md` | requirements and golden scenarios mapped to the tests that passed |

## Why Allure shows 518 test cases while JUnit shows 520

The JUnit file, the pytest-html report and `test_results.csv` list all 520 tests. Allure's Overview counts 518 because the three parametrized cases of
`test_non_json_bodies_are_rejected_regardless_of_content_type` (`form-body`, `empty`, `not-utf8`) take `bytes` parameters, which allure-pytest renders identically;
the generator therefore folds them into one test case (two of the three are shown as retries of it). All 520 raw result files exist (`artifacts/allure-results`)
and all 520 passed; nothing is hidden - this is a property of Allure's identity rule, recorded here instead of being left unexplained.

## Allure needs a Java runtime (not a project dependency)

The Allure CLI is a Java program. It is deliberately not part of `requirements.lock.txt`. To render the report from the results
(`artifacts/allure-results`, produced by `pytest --alluredir=artifacts/allure-results`):

```bash
# 1. Any Java 17+ runtime and the Allure 2 command line (free, from Maven Central), unpacked into a folder of your choice
export JAVA_HOME=/path/to/jre
export ALLURE_BIN=/path/to/allure-2.46.2/bin/allure
# 2. Scrub machine identifiers from the results and render a single-file report
python tools/allure_report.py --results artifacts/allure-results --out artifacts/allure-report --versions docs/evidence/run/versions.json
```

`tools/allure_report.py` replaces the `host` and `thread` labels and any private path in a *copy* of the results, refuses to overwrite an
existing report folder, and fails if the Allure CLI is missing, the generator fails or a private identifier is left in its input.
Open `artifacts/allure-report/index.html` in a browser (it is one self-contained file).

## Traces

`python -m playwright show-trace docs/evidence/diagnostics/playwright_trace_01.zip` opens the recorded timeline (actions, DOM snapshots, network)
of a failing test. The retained traces have scrubbed machine paths and omit bundled source snapshots from the trace viewer. The repository includes report summaries and screenshots. Generate interactive HTML reports locally or retrieve them from the private CI artifacts.
