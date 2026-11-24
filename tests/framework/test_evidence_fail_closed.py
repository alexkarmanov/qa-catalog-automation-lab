"""KQA-004 regression: report generation fails closed on missing, malformed or inconsistent evidence.

Each test builds its own small, synthetic but structurally complete evidence set in a temporary folder and runs
``tools/build_reports.py`` against a temporary docs folder, so nothing here depends on (or can disturb) the
committed evidence. The evidence is plain and unsigned; these tests prove detection of incomplete or
inconsistent evidence, not authenticity.
"""
from __future__ import annotations

import copy
import json
import socket
from pathlib import Path
from typing import Callable, Dict, List

import pytest

from tools import build_reports, mutation_runner
from tools import evidence_check as ec

pytestmark = [pytest.mark.framework, pytest.mark.negative]

LAYER_SEQ = list(ec.REQUIRED_CASE_LAYERS)
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 16


def _cases() -> List[Dict[str, str]]:
    out = []
    for n in range(1, 17):
        layer = LAYER_SEQ[(n - 1) % len(LAYER_SEQ)]
        out.append({"cls": "tests.%s.test_synth" % layer, "name": "test_g%02d" % n, "golden": "G%02d" % n,
                    "markers": layer, "layer": layer})
    return out


def _counts(total: int) -> Dict[str, int]:
    return {"tests": total, "passed": total, "failed": 0, "errors": 0, "skipped": 0}


def _step(total: int, mandatory: bool) -> Dict[str, object]:
    return {"command": "pytest", "exit_code": 0, "seconds": 1.0, "stdout_tail": "", "stderr_tail": "",
            "junit": _counts(total), "ok": True, "mandatory": mandatory}


def _layer_counts() -> Dict[str, int]:
    out: Dict[str, int] = {}
    for c in _cases():
        out[c["layer"]] = out.get(c["layer"], 0) + 1
    return out


def _summary(total: int, versions: Dict[str, object]) -> Dict[str, object]:
    per_layer = _layer_counts()
    layers = {d: {"exit_code": 0, "junit": _counts(per_layer[ec.LAYER_NAMES[d]]), "seconds": 1.0} for d in ec.LAYER_DIRS}
    steps: Dict[str, object] = {"collect_only": {"command": "pytest --collect-only", "exit_code": 0, "seconds": 1.0,
                                                 "stdout_tail": "", "stderr_tail": "", "ok": True, "mandatory": True}}
    for name in ("first_run", "reverse_order", "shuffled_order"):
        steps[name] = _step(total, True)
    steps["separate_processes"] = {"ok": True, "mandatory": True, "layers": layers, "junit": _counts(total)}
    browser_total = per_layer["ui_playwright"] + per_layer["e2e"]
    for name in ec.BROWSER_STEPS:
        steps[name] = dict(_step(browser_total, True), browser=name.split("_", 1)[1])
    steps["browser_firefox"] = dict(_step(browser_total, False), browser="firefox")
    steps["parallel_xdist"] = _step(total, False)
    steps["coverage"] = _step(total, False)
    return {"steps": steps, "date": "2026-11-18", "mandatory_failures": [], "versions": versions,
            "mandatory_steps": list(ec.MANDATORY_STEPS), "optional_steps": list(ec.OPTIONAL_STEPS),
            "leftover_chromedriver_processes": []}


def _versions() -> Dict[str, object]:
    return {"python": "3.12.0", "ssl": "x", "platform": "synthetic-os", "machine": "x",
            "packages": {p: "1.0" for p in ec.REQUIRED_PACKAGES}, "playwright_chromium": "148.0",
            "playwright_firefox": "150.0", "playwright_webkit": "26.0",
            "selenium_chrome_and_driver": "157.0 | 157.0"}


