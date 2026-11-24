"""Derive TRACEABILITY.md, QA_REPORT.md and MUTATION_REPORT.md from the real evidence of a run.

Evidence that is missing, malformed, incomplete or inconsistent makes this tool exit non-zero - it never turns into a pass:
* JUnit must parse, every collected test id must appear in the JUnit file exactly once and vice versa,
* every test must have passed (no hidden skips/xfails) and every test layer must be present,
* every golden scenario G01-G16 must be covered by at least one test,
* every new-test reference in docs/LEGACY_MIGRATION_MAP.md must resolve to at least one collected test,
* the exact mandatory run configurations must be recorded, internally consistent and green (tools/evidence_check.py),
* the exact expected mutant population must be present, caught by assertion, between two green baselines,
* no host name, home directory or project path may survive in the curated evidence (it is scrubbed first).

Everything is validated and staged BEFORE any current file is replaced. On failure the current reports are not
overwritten with new content: they receive a STALE banner and docs/REPORT_GENERATION_FAILED.md is written, so a
failed run can never leave a report that looks like current PASS evidence. The evidence is plain, unsigned files;
these checks detect incomplete or inconsistent evidence, not deliberate, consistent tampering.

Usage: python tools/build_reports.py --evidence artifacts/evidence_run [--mutation docs/evidence/mutation/mutation_results.json]
       [--docs-dir docs]
"""
from __future__ import annotations

import argparse
import csv
import fnmatch
import json
import os
import re
import shutil
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from collections import Counter, OrderedDict
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import evidence_check as ec  # noqa: E402

DOCS = ROOT / "docs"
GENERATED_REPORTS = ("QA_REPORT.md", "TRACEABILITY.md", "MUTATION_REPORT.md")
FAILURE_NOTE = "REPORT_GENERATION_FAILED.md"

GOLDEN = OrderedDict([
    ("G01", "Invalid login: rejected, no session, UI error, protected endpoint rejects"),
    ("G02", "Valid viewer login/logout: published catalog visible, logout revokes access"),
    ("G03", "Draft visibility: anonymous/viewer cannot see the seeded draft, editor can"),
    ("G04", "Viewer/anonymous mutation attempts: forbidden, database unchanged"),
    ("G05", "Editor creates SYN-NEW qty 7: one committed DRAFT, viewer cannot see it"),
    ("G06", "Editor cannot publish: draft stays hidden"),
    ("G07", "Publisher publishes: PUBLISHED row, fresh viewer session sees it, DB matches"),
    ("G08", "Duplicate SKU: conflict, original unchanged"),
    ("G09", "Invalid input (types, bounds, unknown field, malformed JSON): rejected, no DB delta"),
    ("G10", "Edit draft with apostrophe: literal value persisted, other rows unchanged"),
    ("G11", "Edit published item: rejected under v1 policy"),
    ("G12", "Missing item / nonexistent update target: explicit error, no phantom row"),
    ("G13", "DB adapter insert/update/delete/unknown id: counts, values, affected rows"),
    ("G14", "Customer/item/order JOIN and foreign keys"),
    ("G15", "Timeout / malformed response: bounded typed failure"),
    ("G16", "Cross-test isolation and failed-test teardown"),
])

REQUIREMENTS = OrderedDict([
    ("R-03", ("No live third-party calls; loopback only", {"names": ["test_server_refuses_non_loopback_hosts", "test_test_only_routes_are_absent"]})),
    ("R-04", ("Meaningful login rejection", {"golden": ["G01"]})),
    ("R-05", ("Role-dependent catalog visibility", {"golden": ["G02", "G03"]})),
    ("R-06", ("Rejected mutations cause no DB change", {"golden": ["G04", "G06", "G09", "G11", "G12"]})),
    ("R-07", ("Only publisher publishes; published is immutable", {"golden": ["G05", "G06", "G07", "G11"]})),
    ("R-08", ("DB-enforced unique SKU, no overwrite", {"golden": ["G08"]})),
    ("R-09", ("Strict input schema", {"golden": ["G09"]})),
    ("R-10", ("Adapter CRUD/FK/rollback/JOIN concepts", {"golden": ["G13", "G14"]})),
    ("R-11", ("Bounded typed client failures", {"golden": ["G15"]})),
    ("R-12", ("Isolation and teardown", {"golden": ["G16"]})),
    ("R-13", ("Real browsers (Playwright primary, Selenium smoke)", {"markers": ["selenium", "playwright"]})),
    ("R-14", ("Complete browser -> API -> DB flows", {"markers": ["e2e"]})),
])


