"""Run the mandatory checks in order and aggregate failures into one non-zero exit status.

Used by humans (``python tools/ci_check.py``) and by the CI workflow, so both run exactly the same commands.
Every step is executed even if an earlier one fails; the exit status is 1 if any mandatory step failed.
"""
from __future__ import annotations

import subprocess
import sys
import time
from typing import List, Optional, Sequence, Tuple

Step = Tuple[str, List[str]]


def default_steps() -> List[Step]:
    py = sys.executable
    return [
        ("lint (ruff)", [py, "-m", "ruff", "check", "."]),
        ("static types (mypy)", [py, "-m", "mypy"]),
        ("tests (pytest: JUnit, HTML, Allure results)", [
            py, "-m", "pytest", "-p", "no:cacheprovider",
            "--junitxml=artifacts/junit.xml", "--html=artifacts/report.html", "--self-contained-html",
            "--alluredir=artifacts/allure-results",
        ]),
    ]


def run_checks(steps: Sequence[Step], stream=None) -> int:
    out = stream or sys.stdout
    failed: List[str] = []
    for name, cmd in steps:
        started = time.monotonic()
        print("== %s" % name, file=out, flush=True)
        code = subprocess.call(cmd)
        print("-- %s: exit %d in %.1f s" % (name, code, time.monotonic() - started), file=out, flush=True)
        if code != 0:
            failed.append("%s (exit %d)" % (name, code))
    if failed:
        print("FAILED STEPS: " + "; ".join(failed), file=out, flush=True)
        return 1
    print("ALL STEPS PASSED", file=out, flush=True)
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    return run_checks(default_steps())


if __name__ == "__main__":
    sys.exit(main())
