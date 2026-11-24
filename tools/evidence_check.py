"""Fail-closed consistency checks for run and mutation evidence (KQA-004), plus privacy scrubbing (KQA-006).

Every function returns a list of problems; an empty list is the only "pass". Missing, duplicated, malformed or
incomplete mandatory evidence is a problem, never a default. These checks catch accidental inconsistency and
incomplete runs. The evidence files are plain, unsigned files: nothing here authenticates them or makes them
tamper-proof, and a person who rewrites *all* of the files consistently cannot be detected by this code.
"""
from __future__ import annotations

import re
import socket
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.parse import quote

BROWSER_STEPS = ("browser_chromium", "browser_webkit")  # mandatory engines
OPTIONAL_BROWSER_STEPS = ("browser_firefox",)  # attempted; reported honestly when the engine cannot run on the machine
MANDATORY_STEPS = ("collect_only", "first_run", "reverse_order", "shuffled_order", "separate_processes") + BROWSER_STEPS
REQUIRED_BROWSER_VERSIONS = ("playwright_chromium", "playwright_webkit", "selenium_chrome_and_driver")
OPTIONAL_STEPS = ("parallel_xdist", "coverage", "browser_firefox")
LAYER_DIRS = ("tests/framework", "tests/database", "tests/api", "tests/ui_selenium", "tests/ui_playwright", "tests/e2e")
LAYER_NAMES = {d: d.split("/")[1] for d in LAYER_DIRS}
REQUIRED_CASE_LAYERS = ("framework", "database", "api", "ui_selenium", "ui_playwright", "e2e")
REQUIRED_PACKAGES = ("pytest", "playwright", "selenium", "Flask", "requests")
COUNT_KEYS = ("tests", "passed", "failed", "errors", "skipped")

# The exact mutant population the release evidence must contain (kept here, independent of the runner's list;
# a test proves both lists agree).
EXPECTED_MUTANT_IDS: Tuple[str, ...] = tuple("M%02d" % n for n in range(1, 27))

STALE_BANNER = (
    "> **STALE - NOT CURRENT EVIDENCE.** The last attempt to regenerate the reports FAILED its consistency "
    "checks (see `docs/REPORT_GENERATION_FAILED.md`). Nothing below reflects the current evidence.\n\n"
)


# --------------------------------------------------------------------------------------------- helpers
def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_count(value: Any) -> bool:
    """A real, non-negative integer (bool is not a count)."""
    return _is_int(value) and value >= 0


def _str_list(value: Any, what: str, problems: List[str]) -> Optional[List[str]]:
    """Return ``value`` as a list of unique non-empty strings, or record a problem and return None.

    Evidence structures are validated *before* they are iterated, so a malformed field (an integer, a string, a
    list of numbers, duplicates) is reported as a problem and can never raise from inside the checker.
    """
    if not isinstance(value, list) or not all(isinstance(v, str) and v for v in value):
        problems.append("%s must be a list of non-empty strings, got %s" % (what, type(value).__name__))
        return None
    if len(set(value)) != len(value):
        problems.append("%s contains duplicates: %s" % (what, sorted({v for v in value if value.count(v) > 1})))
        return None
    return list(value)


def _counts_problem(label: str, junit: Any) -> Optional[str]:
    if not isinstance(junit, dict):
        return "%s: junit counts missing" % label
    if any(not _is_count(junit.get(k)) for k in COUNT_KEYS):
        return "%s: junit counts incomplete, negative or not integers (%s)" % (label, junit)
    if junit["tests"] != junit["passed"] + junit["failed"] + junit["errors"] + junit["skipped"]:
        return "%s: junit counts do not add up (%s)" % (label, junit)
    return None


def _expected_ok(exit_code: Any, junit: Dict[str, int]) -> bool:
    return exit_code == 0 and junit["failed"] == 0 and junit["errors"] == 0 and junit["tests"] > 0