def sanitize(text: str) -> str:
    return re.sub(r"/(?:Users|private|var|tmp)/[^\s'\"|]+", "<PATH>", text)


def load_junit(path: Path) -> List[Dict]:
    root = ET.parse(str(path)).getroot()
    cases = []
    for case in root.iter("testcase"):
        classname = case.get("classname", "")
        nodeid = classname.replace(".", "/") + ".py::" + (case.get("name") or "")
        props = {p.get("name"): p.get("value") for p in case.iter("property")}
        status = "passed"
        for child in case:
            if child.tag == "failure":
                status = "failed"
            elif child.tag == "error":
                status = "error"
            elif child.tag == "skipped":
                status = "xfail" if "xfail" in (child.get("type") or "") else "skipped"
        cases.append({"id": nodeid, "status": status, "time": float(case.get("time") or 0),
                      "golden": [g for g in (props.get("golden") or "").split(",") if g],
                      "markers": [m for m in (props.get("markers") or "").split(",") if m],
                      "layer": props.get("layer") or ""})
    return cases


def collected_ids(path: Path) -> List[str]:
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if "::" in line and line.startswith("tests/")]


def check_map_references(collected: List[str], docs: Path = DOCS) -> Tuple[List[Tuple[str, int]], List[str]]:
    """Check the *New tests* column (last cell) of the 22-row table in LEGACY_MIGRATION_MAP.md against the collected ids."""
    text = (docs / "LEGACY_MIGRATION_MAP.md").read_text(encoding="utf-8")
    rows, missing = [], []
    last_path = ""
    for line in text.splitlines():
        if not re.match(r"^\| \d+ \|", line):
            continue
        new_cell = line.strip().strip("|").split(" | ")[-1]
        for token in re.findall(r"`((?:tests/[\w/]+\.py)?(?:\.\.\.)?::[\w\*\[\]\-]+|tests/[\w/]+\.py)`", new_cell):
            if token.startswith("..."):
                if not last_path:
                    continue
                token = last_path + token[3:]
            if "::" in token:
                last_path = token.split("::")[0]
            if "*" in token:
                matches = [c for c in collected if fnmatch.fnmatchcase(c, token)]
            else:
                matches = [c for c in collected if c.startswith(token)]
            rows.append((token, len(matches)))
            if not matches:
                missing.append(token)
    return rows, missing


def md_table(header: Sequence[str], body: Sequence[Sequence[object]]) -> str:
    out = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    out += ["| " + " | ".join(str(c).replace("|", "/") for c in row) + " |" for row in body]
    return "\n".join(out) + "\n"


def mark_stale(docs: Path, problems: Sequence[str]) -> None:
    """A failed generation must not leave current-looking PASS reports: banner them and write a failure note."""
    for name in GENERATED_REPORTS:
        path = docs / name
        if path.exists():
            text = path.read_text(encoding="utf-8")
            if not text.startswith(ec.STALE_BANNER):
                path.write_text(ec.STALE_BANNER + text, encoding="utf-8")
    note = ["# Report generation FAILED\n",
            "Date: %s\n" % time.strftime("%Y-%m-%d"),
            "`tools/build_reports.py` rejected the evidence. The generated reports in this folder are marked STALE and "
            "must not be cited as current results. Problems:\n"]
    note += ["* %s" % ec.scrub_text(str(p), ROOT) for p in problems]
    (docs / FAILURE_NOTE).write_text("\n".join(note) + "\n", encoding="utf-8")