def _mutation(total: int) -> Dict[str, object]:
    mutants = []
    for mid in ec.EXPECTED_MUTANT_IDS:
        tid = "tests/api/test_synth::test_for_%s" % mid
        mutants.append({"id": mid, "name": "defect " + mid, "description": "d", "intended": ["test_for_" + mid],
                        "patched_files": ["sandbox/app.py"], "verdict": "CAUGHT_BY_ASSERTION", "total": total, "failed": 1,
                        "errors": 0, "intended_failed": [tid], "first_failing_assertion": {"test": tid, "message": "assert 1 == 2"},
                        "all_failed": [tid], "exit_code": 1, "seconds": 1.0})
    base = {"exit_code": 0, "seconds": 1.0, "total": total, "failed": 0}
    return {"baseline_before": dict(base), "baseline_after": dict(base), "mutants": mutants,
            "restoration": {"real_tree_unchanged": True, "patched_files_checked": 3}}


class Env:
    def __init__(self, root: Path):
        self.ev, self.docs = root / "evidence_run", root / "docs"
        self.mutation = self.docs / "evidence" / "mutation" / "mutation_results.json"
        cases = _cases()
        self.total = len(cases)
        self.ev.mkdir()
        (self.ev / "artifacts" / "screenshots").mkdir(parents=True)
        (self.ev / "artifacts" / "screenshots" / "synthetic.png").write_bytes(PNG)
        self.docs.mkdir()
        self.mutation.parent.mkdir(parents=True)
        body = "".join(
            '<testcase classname="%s" name="%s" time="0.01"><properties><property name="golden" value="%s"/>'
            '<property name="markers" value="%s"/><property name="layer" value="%s"/></properties></testcase>'
            % (c["cls"], c["name"], c["golden"], c["markers"], c["layer"]) for c in cases)
        self.junit_text = ('<?xml version="1.0" encoding="utf-8"?><testsuites><testsuite name="pytest" tests="%d" failures="0" '
                           'errors="0" skipped="0" hostname="%s">%s</testsuite></testsuites>' % (self.total, socket.gethostname(), body))
        (self.ev / "junit_first_run.xml").write_text(self.junit_text, encoding="utf-8")
        ids = ["%s.py::%s" % (c["cls"].replace(".", "/"), c["name"]) for c in cases]
        (self.ev / "collect_only.txt").write_text("\n".join(ids) + "\n", encoding="utf-8")
        (self.ev / "report.html").write_text("<html>synthetic %s</html>" % self.ev, encoding="utf-8")
        self.versions = _versions()
        self.summary = _summary(self.total, self.versions)
        self.mut = _mutation(self.total)
        (self.docs / "LEGACY_MIGRATION_MAP.md").write_text(
            "| 1 | a | b | c | d | `%s` |\n" % ids[0], encoding="utf-8")
        self.write()

    def write(self) -> None:
        (self.ev / "run_summary.json").write_text(json.dumps(self.summary), encoding="utf-8")
        (self.ev / "versions.json").write_text(json.dumps(self.versions), encoding="utf-8")
        if self.mut is None:
            self.mutation.unlink()
        else:
            self.mutation.write_text(json.dumps(self.mut), encoding="utf-8")

    def build(self) -> int:
        return build_reports.main(["--evidence", str(self.ev), "--docs-dir", str(self.docs)])

    def reports(self) -> Dict[str, bytes]:
        return {n: (self.docs / n).read_bytes() for n in build_reports.GENERATED_REPORTS}


@pytest.fixture
def env(tmp_path: Path) -> Env:
    return Env(tmp_path)


def test_complete_synthetic_evidence_is_accepted_and_reports_are_written(env):
    assert env.build() == 0
    assert set(env.reports()) == set(build_reports.GENERATED_REPORTS)
    assert not (env.docs / build_reports.FAILURE_NOTE).exists()
    qa = (env.docs / "QA_REPORT.md").read_text(encoding="utf-8")
    assert "unsigned" in qa and "not tamper-proof" in qa
    assert "| mandatory |" in qa and "| optional |" in qa


def test_host_name_and_paths_are_scrubbed_from_curated_evidence(env):
    summary = copy.deepcopy(env.summary)
    summary["steps"]["first_run"]["stdout_tail"] = ("wrote /Us" + "ers/someone/My Project/x.xml and /private/var" + "/folders/ab/cd/T/pytest-of-someone/p")
    env.summary = summary
    env.write()
    assert env.build() == 0
    curated = env.docs / "evidence" / "run"
    junit = (curated / "junit_first_run.xml").read_text(encoding="utf-8")
    assert 'hostname="redacted"' in junit and socket.gethostname() not in junit
    blob = "".join(p.read_text(encoding="utf-8") for p in curated.glob("*") if p.is_file())
    assert "someone" not in blob and str(env.ev) not in blob
    assert ec.find_private(blob, build_reports.ROOT) == []


