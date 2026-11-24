"""KQA-001 regression: the SQLite URI must name exactly the file the caller passed.

The 2026 v1.0 adapter escaped only '?', so a path containing '#' (fragment) or '%' (escape) could open a
*different* existing database, and a "read-only" connection could then modify it. All databases here are
tiny synthetic SQLite files created in a pytest temporary directory.
"""
from __future__ import annotations

import os
import sqlite3
import sys
from contextlib import closing
from pathlib import Path
from typing import List, Tuple

import pytest

from modules.common.database import Database, DatabaseError, sqlite_file_uri
from tests.support.observer import Observer

pytestmark = [pytest.mark.database, pytest.mark.negative]

# (intended file name, decoy file name an unescaped URI would resolve to instead)
CASES: List[Tuple[str, str]] = [
    ("data#2026.db", "data"),            # '#' starts a URI fragment
    ("pct%41.db", "pctA.db"),            # '%41' would decode to 'A'
    ("with space.db", "with"),
    ("unicodé-данные.db", "unicod"),
    ("100%.db", "100.db"),
    ("a%23b.db", "a#b.db"),               # an already-encoded look-alike must stay literal
]
if sys.platform != "win32":
    CASES.append(("question?mark.db", "question"))  # '?' is not a legal file-name character on Windows


def _make(path: Path, marker: str) -> None:
    with closing(sqlite3.connect(str(path))) as conn:
        conn.execute("CREATE TABLE marker (v TEXT NOT NULL)")
        conn.execute("INSERT INTO marker VALUES (?)", (marker,))
        conn.commit()


def _marker(path: Path) -> str:
    with closing(sqlite3.connect(str(path))) as conn:
        return str(conn.execute("SELECT v FROM marker").fetchone()[0])


def _listing(folder: Path) -> List[str]:
    return sorted(os.listdir(str(folder)))


@pytest.mark.parametrize("intended,decoy", CASES, ids=[c[0] for c in CASES])
def test_readonly_adapter_opens_the_intended_file_and_cannot_write(tmp_path, intended, decoy):
    target, other = tmp_path / intended, tmp_path / decoy
    _make(target, "intended")
    _make(other, "decoy")
    files_before = _listing(tmp_path)

    with Database(str(target), readonly=True) as db:
        assert db.conn.execute("SELECT v FROM marker").fetchone()[0] == "intended"
        with pytest.raises(DatabaseError):
            db._execute("UPDATE marker SET v = 'changed'")

    assert _marker(target) == "intended"
    assert _marker(other) == "decoy"
    assert _listing(tmp_path) == files_before  # no journal, no new database file


@pytest.mark.parametrize("intended,decoy", CASES, ids=[c[0] for c in CASES])
def test_readwrite_adapter_writes_only_the_intended_file(tmp_path, intended, decoy):
    target, other = tmp_path / intended, tmp_path / decoy
    _make(target, "intended")
    _make(other, "decoy")
    with Database(str(target)) as db:
        db._write("UPDATE marker SET v = 'changed'")
    assert _marker(target) == "changed"
    assert _marker(other) == "decoy"


@pytest.mark.parametrize("intended,decoy", CASES, ids=[c[0] for c in CASES])
def test_observer_reads_the_intended_file(tmp_path, intended, decoy):
    target, other = tmp_path / intended, tmp_path / decoy
    _make(target, "intended")
    _make(other, "decoy")
    obs = Observer(str(target))
    assert obs._query("SELECT v FROM marker") == [("intended",)]
    with pytest.raises(sqlite3.OperationalError):
        # the observer's connection is read-only even for a hostile path
        with closing(sqlite3.connect(Path(str(target)).as_uri() + "?mode=ro", uri=True)) as conn:
            conn.execute("UPDATE marker SET v = 'changed'")
    assert _marker(target) == "intended"
    assert _marker(other) == "decoy"


@pytest.mark.parametrize("name", [c[0] for c in CASES], ids=[c[0] for c in CASES])
def test_missing_database_is_never_created_in_either_mode(tmp_path, name):
    missing = tmp_path / name
    for readonly in (True, False):
        with pytest.raises(sqlite3.OperationalError):
            with Database(str(missing), readonly=readonly):
                pass
    with pytest.raises(sqlite3.OperationalError):
        Observer(str(missing))._query("SELECT 1")
    assert _listing(tmp_path) == []


def test_relative_path_is_resolved_to_an_absolute_uri(tmp_path, monkeypatch):
    _make(tmp_path / "rel#1.db", "intended")
    _make(tmp_path / "rel", "decoy")
    monkeypatch.chdir(tmp_path)
    with Database("rel#1.db", readonly=True) as db:
        assert db.conn.execute("SELECT v FROM marker").fetchone()[0] == "intended"


def test_uri_builder_encodes_special_characters_and_sets_an_explicit_mode(tmp_path):
    uri = sqlite_file_uri(str(tmp_path / "a#b%c?d e.db"), readonly=True)
    assert uri.startswith("file:///") or uri.startswith("file://")
    assert uri.endswith("?mode=ro")
    stem = uri[: -len("?mode=ro")]
    assert "#" not in stem and "?" not in stem and " " not in stem
    assert "%23" in stem and "%25" in stem and "%3F" in stem.upper()
    assert sqlite_file_uri(str(tmp_path / "x.db"), readonly=False).endswith("?mode=rw")
    assert "rwc" not in uri