def commit(stage: Path, docs: Path) -> None:
    """Move staged, fully validated outputs into place; clear any earlier failure marker."""
    try:
        run_dir = docs / "evidence" / "run"
        run_dir.parent.mkdir(parents=True, exist_ok=True)
        old = run_dir.with_name("run.old")
        if old.exists():
            shutil.rmtree(str(old))
        if run_dir.exists():
            os.replace(str(run_dir), str(old))
        os.replace(str(stage / "evidence" / "run"), str(run_dir))
        shutil.rmtree(str(old), ignore_errors=True)
        for name in GENERATED_REPORTS:
            os.replace(str(stage / name), str(docs / name))
        failure = docs / FAILURE_NOTE
        if failure.exists():
            failure.unlink()
    finally:
        shutil.rmtree(str(stage), ignore_errors=True)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--docs-dir", default=str(DOCS), help="documentation folder to update (default: docs)")
    parser.add_argument("--mutation", default=None, help="default: <docs-dir>/evidence/mutation/mutation_results.json")
    args = parser.parse_args(argv)
    try:
        return _generate(args)
    except Exception as exc:  # noqa: BLE001 - any unexpected failure is a controlled non-zero exit with stale-marking
        print("REPORT GENERATION FAILED (%s)" % type(exc).__name__, file=sys.stderr)
        try:
            mark_stale(Path(args.docs_dir), ["unexpected %s while validating the evidence" % type(exc).__name__])
        except OSError:
            pass
        return 1


