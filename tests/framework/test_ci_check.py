"""The CI aggregator must fail when any child fails (it must never turn a failure into a pass)."""
from __future__ import annotations

import io
import sys

import pytest

from tools.ci_check import run_checks

pytestmark = [pytest.mark.framework, pytest.mark.negative]

OK = [sys.executable, "-c", "raise SystemExit(0)"]
BAD = [sys.executable, "-c", "raise SystemExit(3)"]


def test_all_children_passing_gives_exit_zero():
    stream = io.StringIO()
    assert run_checks([("one", OK), ("two", OK)], stream) == 0
    assert "ALL STEPS PASSED" in stream.getvalue()


def test_one_failing_child_gives_exit_one_and_names_the_step():
    stream = io.StringIO()
    assert run_checks([("good", OK), ("broken step", BAD), ("later", OK)], stream) == 1
    text = stream.getvalue()
    assert "FAILED STEPS: broken step (exit 3)" in text
    assert "== later" in text  # later steps still ran
    assert "ALL STEPS PASSED" not in text


def test_a_missing_executable_is_an_error_not_a_pass():
    with pytest.raises(FileNotFoundError):
        run_checks([("ghost", ["/nonexistent/binary-that-does-not-exist"])], io.StringIO())
