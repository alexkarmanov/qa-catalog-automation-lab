# Glossary / Глоссарий (EN / RU)

| English | Русский | Meaning in this project |
|---|---|---|
| assertion | проверка (assert) | A statement in a test that must be true; if false, the test fails. |
| fixture | фикстура | Reusable set-up/tear-down code that provides a test with a resource (pytest). |
| marker | маркер | A label on a test (`@pytest.mark.api`) used to select or classify tests. |
| parametrize | параметризация | Run one test function with several data sets. |
| test double / mock | заглушка / мок | A fake dependency. Not used for acceptance here: browsers, HTTP and SQLite are real. |
| system under test (SUT) | тестируемая система | The sandbox application that the tests exercise. |
| sandbox | песочница | The small synthetic local web application (CAPS). |
| synthetic data | синтетические данные | Invented data with no link to real people or customers. |
| golden value | эталонное значение | A literal expected value written before the implementation. |
| oracle | оракул (источник ожидаемого) | The independent source that says what the right answer is (here: golden literals and the observer's own SQL). |
| observer | наблюдатель | Test helper that reads the database directly with its own SQL. |
| REST API | REST API | HTTP interface returning JSON. |
| status code | код статуса | HTTP result: 200 OK, 201 Created, 400 Bad Request, 401 Unauthorized, 403 Forbidden, 404 Not Found, 409 Conflict. |
| authentication | аутентификация | Proving who you are (login). |
| authorization | авторизация | Deciding what a known user may do (roles). |
| role | роль | viewer, editor or publisher. |
| session / cookie | сессия / cookie | Server-side login record and the browser cookie that points to it. |
| negative test | негативный тест | A test that checks that something is rejected. |
| side effect | побочный эффект | An unwanted change, for example a database write caused by a rejected request. |
| delta | дельта (разница) | Difference between the database before and after an action; "no DB delta" means no change. |
| isolation | изоляция | Each test has its own data and server, so tests cannot affect each other. |
| flaky test | нестабильный тест | A test that sometimes passes and sometimes fails without a code change. |
| timeout | тайм-аут | Maximum waiting time; after it the operation fails with a clear error. |
| explicit wait | явное ожидание | Waiting for a condition with a limit, instead of a fixed `sleep`. |
| locator | локатор | How a test finds an element on a page (id, CSS selector, test id). |
| stale selector | устаревший селектор | A locator that no longer matches because the page changed. |
| Page Object | объект страницы | A class that hides locators and actions of one page. |
| browser context | контекст браузера | An isolated browser profile (cookies, storage) inside one browser (Playwright). |
| headless | без графического окна | A browser that runs without a visible window. |
| end-to-end (E2E) | сквозной тест | A test that goes through UI, API and database together. |
| test pyramid | пирамида тестирования | Many fast low-level tests, fewer slow UI tests. |
| mutation / mutant | мутация / мутант | A deliberately injected defect used to check that the tests notice it. |
| baseline | базовая линия | The unchanged starting point (the 2023 repository). |
| traceability | прослеживаемость | A table linking requirements to tests and results. |
| JUnit XML | JUnit XML | Machine-readable test result file. |
| CI (continuous integration) | непрерывная интеграция | Automatic run of checks on every change (configured here, not executed). |
| provenance | происхождение | Where code and data came from and who owns them. |
| foreign key | внешний ключ | A database rule that a reference must point to an existing row. |
| transaction / rollback | транзакция / откат | A group of changes applied all together or not at all. |
| parameterized SQL | параметризованный SQL | Values passed separately from the SQL text, which prevents quoting bugs and injection. |