def _generate(args: argparse.Namespace) -> int:
    ev = Path(args.evidence)
    docs = Path(args.docs_dir)
    problems: List[str] = []

    try:
        cases = load_junit(ev / "junit_first_run.xml")
        collected = collected_ids(ev / "collect_only.txt")
        summary = json.loads((ev / "run_summary.json").read_text(encoding="utf-8"))
        versions = json.loads((ev / "versions.json").read_text(encoding="utf-8"))
    except (OSError, ET.ParseError, ValueError) as exc:
        print("EVIDENCE MISSING OR MALFORMED:", exc, file=sys.stderr)
        mark_stale(docs, ["evidence missing or malformed: %s" % type(exc).__name__])
        return 2
    mpath = Path(args.mutation) if args.mutation else docs / "evidence" / "mutation" / "mutation_results.json"
    mres: Optional[Dict] = None
    try:
        mres = json.loads(mpath.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        problems.append("mutation evidence is missing or unreadable (%s): it is mandatory" % type(exc).__name__)
    shots_src = ev / "artifacts" / "screenshots"
    shot_names = sorted(p.name for p in shots_src.glob("*.png")) if shots_src.exists() else []
    for png in (shots_src.glob("*.png") if shots_src.exists() else []):
        if not png.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"):
            problems.append("screenshot %s is not a PNG file" % png.name)

    ids = [c["id"] for c in cases]
    if len(set(ids)) != len(ids):
        problems.append("duplicate test ids in JUnit")
    if sorted(ids) != sorted(collected):
        only_j = sorted(set(ids) - set(collected))[:5]
        only_c = sorted(set(collected) - set(ids))[:5]
        problems.append("JUnit and collect-only differ (junit=%d collected=%d) e.g. %s %s" % (len(ids), len(collected), only_j, only_c))
    status_counts = Counter(c["status"] for c in cases)
    if status_counts.get("passed", 0) != len(cases):
        problems.append("not every test passed: %s" % dict(status_counts))
    for gid in GOLDEN:
        if not any(gid in c["golden"] for c in cases):
            problems.append("golden scenario %s has no test" % gid)
    map_rows, map_missing = check_map_references(collected, docs)
    if map_missing:
        problems.append("LEGACY_MIGRATION_MAP references that resolve to no test: %s" % map_missing)
    run_problems, optional_notes = ec.check_run_evidence(cases, collected, summary, versions, shot_names)
    problems.extend(run_problems)
    if mres is not None:
        problems.extend(ec.check_mutation_evidence(mres, len(cases)))
    if problems:
        print("PROBLEMS (nothing was regenerated):", *problems, sep="\n  ", file=sys.stderr)
        mark_stale(docs, problems)
        return 1

    stage = Path(tempfile.mkdtemp(prefix=".reports_stage_", dir=str(docs)))  # staged next to the target, same filesystem
    try:
        code = build(args, ev, docs, stage, cases, collected, summary, versions, mres, mpath, optional_notes, map_rows)
    except Exception as exc:  # noqa: BLE001 - controlled non-zero exit instead of a traceback; never leaves current-looking reports
        shutil.rmtree(str(stage), ignore_errors=True)
        print("REPORT GENERATION FAILED (%s)" % type(exc).__name__, file=sys.stderr)
        mark_stale(docs, ["report generation raised %s" % type(exc).__name__])
        return 1
    except BaseException:
        shutil.rmtree(str(stage), ignore_errors=True)
        raise
    return code


def build(args: argparse.Namespace, ev: Path, docs: Path, stage: Path, cases: List[Dict], collected: List[str],
          summary: Dict, versions: Dict, mres: Optional[Dict], mpath: Path, optional_notes: List[str],
          map_rows: List[Tuple[str, int]]) -> int:
    problems: List[str] = []
    status_counts = Counter(c["status"] for c in cases)

    # ---------------------------------------------------------------- copy curated evidence
    run_dir = stage / "evidence" / "run"
    run_dir.mkdir(parents=True)
    leaks: List[str] = []
    for name in ("junit_first_run.xml", "report.html", "collect_only.txt", "run_summary.json", "versions.json", "coverage.json"):
        if (ev / name).exists():
            clean = ec.scrub_text((ev / name).read_text(encoding="utf-8"), ROOT)  # host name / home / project paths removed
            leaks += ["%s: %s" % (name, m) for m in ec.find_private(clean, ROOT)]
            (run_dir / name).write_text(clean, encoding="utf-8")
    shots_src = ev / "artifacts" / "screenshots"
    shots: List[str] = []
    (run_dir / "screenshots").mkdir()
    for png in sorted(shots_src.glob("*.png")):
        shutil.copy2(png, run_dir / "screenshots" / png.name)
        shots.append(png.name)
    engine_shots: Dict[str, List[str]] = {}
    for engine in ("chromium", "webkit", "firefox"):  # real screenshots of the same scenarios taken by each engine's own run
        src_dir = ev / "artifacts" / ("browser_" + engine) / "screenshots"
        pngs = sorted(src_dir.glob("*.png")) if src_dir.exists() else []
        if pngs:
            (run_dir / ("screenshots_" + engine)).mkdir()
            for png in pngs:
                if not png.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"):
                    problems.append("screenshot %s/%s is not a PNG file" % (engine, png.name))
                shutil.copy2(png, run_dir / ("screenshots_" + engine) / png.name)
            engine_shots[engine] = [p.name for p in pngs]
    with open(run_dir / "test_results.csv", "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["test_id", "layer", "golden", "markers", "status", "seconds"])
        for c in cases:
            writer.writerow([c["id"], c["layer"], ";".join(c["golden"]), ";".join(c["markers"]), c["status"], c["time"]])

    # ---------------------------------------------------------------- TRACEABILITY.md
    trace = ["# Requirements traceability (generated from the first full run)\n",
             "Generated by `tools/build_reports.py` from `docs/evidence/run/junit_first_run.xml` and `collect_only.txt`. "
             "Do not edit by hand. The complete per-test list is `docs/evidence/run/test_results.csv`.\n",
             "## 1. Requirements -> tests (see `SPEC.md`)\n"]
    body = []
    for rid, (title, sel) in REQUIREMENTS.items():
        matched = [c for c in cases if (set(sel.get("golden", [])) & set(c["golden"])) or (set(sel.get("markers", [])) & set(c["markers"]))
                   or any(n in c["id"] for n in sel.get("names", []))]
        body.append([rid, title, len(matched), sum(c["status"] == "passed" for c in matched),
                     ", ".join(sorted({c["golden"][0] for c in matched if c["golden"]})) or "-"])
    body += [["R-01, R-02, R-18", "Baseline preserved; every legacy test decided; history separated", "docs", "-", "GATE0_PROVENANCE, LEGACY_AUDIT, LEGACY_MIGRATION_MAP, evidence/baseline_2023, evidence/git_ancestry.txt"],
             ["R-15", "Seeded defects detected", "mutation", "-", "MUTATION_REPORT.md"],
             ["R-16, R-17", "Reports and clean reproducibility", "reports", "-", "QA_REPORT.md, CLEAN_VERIFICATION (package log)"]]
    trace.append(md_table(["Requirement", "Title", "Tests", "Passed", "Golden / evidence"], body))
    trace.append("\n## 2. Golden scenarios -> tests\n")
    body = []
    for gid, title in GOLDEN.items():
        matched = [c for c in cases if gid in c["golden"]]
        layers = Counter(c["layer"] for c in matched)
        body.append([gid, title, len(matched), sum(c["status"] == "passed" for c in matched),
                     ", ".join("%s:%d" % (k, v) for k, v in sorted(layers.items()))])
    trace.append(md_table(["ID", "Scenario", "Tests", "Passed", "Layers"], body))
    trace.append("\n## 3. Legacy migration map -> collected tests (reference check)\n")
    trace.append("Each new-test reference written in `LEGACY_MIGRATION_MAP.md` must resolve to at least one collected test (prefix or `*` match).\n\n")
    trace.append(md_table(["Reference in the map", "Collected tests matched"], [["`%s`" % t, n] for t, n in map_rows]))
    (stage / "TRACEABILITY.md").write_text("\n".join(trace), encoding="utf-8")

    # ---------------------------------------------------------------- QA_REPORT.md
    layer_counts = Counter(c["layer"] for c in cases)
    marker_counts = Counter(m for c in cases for m in c["markers"])
    total_time = sum(c["time"] for c in cases)
    steps = summary["steps"]

    def step_row(name: str, label: str) -> List[str]:
        s = steps.get(name)
        kind = "mandatory" if name in ec.MANDATORY_STEPS else "optional"
        if not s:
            return [label, kind, "not run", "-", "-"]
        j = s.get("junit", {})
        return [label, kind, "OK" if s.get("ok") else "FAILED", "%s passed / %s failed / %s errors / %s skipped" % (
            j.get("passed", "-"), j.get("failed", "-"), j.get("errors", "-"), j.get("skipped", "-")), "%s s" % (s.get("seconds") if "seconds" in s else round(sum(v.get("seconds", 0) for v in s.get("layers", {}).values()), 1))]

    cov_text = "Coverage was not collected in this evidence set.\n"
    cov_path = ev / "coverage.json"
    if cov_path.exists():
        cov = json.loads(cov_path.read_text(encoding="utf-8"))
        groups = {"target (sandbox/)": lambda p: p.startswith("sandbox/"),
                  "test support (modules/, tests/support/)": lambda p: p.startswith("modules/") or p.startswith("tests/support/")}
        rows = []
        for label, pred in groups.items():
            stmts = covered = branches = cbranches = 0
            for fname, data in cov["files"].items():
                if pred(fname):
                    s = data["summary"]
                    stmts += s["num_statements"]
                    covered += s["covered_lines"]
                    branches += s.get("num_branches", 0)
                    cbranches += s.get("covered_branches", 0)
            pct = lambda a, b: "%.1f%%" % (100.0 * a / b) if b else "n/a"  # noqa: E731
            rows.append([label, "%d / %d (%s)" % (covered, stmts, pct(covered, stmts)), "%d / %d (%s)" % (cbranches, branches, pct(cbranches, branches))])
        cov_text = md_table(["Measured area", "Lines covered", "Branches covered"], rows)
        cov_text += ("\nSubprocess coverage is **not** collected: the isolation tests start inner pytest sessions as subprocesses, and those are not "
                     "measured. The sandbox server runs in a thread of the test process, so its code *is* measured. Coverage is a diagnostic for "
                     "omissions, not an acceptance criterion.\n")

    pk = versions.get("packages", {})
    report = ["# QA report - karmanovqaauto 1.0.2 (modern suite)\n",
              "Generated by `tools/build_reports.py` from real runs (`docs/evidence/run/`). Historical 2023 results are kept separately in `docs/evidence/baseline_2023/` and in `LEGACY_AUDIT.md`.\n",
              "## 1. Environment (exactly what was used)\n",
              md_table(["Item", "Value"], [
                  ["Date", summary.get("date", "?")], ["OS", versions.get("platform")], ["Python", "%s (OpenSSL: %s)" % (versions.get("python"), versions.get("ssl"))],
                  ["Playwright Chromium", versions.get("playwright_chromium")], ["Playwright WebKit", versions.get("playwright_webkit")],
                  ["Playwright Firefox", versions.get("playwright_firefox", "not probed")], ["Chrome for Selenium / chromedriver", versions.get("selenium_chrome_and_driver")],
                  ["Chrome app", versions.get("chrome_for_selenium")],
                  ["Packages", ", ".join("%s %s" % (k, v) for k, v in sorted(pk.items()))]]),
              "\n**Not verified:** other operating systems (Linux, Windows), Python versions other than the one above%s, hosted CI (see `LIMITATIONS.md`).\n"
              % ("; **Firefox could not be launched on this machine** (%s)" % versions.get("playwright_firefox")
                 if str(versions.get("playwright_firefox", "unavailable")).startswith("unavailable") else ""),
              "\n## 2. Collection and first-run outcome\n",
              md_table(["Metric", "Value"], [
                  ["Tests collected", len(collected)], ["Tests in JUnit XML", len(cases)],
                  ["Passed", status_counts.get("passed", 0)], ["Failed", status_counts.get("failed", 0)], ["Errors", status_counts.get("error", 0)],
                  ["Skipped", status_counts.get("skipped", 0)], ["xfail", status_counts.get("xfail", 0)],
                  ["Retries / reruns", "none (no rerun plugin installed); the first run is the result"],
                  ["Sum of test durations", "%.1f s" % total_time]]),
              "\n### Collected tests per layer\n", md_table(["Layer", "Tests"], [[k, v] for k, v in sorted(layer_counts.items())]),
              "\n### Collected tests per marker (a test can carry several)\n", md_table(["Marker", "Tests"], [[k, v] for k, v in sorted(marker_counts.items())]),
              "\n## 3. Verification matrix\n",
              md_table(["Configuration", "Kind", "Result", "Counts", "Duration"], [
                  step_row("first_run", "First full run (JUnit + HTML + Allure results; includes Selenium Chrome)"),
                  step_row("reverse_order", "Reversed collection order"),
                  step_row("shuffled_order", "Shuffled order (seed 20261118)"),
                  step_row("separate_processes", "One pytest process per layer (6 processes)"),
                  step_row("browser_chromium", "Playwright scenarios on Chromium (ui_playwright + e2e)"),
                  step_row("browser_webkit", "Playwright scenarios on WebKit (same tests, `--browser webkit`)"),
                  step_row("browser_firefox", "Playwright scenarios on Firefox (same tests, `--browser firefox`)"),
                  step_row("parallel_xdist", "Parallel, pytest-xdist -n 4"),
                  step_row("coverage", "Coverage run")]),
              "\nParallel execution is **optional**; it was executed and is reported above. Leftover chromedriver processes after all runs: %s.\n"
              % (summary.get("leftover_chromedriver_processes") or "none"),
              "\n## 4. Coverage (target and test support reported separately)\n", cov_text,
              "\n## 5. Evidence files\n",
              "* `docs/evidence/run/junit_first_run.xml` - machine-readable first-run result\n"
              "* `docs/evidence/run/report.html` - self-contained pytest-html report\n"
              "* `docs/evidence/run/test_results.csv` - every test with layer, golden id, markers, status\n"
              "* `docs/evidence/run/screenshots/` - real browser screenshots: %s\n"
              "%s"
              "* Allure results are produced by the first run (`--alluredir`); rendering needs the Allure CLI (needs Java), which is not installed here, so **Allure was not rendered**.\n"
              "* Failure artifacts: a failing browser test stores a real screenshot under `artifacts/failures/`; see `MUTATION_REPORT.md` for representative failures produced by the seeded defects.\n"
              % (", ".join(shots) or "none",
                 "".join("* `docs/evidence/run/screenshots_%s/` - the same scenarios captured by the %s run: %s\n" % (e, e, ", ".join(n))
                         for e, n in engine_shots.items())),
              "\n## 6. Commands\n",
              "```bash\n"
              "python -m venv .venv && . .venv/bin/activate\n"
              "pip install -r requirements.lock.txt\n"
              "export PLAYWRIGHT_BROWSERS_PATH=\"$PWD/.pw-browsers\" && python -m playwright install chromium\n"
              "python -m pytest -p no:cacheprovider --junitxml=artifacts/junit.xml --html=artifacts/report.html --self-contained-html --alluredir=artifacts/allure-results\n"
              "python tools/run_evidence.py --out artifacts/evidence_run     # all configurations above\n"
              "python tools/mutation_runner.py                                  # seeded defects\n"
              "```\n",
              "\n## 7. Defects found during development\nSee `DEVELOPMENT_DEFECTS.md` (real defects of the 2026 code, not seeded mutants).\n",
              "\n## 8. Outcome of this generator's own consistency checks\n",
              "All mandatory checks passed: JUnit and collect-only reconcile exactly, every test passed, every layer and G01-G16 are covered, "
              "every reference in the migration map resolves, the exact mandatory run configurations are recorded with consistent counts and "
              "exit statuses, the exact expected mutant population is present and caught by assertion between two green baselines, and host "
              "names and filesystem paths were scrubbed from the curated evidence.\n"
              + "".join("* Note: %s.\n" % n for n in optional_notes)
              + "\n**Limits of this evidence:** the files are plain and unsigned. These checks detect missing, incomplete or inconsistent "
                "evidence and accidental errors; they do not authenticate the evidence and are not tamper-proof.\n"]
    (stage / "QA_REPORT.md").write_text("\n".join(report), encoding="utf-8")

    # ---------------------------------------------------------------- MUTATION_REPORT.md
    if mres is not None:
        rep = ["# Mutation (controlled defect) report\n",
               "Each mutant is a set of exact text patches applied to a **throw-away copy** of the project (`tools/mutation_runner.py`); the real tree is never modified, so no mutated code can ship. "
               "These are *seeded* defects, not real customer defects.\n",
               "Verdicts: `CAUGHT_BY_ASSERTION` = at least one pre-existing, relevant test failed with an assertion; `INFRASTRUCTURE_FAILURE` = fixture/collection error or crash (never counted as detection).\n",
               "\n## Baseline and restoration\n",
               md_table(["Check", "Result"], [
                   ["Baseline before (unmodified copy)", "exit %s, %s tests, %s failed" % (mres["baseline_before"]["exit_code"], mres["baseline_before"]["total"], mres["baseline_before"]["failed"])],
                   ["Baseline after (unmodified copy)", "exit %s, %s tests, %s failed" % (mres["baseline_after"]["exit_code"], mres["baseline_after"]["total"], mres["baseline_after"]["failed"])],
                   ["Real tree unchanged (hashes of all %s patched files)" % mres["restoration"]["patched_files_checked"], "yes" if mres["restoration"]["real_tree_unchanged"] else "NO"]]),
               "\n## Results\n"]
        body = []
        for m in mres["mutants"]:
            first = m.get("first_failing_assertion") or {}
            body.append([m["id"], m["name"], ", ".join(m["patched_files"]), "; ".join(m["intended"])[:160], m["verdict"], m["failed"],
                         ("`%s` - %s" % (first.get("test", "-").split("::")[-1], (first.get("message", "") or "")[:140].replace("|", "/"))) if first else "-"])
        rep.append(md_table(["ID", "Defect", "Patched files", "Intended tests (match)", "Verdict", "Failing tests", "First failing assertion"], body))
        rep.append("\nRestoration: every run used a fresh copy that was deleted afterwards; the final unmodified baseline run is green.\n")
        caught = sum(m["verdict"] == "CAUGHT_BY_ASSERTION" for m in mres["mutants"])
        rep.append("\n**Summary: %d of %d mutants caught by assertion.**\n" % (caught, len(mres["mutants"])))
        (stage / "MUTATION_REPORT.md").write_text("\n".join(rep), encoding="utf-8")
        if caught != len(mres["mutants"]):
            problems.append("not every mutant was caught by assertion")

    for name in GENERATED_REPORTS:
        text = (stage / name).read_text(encoding="utf-8")
        leaks += ["%s: %s" % (name, m) for m in ec.find_private(text, ROOT)]
    leaks += ["mutation evidence: %s" % m for m in ec.find_private(mpath.read_text(encoding="utf-8"), ROOT)]
    problems.extend("private identifier left in %s" % leak for leak in leaks)
    if problems:
        print("PROBLEMS (nothing was regenerated):", *problems, sep="\n  ", file=sys.stderr)
        shutil.rmtree(str(stage), ignore_errors=True)
        mark_stale(docs, problems)
        return 1
    commit(stage, docs)
    print("reports written; all consistency checks passed (%d tests)" % len(cases))
    return 0


if __name__ == "__main__":
    sys.exit(main())
