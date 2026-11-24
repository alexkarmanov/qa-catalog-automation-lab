"""Page Object of the catalog list (Selenium)."""
from __future__ import annotations

from typing import Dict, Tuple

from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver

from modules.ui.page_objects.base_page import BasePage

TABLE = (By.CSS_SELECTOR, "[data-testid=catalog-table]")
CURRENT_USER = (By.CSS_SELECTOR, "[data-testid=current-user]")
LOGOUT = (By.CSS_SELECTOR, "[data-testid=logout]")
ROWS = (By.CSS_SELECTOR, "[data-testid=catalog-table] tbody tr")


class CatalogPage(BasePage):
    def __init__(self, driver: WebDriver, base_url: str):
        super().__init__(driver, base_url)

    def go_to(self) -> "CatalogPage":
        self.open("/catalog")
        return self

    def wait_loaded(self) -> "CatalogPage":
        self.wait_visible(TABLE)
        return self

    def current_user(self) -> str:
        return self.wait_visible(CURRENT_USER).text

    def rows(self) -> Dict[str, Tuple[str, str, str]]:
        """Return ``{sku: (name, quantity, state)}`` as displayed."""
        result: Dict[str, Tuple[str, str, str]] = {}
        for row in self.driver.find_elements(*ROWS):
            sku = row.get_attribute("data-sku") or ""
            result[sku] = (
                row.find_element(By.CSS_SELECTOR, ".col-name").text,
                row.find_element(By.CSS_SELECTOR, ".col-quantity").text,
                row.find_element(By.CSS_SELECTOR, ".col-state").text,
            )
        return result

    def logout(self) -> None:
        self.driver.find_element(*LOGOUT).click()