def _mut(fn: Callable[[Env], None]) -> Callable[[Env], None]:
    return fn


def _drop_mutants(e: Env) -> None:
    e.mut["mutants"] = []


def _empty_steps(e: Env) -> None:  # the reproduced v1.0 case: steps={} and no mandatory_failures key
    e.summary["steps"] = {}
    del e.summary["mandatory_failures"]


def _drop_step(e: Env) -> None:
    del e.summary["steps"]["reverse_order"]


def _exit_nonzero_but_ok(e: Env) -> None:
    e.summary["steps"]["first_run"]["exit_code"] = 1


def _count_mismatch(e: Env) -> None:
    e.summary["steps"]["shuffled_order"]["junit"] = _counts(e.total - 1)


def _mandatory_failure_recorded(e: Env) -> None:
    e.summary["mandatory_failures"] = ["first_run"]


def _leftover_driver(e: Env) -> None:
    e.summary["leftover_chromedriver_processes"] = ["123"]


def _duplicate_mutant(e: Env) -> None:
    e.mut["mutants"][4] = copy.deepcopy(e.mut["mutants"][3])


def _missing_mutant(e: Env) -> None:
    e.mut["mutants"].pop()


def _extra_mutant(e: Env) -> None:
    extra = copy.deepcopy(e.mut["mutants"][0])
    extra["id"] = "M99"
    e.mut["mutants"].append(extra)


def _survived(e: Env) -> None:
    e.mut["mutants"][2]["verdict"] = "SURVIVED"


def _baseline_after_failed(e: Env) -> None:
    e.mut["baseline_after"]["failed"] = 2
    e.mut["baseline_after"]["exit_code"] = 1


def _baseline_total(e: Env) -> None:
    e.mut["baseline_before"]["total"] = e.total + 3


def _no_intended_failure(e: Env) -> None:
    e.mut["mutants"][0]["intended_failed"] = []


def _no_assertion_evidence(e: Env) -> None:
    e.mut["mutants"][1]["first_failing_assertion"] = None


def _tree_changed(e: Env) -> None:
    e.mut["restoration"]["real_tree_unchanged"] = False


def _layer_missing(e: Env) -> None:
    del e.summary["steps"]["separate_processes"]["layers"]["tests/e2e"]


def _unknown_step(e: Env) -> None:
    e.summary["steps"]["invented"] = _step(e.total, False)


def _no_screenshots(e: Env) -> None:
    (e.ev / "artifacts" / "screenshots" / "synthetic.png").unlink()


def _browser_unavailable(e: Env) -> None:
    e.versions["playwright_chromium"] = "unavailable: probe failed"
    e.summary["versions"] = e.versions


def _optional_inconsistent(e: Env) -> None:
    e.summary["steps"]["coverage"]["junit"] = _counts(e.total - 2)


def _wrong_mandatory_flag(e: Env) -> None:
    e.summary["steps"]["first_run"]["mandatory"] = False


def _mutation_file_missing(e: Env) -> None:
    e.mut = None  # type: ignore[assignment]


def _versions_differ(e: Env) -> None:
    e.versions = dict(e.versions, python="9.9.9")


def _bad_png(e: Env) -> None:
    (e.ev / "artifacts" / "screenshots" / "synthetic.png").write_bytes(b"not a png")


def _layer_skip(e: Env) -> None:  # the audit case: one skipped test in a layer, grand total unchanged
    layer = e.summary["steps"]["separate_processes"]["layers"]["tests/api"]["junit"]
    layer["passed"] -= 1
    layer["skipped"] += 1
    sums = e.summary["steps"]["separate_processes"]["junit"]
    sums["passed"] -= 1
    sums["skipped"] += 1