def _check_step(name: str, step: Any, total: int, mandatory: bool, problems: List[str],
                layer_totals: Optional[Dict[str, int]] = None) -> Optional[bool]:
    """Validate one step record; return its recorded ``ok`` (None when the record is unusable)."""
    if not isinstance(step, dict):
        problems.append("step %s is not an object" % name)
        return None
    if step.get("mandatory") is not mandatory:
        problems.append("step %s: 'mandatory' flag is %r, expected %r" % (name, step.get("mandatory"), mandatory))
    if name == "separate_processes":
        return _check_separate(step, total, mandatory, problems, layer_totals or {})
    if not _is_int(step.get("exit_code")) or not isinstance(step.get("ok"), bool):
        problems.append("step %s: exit_code/ok missing or malformed" % name)
        return None
    if name.startswith("browser_") and step.get("browser") != name.split("_", 1)[1]:
        problems.append("step %s does not record the browser it ran (%r)" % (name, step.get("browser")))
    if name == "collect_only":
        if step["ok"] != (step["exit_code"] == 0):
            problems.append("step collect_only: ok=%r contradicts exit_code=%r" % (step["ok"], step["exit_code"]))
        return bool(step["ok"])
    bad = _counts_problem("step " + name, step.get("junit"))
    if bad:
        problems.append(bad)
        return None
    junit = step["junit"]
    if step["ok"] != _expected_ok(step["exit_code"], junit):
        problems.append("step %s: ok=%r contradicts exit_code=%r and counts %s" % (name, step["ok"], step["exit_code"], junit))
    if junit["tests"] != total:
        problems.append("step %s ran %d tests but %d were collected" % (name, junit["tests"], total))
    if mandatory and (not step["ok"] or junit["passed"] != total):
        problems.append("mandatory step %s did not pass completely (%s, exit %s)" % (name, junit, step["exit_code"]))
    return bool(step["ok"])


def _check_separate(step: Dict[str, Any], total: int, mandatory: bool, problems: List[str],
                    layer_totals: Dict[str, int]) -> Optional[bool]:
    layers = step.get("layers")
    if not isinstance(layers, dict) or set(layers) != set(LAYER_DIRS):
        problems.append("separate_processes must record exactly the layers %s, got %s"
                        % (sorted(LAYER_DIRS), sorted(layers) if isinstance(layers, dict) else layers))
        return None
    sums = {k: 0 for k in COUNT_KEYS}
    all_ok = True
    for layer, rec in layers.items():
        if not isinstance(rec, dict) or not _is_int(rec.get("exit_code")):
            problems.append("separate_processes layer %s: exit_code missing" % layer)
            all_ok = False
            continue
        bad = _counts_problem("layer " + layer, rec.get("junit"))
        if bad:
            problems.append(bad)
            all_ok = False
            continue
        if not _expected_ok(rec["exit_code"], rec["junit"]):
            all_ok = False
        # every layer must pass ALL of its tests: the first run says how many tests the layer has, so a skipped
        # (or missing, or extra) test cannot hide behind an unchanged grand total
        expected_layer = layer_totals.get(LAYER_NAMES[layer], -1)
        junit = rec["junit"]
        if junit["tests"] != expected_layer or junit["passed"] != expected_layer or junit["skipped"] or junit["failed"] or junit["errors"]:
            problems.append("layer %s must pass all %d of its tests with no skips, failures or errors, recorded %s"
                            % (layer, expected_layer, junit))
            all_ok = False
        for key in COUNT_KEYS:
            sums[key] += rec["junit"][key]
    if all_ok:
        if step.get("junit") != sums:
            problems.append("separate_processes: recorded totals %s differ from the sum of its layers %s" % (step.get("junit"), sums))
        if sums["tests"] != total:
            problems.append("separate_processes ran %d tests in total but %d were collected" % (sums["tests"], total))
    if not isinstance(step.get("ok"), bool) or step["ok"] != all_ok:
        problems.append("separate_processes: ok=%r contradicts its layers" % (step.get("ok"),))
    if mandatory and not all_ok:
        problems.append("mandatory step separate_processes did not pass in every layer")
    return all_ok


