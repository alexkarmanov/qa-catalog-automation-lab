"""Render a real Allure report from allure-pytest results, after scrubbing machine identifiers (fail-closed).

allure-pytest records the machine host name as a ``host`` label and may keep absolute paths in traces. Both are
replaced in a *staged copy* of the results before ``allure generate`` runs, and the generated report is searched for
the markers again. Any leftover marker, a missing Allure CLI/Java runtime or a failing generator gives a non-zero
exit and leaves no report behind.

The Allure CLI needs a Java runtime. Neither is a project dependency: install them in an isolated folder and point
``ALLURE_BIN`` (and ``JAVA_HOME``) at them, or put ``allure`` on PATH. See docs/REPORTING.md.

Usage: python tools/allure_report.py --results artifacts/allure-results --out artifacts/allure-report [--versions versions.json]
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.evidence_check import find_private, scrub_text  # noqa: E402

TEXT_SUFFIXES = {".json", ".txt", ".properties", ".log", ".csv", ".xml", ".html"}
CATEGORIES = [
    {"name": "Product defects (assertion failed)", "matchedStatuses": ["failed"], "messageRegex": ".*(AssertionError|assert ).*"},
    {"name": "Test infrastructure (error or timeout)", "matchedStatuses": ["broken", "failed"], "messageRegex": ".*(Timeout|Error).*"},
]


def scrub_results(src: Path, dst: Path, root: Path = ROOT) -> int:
    """Copy ``src`` to ``dst`` replacing host-name labels and private paths in every text file; return files changed."""
    dst.mkdir(parents=True)
    changed = 0
    for path in sorted(src.iterdir()):
        target = dst / path.name
        if not path.is_file():
            continue
        if path.suffix.lower() in TEXT_SUFFIXES:
            text = path.read_text(encoding="utf-8", errors="replace")
            clean = scrub_results_text(text, root)
            changed += clean != text
            target.write_text(clean, encoding="utf-8")
        else:
            shutil.copy2(str(path), str(target))
    return changed


def scrub_results_text(text: str, root: Path) -> str:
    clean = scrub_text(text, root)
    if path_is_json_result(text):
        data = json.loads(clean)
        for label in data.get("labels", []):
            if label.get("name") in ("host", "thread"):
                label["value"] = "redacted"
        clean = json.dumps(data)
    return clean


def path_is_json_result(text: str) -> bool:
    return text.lstrip().startswith("{") and '"labels"' in text


def write_environment(dst: Path, versions: Optional[Dict[str, object]]) -> None:
    props: List[str] = []
    for key, value in sorted((versions or {}).items()):
        if isinstance(value, dict):
            props.extend("package.%s=%s" % (k, v) for k, v in sorted(value.items()))
        else:
            props.append("%s=%s" % (key, value))
    (dst / "environment.properties").write_text("\n".join(props) + "\n", encoding="utf-8")
    (dst / "categories.json").write_text(json.dumps(CATEGORIES, indent=2), encoding="utf-8")


def find_allure() -> Optional[str]:
    candidate = os.environ.get("ALLURE_BIN") or shutil.which("allure")
    return candidate if candidate and Path(candidate).exists() else None


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--versions", default=None, help="versions.json from tools/run_evidence.py (becomes the Environment widget)")
    args = parser.parse_args(argv)
    results, out = Path(args.results), Path(args.out)
    if not results.is_dir() or not any(results.glob("*-result.json")):
        print("no Allure results found in %s" % results.name, file=sys.stderr)
        return 2
    if out.exists():
        print("REFUSING to overwrite an existing report folder: %s" % out.name, file=sys.stderr)
        return 2
    allure = find_allure()
    if allure is None:
        print("Allure CLI not found (set ALLURE_BIN or add `allure` to PATH; it needs a Java runtime)", file=sys.stderr)
        return 3
    versions = json.loads(Path(args.versions).read_text(encoding="utf-8")) if args.versions else None
    work = Path(tempfile.mkdtemp(prefix="kqa_allure_"))
    try:
        staged = work / "results"
        changed = scrub_results(results, staged)
        write_environment(staged, versions)
        # The single-file report embeds its data (base64), so a marker could not be found in the output afterwards:
        # the staged INPUT must therefore be clean before generation.
        pre = []
        for path in staged.iterdir():
            if path.suffix.lower() in TEXT_SUFFIXES:
                pre += ["%s: %s" % (path.name, m) for m in find_private(path.read_text(encoding="utf-8", errors="replace"), ROOT)]
        if pre:
            print("private identifiers left in the scrubbed results:", *pre[:5], sep="\n  ", file=sys.stderr)
            return 5
        staged_out = work / "report"
        proc = subprocess.run([allure, "generate", "--single-file", "--clean", str(staged), "-o", str(staged_out)],
                              capture_output=True, text=True, timeout=900)
        if proc.returncode != 0 or not (staged_out / "index.html").exists():
            print("allure generate failed (exit %d): %s" % (proc.returncode, scrub_text(proc.stderr[-500:], ROOT)), file=sys.stderr)
            return 4
        leaks = []
        for path in staged_out.rglob("*"):
            if path.is_file() and path.suffix.lower() in TEXT_SUFFIXES:
                leaks += ["%s: %s" % (path.name, m) for m in find_private(path.read_text(encoding="utf-8", errors="replace"), ROOT)]
        if leaks:
            print("private identifiers left in the generated report:", *leaks[:5], sep="\n  ", file=sys.stderr)
            return 5
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(staged_out), str(out))
        print("Allure report written: %s (%d result files scrubbed)" % (out.name, changed))
        return 0
    finally:
        shutil.rmtree(str(work), ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
