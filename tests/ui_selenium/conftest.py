"""Selenium fixtures: one real headless Chrome per test, always quit."""
from __future__ import annotations

from typing import Iterator

import pytest
from selenium.webdriver.remote.webdriver import WebDriver

from modules.ui.page_objects.base_page import make_chrome_driver


@pytest.fixture
def chrome(request: pytest.FixtureRequest) -> Iterator[WebDriver]:
    driver = make_chrome_driver(headless=True)
    request.node._kqa_driver = driver  # for the failure-screenshot hook in the root conftest
    try:
        yield driver
    finally:
        driver.quit()
