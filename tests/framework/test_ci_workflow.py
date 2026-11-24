"""CI/CD readiness checks that need no network and no hosted runner (the workflow itself has never run hosted).

The syntax of ``.github/workflows/ci.yml`` was additionally validated against the published GitHub workflow JSON
schema with ``check-jsonschema`` (outside the locked dependencies; recorded in docs/CI_FIRST_HOSTED_RUN.md). These
tests pin the properties that matter for honesty: failures propagate, artifacts are kept even on failure, the
dependencies are the hash-locked ones, and the lock matches the declared direct dependencies.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = [pytest.mark.framework]
ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")


def _jobs(text: str) -> dict:
    body = text.split("\njobs:\n", 1)[1]
    parts = re.split(r"^  ([a-z][\w-]*):\n", body, flags=re.M)
    return {parts[i]: parts[i + 1] for i in range(1, len(parts), 2)}


def test_the_workflow_never_swallows_a_failure():
    code = "\n".join(line for line in WORKFLOW.splitlines() if not line.lstrip().startswith("#"))
    assert "continue-on-error" not in code
    assert "|| true" not in code and "set +e" not in code


def test_every_required_job_feeds_a_gate_that_fails_on_any_non_success():
    jobs = _jobs(WORKFLOW)
    assert set(jobs) == {"lint-types", "tests", "browsers", "ci-gate"}
    gate = jobs["ci-gate"]
    assert "needs: [lint-types, tests, browsers]" in gate
    assert "if: always()" in gate
    assert 'if [ "$r" != "success" ]' in gate and "exit 1" in gate


def test_reports_and_failure_diagnostics_are_uploaded_even_when_tests_fail():
    for name in ("tests", "browsers"):
        job = _jobs(WORKFLOW)[name]
        step = job.split("Keep reports and failure diagnostics", 1)[1]
        assert "if: always()" in step.split("uses:", 1)[0]
        assert "actions/upload-artifact@v4" in step
        assert "--junitxml=" in job and "--html=" in job and "--tracing retain-on-failure" in job


def test_all_three_playwright_engines_and_maintained_python_versions_are_in_the_matrix():
    jobs = _jobs(WORKFLOW)
    assert "browser: [chromium, firefox, webkit]" in jobs["browsers"]
    assert 'python: ["3.11", "3.12", "3.13"]' in jobs["tests"]
    assert '"3.9"' not in WORKFLOW and '"3.10"' not in WORKFLOW  # end-of-life interpreters are not tested


def test_dependencies_come_from_the_hash_locked_file_only():
    installs = re.findall(r"pip install (.+)", WORKFLOW)
    assert installs and all(i.strip() == "--require-hashes -r requirements.lock.txt" for i in installs)


def test_workflow_states_that_it_has_not_run_and_has_no_pass_badge():
    assert "NEVER been executed on a hosted runner" in WORKFLOW
    for doc in ("README.md",):
        text = (ROOT / doc).read_text(encoding="utf-8")
        assert "actions/workflows" not in text and "badge.svg" not in text, "a CI badge needs a real hosted pass first"


def _lock_entries() -> dict:
    text = (ROOT / "requirements.lock.txt").read_text(encoding="utf-8")
    entries = {}
    for block in re.split(r"\n(?=[A-Za-z0-9_.-]+==)", text):
        match = re.match(r"([A-Za-z0-9_.-]+)==([^\s;\\]+)", block)
        if match:
            entries[match.group(1).lower().replace("_", "-")] = (match.group(2), len(re.findall(r"--hash=sha256:[0-9a-f]{64}", block)))
    return entries


def test_every_locked_package_carries_sha256_hashes():
    entries = _lock_entries()
    assert len(entries) > 30
    assert all(count >= 1 for _, count in entries.values()), [n for n, (_, c) in entries.items() if c < 1]


def test_lock_contains_every_direct_dependency_at_the_declared_version():
    entries = _lock_entries()
    for line in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.startswith("#"):
            name, version = line.split("==")
            assert entries[name.lower().replace("_", "-")][0] == version.strip(), name


def test_project_declares_a_maintained_python_floor():
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'requires-python = ">=3.11"' in text and 'target-version = "py311"' in text
