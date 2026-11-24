"""KQA-006: numbers quoted in the learning material and case study must match the suite that is actually collected.

The counts are recomputed with ``pytest --collect-only`` (collection only: nothing is executed), so adding or removing
a test without updating the documents fails here instead of leaving stale figures behind.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path
from typing import List

import pytest

pytestmark = [pytest.mark.framework]
ROOT = Path(__file__).resolve().parents[2]


def _collect(args: List[str]) -> int:
    env = dict(os.environ)
    env.pop("KQA_ORDER", None)
    cmd = [sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider", "-W", "ignore"] + args
    proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, env=env, timeout=300)
    match = re.search(r"(?:(\d+)/)?(\d+) tests? (?:collected|selected)", proc.stdout.strip().splitlines()[-1])
    assert match, proc.stdout[-300:]
    return int(match.group(1) or match.group(2))


@pytest.fixture(scope="module")
def total() -> int:
    return _collect([])


def _doc(name: str) -> str:
    """Text of ``docs/<name>`` (or a root-level file when ``name`` starts with ``/``); empty if the file is not shipped.

    Some documents are private to the review package and absent from the public snapshot; the number of tests must
    not depend on which documents exist, so the checks below loop over the files that are present.
    """
    path = ROOT / name[1:] if name.startswith("/") else ROOT / "docs" / name
    return path.read_text(encoding="utf-8") if path.exists() else ""


QUOTING_DOCS = ("/README.md", "CASE_STUDY.md", "CV_READY.md", "CV_LINKEDIN_UPWORK.md", "PUBLIC_README.md")
LEARNING_DOCS = ("ANSWER_KEY.md", "EXERCISES.md", "LEARNING_PATH.md", "INTERVIEW_QA.md")


def test_answer_key_header_states_the_current_suite_size(total):
    header = re.search(r"## E02 \(counts measured on the (\d+)-test suite\)", _doc("ANSWER_KEY.md"))
    assert header, "E02 header with the measured suite size is missing"
    assert int(header.group(1)) == total


def test_answer_key_selection_counts_match_the_real_collection():
    text = _doc("ANSWER_KEY.md")
    lines = re.findall(r"python -m pytest (.+?) --collect-only -q \| tail -1\s+# (\d+) selected", text)
    assert len(lines) == 3, "the three E02 commands must stay documented"
    for args, stated in lines:
        selection = [a.strip('"') for a in re.findall(r'"[^"]+"|\S+', args)]
        assert _collect(selection) == int(stated), "ANSWER_KEY says %s selected for: %s" % (stated, args)


def test_quoted_test_totals_match_the_collected_suite(total):
    quoted = 0
    for name in QUOTING_DOCS:
        stated = [int(n) for n in re.findall(r"\b(\d{3}) (?:passing |collected )?tests\b", _doc(name))]
        quoted += len(stated)
        assert set(stated) <= {total}, "%s quotes %s but the suite has %d tests" % (name, stated, total)
    assert quoted, "at least one document should quote the suite size"


def test_no_stale_suite_size_remains_in_the_learning_material(total):
    pattern = re.compile(r"\b(\d{3})(?:-test suite| (?:passing )?tests\b)")
    for name in LEARNING_DOCS + QUOTING_DOCS:
        for hit in pattern.findall(_doc(name)):
            assert int(hit) == total, "%s still quotes %s (suite has %d tests)" % (name, hit, total)


PRESENTED_DOCS = ("/README.md", "/CHANGELOG.md", "CASE_STUDY.md", "CV_LINKEDIN_UPWORK.md", "CV_READY.md", "LEARNING_PATH.md",
                  "INTERVIEW_QA.md", "PUBLIC_README.md", "LIMITATIONS.md")
AI_WORD = re.compile(r"\bAI\b|\bClaude\b", re.IGNORECASE)


def test_documents_present_the_project_and_its_history_accurately():
    """One test (the suite size is pinned by the evidence) for the settled presentation rules.

    The owner clarified that the 2023 project is their own work and asked that the project be presented by its technical content, with the
    AI involvement recorded accurately and concisely in the development history only.
    """
    checked = 0
    for name in PRESENTED_DOCS:
        text = _doc(name).lower()
        if not text:
            continue
        checked += 1
        # the old 'unconfirmed course material' stance must not return
        for phrase in ("course-based", "unconfirmed", "not been confirmed", "has not yet confirmed", "training and portfolio project"):
            assert phrase not in text, "%s still contains %r" % (name, phrase)
    assert checked >= 3

    # no overclaiming of authorship or skills anywhere that is presented
    for name in PRESENTED_DOCS + ("DEVELOPMENT_HISTORY.md",):
        text = _doc(name).lower()
        for phrase in ("written entirely by the owner", "written entirely by the author", "i personally implemented every",
                       "i have mastered", "i am an expert", "i built everything myself"):
            assert phrase not in text, "%s contains the overclaim %r" % (name, phrase)

    # the README leads with the project, not with AI, and points to the honest account
    for name in ("/README.md", "PUBLIC_README.md"):
        text = _doc(name)
        if not text:
            continue
        head = text.split("\n## ")[0].split("\n> ")[0]  # title and opening paragraph, before the history note
        assert not AI_WORD.search(head), "%s mentions AI in its title or opening paragraph" % name
        assert "personal QA automation project" in head
        assert "docs/DEVELOPMENT_HISTORY.md" in text, "the README must point to the development history"

    # CV entries are titled by the work, never by an AI label
    titles = 0
    for name in ("CV_READY.md", "CV_LINKEDIN_UPWORK.md"):
        for line in _doc(name).splitlines():
            if re.search(r"\(20\d\d[^)]*\)", line) and not line.startswith(("|", "- ", "* ")):
                titles += 1
                assert not AI_WORD.search(line), "%s: AI label in an entry title: %s" % (name, line)
    if _doc("CV_READY.md"):
        assert titles >= 3

    # the development history states the AI involvement briefly and honestly
    history = _doc("DEVELOPMENT_HISTORY.md")
    assert history, "docs/DEVELOPMENT_HISTORY.md must ship"
    assert "Claude" in history and "AI involvement" in history
    assert "does not claim" in history and "by hand" in history, "it must say that not every change was typed by hand"
    assert "independently coded" in history and "instructor" in history
    assert len(history.splitlines()) <= 70, "the AI account is meant to stay concise"
