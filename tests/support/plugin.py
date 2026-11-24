"""Shared fixtures: per-test database, per-test real HTTP server on a random loopback port, API clients.

Loaded as a pytest plugin from the root ``conftest.py`` (so that the pytester-based isolation tests can load
exactly the same fixtures into an inner test session).
"""
from __future__ import annotations

import os
import shutil
from contextlib import ExitStack
from pathlib import Path
from typing import Callable, Iterator

import pytest

from modules.api.clients.catalog import CatalogClient
from sandbox.seed import create_database
from sandbox.server import RunningServer, start_server
from tests.support import golden
from tests.support.observer import Observer


@pytest.fixture
def db_path(tmp_path: Path) -> Iterator[str]:
    """A fresh seeded SQLite file in a directory owned by this test; removed afterwards."""
    owned = tmp_path / "caps_db"
    owned.mkdir()
    path = str(owned / "caps.db")
    create_database(path)
    try:
        yield path
    finally:
        shutil.rmtree(str(owned), ignore_errors=True)


@pytest.fixture
def server(db_path: str) -> Iterator[RunningServer]:
    srv = start_server(db_path)
    try:
        yield srv
    finally:
        srv.stop()


@pytest.fixture
def server_with_test_routes(db_path: str) -> Iterator[RunningServer]:
    srv = start_server(db_path, test_routes=True)
    try:
        yield srv
    finally:
        srv.stop()


@pytest.fixture
def observer(db_path: str) -> Observer:
    return Observer(db_path)


@pytest.fixture
def client_factory(server: RunningServer) -> Iterator[Callable[..., CatalogClient]]:
    """Return ``make(username=None)``: a new independent client (own cookie jar), logged in when a user is given."""
    with ExitStack() as stack:

        def make(username: str = "") -> CatalogClient:
            client = stack.enter_context(CatalogClient(server.url))
            if username:
                client.login(username, golden.USERS[username]["password"])
            return client

        yield make


@pytest.fixture
def anon(client_factory: Callable[..., CatalogClient]) -> CatalogClient:
    return client_factory()


@pytest.fixture
def viewer(client_factory: Callable[..., CatalogClient]) -> CatalogClient:
    return client_factory("viewer1")


@pytest.fixture
def editor(client_factory: Callable[..., CatalogClient]) -> CatalogClient:
    return client_factory("editor1")


@pytest.fixture
def publisher(client_factory: Callable[..., CatalogClient]) -> CatalogClient:
    return client_factory("publisher1")


@pytest.fixture(scope="session")
def artifacts_dir(pytestconfig: pytest.Config) -> Path:
    """Where screenshots and failure artifacts go (``KQA_ARTIFACTS`` or ``<rootdir>/artifacts``)."""
    path = Path(os.environ.get("KQA_ARTIFACTS", str(Path(str(pytestconfig.rootpath)) / "artifacts")))
    path.mkdir(parents=True, exist_ok=True)
    return path


@pytest.fixture
def evidence_shot(artifacts_dir: Path) -> Callable[..., str]:
    """``evidence_shot(page, 'name')`` stores a real screenshot under artifacts/screenshots/ and returns its path."""

    def take(page: object, name: str) -> str:
        target = artifacts_dir / "screenshots"
        target.mkdir(parents=True, exist_ok=True)
        path = str(target / (name + ".png"))
        page.screenshot(path=path)  # type: ignore[attr-defined]
        return path

    return take


def pytest_configure(config: pytest.Config) -> None:
    # Keep Playwright browsers inside the project folder unless the caller chose another location.
    root = Path(str(config.rootpath))
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(root / ".pw-browsers"))
