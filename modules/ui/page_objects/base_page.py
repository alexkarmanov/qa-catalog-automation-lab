"""Selenium base page (modernized successor of the 2023 ``BasePage``).

Defects fixed (docs/LEGACY_AUDIT.md LEG-01, LEG-10): no hard-coded driver path (Selenium 4 Selenium Manager
resolves the driver), the driver is always ``quit()`` rather than ``close()``d, and element access waits
explicitly with a bounded timeout instead of failing immediately.
"""
from __future__ import annotations

from typing import Optional, Tuple

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.support.ui import WebDriverWait

from modules.config import DEFAULT

Locator = Tuple[str, str]


def make_chrome_driver(headless: bool = True, binary_location: Optional[str] = None) -> WebDriver:
    options = Options()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--window-size=1280,900")
    options.add_argument("--no-first-run")
    options.add_argument("--no-default-browser-check")
    if binary_location:
        options.binary_location = binary_location
    return webdriver.Chrome(options=options)  # no Service(path): Selenium Manager finds/downloads the driver


class BasePage:
    def __init__(self, driver: WebDriver, base_url: str):
        self.driver = driver
        self.base_url = base_url.rstrip("/")
        self.timeout_s = DEFAULT.ui_timeout_ms / 1000.0

    def open(self, path: str) -> None:
        self.driver.get(self.base_url + path)

    def wait_visible(self, locator: Locator) -> WebElement:
        return WebDriverWait(self.driver, self.timeout_s).until(ec.visibility_of_element_located(locator))

    def wait_url_path(self, path: str) -> None:
        WebDriverWait(self.driver, self.timeout_s).until(lambda d: d.current_url == self.base_url + path)

    @property
    def current_path(self) -> str:
        return self.driver.current_url[len(self.base_url):]

    def quit(self) -> None:
        self.driver.quit()
