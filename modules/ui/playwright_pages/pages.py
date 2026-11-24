"""Playwright page objects. Locators use stable ``data-testid``/id attributes defined in docs/API_CONTRACT.md.

Assertions on visible state are done by the tests with ``expect(...)`` (auto-waiting, bounded); page objects only
expose locators and user actions, so a failing expectation always names the thing that was wrong.
"""
from __future__ import annotations

from playwright.sync_api import Locator, Page, expect


class LoginPage:
    def __init__(self, page: Page, base_url: str):
        self.page = page
        self.base_url = base_url.rstrip("/")
        self.username = page.locator("#username")
        self.password = page.locator("#password")
        self.submit = page.locator("#login-submit")
        self.error = page.get_by_test_id("login-error")
        self.notice = page.get_by_test_id("login-notice")

    def go_to(self) -> "LoginPage":
        self.page.goto(self.base_url + "/login")
        expect(self.submit).to_be_visible()
        return self

    def login(self, username: str, password: str) -> None:
        self.username.fill(username)
        self.password.fill(password)
        self.submit.click()


class CatalogPage:
    def __init__(self, page: Page, base_url: str):
        self.page = page
        self.base_url = base_url.rstrip("/")
        self.table = page.get_by_test_id("catalog-table")
        self.current_user = page.get_by_test_id("current-user")
        self.logout_button = page.get_by_test_id("logout")
        self.new_item_link = page.get_by_test_id("new-item-link")
        self.flash = page.get_by_test_id("flash")

    def go_to(self) -> "CatalogPage":
        self.page.goto(self.base_url + "/catalog")
        return self

    def row(self, sku: str) -> Locator:
        return self.page.locator('[data-testid=catalog-table] tbody tr[data-sku="%s"]' % sku)

    @property
    def rows(self) -> Locator:
        return self.page.locator("[data-testid=catalog-table] tbody tr")

    def displayed_skus(self) -> list:
        return [el.get_attribute("data-sku") for el in self.rows.all()]


class NewItemPage:
    def __init__(self, page: Page, base_url: str):
        self.page = page
        self.base_url = base_url.rstrip("/")
        self.sku = page.locator("#sku")
        self.name = page.locator("#name")
        self.description = page.locator("#description")
        self.quantity = page.locator("#quantity")
        self.submit = page.get_by_test_id("item-submit")
        self.errors = page.get_by_test_id("form-error")

    def go_to(self) -> "NewItemPage":
        self.page.goto(self.base_url + "/items/new")
        return self

    def create(self, sku: str, name: str, quantity: str, description: str = "") -> None:
        self.sku.fill(sku)
        self.name.fill(name)
        self.description.fill(description)
        self.quantity.fill(quantity)
        self.submit.click()


class ItemPage:
    def __init__(self, page: Page, base_url: str):
        self.page = page
        self.base_url = base_url.rstrip("/")
        self.state = page.get_by_test_id("item-state")
        self.name = page.get_by_test_id("item-name")
        self.quantity = page.get_by_test_id("item-quantity")
        self.flash = page.get_by_test_id("flash")
        self.edit_form = page.get_by_test_id("edit-form")
        self.edit_name = page.locator("#edit-name")
        self.edit_quantity = page.locator("#edit-quantity")
        self.edit_submit = page.get_by_test_id("edit-submit")
        self.publish_button = page.get_by_test_id("publish-button")
        self.lock_note = page.get_by_test_id("published-lock-note")
        self.errors = page.get_by_test_id("form-error")
        self.error_title = page.get_by_test_id("error-title")

    def go_to(self, sku: str) -> "ItemPage":
        self.page.goto(self.base_url + "/items/" + sku)
        return self