def _layer_shifted_tests(e: Env) -> None:  # one test fewer in a layer, one more in another: totals still equal
    layers = e.summary["steps"]["separate_processes"]["layers"]
    for d, delta in (("tests/api", -1), ("tests/database", 1)):
        layers[d]["junit"]["tests"] += delta
        layers[d]["junit"]["passed"] += delta


def _mandatory_steps_int(e: Env) -> None:
    e.summary["mandatory_steps"] = 5


def _mandatory_steps_string(e: Env) -> None:
    e.summary["mandatory_steps"] = "first_run"


def _mandatory_steps_duplicates(e: Env) -> None:
    e.summary["mandatory_steps"] = list(ec.MANDATORY_STEPS) + ["first_run"]


def _optional_steps_none(e: Env) -> None:
    e.summary["optional_steps"] = None


def _steps_is_list(e: Env) -> None:
    e.summary["steps"] = [e.summary["steps"]]


def _step_is_list(e: Env) -> None:
    e.summary["steps"]["first_run"] = ["not", "an", "object"]


def _negative_counts(e: Env) -> None:
    e.summary["steps"]["first_run"]["junit"] = {"tests": e.total, "passed": e.total + 1, "failed": -1, "errors": 0, "skipped": 0}


def _bool_count(e: Env) -> None:
    e.summary["steps"]["reverse_order"]["junit"]["failed"] = False
    e.summary["steps"]["reverse_order"]["junit"]["errors"] = True


def _layers_is_list(e: Env) -> None:
    e.summary["steps"]["separate_processes"]["layers"] = ["tests/api"]


def _mandatory_failures_string(e: Env) -> None:
    e.summary["mandatory_failures"] = "none"


def _leftover_int(e: Env) -> None:
    e.summary["leftover_chromedriver_processes"] = 0


def _browser_step_missing(e: Env) -> None:
    del e.summary["steps"]["browser_webkit"]


def _browser_step_wrong_count(e: Env) -> None:
    e.summary["steps"]["browser_webkit"]["junit"] = _counts(e.total)  # ran the whole suite's worth, not the browser layers


def _browser_step_skipped_test(e: Env) -> None:
    j = e.summary["steps"]["browser_webkit"]["junit"]
    j["passed"] -= 1
    j["skipped"] += 1


def _browser_name_mismatch(e: Env) -> None:
    e.summary["steps"]["browser_webkit"]["browser"] = "chromium"


def _webkit_unavailable(e: Env) -> None:
    e.versions["playwright_webkit"] = "unavailable: not installed"
    e.summary["versions"] = e.versions


def _optional_firefox_inconsistent(e: Env) -> None:  # an optional browser step that WAS run must still be internally consistent
    e.summary["steps"]["browser_firefox"]["junit"] = _counts(e.total)


def _duplicate_test_identity(e: Env) -> None:
    first = e.junit_text.index("<testcase")
    end = e.junit_text.index("</testcase>", first) + len("</testcase>")
    e.junit_text = e.junit_text[:end] + e.junit_text[first:end] + e.junit_text[end:]
    (e.ev / "junit_first_run.xml").write_text(e.junit_text, encoding="utf-8")
    lines = (e.ev / "collect_only.txt").read_text(encoding="utf-8").splitlines()
    (e.ev / "collect_only.txt").write_text("\n".join(lines + [lines[0]]) + "\n", encoding="utf-8")


def _mutation_negative_total(e: Env) -> None:
    e.mut["baseline_before"]["total"] = -e.total


def _mutant_entry_not_object(e: Env) -> None:
    e.mut["mutants"][3] = "M04"


def _mutant_id_unhashable(e: Env) -> None:
    e.mut["mutants"][3]["id"] = ["M04"]


def _mutant_all_failed_unhashable(e: Env) -> None:
    e.mut["mutants"][5]["all_failed"] = [["nested"]]


def _mutant_intended_not_list(e: Env) -> None:
    e.mut["mutants"][6]["intended"] = "test_for_M07"


def _patched_files_negative(e: Env) -> None:
    e.mut["restoration"]["patched_files_checked"] = -3


