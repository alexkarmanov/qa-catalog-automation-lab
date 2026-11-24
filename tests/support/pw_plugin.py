"""Playwright fixtures (shared by tests/ui_playwright and tests/e2e). pytest-playwright supplies ``browser`` (one real Chromium per session) and ``page``
(a fresh, isolated browser context per test). A second, independent browser session is a second context."""
from __future__ import annotations

from contextlib import ExitStack
from typing import Callable, Iterator

import pytest
from playwright.sync_api import Browser, BrowserContext, Page, expect

from modules.config import DEFAULT
from tests.support import golden


@pytest.fixture(autouse=True)
def _bounded_expect_timeout() -> None:
    expect.set_options(timeout=DEFAULT.ui_timeout_ms)


@pytest.fixture
def new_session(browser: Browser) -> Iterator[Callable[[], Page]]:
    """Open an additional, fully independent browser context (own cookies/storage); all are closed afterwards."""
    with ExitStack() as stack:

        def make() -> Page:
            context: BrowserContext = browser.new_context()
            stack.callback(context.close)
            return context.new_page()

        yield make


@pytest.fixture
def sign_in(server) -> Callable[..., None]:
    """``sign_in(page, 'editor1')`` logs the page in through the real login form."""
    from modules.ui.playwright_pages.pages import LoginPage

    def _sign_in(page: Page, username: str) -> None:
        login = LoginPage(page, server.url).go_to()
        login.login(username, golden.USERS[username]["password"])
        expect(page.get_by_test_id("current-user")).to_have_text("%s (%s)" % (username, golden.USERS[username]["role"]))

    return _sign_in
