"""Setup-failure behaviour: a missing browser, a missing database or a bad bind must fail loudly and clearly."""
from __future__ import annotations

import subprocess
import sys

import pytest
from selenium.common.exceptions import WebDriverException

from modules.ui.page_objects.base_page import make_chrome_driver
from sandbox.server import start_server

pytestmark = [pytest.mark.framework, pytest.mark.negative]


def test_selenium_with_a_missing_chrome_binary_fails_with_a_driver_exception():
    with pytest.raises(WebDriverException) as info:
        make_chrome_driver(binary_location="/nonexistent/path/to/chrome")
    assert str(info.value)  # a readable message is present; the exception is a real driver error, not a hang


def test_playwright_without_installed_browsers_reports_the_missing_executable(tmp_path):
    empty = tmp_path / "no-browsers"
    empty.mkdir()
    code = (
        "from playwright.sync_api import sync_playwright\n"
        "with sync_playwright() as p:\n"
        "    p.chromium.launch()\n"
    )
    env = {"PATH": "/usr/bin:/bin", "PLAYWRIGHT_BROWSERS_PATH": str(empty), "HOME": str(tmp_path)}
    proc = subprocess.run([sys.executable, "-I", "-c", code], env=env, capture_output=True, text=True, timeout=60)
    assert proc.returncode != 0
    assert "Executable doesn't exist" in proc.stderr
    assert "playwright install" in proc.stderr  # the error tells the user how to fix it


def test_server_start_with_a_missing_database_file_fails_before_binding(tmp_path):
    with pytest.raises(FileNotFoundError):
        start_server(str(tmp_path / "does-not-exist.db"))