def _mutation_is_list(e: Env) -> None:
    e.mut = [e.mut]  # type: ignore[assignment]


TAMPERS = [_layer_skip, _layer_shifted_tests, _mandatory_steps_int, _mandatory_steps_string, _mandatory_steps_duplicates,
           _optional_steps_none, _steps_is_list, _step_is_list, _negative_counts, _bool_count, _layers_is_list,
           _mandatory_failures_string, _leftover_int, _browser_step_missing, _browser_step_wrong_count,
           _browser_step_skipped_test, _browser_name_mismatch, _webkit_unavailable, _optional_firefox_inconsistent, _duplicate_test_identity,
           _mutation_negative_total, _mutant_entry_not_object, _mutant_id_unhashable, _mutant_all_failed_unhashable,
           _mutant_intended_not_list, _patched_files_negative, _mutation_is_list,
           _drop_mutants, _empty_steps, _drop_step, _exit_nonzero_but_ok, _count_mismatch, _mandatory_failure_recorded,
           _leftover_driver, _duplicate_mutant, _missing_mutant, _extra_mutant, _survived, _baseline_after_failed,
           _baseline_total, _no_intended_failure, _no_assertion_evidence, _tree_changed, _layer_missing, _unknown_step,
           _no_screenshots, _browser_unavailable, _optional_inconsistent, _wrong_mandatory_flag, _mutation_file_missing,
           _versions_differ, _bad_png]


@pytest.mark.parametrize("tamper", TAMPERS, ids=[t.__name__.lstrip("_") for t in TAMPERS])
def test_defective_evidence_fails_closed_and_leaves_no_current_pass_report(env, tamper):
    assert env.build() == 0
    good = env.reports()
    good_run = (env.docs / "evidence" / "run" / "junit_first_run.xml").read_bytes()

    tamper(env)
    env.write()
    assert env.build() != 0

    # nothing was regenerated: the old content is intact but is now bannered as stale, never a clean PASS
    for name, before in good.items():
        now = (env.docs / name).read_bytes()
        assert now == ec.STALE_BANNER.encode("utf-8") + before
    assert (env.docs / build_reports.FAILURE_NOTE).exists()
    assert (env.docs / "evidence" / "run" / "junit_first_run.xml").read_bytes() == good_run
    assert env.build() != 0  # repeating does not double the banner
    assert (env.docs / "QA_REPORT.md").read_bytes().count(ec.STALE_BANNER.encode("utf-8")) == 1


def test_first_generation_failure_never_creates_pass_reports(env):
    _drop_mutants(env)
    env.write()
    assert env.build() != 0
    assert not (env.docs / "QA_REPORT.md").exists()
    assert (env.docs / build_reports.FAILURE_NOTE).exists()


def test_a_later_good_run_removes_the_stale_marker(env):
    assert env.build() == 0
    _missing_mutant(env)
    env.write()
    assert env.build() != 0
    env.mut = _mutation(env.total)
    env.write()
    assert env.build() == 0
    assert not (env.docs / build_reports.FAILURE_NOTE).exists()
    for data in env.reports().values():
        assert not data.startswith(ec.STALE_BANNER.encode("utf-8"))


def test_unreadable_evidence_marks_reports_stale(env):
    assert env.build() == 0
    (env.ev / "run_summary.json").write_text("{not json", encoding="utf-8")
    assert env.build() == 2
    assert (env.docs / "QA_REPORT.md").read_text(encoding="utf-8").startswith(ec.STALE_BANNER)


def test_optional_steps_are_distinguishable_and_may_be_absent(env):
    del env.summary["steps"]["parallel_xdist"]
    del env.summary["steps"]["coverage"]
    env.write()
    assert env.build() == 0
    qa = (env.docs / "QA_REPORT.md").read_text(encoding="utf-8")
    assert "| optional | not run |" in qa
    assert "optional step parallel_xdist was not run" in qa


def test_a_failed_optional_step_is_reported_not_hidden(env):
    step = env.summary["steps"]["parallel_xdist"]
    step["exit_code"], step["ok"] = 1, False
    step["junit"] = {"tests": env.total, "passed": env.total - 1, "failed": 1, "errors": 0, "skipped": 0}
    env.write()
    assert env.build() == 0
    qa = (env.docs / "QA_REPORT.md").read_text(encoding="utf-8")
    assert "optional step parallel_xdist was run and FAILED" in qa and "| optional | FAILED |" in qa


