# Mutation (controlled defect) report

Each mutant is a set of exact text patches applied to a **throw-away copy** of the project (`tools/mutation_runner.py`); the real tree is never modified, so no mutated code can ship. These are *seeded* defects, not real customer defects.

Verdicts: `CAUGHT_BY_ASSERTION` = at least one pre-existing, relevant test failed with an assertion; `INFRASTRUCTURE_FAILURE` = fixture/collection error or crash (never counted as detection).


## Baseline and restoration

| Check | Result |
|---|---|
| Baseline before (unmodified copy) | exit 0, 520 tests, 0 failed |
| Baseline after (unmodified copy) | exit 0, 520 tests, 0 failed |
| Real tree unchanged (hashes of all 12 patched files) | yes |


## Results

| ID | Defect | Patched files | Intended tests (match) | Verdict | Failing tests | First failing assertion |
|---|---|---|---|---|---|---|
| M01 | accept invalid credentials | sandbox/app.py | test_g01_invalid_login_is_rejected_without_session; test_g01_invalid_login_shows_an_error; test_g01_invalid_login_is_rejected | CAUGHT_BY_ASSERTION | 9 | `test_g01_invalid_login_is_rejected_without_session[wrong-password]` - assert 200 == 401 |
| M02 | viewer can read drafts | sandbox/policy.py | test_g03_viewer_list_and_search_do_not_disclose; test_g03_viewer_direct_read_of_draft; test_g03_viewer_does_not_see_the_draft | CAUGHT_BY_ASSERTION | 13 | `test_g03_viewer_list_and_search_do_not_disclose_the_seeded_draft` - AssertionError: assert 'SYN-2001' not in ['SYN-1001', 'SYN-1002', 'SYN-2001'] |
| M03 | editor can publish | sandbox/policy.py | test_g06_editor_cannot_publish; test_g06_editor_has_no_publish_button | CAUGHT_BY_ASSERTION | 2 | `test_g06_editor_cannot_publish_and_the_draft_stays_hidden` - assert 200 == 403 |
| M04 | state is mutated by a forbidden request | sandbox/app.py | test_g04_viewer_mutations_are_forbidden_and_change_nothing; test_e2e_forbidden_viewer_request | CAUGHT_BY_ASSERTION | 4 | `test_g04_viewer_mutations_are_forbidden_and_change_nothing[draft]` - AssertionError: assert [(1, 'SYN-100..., 0, 'DRAFT')] == [(1, 'SYN-100..., 5, 'DRAFT')] |
| M05 | invalid quantity is committed | sandbox/schema.sql, sandbox/validation.py | test_g09_invalid_create_is_rejected_with_a_field_error_and_no_db_delta[qty-negative]; test_g09_invalid_create_is_rejected_with_a_field_error_and_no_db_delta[qty | CAUGHT_BY_ASSERTION | 10 | `test_g09_invalid_create_is_rejected_with_a_field_error_and_no_db_delta[qty-negative]` - assert 201 == 400 |
| M06 | duplicate SKU overwrites the original | sandbox/store.py | test_g08_duplicate_sku_conflicts; test_g08_duplicate_of_a_draft_sku; test_g08_duplicate_sku_is_rejected_by_the_form | CAUGHT_BY_ASSERTION | 3 | `test_g08_duplicate_sku_conflicts_and_the_original_row_is_unchanged[SYN-1002-editor]` - assert 201 == 409 |
| M07 | publish reports success but is never committed | sandbox/store.py | test_g07_publisher_publishes_and_a_fresh_viewer_session_sees_the_same_values; test_e2e_publish_is_visible_to_a_fresh_viewer | CAUGHT_BY_ASSERTION | 3 | `test_g07_publisher_publishes_and_a_fresh_viewer_session_sees_the_same_values` - AssertionError: assert 2 == 3 |
| M08 | adapter alters literal values (unsafe literal handling) | modules/common/database.py | test_g13_apostrophes_and_sql_metacharacters_are_stored_literally | CAUGHT_BY_ASSERTION | 1 | `test_g13_apostrophes_and_sql_metacharacters_are_stored_literally` - assert (4, 'SYN-DB2'...', 1, 'DRAFT') == (4, 'SYN-DB2'...", 1, 'DRAFT') |
| M09 | cross-test contamination (shared database) | tests/support/plugin.py | test_g16_seed_equals_the_independent_golden_literals; test_g16_consecutive_runs_and_any_order_see_the_original_seed | CAUGHT_BY_ASSERTION | 54 | `test_g16_seed_equals_the_independent_golden_literals` - AssertionError: assert [(1, 'SYN-100...'DRAFT'), ...] == [(1, 'SYN-100..., 5, 'DRAFT')] |
| M10 | logout does not invalidate the session | sandbox/app.py | test_g02_logout_invalidates_session_even_when_old_cookie_is_replayed | CAUGHT_BY_ASSERTION | 2 | `test_g02_logout_invalidates_session_even_when_old_cookie_is_replayed` - assert 1 == 0 |
| M11 | published item can be edited | sandbox/app.py, sandbox/store.py | test_g11_editing_a_published_item_is_rejected_and_unchanged | CAUGHT_BY_ASSERTION | 5 | `test_g11_editing_a_published_item_is_rejected_and_unchanged[name-editor]` - assert 200 == 409 |
| M12 | update of a missing item creates a phantom row | sandbox/app.py | test_g12_missing_target_gives_404_and_creates_no_phantom_row | CAUGHT_BY_ASSERTION | 3 | `test_g12_missing_target_gives_404_and_creates_no_phantom_row[editor]` - assert 200 == 404 |
| M13 | UI shows a stale state after publish | sandbox/templates/item_detail.html | test_g07_publisher_publishes_and_a_fresh_viewer_session_sees_it; test_e2e_publish_is_visible_to_a_fresh_viewer; test_g11_a_published_item_shows_a_lock_note | CAUGHT_BY_ASSERTION | 4 | `test_e2e_publish_is_visible_to_a_fresh_viewer_in_ui_api_and_db[chromium]` - AssertionError: Locator expected to have text 'PUBLISHED' |
| M14 | adapter builds an unescaped SQLite URI (KQA-001) | modules/common/database.py | test_readonly_adapter_opens_the_intended_file_and_cannot_write; test_readwrite_adapter_writes_only_the_intended_file | CAUGHT_BY_ASSERTION | 9 | `test_readonly_adapter_opens_the_intended_file_and_cannot_write[data#2026.db]` - AssertionError: assert 'decoy' == 'intended' |
| M15 | observer builds an unescaped SQLite URI (KQA-001) | tests/support/observer.py | test_observer_reads_the_intended_file | CAUGHT_BY_ASSERTION | 6 | `test_observer_reads_the_intended_file[data#2026.db]` - AssertionError: assert [('decoy',)] == [('intended',)] |
| M16 | SKU validation accepts a trailing newline (KQA-002) | sandbox/app.py, sandbox/validation.py | test_sku_with_trailing_newline_is_a_bad_format_not_a_valid_sku; test_create_rejects_whitespace_decorated_sku_and_changes_nothing; test_sku_pattern_uses_a_full_m | CAUGHT_BY_ASSERTION | 3 | `test_create_rejects_whitespace_decorated_sku_and_changes_nothing[lf]` - assert 409 == 400 |
| M17 | database no longer bounds quantity above (KQA-002) | sandbox/schema.sql | test_schema_sql_accepts_or_rejects_exactly_as_the_contract_says | CAUGHT_BY_ASSERTION | 1 | `test_schema_sql_accepts_or_rejects_exactly_as_the_contract_says[qty-over-max]` - Failed: DID NOT RAISE <class 'modules.common.database.ConstraintViolationError'> |
| M18 | database no longer checks the SKU format (KQA-002) | sandbox/schema.sql | test_schema_sql_accepts_or_rejects_exactly_as_the_contract_says | CAUGHT_BY_ASSERTION | 5 | `test_schema_sql_accepts_or_rejects_exactly_as_the_contract_says[sku-lowercase]` - Failed: DID NOT RAISE <class 'modules.common.database.ConstraintViolationError'> |
| M19 | typed client skips item-list verification (KQA-003) | modules/api/clients/catalog.py | test_malformed_success_bodies_are_a_typed_failure_never_a_result; test_http_malformed_item_lists_are_rejected | CAUGHT_BY_ASSERTION | 15 | `test_malformed_success_bodies_are_a_typed_failure_never_a_result[list-items-null]` - Failed: DID NOT RAISE <class 'modules.api.clients.errors.ApiMalformedResponse'> |
| M20 | malformed error envelope is reported as valid (KQA-003) | modules/api/clients/catalog.py | test_error_envelopes_always_become_an_http_error_with_the_real_status; test_http_500_with_a_string_error_is_a_controlled_http_error | CAUGHT_BY_ASSERTION | 9 | `test_error_envelopes_always_become_an_http_error_with_the_real_status[string-error]` - AssertionError: assert True is False |
| M21 | report generator accepts an empty mutation list (KQA-004) | tools/evidence_check.py | [drop_mutants]; test_mutation_check_unit_cases | CAUGHT_BY_ASSERTION | 5 | `test_defective_evidence_fails_closed_and_leaves_no_current_pass_report[drop_mutants]` - assert 0 != 0 |
| M22 | package verifier ignores manifest sizes (KQA-005) | tools/package_common.py | test_manifest_size_must_match_the_actual_byte_length; test_manifest_with_correct_hash_but_wrong_size_is_not_accepted | CAUGHT_BY_ASSERTION | 2 | `test_manifest_size_must_match_the_actual_byte_length` - AssertionError: assert 'size mismatch: README.md (manifest 999, actual 5)' in [] |
| M23 | package verifier accepts duplicate ZIP entries (KQA-005) | tools/package_common.py | test_duplicate_archive_entries_are_rejected_even_if_the_last_matches_the_manifest; test_ambiguous_or_unsafe_paths_are_rejected | CAUGHT_BY_ASSERTION | 1 | `test_duplicate_archive_entries_are_rejected_even_if_the_last_matches_the_manifest` - AssertionError: assert 0 != 0 |
| M24 | separate-process evidence accepts a skipped test (v1.0.2) | tools/evidence_check.py | [layer_skip]; test_a_skipped_test_in_a_mandatory_layer_is_rejected_even_when_the_total_is_unchanged | CAUGHT_BY_ASSERTION | 3 | `test_defective_evidence_fails_closed_and_leaves_no_current_pass_report[layer_skip]` - assert 0 != 0 |
| M25 | malformed list field crashes the evidence checker (v1.0.2) | tools/evidence_check.py | test_run_evidence_checker_reports_garbage_as_problems_and_never_needs_its_safety_net | CAUGHT_BY_ASSERTION | 3 | `test_run_evidence_checker_reports_garbage_as_problems_and_never_needs_its_safety_net[7]` - AssertionError: ['no test of layer framework in the JUnit evidence', 'no test of layer database in the JUnit evidence', 'no test of la...ht  |
| M26 | negative counts are accepted as evidence (v1.0.2) | tools/evidence_check.py | test_negative_or_boolean_counts_are_rejected_even_when_the_arithmetic_adds_up | CAUGHT_BY_ASSERTION | 2 | `test_negative_or_boolean_counts_are_rejected_even_when_the_arithmetic_adds_up[junit0]` - AssertionError: assert None is not None |


Restoration: every run used a fresh copy that was deleted afterwards; the final unmodified baseline run is green.


**Summary: 26 of 26 mutants caught by assertion.**
