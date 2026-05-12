"""Test login/logout flow."""
import pytest
from playwright.sync_api import Page

BASE_URL = "http://localhost:3000"


def test_login_page_loads(page: Page):
    page.goto(f"{BASE_URL}/login")
    assert page.locator('input[placeholder*="用户名"]').is_visible()
    assert page.locator('input[type="password"]').is_visible()
    assert page.locator('button[type="submit"]').is_visible()


def test_login_success(page: Page):
    page.goto(f"{BASE_URL}/login")
    page.fill('input[placeholder*="用户名"]', "admin")
    page.fill('input[type="password"]', "admin123")
    page.click('button[type="submit"]')
    page.wait_for_url(f"{BASE_URL}/", timeout=10000)
    assert page.url == f"{BASE_URL}/"


def test_login_failure(page: Page):
    page.goto(f"{BASE_URL}/login")
    page.fill('input[placeholder*="用户名"]', "admin")
    page.fill('input[type="password"]', "wrongpassword")
    page.click('button[type="submit"]')
    page.wait_for_timeout(2000)
    # Error message should appear
    error = page.locator('.err-tip')
    assert error.is_visible() or page.url == f"{BASE_URL}/login"


def test_logout(page: Page):
    # Login first
    page.goto(f"{BASE_URL}/login")
    page.fill('input[placeholder*="用户名"]', "admin")
    page.fill('input[type="password"]', "admin123")
    page.click('button[type="submit"]')
    page.wait_for_url(f"{BASE_URL}/", timeout=10000)
    # Click logout
    page.click('button[title="退出登录"]')
    page.wait_for_url(f"{BASE_URL}/login", timeout=5000)
    assert "login" in page.url.lower()
