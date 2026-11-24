"""G16: per-test isolation and teardown of owned resources (also when set-up or the body fails)."""
from __future__ import annotations

import json
import socket
import threading
from pathlib import Path

import pytest

from modules.common.database import Database
from sandbox.server import start_server
from tests.support import golden
from tests.support.observer import Observer

pytestmark = [pytest.mark.framework, pytest.mark.golden("G16")]

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def _inner_sessions_can_import_the_project(monkeypatch):
    """Inner pytest sessions run as subprocesses in a temporary directory; they need the project on sys.path."""
    monkeypatch.setenv("PYTHONPATH", str(REPO_ROOT))


def _port_is_closed(host: str, port: int) -> bool:
    with socket.socket() as sock:
        sock.settimeout(1.0)
        return sock.connect_ex((host, port)) != 0


def test_g16_seed_equals_the_independent_golden_literals(db_path, observer):
    assert observer.items() == golden.SEED_CATALOG_ROWS
    assert observer.customers() == golden.SEED_CUSTOMERS
    assert observer.orders() == golden.SEED_ORDERS
    assert observer.count_sessions() == 0
    users = Observer(db_path)._query("SELECT username, role FROM users ORDER BY username")
    assert users == sorted((u, d["role"]) for u, d in golden.USERS.items())


def test_g16_two_fixtures_in_one_test_are_independent(tmp_path):
    from sandbox.seed import create_database

    paths = []
    for name in ("a", "b"):
        path = str(tmp_path / (name + ".db"))
        create_database(path)
        paths.append(path)
    with start_server(paths[0]) as first, start_server(paths[1]) as second:
        assert first.port != second.port
        with Database(paths[0]) as db:
            db.insert_item("SYN-ONLY-A", "only in a", "", 1)
        assert Observer(paths[0]).count_items() == 4
        assert Observer(paths[1]).items() == golden.SEED_CATALOG_ROWS
        assert first.db_path != second.db_path


INNER_TESTS = '''
import os
import pytest
from modules.common.database import Database

def test_a_mutates_the_database(db_path):
    with Database(db_path) as db:
        db.insert_item("SYN-MUT", "mutation", "", 1)
        assert db.count("catalog_items") == 4

def test_b_sees_the_original_seed(db_path):
    with Database(db_path) as db:
        assert db.count("catalog_items") == 3
'''


@pytest.mark.parametrize("order", ["a_then_b", "b_then_a"])
def test_g16_consecutive_runs_and_any_order_see_the_original_seed(pytester, order):
    pytester.makepyfile(test_inner=INNER_TESTS)
    ids = ["test_inner.py::test_a_mutates_the_database", "test_inner.py::test_b_sees_the_original_seed"]
    if order == "b_then_a":
        ids.reverse()
    for _ in range(2):  # two separate sessions
        result = pytester.runpytest_subprocess("-p", "tests.support.plugin", "-p", "no:cacheprovider", *ids)
        result.assert_outcomes(passed=2)


FAILING_INNER = '''
import json, os
import pytest

def _record(tmp_path, server, db_path, kind):
    foreign = tmp_path / "foreign.txt"
    foreign.write_text("keep me")
    with open(os.environ["KQA_RECORD"], "a") as handle:
        handle.write(json.dumps({"kind": kind, "host": server.host, "port": server.port, "db": db_path,
                                 "foreign": str(foreign)}) + "\\n")

def test_body_fails(server, db_path, tmp_path):
    _record(tmp_path, server, db_path, "body")
    assert False, "intentional failure of the inner test body"

@pytest.fixture
def broken_setup(server, db_path, tmp_path):
    _record(tmp_path, server, db_path, "setup")
    raise RuntimeError("intentional set-up failure")

def test_setup_fails(broken_setup):
    pass
'''


def test_g16_failed_body_and_failed_setup_release_every_owned_resource(pytester, monkeypatch):
    record = pytester.path / "record.jsonl"
    monkeypatch.setenv("KQA_RECORD", str(record))
    pytester.makepyfile(test_failing=FAILING_INNER)

    result = pytester.runpytest_subprocess("-p", "tests.support.plugin", "-p", "no:cacheprovider")

    result.assert_outcomes(failed=1, errors=1)  # the inner failures are real and expected
    entries = [json.loads(line) for line in record.read_text().splitlines()]
    assert sorted(e["kind"] for e in entries) == ["body", "setup"]
    for entry in entries:
        assert _port_is_closed(entry["host"], entry["port"]), "server port still open after %s failure" % entry["kind"]
        assert not Path(entry["db"]).parent.exists(), "owned DB directory still exists"
        assert Path(entry["foreign"]).read_text() == "keep me"  # a foreign file next to the owned dir is untouched


def test_g16_server_stop_is_idempotent_and_frees_the_port(db_path):
    srv = start_server(db_path)
    host, port = srv.host, srv.port
    srv.stop()
    srv.stop()
    assert _port_is_closed(host, port)


def test_g16_failed_start_leaves_no_thread_behind(db_path):
    before = {t.name for t in threading.enumerate()}
    with socket.socket() as blocker:
        blocker.bind(("127.0.0.1", 0))
        blocker.listen(1)
        with pytest.raises(OSError):
            start_server(db_path, port=blocker.getsockname()[1])
    assert {t.name for t in threading.enumerate()} == before


def test_g16_server_refuses_non_loopback_hosts(db_path):
    for host in ("0.0.0.0", "192.0.2.1", "example.com", ""):
        with pytest.raises(ValueError):
            start_server(db_path, host=host)
