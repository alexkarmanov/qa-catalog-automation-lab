# Defects found and fixed during development

Real defects in the 2026 code, found by the tests while building this project (not the seeded mutants, which are reported in `MUTATION_REPORT.md`). Not customer defects.

| ID | Found by | Defect | Fix |
|---|---|---|---|
| DEV-01 | `tests/api/test_auth_api.py::test_logout_without_session_is_rejected` (first run) | `CatalogClient.request(expect_json=False)` discarded the body of error responses, so the typed error carried no error code. | Error bodies (status >= 400) are now parsed even when a JSON success body is not expected. |
| DEV-02 | Test run speed (111 API tests took 60 s) | `RunningServer.stop()` waited up to the 0.5 s default poll interval of `serve_forever` on every shutdown. | `serve_forever(poll_interval=0.02)`; the same suite now takes under 5 s. |
| DEV-03 | `tests/framework/test_isolation_teardown.py::test_g16_failed_start_leaves_no_thread_behind` (first run) | When the port was taken, Werkzeug called `sys.exit(1)`, so `start_server` raised `SystemExit` instead of a normal `OSError`. | `start_server` converts it to `OSError` and leaves no thread behind. |
| DEV-04 | pytester isolation tests (first run) | Inner pytest sessions could not import the project (infrastructure error, not a product defect). | The test sets `PYTHONPATH` for the inner subprocess. |
| DEV-05 (test gap) | First full mutation run, mutant M06 | Only one of the G08 tests failed under "INSERT OR REPLACE": the seeded order references `SYN-1001`, so the foreign key accidentally turned the REPLACE into a 409 for that SKU and the SYN-1001 duplicate tests did not notice the defect. | The duplicate-SKU test is now also parametrized over `SYN-1002` (an item without orders); the draft-SKU test was already catching it. A gap in the *tests*, found by mutation testing, not a product defect. |
| DEV-06 | Scripted UAT step U08 (first run) | An unused import in `tools/uat.py` made `ruff` fail after the tool was written (lint was last run before that file existed). | Import removed; UAT repeated. |

## External audit findings fixed in v1.0.1

Found by an independent audit of the v1.0 package (an AI assistant working from the supplied ZIP in a Linux/Python 3.13 sandbox with limited packages; its own results are summarized in `LIMITATIONS.md`). Each finding was reproduced, fixed, covered by regression tests and, where practical, by a seeded mutant (M14-M23).

| ID | Defect | Fix | Regression tests / mutants |
|---|---|---|---|
| KQA-001 | SQLite URI built by escaping only `?`: a path with `#` or `%` could open a different database, and a "read-only" connection then modified it. Same flaw in the independent Observer. | `sqlite_file_uri()` percent-encodes the absolute path and sets an explicit mode; the Observer has its own stdlib implementation. | `tests/database/test_uri_paths.py` (spaces, Unicode, `#`, `%`, `?`, relative paths, no file created); M14, M15 |
| KQA-002 | `validate_item` accepted `"SYN-X\n"` (`$` matches before a trailing newline); `schema.sql` allowed `sku='x'` and `quantity=1000001`; Content-Type handling was described as protection but not enforced. | Full-match SKU everywhere; schema CHECKs mirror the contract; the contract now states that the media type is not enforced. | `tests/database/test_schema_constraints.py`, `tests/api/test_request_validation_contract.py`; M16, M17, M18 |
| KQA-003 | Typed client accepted `{"items": null}`, `"not a list"`, `[123]`, `[{"sku": "only"}]`; a 500 with `{"error": "wrong shape"}` raised `AttributeError`. | Shape verification for every typed operation; controlled `ApiHttpError` for malformed error envelopes. | `tests/api/test_client_response_shapes.py` (fixtures and a scripted loopback stub); M19, M20 |
| KQA-004 | `build_reports.py` exited 0 with `mutants=[]` or `steps={}`. | `tools/evidence_check.py`: exact mandatory step population, consistent counts and exit statuses, exact mutant IDs and baselines; validate-then-stage; STALE banner on failure. | `tests/framework/test_evidence_fail_closed.py`; M21 |
| KQA-005 | `verify_inventory` ignored the manifest size; a ZIP with two `README.md` entries passed `clean_verify.py`. | Size and SHA-256 are both verified; entries are validated (duplicates, ambiguous or unsafe paths, special files, encryption) before extraction. | `tests/framework/test_package_tools.py`; M22, M23 |
| KQA-006 | Stale counts in the learning material; wording that could be read as confirmed independent authorship of the 2023 code; a machine host name in the exported JUnit. | Counts checked by a test; provenance layers stated; evidence scrubbed on generation and re-checked at packaging. | `tests/framework/test_docs_consistency.py`, `test_package_tools.py` |

Note: v1.0 remains in Git history and in the v1.0 ZIP, which contain the host name attribute; history was deliberately not rewritten.

## Remaining audit findings fixed in v1.0.2

| ID | Defect | Fix | Regression tests / mutants |
|---|---|---|---|
| KQA-007 | `separate_processes` evidence accepted a skipped test in a layer when the grand total of collected tests stayed the same. | Each mandatory layer must pass **all** of its expected tests (the expected count comes from the first run), with zero skips, failures and errors; browser runs are checked the same way. | `test_evidence_fail_closed.py` (`layer_skip`, `layer_shifted_tests`, `browser_step_skipped_test`); M24 |
| KQA-008 | A malformed `mandatory_steps` field (an integer) raised `TypeError` inside the checker before the reports could be marked STALE. | Structures are validated before iteration (`_str_list`); the checkers never raise on malformed input; the generator turns any unexpected error into a controlled non-zero exit and stale-marks the reports. Adjacent boundaries reviewed and covered: negative and boolean counts, malformed lists, duplicate identifiers (steps, failures, test ids, mutant ids), inconsistent totals. | `test_evidence_fail_closed.py` (30+ tamper cases and garbage-input unit tests); M25, M26 |

Also in v1.0.2: the whole documented project baseline moved to maintained Python versions (3.11+), the hash-locked dependency set was re-resolved and verified on 3.12, the CI workflow was modernised, and real Allure reports, failure diagnostics and a publication candidate were added (see `CHANGELOG.md`).