# --------------------------------------------------------------------------------------------- run evidence
def check_run_evidence(cases: Sequence[Dict[str, Any]], collected: Sequence[str], summary: Any, versions: Any,
                       screenshots: Sequence[str]) -> Tuple[List[str], List[str]]:
    """Return (problems, optional_notes). ``problems`` must be empty for the evidence to be accepted.

    Never raises on malformed evidence: an unexpected failure inside the checks is itself reported as a problem.
    """
    problems: List[str] = []
    notes: List[str] = []
    try:
        _check_run_evidence(cases, collected, summary, versions, screenshots, problems, notes)
    except Exception as exc:  # noqa: BLE001 - last line of defence; the explicit validation above should make this unreachable
        problems.append("run evidence is malformed (checker raised %s)" % type(exc).__name__)
    return problems, notes


def _check_run_evidence(cases: Sequence[Dict[str, Any]], collected: Sequence[str], summary: Any, versions: Any,
                        screenshots: Sequence[str], problems: List[str], notes: List[str]) -> None:
    total = len(cases)
    if total == 0:
        problems.append("JUnit contains no test cases")
    ids = [c.get("id") for c in cases]
    if len(set(ids)) != len(ids):
        problems.append("duplicate test identities in the JUnit evidence")
    if len(set(collected)) != len(list(collected)):
        problems.append("duplicate test identities in the collect-only evidence")
    layer_totals: Dict[str, int] = {}
    for c in cases:
        layer_totals[str(c.get("layer"))] = layer_totals.get(str(c.get("layer")), 0) + 1
    for layer in REQUIRED_CASE_LAYERS:
        if layer not in layer_totals:
            problems.append("no test of layer %s in the JUnit evidence" % layer)
    browser_expected = layer_totals.get("ui_playwright", 0) + layer_totals.get("e2e", 0)
    if not screenshots:
        problems.append("no browser screenshots in the evidence")

    if not isinstance(summary, dict):
        problems.append("run_summary.json is not an object")
        return
    steps = summary.get("steps")
    if not isinstance(steps, dict):
        problems.append("run_summary.steps is missing or not an object")
        return
    for key, expected_names in (("mandatory_steps", MANDATORY_STEPS), ("optional_steps", OPTIONAL_STEPS)):
        listed = _str_list(summary.get(key), "run_summary." + key, problems)
        if listed is not None and tuple(listed) != expected_names:
            problems.append("run_summary.%s must be exactly %s" % (key, list(expected_names)))
    for name in steps:
        if name not in MANDATORY_STEPS and name not in OPTIONAL_STEPS:
            problems.append("unknown step %r in run_summary" % (name,))

    failing_mandatory: List[str] = []
    for name in MANDATORY_STEPS:
        if name not in steps:
            problems.append("mandatory step %s is missing from run_summary" % name)
            continue
        expected = browser_expected if name.startswith("browser_") else total
        if _check_step(name, steps[name], expected, True, problems, layer_totals) is not True:
            failing_mandatory.append(name)
    for name in OPTIONAL_STEPS:
        if name not in steps:
            notes.append("optional step %s was not run" % name)
            continue
        ok = _check_step(name, steps[name], browser_expected if name.startswith("browser_") else total, False, problems, layer_totals)
        if ok is False:
            notes.append("optional step %s was run and FAILED" % name)

    leftover = _str_list(summary.get("leftover_chromedriver_processes"), "run_summary.leftover_chromedriver_processes", problems)
    if leftover:
        problems.append("chromedriver processes were left behind: %s" % leftover)
    mf = _str_list(summary.get("mandatory_failures"), "run_summary.mandatory_failures", problems)
    if mf is not None:
        expected_mf = list(failing_mandatory) + (["leftover_chromedriver_processes"] if leftover else [])
        if sorted(mf) != sorted(expected_mf):
            problems.append("run_summary.mandatory_failures %s disagrees with the recorded steps %s" % (mf, expected_mf))
        if mf:
            problems.append("run_summary records mandatory failures: %s" % mf)
    if not isinstance(summary.get("date"), str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", summary["date"]):
        problems.append("run_summary.date is missing or malformed")

    if not isinstance(versions, dict):
        problems.append("versions.json is not an object")
        return
    if summary.get("versions") != versions:
        problems.append("versions.json differs from run_summary.versions")
    for key in ("python", "platform"):
        if not isinstance(versions.get(key), str) or not versions[key]:
            problems.append("versions.%s is missing" % key)
    pk = versions.get("packages")
    if not isinstance(pk, dict):
        problems.append("versions.packages is missing")
    else:
        for pkg in REQUIRED_PACKAGES:
            if not pk.get(pkg):
                problems.append("versions.packages lacks %s" % pkg)
    for key in REQUIRED_BROWSER_VERSIONS:
        value = versions.get(key)
        if not isinstance(value, str) or not value or value.startswith("unavailable"):
            problems.append("versions.%s is missing or unavailable (a browser result cannot be claimed)" % key)


# --------------------------------------------------------------------------------------------- mutation evidence
def check_mutation_evidence(mres: Any, collected_total: int,
                            expected_ids: Iterable[str] = EXPECTED_MUTANT_IDS) -> List[str]:
    """Problems found in the mutation evidence; never raises on malformed input."""
    problems: List[str] = []
    try:
        _check_mutation_evidence(mres, collected_total, list(expected_ids), problems)
    except Exception as exc:  # noqa: BLE001 - last line of defence behind the explicit validation
        problems.append("mutation evidence is malformed (checker raised %s)" % type(exc).__name__)
    return problems


def _check_mutation_evidence(mres: Any, collected_total: int, expected: List[str], problems: List[str]) -> None:
    if not isinstance(mres, dict):
        problems.append("mutation_results.json is not an object")
        return
    base_totals = []
    for label in ("baseline_before", "baseline_after"):
        b = mres.get(label)
        if not isinstance(b, dict) or not all(_is_count(b.get(k)) for k in ("exit_code", "total", "failed")):
            problems.append("%s is missing or malformed" % label)
            continue
        if b["exit_code"] != 0 or b["failed"] != 0 or b["total"] <= 0:
            problems.append("%s is not a green baseline (%s)" % (label, b))
        base_totals.append(b["total"])
    if any(t != collected_total for t in base_totals):
        problems.append("baseline totals %s differ from the collected total %d" % (base_totals, collected_total))
    rest = mres.get("restoration")
    if not isinstance(rest, dict) or rest.get("real_tree_unchanged") is not True or not _is_count(rest.get("patched_files_checked")) \
            or rest["patched_files_checked"] <= 0:
        problems.append("restoration evidence is missing, empty or reports a modified real tree")

    mutants = mres.get("mutants")
    if not isinstance(mutants, list) or not mutants:
        problems.append("mutants list is missing or empty")
        return
    ids = [m.get("id") if isinstance(m, dict) and isinstance(m.get("id"), str) else None for m in mutants]
    if None in ids:
        problems.append("a mutant record is not an object with a string id")
    duplicates = sorted({i for i in ids if ids.count(i) > 1 and i is not None})
    if duplicates:
        problems.append("duplicate mutant ids: %s" % duplicates)
    missing = [i for i in expected if i not in ids]
    unexpected = [i for i in ids if i not in expected]
    if missing:
        problems.append("expected mutants missing from the evidence: %s" % missing)
    if unexpected:
        problems.append("unexpected mutant ids in the evidence: %s" % unexpected)
    for m in mutants:
        if not isinstance(m, dict):
            problems.append("a mutant record is not an object")
            continue
        mid = m.get("id")
        where = "mutant %s" % mid
        if m.get("verdict") != "CAUGHT_BY_ASSERTION":
            problems.append("%s verdict is %r, not CAUGHT_BY_ASSERTION" % (where, m.get("verdict")))
        intended, intended_failed = m.get("intended"), m.get("intended_failed")
        if not isinstance(intended, list) or not intended or not all(isinstance(t, str) and t for t in intended):
            problems.append("%s has no intended-test tokens" % where)
            continue
        if not isinstance(intended_failed, list) or not intended_failed or not all(isinstance(t, str) for t in intended_failed):
            problems.append("%s: no intended test failed (or the record is malformed)" % where)
            continue
        if not all(isinstance(t, str) and any(tok in t for tok in intended) for t in intended_failed):
            problems.append("%s: a recorded intended failure does not match its intended tokens" % where)
        first = m.get("first_failing_assertion")
        if not isinstance(first, dict) or not isinstance(first.get("test"), str) or not first.get("test") \
                or not isinstance(first.get("message"), str) or not first.get("message"):
            problems.append("%s: first failing assertion evidence is missing" % where)
        elif first["test"] not in intended_failed:
            problems.append("%s: the first failing assertion is not one of the intended failing tests" % where)
        raw_failed = m.get("all_failed")
        all_failed: List[str] = list(raw_failed) if isinstance(raw_failed, list) and all(isinstance(t, str) for t in raw_failed) else []
        all_failed_ok = bool(all_failed)
        if not all_failed_ok or not set(intended_failed) <= set(all_failed):
            problems.append("%s: all_failed does not contain the intended failures" % where)
        if not _is_count(m.get("failed")) or m["failed"] < 1 or (all_failed_ok and m["failed"] != len(all_failed)):
            problems.append("%s: failed count missing or inconsistent" % where)
        if m.get("errors") != 0:
            problems.append("%s: infrastructure errors recorded (%r)" % (where, m.get("errors")))
        if m.get("total") != collected_total:
            problems.append("%s ran %r tests but %d were collected" % (where, m.get("total"), collected_total))
        if not isinstance(m.get("patched_files"), list) or not m["patched_files"]:
            problems.append("%s records no patched files" % where)


# --------------------------------------------------------------------------------------------- privacy scrubbing
def private_markers(root: Path) -> List[str]:
    """Exact strings that identify this machine/user and must never appear in curated evidence."""
    markers: List[str] = []
    home = str(Path.home())
    for text in (str(root), home):
        for variant in (text, quote(text), quote(text, safe="")):
            if variant and variant not in markers:
                markers.append(variant)
    names = {socket.gethostname(), socket.gethostname().split(".")[0]}
    try:
        import platform
        names.add(platform.node())
        names.add(platform.node().split(".")[0])
    except Exception:  # pragma: no cover - best effort only
        pass
    for name in sorted(names, key=len, reverse=True):
        if len(name) >= 4 and name.lower() not in ("localhost", "local") and name not in markers:
            markers.append(name)
    return sorted(markers, key=len, reverse=True)


def scrub_text(text: str, root: Path) -> str:
    """Replace the project path, home directory, host name and temp-dir user names with neutral placeholders."""
    root_s, home_s = str(root), str(Path.home())
    for variant, label in ((quote(root_s), "<PROJECT>"), (quote(root_s, safe=""), "<PROJECT>"), (root_s, "<PROJECT>"),
                           (quote(home_s), "<HOME>"), (quote(home_s, safe=""), "<HOME>"), (home_s, "<HOME>")):
        if variant:
            text = text.replace(variant, label)
    for name in private_markers(root):
        if "/" not in name and "%" not in name:
            text = text.replace(name, "<host>")
    text = re.sub(r'hostname="[^"]*"', 'hostname="redacted"', text)
    text = re.sub(r"pytest-of-[A-Za-z0-9._-]+", "pytest-of-<user>", text)
    text = re.sub(r"/(?:private/)?var/folders/[^\s'\"<>\\]+", "<TMP>", text)
    text = re.sub(r"/(?:private/)?tmp/[^\s'\"<>\\]+", "<TMP>", text)
    text = re.sub(r"/Users/[^/\s'\"<>\\]+", "/Users/<user>", text)
    text = re.sub(r"/home/[^/\s'\"<>\\]+", "/home/<user>", text)
    return text


def find_private(text: str, root: Path) -> List[str]:
    """Markers that are still present in ``text`` (empty list = clean)."""
    found = [m for m in private_markers(root) if m in text]
    if re.search(r'hostname="(?!redacted")[^"]+"', text):
        found.append('hostname="..."')
    if re.search(r"/Users/(?!<user>)[^/\s'\"<>\\]+", text):
        found.append("/Users/<name>")
    return found
