"""Page Object of the sandbox sign-in page (successor of the 2023 GitHub ``SignInPage``)."""
from __future__ import annotations

from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver

from modules.ui.page_objects.base_page import BasePage

USERNAME = (By.ID, "username")
PASSWORD = (By.ID, "password")
SUBMIT = (By.ID, "login-submit")
ERROR = (By.CSS_SELECTOR, "[data-testid=login-error]")


class SignInPage(BasePage):
    def __init__(self, driver: WebDriver, base_url: str):
        super().__init__(driver, base_url)

    def go_to(self) -> "SignInPage":
        self.open("/login")
        self.wait_visible(SUBMIT)
        return self

    def try_login(self, username: str, password: str) -> None:
        self.wait_visible(USERNAME).send_keys(username)
        self.driver.find_element(*PASSWORD).send_keys(password)
        self.driver.find_element(*SUBMIT).click()

    def error_text(self) -> str:
        """Visible rejection message (waits for it; raises TimeoutException if it never appears)."""
        return self.wait_visible(ERROR).text
