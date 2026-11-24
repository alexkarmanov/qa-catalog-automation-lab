"""Helpers behind the publication and diagnostics evidence: the 2023-baseline line scanner and the Playwright trace scrubber."""
from __future__ import annotations

import json
import zipfile

import pytest

from tools import diagnostics_demo as dd
from tools import ip_audit as ia

pytestmark = [pytest.mark.framework, pytest.mark.negative]


def test_scanner_reports_location_and_origin_but_never_the_text(tmp_path, capsys):
    base = {"legacy/x.py": {"value = compute_something_distinctive(alpha, beta)"}}
    tree = tmp_path / "tree"
    tree.mkdir()
    (tree / "a.py").write_text("import os\nvalue = compute_something_distinctive(alpha,   beta)\nx = 1\n", encoding="utf-8")
    (tree / "b.md").write_text("nothing shared here, only prose\n", encoding="utf-8")
    hits = ia.scan_tree(tree, base, 24)
    assert hits == [("a.py", 2, "legacy/x.py")]
    assert "compute_something_distinctive" not in capsys.readouterr().out


def test_trivial_and_short_lines_are_not_leads():
    for line in ("import pytest", "from x import y", "def __init__(self) -> None:", "class Page(BasePage):", "}", "pass", "short = 1"):
        assert ia.TRIVIAL.match(line) or len(line) < 24


def test_trace_scrubber_removes_machine_paths_and_keeps_the_trace_valid(tmp_path):
    src, dst = tmp_path / "in.zip", tmp_path / "out.zip"
    event = json.dumps({"type": "before", "stack": [{"file": "%s/tests/x.py" % dd.ROOT, "line": 3}]})
    with zipfile.ZipFile(str(src), "w") as archive:
        archive.writestr("trace.trace", event + "\n" + json.dumps({"type": "after"}) + "\n")
        archive.writestr("trace.network", json.dumps({"url": "http://127.0.0.1:1/"}) + "\n")
        archive.writestr("resources/shot.png", b"\x89PNG\r\n\x1a\n")
    dd.scrub_trace(src, dst)
    with zipfile.ZipFile(str(dst)) as check:
        text = check.read("trace.trace").decode("utf-8")
        assert str(dd.ROOT) not in text and "<PROJECT>" in text
        assert check.read("resources/shot.png") == b"\x89PNG\r\n\x1a\n"
        assert check.testzip() is None


def test_diagnostics_tool_refuses_to_overwrite_and_rejects_unknown_mutants(tmp_path):
    existing = tmp_path / "keep"
    existing.mkdir()
    assert dd.main(["--mutant", "M13", "--out", str(existing)]) == 2
    assert dd.main(["--mutant", "M99", "--out", str(tmp_path / "new")]) == 2
    assert not (tmp_path / "new").exists()
