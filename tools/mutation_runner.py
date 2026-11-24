"""Controlled-defect (mutation) runner.

Each mutant is a list of exact text patches applied to a *throw-away copy* of the project; the real tree is never
modified, so nothing mutated can ship. For every mutant the runner

1. copies the project (without .git, .venv, caches, artifacts),
2. applies each patch and refuses to continue unless the old text occurs exactly once,
3. runs the whole suite in the copy and reads the JUnit XML,
4. classifies every failing test as ASSERTION failure (a pre-existing assertion caught the defect) or EXCEPTION,
   and treats `<error>` elements, crashes and missing results as INFRASTRUCTURE failure (never a detection),
5. requires at least one failing test whose id matches the mutant's *intended* tests, and an assertion-type failure.

A green baseline is required before the first mutant and again after the last one. The real tree's file hashes are
compared before/after to prove restoration.

Usage: python tools/mutation_runner.py [--only M01,M02] [--out docs/evidence/mutation]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.evidence_check import scrub_text  # noqa: E402

EXCLUDE = {".git", ".venv", ".pw-browsers", "artifacts", "dist", "__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache"}

APP = "sandbox/app.py"

MUTANTS: List[Dict] = [
    {
        "id": "M01", "name": "accept invalid credentials",
        "description": "Password verification is skipped for known users (API and HTML login).",
        "patches": [
            (APP, 'if not check_password_hash(user["password_hash"], data["password"]):', "if False:"),
            (APP, 'if user is None or not check_password_hash(user["password_hash"], password):', "if user is None:"),
        ],
        "intended": ["test_g01_invalid_login_is_rejected_without_session", "test_g01_invalid_login_shows_an_error", "test_g01_invalid_login_is_rejected"],
    },
    {
        "id": "M02", "name": "viewer can read drafts",
        "description": "The viewer role is added to the roles that may read DRAFT items.",
        "patches": [("sandbox/policy.py", 'READ_DRAFT_ROLES = frozenset({"editor", "publisher"})', 'READ_DRAFT_ROLES = frozenset({"viewer", "editor", "publisher"})')],
        "intended": ["test_g03_viewer_list_and_search_do_not_disclose", "test_g03_viewer_direct_read_of_draft", "test_g03_viewer_does_not_see_the_draft"],
    },
    {
        "id": "M03", "name": "editor can publish",
        "description": "The editor role is added to the roles that may publish.",
        "patches": [("sandbox/policy.py", 'PUBLISH_ROLES = frozenset({"publisher"})', 'PUBLISH_ROLES = frozenset({"editor", "publisher"})')],
        "intended": ["test_g06_editor_cannot_publish", "test_g06_editor_has_no_publish_button"],
    },
    {
        "id": "M04", "name": "state is mutated by a forbidden request",
        "description": "A viewer's forbidden POST /items inserts a row before answering 403.",
        "patches": [(APP, "        if user[\"role\"] not in policy.CREATE_ROLES:\n            return forbidden()\n",
                     "        if user[\"role\"] not in policy.CREATE_ROLES:\n            store.insert_draft(db(), {\"sku\": \"SYN-LEAK\", \"name\": \"leak\", \"description\": \"\", \"quantity\": 0})\n            return forbidden()\n")],
        "intended": ["test_g04_viewer_mutations_are_forbidden_and_change_nothing", "test_e2e_forbidden_viewer_request"],
    },
    {
        "id": "M05", "name": "invalid quantity is committed",
        "description": "Range validation and the database CHECK on quantity are both removed.",
        "patches": [("sandbox/validation.py", "elif value < 0 or value > MAX_QUANTITY:", "elif False:"),
                    ("sandbox/schema.sql", "CHECK (typeof(quantity) = 'integer' AND quantity BETWEEN 0 AND 1000000)", "CHECK (typeof(quantity) = 'integer')")],
        "intended": ["test_g09_invalid_create_is_rejected_with_a_field_error_and_no_db_delta[qty-negative]", "test_g09_invalid_create_is_rejected_with_a_field_error_and_no_db_delta[qty-too-large]", "test_g09_invalid_form_input_shows_the_problem_and_writes_nothing[negative]"],
    },
    {
        "id": "M06", "name": "duplicate SKU overwrites the original",
        "description": "INSERT becomes INSERT OR REPLACE, so a duplicate create silently replaces the row.",
        "patches": [("sandbox/store.py", '"INSERT INTO catalog_items (sku, name, description, quantity, state) VALUES (?, ?, ?, ?, \'DRAFT\')"',
                     '"INSERT OR REPLACE INTO catalog_items (sku, name, description, quantity, state) VALUES (?, ?, ?, ?, \'DRAFT\')"')],
        "intended": ["test_g08_duplicate_sku_conflicts", "test_g08_duplicate_of_a_draft_sku", "test_g08_duplicate_sku_is_rejected_by_the_form"],
    },
    {
        "id": "M07", "name": "publish reports success but is never committed",
        "description": "publish_item no longer commits: the API/UI answer PUBLISHED while the database keeps DRAFT.",
        "patches": [("sandbox/store.py", "(sku,))\n    conn.commit()\n    return cur.rowcount\n", "(sku,))\n    return cur.rowcount\n")],
        "intended": ["test_g07_publisher_publishes_and_a_fresh_viewer_session_sees_the_same_values", "test_e2e_publish_is_visible_to_a_fresh_viewer"],
    },
    {
        "id": "M08", "name": "adapter alters literal values (unsafe literal handling)",
        "description": "Database.insert_item strips apostrophes from values - the naive 'fix' for the 2023 string-interpolation bug.",
        "patches": [("modules/common/database.py", "        cur = self._write(\n            \"INSERT INTO catalog_items (sku, name, description, quantity, state) VALUES (?, ?, ?, ?, ?)\",",
                     "        name = name.replace(\"'\", \"\")\n        description = description.replace(\"'\", \"\")\n        cur = self._write(\n            \"INSERT INTO catalog_items (sku, name, description, quantity, state) VALUES (?, ?, ?, ?, ?)\",")],
        "intended": ["test_g13_apostrophes_and_sql_metacharacters_are_stored_literally"],
    },
    {
        "id": "M09", "name": "cross-test contamination (shared database)",
        "description": "The db_path fixture reuses one shared database file and never removes it, so tests see each other's data.",
        "patches": [("tests/support/plugin.py",
                     "    owned = tmp_path / \"caps_db\"\n    owned.mkdir()\n    path = str(owned / \"caps.db\")\n    create_database(path)\n    try:\n        yield path\n    finally:\n        shutil.rmtree(str(owned), ignore_errors=True)",
                     "    owned = Path(__file__).parent / \"_shared_db\"\n    owned.mkdir(exist_ok=True)\n    path = str(owned / \"caps.db\")\n    if not os.path.exists(path):\n        create_database(path)\n    yield path")],
        "intended": ["test_g16_seed_equals_the_independent_golden_literals", "test_g16_consecutive_runs_and_any_order_see_the_original_seed"],
    },
    {
        "id": "M10", "name": "logout does not invalidate the session",
        "description": "DELETE /api/v1/session clears the cookie but leaves the server-side session row.",
        "patches": [(APP, "        store.delete_session(db(), request.cookies[COOKIE])\n        resp = Response(status=204)", "        resp = Response(status=204)")],
        "intended": ["test_g02_logout_invalidates_session_even_when_old_cookie_is_replayed"],
    },
    {
        "id": "M11", "name": "published item can be edited",
        "description": "The 409 item_published rule and the DRAFT-only guard of the UPDATE are removed.",
        "patches": [(APP, '        if item["state"] == "PUBLISHED":\n            return api_error(409, "item_published", "Published items cannot be modified.")\n', ""),
                    ("sandbox/store.py", "WHERE sku = ? AND state = 'DRAFT'\" % assignments", "WHERE sku = ?\" % assignments")],
        "intended": ["test_g11_editing_a_published_item_is_rejected_and_unchanged"],
    },
    {
        "id": "M12", "name": "update of a missing item creates a phantom row",
        "description": "PATCH on an unknown SKU inserts a new draft instead of answering 404.",
        "patches": [(APP, "        item = visible_item(user, sku)\n        if item is None:\n            return not_found()\n        if item[\"state\"] == \"PUBLISHED\":\n            return api_error(409, \"item_published\"",
                     "        item = visible_item(user, sku)\n        if item is None:\n            store.insert_draft(db(), {\"sku\": sku, \"name\": clean.get(\"name\", \"phantom\"), \"description\": \"\", \"quantity\": clean.get(\"quantity\", 0)})\n            return jsonify(store.get_item(db(), sku))\n        if item[\"state\"] == \"PUBLISHED\":\n            return api_error(409, \"item_published\"")],
        "intended": ["test_g12_missing_target_gives_404_and_creates_no_phantom_row"],
    },
    {
        "id": "M13", "name": "UI shows a stale state after publish",
        "description": "The item detail page always renders the state DRAFT although API and database say PUBLISHED.",
        "patches": [("sandbox/templates/item_detail.html", '<dd data-testid="item-state">{{ item.state }}</dd>', '<dd data-testid="item-state">DRAFT</dd>')],
        "intended": ["test_g07_publisher_publishes_and_a_fresh_viewer_session_sees_it", "test_e2e_publish_is_visible_to_a_fresh_viewer", "test_g11_a_published_item_shows_a_lock_note"],
    },
    # ---- v1.0.1 maintenance: targeted mutants for the corrected defects (KQA-001 .. KQA-005) ----------------------------
    {
        "id": "M14", "name": "adapter builds an unescaped SQLite URI (KQA-001)",
        "description": "Database opens file:<path> escaping only '?', so '#' and '%' in a file name select a different database.",
        "patches": [("modules/common/database.py",
                     "    base = PurePath(os.path.abspath(path)).as_uri()\n    return \"%s?mode=%s\" % (base, \"ro\" if readonly else \"rw\")",
                     "    return \"file:%s?mode=%s\" % (path.replace(\"?\", \"%3f\"), \"ro\" if readonly else \"rw\")")],
        "intended": ["test_readonly_adapter_opens_the_intended_file_and_cannot_write", "test_readwrite_adapter_writes_only_the_intended_file"],
    },
    {
        "id": "M15", "name": "observer builds an unescaped SQLite URI (KQA-001)",
        "description": "The independent Observer interpolates the raw path into the URI again.",
        "patches": [("tests/support/observer.py", "uri = PurePath(os.path.abspath(self.db_path)).as_uri() + \"?mode=ro\"",
                     "uri = \"file:%s?mode=ro\" % self.db_path")],
        "intended": ["test_observer_reads_the_intended_file"],
    },
    {
        "id": "M16", "name": "SKU validation accepts a trailing newline (KQA-002)",
        "description": "The SKU pattern is anchored with ^...$ and used with match(), which lets 'SYN-X\\n' through (API and path check).",
        "patches": [("sandbox/validation.py", 'SKU_RE = re.compile(r"[A-Z0-9][A-Z0-9-]{1,31}")', 'SKU_RE = re.compile(r"^[A-Z0-9][A-Z0-9-]{1,31}$")'),
                    ("sandbox/validation.py", 'SKU_RE.fullmatch(payload["sku"])', 'SKU_RE.match(payload["sku"])'),
                    (APP, "_SKU_PATH_RE.fullmatch(sku)", "_SKU_PATH_RE.match(sku)")],
        "intended": ["test_sku_with_trailing_newline_is_a_bad_format_not_a_valid_sku", "test_create_rejects_whitespace_decorated_sku_and_changes_nothing",
                     "test_sku_pattern_uses_a_full_match"],
    },
    {
        "id": "M17", "name": "database no longer bounds quantity above (KQA-002)",
        "description": "The catalog_items CHECK drops the 1,000,000 upper bound, so the schema permits what the contract forbids.",
        "patches": [("sandbox/schema.sql", "AND quantity BETWEEN 0 AND 1000000)", "AND quantity >= 0)")],
        "intended": ["test_schema_sql_accepts_or_rejects_exactly_as_the_contract_says"],
    },
    {
        "id": "M18", "name": "database no longer checks the SKU format (KQA-002)",
        "description": "The SKU character-set and leading-hyphen CHECK is removed, so rows such as 'x' or 'SYN-X<newline>' can be stored.",
        "patches": [("sandbox/schema.sql", "\n                       AND sku NOT GLOB '*[^A-Z0-9-]*' AND substr(sku, 1, 1) <> '-'", "")],
        "intended": ["test_schema_sql_accepts_or_rejects_exactly_as_the_contract_says"],
    },
    {
        "id": "M19", "name": "typed client skips item-list verification (KQA-003)",
        "description": "list_items returns body['items'] without checking the envelope, element types, required fields or count.",
        "patches": [("modules/api/clients/catalog.py",
                     "self._checked(resp, _check_item_list)  # the whole envelope: items, count and their consistency", "pass")],
        "intended": ["test_malformed_success_bodies_are_a_typed_failure_never_a_result", "test_http_malformed_item_lists_are_rejected"],
    },
    {
        "id": "M20", "name": "malformed error envelope is reported as valid (KQA-003)",
        "description": "ApiHttpError always claims envelope_valid=True, hiding that the server error body was unreadable.",
        "patches": [("modules/api/clients/catalog.py", "envelope_valid=code is not None)", "envelope_valid=True)")],
        "intended": ["test_error_envelopes_always_become_an_http_error_with_the_real_status", "test_http_500_with_a_string_error_is_a_controlled_http_error"],
    },
    {
        "id": "M21", "name": "report generator accepts an empty mutation list (KQA-004)",
        "description": "check_mutation_evidence no longer rejects mutants=[] nor missing expected mutant ids.",
        "patches": [("tools/evidence_check.py", "if not isinstance(mutants, list) or not mutants:", "if not isinstance(mutants, list):"),
                    ("tools/evidence_check.py", "    if missing:\n        problems.append(", "    if False:\n        problems.append(")],
        "intended": ["[drop_mutants]", "test_mutation_check_unit_cases"],
    },
    {
        "id": "M22", "name": "package verifier ignores manifest sizes (KQA-005)",
        "description": "verify_inventory compares SHA-256 only; a forged size in the manifest is accepted.",
        "patches": [("tools/package_common.py", "        if len(present[rel]) != size:", "        if False:")],
        "intended": ["test_manifest_size_must_match_the_actual_byte_length", "test_manifest_with_correct_hash_but_wrong_size_is_not_accepted"],
    },
    {
        "id": "M23", "name": "package verifier accepts duplicate ZIP entries (KQA-005)",
        "description": "check_zip_entries no longer flags duplicate or ambiguous names, so the last duplicate wins silently.",
        "patches": [("tools/package_common.py", "        if key in seen:", "        if False:")],
        "intended": ["test_duplicate_archive_entries_are_rejected_even_if_the_last_matches_the_manifest", "test_ambiguous_or_unsafe_paths_are_rejected"],
    },
    {
        "id": "M24", "name": "separate-process evidence accepts a skipped test (v1.0.2)",
        "description": "The per-layer 'pass all tests, no skips' rule is disabled, so a skipped test hides behind an unchanged grand total.",
        "patches": [("tools/evidence_check.py",
                     'if junit["tests"] != expected_layer or junit["passed"] != expected_layer or junit["skipped"] or junit["failed"] or junit["errors"]:',
                     "if False:")],
        "intended": ["[layer_skip]", "test_a_skipped_test_in_a_mandatory_layer_is_rejected_even_when_the_total_is_unchanged"],
    },
    {
        "id": "M25", "name": "malformed list field crashes the evidence checker (v1.0.2)",
        "description": "_str_list stops validating its input, so an integer or duplicate-laden list reaches the iteration code.",
        "patches": [("tools/evidence_check.py", "    if not isinstance(value, list) or not all(isinstance(v, str) and v for v in value):",
                     "    if False:")],
        "intended": ["test_run_evidence_checker_reports_garbage_as_problems_and_never_needs_its_safety_net"],
    },
    {
        "id": "M26", "name": "negative counts are accepted as evidence (v1.0.2)",
        "description": "_is_count no longer rejects negative integers.",
        "patches": [("tools/evidence_check.py", "    return _is_int(value) and value >= 0", "    return _is_int(value)")],
        "intended": ["test_negative_or_boolean_counts_are_rejected_even_when_the_arithmetic_adds_up"],
    },
]


def file_hashes(root: Path) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root)
        if path.is_file() and not (set(rel.parts) & EXCLUDE) and not path.suffix == ".pyc":
            out[str(rel)] = hashlib.sha256(path.read_bytes()).hexdigest()
    return out


def copy_project(dst: Path, source: Optional[Path] = None) -> None:
    def ignore(_dir: str, names: List[str]) -> List[str]:
        return [n for n in names if n in EXCLUDE or n.endswith(".pyc")]

    shutil.copytree(source or ROOT, dst, ignore=ignore)


def apply_patches(root: Path, patches: List) -> None:
    for rel, old, new in patches:
        target = root / rel
        text = target.read_text(encoding="utf-8")
        count = text.count(old)
        if count != 1:
            raise RuntimeError("patch anchor must occur exactly once in %s (found %d): %r" % (rel, count, old[:70]))
        target.write_text(text.replace(old, new), encoding="utf-8")


def run_suite(workdir: Path, junit: Path) -> Dict:
    env = dict(os.environ)
    env["PLAYWRIGHT_BROWSERS_PATH"] = str(ROOT / ".pw-browsers")
    env["KQA_ARTIFACTS"] = str(workdir / "artifacts_run")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env.pop("PYTHONPATH", None)
    started = time.monotonic()
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-W", "ignore", "--junitxml", str(junit)],
        cwd=str(workdir), env=env, capture_output=True, text=True, timeout=900,
    )
    return {"exit_code": proc.returncode, "seconds": round(time.monotonic() - started, 1), "tail": proc.stdout[-600:]}


def parse_junit(path: Path) -> Dict:
    if not path.exists():
        return {"ok": False, "reason": "no junit file", "cases": []}
    try:
        root = ET.parse(str(path)).getroot()
    except ET.ParseError:
        return {"ok": False, "reason": "malformed junit file", "cases": []}
    cases = []
    for case in root.iter("testcase"):
        nodeid = "%s::%s" % (case.get("classname", "").replace(".", "/"), case.get("name"))
        status, kind, message = "passed", "", ""
        for child in case:
            if child.tag in ("failure", "error"):
                body = (child.text or "") + (child.get("message") or "")
                status = "failed" if child.tag == "failure" else "error"
                is_assert = bool(re.search(r"^E\s+(assert |AssertionError)", body, re.M)) or "DID NOT RAISE" in body
                kind = ("assertion" if is_assert else "exception") if child.tag == "failure" else "infrastructure"
                lines = [ln[1:].strip() for ln in body.splitlines() if ln.startswith("E ")]
                message = (lines[0] if lines else (child.get("message") or ""))[:300]
            elif child.tag == "skipped":
                status = "skipped"
        cases.append({"id": nodeid, "name": case.get("name"), "status": status, "kind": kind, "message": message})
    return {"ok": True, "cases": cases}


def sanitize(text: str) -> str:
    return scrub_text(text, ROOT)


def evaluate(mutant: Dict, parsed: Dict, exit_code: int) -> Dict:
    cases = parsed["cases"]
    failed = [c for c in cases if c["status"] == "failed"]
    errors = [c for c in cases if c["status"] == "error"]
    intended = [c for c in failed if any(token in c["id"] for token in mutant["intended"])]
    caught_by_assertion = [c for c in intended if c["kind"] == "assertion"]
    infrastructure = (not parsed["ok"]) or bool(errors) or exit_code not in (0, 1) or not cases
    if infrastructure:
        verdict = "INFRASTRUCTURE_FAILURE"
    elif caught_by_assertion:
        verdict = "CAUGHT_BY_ASSERTION"
    elif intended:
        verdict = "CAUGHT_BY_EXCEPTION_ONLY"
    else:
        verdict = "SURVIVED" if not failed else "FAILED_ELSEWHERE_ONLY"
    first = caught_by_assertion[0] if caught_by_assertion else (intended[0] if intended else None)
    return {
        "verdict": verdict, "total": len(cases), "failed": len(failed), "errors": len(errors),
        "intended_failed": [c["id"] for c in intended],
        "first_failing_assertion": {"test": first["id"], "message": sanitize(first["message"])} if first else None,
        "all_failed": [c["id"] for c in failed],
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", default="")
    parser.add_argument("--out", default=str(ROOT / "docs" / "evidence" / "mutation"))
    args = parser.parse_args(argv)
    chosen = [m for m in MUTANTS if not args.only or m["id"] in args.only.split(",")]
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    results: Dict = {"baseline_before": None, "baseline_after": None, "mutants": []}

    work_root = Path(tempfile.mkdtemp(prefix="kqa_mut_"))  # unique owned temp directory
    snapshot = work_root / "snapshot"  # every copy is made from one snapshot, so concurrent edits cannot skew a run
    copy_project(snapshot)
    patched_files = sorted({p[0] for m in chosen for p in m["patches"]})
    patched_before = {f: hashlib.sha256((ROOT / f).read_bytes()).hexdigest() for f in patched_files}
    try:
        for label in ("baseline_before",):
            copy = work_root / label
            copy_project(copy, snapshot)
            run = run_suite(copy, copy / "junit.xml")
            parsed = parse_junit(copy / "junit.xml")
            results[label] = {"exit_code": run["exit_code"], "seconds": run["seconds"], "total": len(parsed["cases"]),
                              "failed": sum(c["status"] != "passed" for c in parsed["cases"])}
            print(label, results[label], flush=True)
            if run["exit_code"] != 0:
                print("baseline is not green; refusing to evaluate mutants", file=sys.stderr)
                return 2
            shutil.rmtree(copy, ignore_errors=True)
        for mutant in chosen:
            copy = work_root / mutant["id"]
            copy_project(copy, snapshot)
            apply_patches(copy, mutant["patches"])
            run = run_suite(copy, copy / "junit.xml")
            parsed = parse_junit(copy / "junit.xml")
            verdict = evaluate(mutant, parsed, run["exit_code"])
            entry = {k: mutant[k] for k in ("id", "name", "description", "intended")}
            entry["patched_files"] = sorted({p[0] for p in mutant["patches"]})
            entry.update(verdict)
            entry["exit_code"] = run["exit_code"]
            entry["seconds"] = run["seconds"]
            results["mutants"].append(entry)
            print(mutant["id"], verdict["verdict"], "failed=%d" % verdict["failed"], flush=True)
            shutil.rmtree(copy, ignore_errors=True)
        copy = work_root / "baseline_after"
        copy_project(copy, snapshot)
        run = run_suite(copy, copy / "junit.xml")
        parsed = parse_junit(copy / "junit.xml")
        results["baseline_after"] = {"exit_code": run["exit_code"], "seconds": run["seconds"], "total": len(parsed["cases"]),
                                     "failed": sum(c["status"] != "passed" for c in parsed["cases"])}
        print("baseline_after", results["baseline_after"], flush=True)
    finally:
        shutil.rmtree(work_root, ignore_errors=True)  # only the directory this run created
    patched_after = {f: hashlib.sha256((ROOT / f).read_bytes()).hexdigest() for f in patched_files}
    results["restoration"] = {"real_tree_unchanged": patched_after == patched_before, "patched_files_checked": len(patched_files)}
    (out_dir / "mutation_results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    bad = [m["id"] for m in results["mutants"] if m["verdict"] != "CAUGHT_BY_ASSERTION"]
    ok = not bad and results["baseline_after"]["exit_code"] == 0 and results["restoration"]["real_tree_unchanged"]
    print("RESULT:", "ALL CAUGHT" if ok else "PROBLEMS %s" % bad, flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
