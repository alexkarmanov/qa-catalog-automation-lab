# Test strategy

1. **Risk first.** The one policy worth protecting is catalog visibility and role-dependent publication (`TEST_PLAN.md`). Counts follow risk, not a quota. No coverage percentage is used as a substitute for risk coverage.
2. **Contract before code.** Plan, literal expectations, schema and API/UI contract were committed before any sandbox code (git history shows the order).
3. **Independent oracles.** Expected values are literals (`golden.py`) or come from the observer's own SQL. Expected values are never computed with the code under test.
4. **Negative paths prove "no change".** Every rejection test compares the full `catalog_items` table before and after.
5. **Layers.** Fast checks at the lowest layer that can see the behaviour (adapter, REST); browsers only for behaviour a user can see; a few complete cross-layer flows.
6. **Real everything for acceptance.** Real HTTP server on loopback, real SQLite files, real Chromium/Chrome. Flask's test client is not used. (Pure unit/mocked tests are only a supplement and none are needed here.)
7. **Determinism.** Per-test database and server, no shared mutable records, no fixed ports/paths, no order dependence (verified with reversed and separate-process runs), bounded waits, no retries.
8. **Markers.** `api`, `http`, `database`, `ui` (umbrella), `selenium`, `playwright`, `e2e`, `framework`, `negative`, `golden("Gnn")`; legacy `change`/`check` for the fixture teaching examples. `--strict-markers` is on.
9. **Evidence.** JUnit XML (machine), pytest-html (human), Allure results (optional), real screenshots, failure screenshots, a requirements-to-test table generated from the run.
10. **Failure classification.** *Assertion failure* = a test assertion caught a deviation. *Exception in the code under test* = the test body raised. *Infrastructure failure* = a fixture/setup error, collection error or crash; it is never counted as detection.
11. **Controlled defects.** 23 mutants (13 in v1.0, 10 more targeted at the v1.0.1 fixes) applied to throw-away copies; detection requires an assertion failure in a relevant test.
12. **Retries.** None. If a retry is ever added, first-run and retried results must be reported separately.
