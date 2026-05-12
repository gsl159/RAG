"""E2E test fixtures for Playwright."""
import pytest
from playwright.sync_api import sync_playwright, Page, Browser

BASE_URL = "http://localhost:3000"


@pytest.fixture(scope="session")
def browser():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, slow_mo=100)
        yield browser
        browser.close()


@pytest.fixture
def page(browser: Browser):
    context = browser.new_context(
        viewport={"width": 1280, "height": 800},
        locale="zh-CN",
    )
    page = context.new_page()
    yield page
    context.close()


@pytest.fixture
def logged_in_page(page: Page):
    """Login and return authenticated page."""
    page.goto(f"{BASE_URL}/login")
    page.fill('input[placeholder*="用户名"]', "admin")
    page.fill('input[type="password"]', "admin123")
    page.click('button[type="submit"]')
    page.wait_for_url(f"{BASE_URL}/", timeout=10000)
    return page