def test_expected_mutant_ids_match_the_runner_definitions():
    assert [m["id"] for m in mutation_runner.MUTANTS] == list(ec.EXPECTED_MUTANT_IDS)
    assert len({m["id"] for m in mutation_runner.MUTANTS}) == len(mutation_runner.MUTANTS)


def test_mutation_check_unit_cases():
    assert ec.check_mutation_evidence(_mutation(10), 10) == []
    assert ec.check_mutation_evidence({}, 10)
    assert ec.check_mutation_evidence(None, 10) == ["mutation_results.json is not an object"]
    assert any("empty" in p for p in ec.check_mutation_evidence(dict(_mutation(10), mutants=[]), 10))


GARBAGE = [None, 5, "x", [], [1, 2], {"steps": 5}, {"steps": []}, {"steps": {}}, {"steps": {}, "mandatory_steps": 5},
           {"steps": {"first_run": 7}, "mandatory_steps": "a", "optional_steps": None, "mandatory_failures": 3,
            "leftover_chromedriver_processes": {}, "date": 20261118, "versions": []}]


@pytest.mark.parametrize("summary", GARBAGE, ids=[str(i) for i in range(len(GARBAGE))])
def test_run_evidence_checker_reports_garbage_as_problems_and_never_needs_its_safety_net(summary):
    cases = [{"id": "tests/x.py::t", "layer": "api", "golden": [], "markers": []}]
    problems, _ = ec.check_run_evidence(cases, ["tests/x.py::t"], summary, summary, [])
    assert problems
    assert not any("checker raised" in p for p in problems), problems  # explicit validation handled it


@pytest.mark.parametrize("mres", [None, 5, "x", [], {"mutants": 5}, {"mutants": [None, 1, "M01"]},
                                  {"baseline_before": [], "baseline_after": 3, "restoration": "x", "mutants": [{"id": ["M01"]}]}])
def test_mutation_checker_reports_garbage_as_problems_and_never_needs_its_safety_net(mres):
    problems = ec.check_mutation_evidence(mres, 10)
    assert problems
    assert not any("checker raised" in p for p in problems), problems


@pytest.mark.parametrize("junit", [{"tests": 1, "passed": 2, "failed": -1, "errors": 0, "skipped": 0},
                                   {"tests": -1, "passed": -1, "failed": 0, "errors": 0, "skipped": 0},
                                   {"tests": 1, "passed": True, "failed": 0, "errors": 0, "skipped": 0}])
def test_negative_or_boolean_counts_are_rejected_even_when_the_arithmetic_adds_up(junit):
    assert ec._counts_problem("x", junit) is not None


def test_a_skipped_test_in_a_mandatory_layer_is_rejected_even_when_the_total_is_unchanged():
    per_layer = _layer_counts()
    layers = {d: {"exit_code": 0, "junit": _counts(per_layer[ec.LAYER_NAMES[d]])} for d in ec.LAYER_DIRS}
    layers["tests/api"]["junit"].update(passed=per_layer["api"] - 1, skipped=1)
    problems: list = []
    total = sum(per_layer.values())
    sums = _counts(total)
    sums.update(passed=total - 1, skipped=1)
    step = {"ok": True, "mandatory": True, "layers": layers, "junit": sums}
    ec._check_step("separate_processes", step, total, True, problems, per_layer)
    assert any("layer tests/api must pass all" in p for p in problems), problems


def test_firefox_may_be_absent_but_its_unavailability_is_reported(env):
    del env.summary["steps"]["browser_firefox"]
    env.versions["playwright_firefox"] = "unavailable: launch timed out"
    env.summary["versions"] = env.versions
    env.write()
    assert env.build() == 0
    qa = (env.docs / "QA_REPORT.md").read_text(encoding="utf-8")
    assert "optional step browser_firefox was not run" in qa
    assert "unavailable: launch timed out" in qa
