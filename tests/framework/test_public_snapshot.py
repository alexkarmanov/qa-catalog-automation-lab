"""The publication-candidate builder: what it excludes, how it rewords, and that its audit refuses unclean content.

Pure functions only (no Git, no ZIP): the real build is part of the release evidence (docs/PUBLICATION_CHECKLIST.md).
Literals that look like personal data or secrets are assembled from pieces so this file itself stays publishable.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from tools import make_public_snapshot as ps

pytestmark = [pytest.mark.framework, pytest.mark.negative]
ROOT = Path(__file__).resolve().parents[2]
FAKE_HOME = "/Us" + "ers/someone/project"
FAKE_TOKEN = "gh" + "p_" + "A" * 36


def test_private_and_process_documents_are_excluded_and_public_versions_take_their_place():
    tracked = ["README.md", "CHANGELOG.md", "STATUS.md", "docs/LIMITATIONS.md", "docs/PUBLIC_README.md", "docs/PUBLIC_CHANGELOG.md",
               "docs/SOURCES_AND_RIGHTS.md", "docs/GATE0_PROVENANCE.md", "docs/CV_READY.md",
               "docs/evidence/baseline_2023/x.txt", "docs/evidence/run/junit_first_run.xml", "sandbox/app.py"]
    chosen = ps.select(tracked)
    assert chosen["README.md"] == "docs/PUBLIC_README.md"
    assert chosen["CHANGELOG.md"] == "docs/PUBLIC_CHANGELOG.md"
    assert chosen["docs/LIMITATIONS.md"] == "docs/LIMITATIONS.md"  # one limitations document, written to be public-safe
    assert "STATUS.md" not in chosen and "docs/SOURCES_AND_RIGHTS.md" not in chosen and "docs/CV_READY.md" not in chosen
    assert not any(k.startswith("docs/evidence/baseline_2023/") for k in chosen)
    assert chosen["sandbox/app.py"] == "sandbox/app.py" and "docs/evidence/run/junit_first_run.xml" in chosen
    assert "docs/PUBLIC_README.md" not in chosen  # only under its public name


def test_transform_rewords_for_a_public_reader_and_drops_private_artifact_lines():
    raw = b"Keep.\nThe owner decides.\nSee SOURCES_AND_RIGHTS for details.\nThe private backup is elsewhere.\nthe owner's choice\n"
    text = ps.transform("docs/x.md", raw).decode("utf-8")
    assert "Keep." in text and "The author decides." in text and "the author's choice" in text
    assert "SOURCES_AND_RIGHTS" not in text and "private backup" not in text
    assert ps.transform("a.py", b"the owner stays in code") == b"the owner stays in code"


@pytest.mark.parametrize("name,data,expected", [
    ("docs/a.md", ("see " + FAKE_HOME).encode(), "/Us" + "ers/someone"),
    ("tools/t.py", ("x = '" + FAKE_TOKEN + "'").encode(), "secret"),
    ("bin/driver.exe", b"MZ", "forbidden"),
    ("data/old.db", b"SQLite", "forbidden"),
    ("docs/big.md", b"x" * 2048, "larger"),
    ("docs/c.md", b"build in C:" + b"\\Users\\x\\y", "absolute path"),
    ("docs/d.md", b"-----BEGIN RSA PRIVATE" + b" KEY-----", "secret"),
], ids=["home-path", "token", "exe", "database", "oversize", "windows-path", "private-key"])
def test_audit_refuses_unclean_content(name, data, expected, monkeypatch):
    monkeypatch.setattr(ps, "MAX_FILE_BYTES", 1024)  # the real limit is 8 MB; a small one keeps the test fast
    problems = ps.audit({name: data})
    assert problems and any(expected in p for p in problems), problems


def test_audit_accepts_clean_content():
    assert ps.audit({"docs/a.md": b"# Title\nplain text\n", "tools/t.py": b"print('ok')\n", "x.png": b"\x89PNG"}) == []


def test_broken_markdown_links_are_found_and_valid_ones_pass():
    files = {"README.md": b"[ok](docs/a.md) [dir](docs/sub) [web](https://example.com/x) [anchor](#top) [bad](docs/missing.md)",
             "docs/a.md": b"[up](../README.md) [sibling](b.md#part) [bad](../nope.md)", "docs/b.md": b"x", "docs/sub/c.txt": b"x"}
    assert ps.broken_links(files) == ["README.md -> docs/missing.md", "docs/a.md -> ../nope.md"]


def test_root_readme_is_the_public_readme_verbatim():
    """In the review package the canonical file docs/PUBLIC_README.md and README.md must be identical. The publication candidate ships
    only README.md (the builder renames it), so the comparison applies when both exist."""
    readme = (ROOT / "README.md").read_bytes()
    canonical = ROOT / "docs" / "PUBLIC_README.md"
    assert readme.startswith(b"# ")
    if canonical.exists():
        assert readme == canonical.read_bytes()
