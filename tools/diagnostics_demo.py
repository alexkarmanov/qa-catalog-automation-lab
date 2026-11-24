"""Produce REAL failure diagnostics: run the browser suites against a copy with one seeded defect and keep what pytest,
Playwright and Selenium recorded (failure screenshots, Playwright traces, JUnit and Allure results).

The defect is applied to a throw-away copy only (same mechanism as tools/mutation_runner.py); the real tree is untouched.
Nothing is fabricated: the folder is filled exclusively from files the failing run itself wrote. The tool exits non-zero if
the run did not fail, or if no screenshot or no valid trace was produced.

Usage: python tools/diagnostics_demo.py --mutant M13 --out docs/evidence/diagnostics
Open a trace with:  python -m playwright show-trace <folder>/trace.zip
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import mutation_runner as mr  # noqa: E402
from tools.evidence_check import find_private, scrub_text  # noqa: E402


def scrub_trace(src: Path, dst: Path) -> None:
    """Copy a Playwright trace replacing machine paths/user names in its text entries; refuse a trace that stays unclean or invalid."""
    with zipfile.ZipFile(str(src)) as zin, zipfile.ZipFile(str(dst), "w", zipfile.ZIP_DEFLATED) as zout:
        for info in zin.infolist():
            data = zin.read(info.filename)
            if not info.filename.startswith("resources/"):
                try:
                    text = data.decode("utf-8")
                except UnicodeDecodeError:
                    pass
                else:
                    data = scrub_text(text, ROOT).encode("utf-8")
            zout.writestr(info.filename, data)
    with zipfile.ZipFile(str(dst)) as check:
        for name in check.namelist():
            if name.endswith((".trace", ".network")):
                for line in check.read(name).decode("utf-8").splitlines():
                    if line.strip():
                        json.loads(line)  # still well-formed NDJSON after scrubbing
            if not name.startswith("resources/"):
                leaks = find_private(check.read(name).decode("utf-8", errors="replace"), ROOT)
                if leaks:
                    raise RuntimeError("private identifiers remain in trace entry %s: %s" % (name, leaks))


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mutant", default="M13")
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    out = Path(args.out)
    if out.exists():
        print("REFUSING to overwrite %s" % out.name, file=sys.stderr)
        return 2
    mutant = next((m for m in mr.MUTANTS if m["id"] == args.mutant), None)
    if mutant is None:
        print("unknown mutant", file=sys.stderr)
        return 2
    work = Path(tempfile.mkdtemp(prefix="kqa_diag_"))
    try:
        copy = work / "copy"
        mr.copy_project(copy)
        mr.apply_patches(copy, mutant["patches"])
        artifacts = work / "artifacts"
        env = dict(os.environ, KQA_ARTIFACTS=str(artifacts), PYTHONDONTWRITEBYTECODE="1",
                   PLAYWRIGHT_BROWSERS_PATH=os.environ.get("PLAYWRIGHT_BROWSERS_PATH", str(ROOT / ".pw-browsers")))
        env.pop("PYTHONPATH", None)
        cmd = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-W", "ignore", "tests/ui_playwright", "tests/e2e", "tests/ui_selenium",
               "--junitxml", str(work / "junit.xml"), "--alluredir", str(work / "allure-results"),
               "--tracing", "retain-on-failure", "--screenshot", "only-on-failure", "--output", str(work / "pw-output")]
        started = time.monotonic()
        proc = subprocess.run(cmd, cwd=str(copy), env=env, capture_output=True, text=True, timeout=900)
        seconds = round(time.monotonic() - started, 1)
        parsed = mr.parse_junit(work / "junit.xml")
        failed = [c for c in parsed["cases"] if c["status"] == "failed"]
        shots = sorted((artifacts / "failures").glob("*.png")) if (artifacts / "failures").exists() else []
        pw_shots = sorted((work / "pw-output").rglob("*.png"))
        traces = sorted((work / "pw-output").rglob("trace.zip"))
        problems = []
        if proc.returncode != 1 or not failed:
            problems.append("the defective copy did not fail (exit %s, %d failed tests)" % (proc.returncode, len(failed)))
        if not shots and not pw_shots:
            problems.append("no failure screenshot was produced")
        if not traces:
            problems.append("no Playwright trace was produced")
        for trace in traces:
            with zipfile.ZipFile(str(trace)) as archive:
                if archive.testzip() is not None or not any(n.endswith(".trace") for n in archive.namelist()):
                    problems.append("trace %s is not a valid Playwright trace" % trace.parent.name)
        if problems:
            print("DIAGNOSTICS FAILED:", *problems, sep="\n  ", file=sys.stderr)
            return 1
        out.mkdir(parents=True)
        index: Dict[str, Any] = {"mutant": mutant["id"], "defect": mutant["name"], "description": mutant["description"],
                                    "run_seconds": seconds, "exit_code": proc.returncode, "failed_tests": len(failed),
                                    "total_tests": len(parsed["cases"]), "failures": [], "files": []}
        for case in failed[:20]:
            index["failures"].append({"test": case["id"], "kind": case["kind"], "message": scrub_text(case["message"], ROOT)})
        seen_hashes = set()
        files_map: List[Dict[str, str]] = []
        for src in shots + pw_shots:
            digest = src.read_bytes()
            if digest in seen_hashes:  # pytest-playwright and our hook may both save the same screenshot
                continue
            seen_hashes.add(digest)
            name = "failure_screenshot_%02d.png" % (len(files_map) + 1)
            shutil.copy2(str(src), str(out / name))
            files_map.append({"file": name, "source": src.parent.name[-90:] if src.parent.name != "failures" else src.stem[-90:]})
        for number, src in enumerate(traces[:2], 1):
            name = "playwright_trace_%02d.zip" % number
            scrub_trace(src, out / name)
            files_map.append({"file": name, "source": src.parent.name[-90:]})
        index["file_sources"] = files_map
        junit = scrub_text((work / "junit.xml").read_text(encoding="utf-8"), ROOT)
        (out / "junit_failing_run.xml").write_text(junit, encoding="utf-8")
        shutil.copytree(str(work / "allure-results"), str(work / "allure-copy"))
        index["files"] = sorted(p.name for p in out.iterdir())
        leaks = [m for m in find_private(junit + json.dumps(index), ROOT)]
        if leaks:
            shutil.rmtree(str(out), ignore_errors=True)
            print("private identifiers in the diagnostics: %s" % leaks, file=sys.stderr)
            return 5
        (out / "INDEX.json").write_text(json.dumps(index, indent=2), encoding="utf-8")
        # the failing Allure results are returned to the caller through a side folder next to the output
        shutil.copytree(str(work / "allure-copy"), str(out.parent / (out.name + "_allure_results")))
        print("diagnostics written: %d failing tests, %d screenshots, %d traces" % (len(failed), len(shots) + len(pw_shots), len(traces)))
        return 0
    finally:
        shutil.rmtree(str(work), ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
