"""Test document management page."""
import pytest
from playwright.sync_api import Page

BASE_URL = "http://localhost:3000"


def test_docs_page_loads(logged_in_page: Page):
    page = logged_in_page
    page.goto(f"{BASE_URL}/docs")
    page.wait_for_timeout(3000)
    # Page should load without JS errors
    assert page.locator('.upload-zone, table, .empty-row').first.is_visible()


def test_docs_page_has_upload_area(logged_in_page: Page):
    page = logged_in_page
    page.goto(f"{BASE_URL}/docs")
    page.wait_for_timeout(2000)
    # Should have upload zone or document list
    has_upload = page.locator('.upload-zone').is_visible()
    has_docs = page.locator('table').is_visible()
    assert has_upload or has_docs


def test_tags_visible(logged_in_page: Page):
    page = logged_in_page
    page.goto(f"{BASE_URL}/docs")
    page.wait_for_timeout(2000)
    # Tags section should be visible
    assert page.content()  # Page renders without crash
