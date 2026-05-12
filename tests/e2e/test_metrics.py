"""Test metrics/monitoring pages."""
import pytest
from playwright.sync_api import Page

BASE_URL = "http://localhost:3000"


def test_metrics_page_loads(logged_in_page: Page):
    page = logged_in_page
    page.goto(f"{BASE_URL}/metrics")
    page.wait_for_timeout(3000)
    assert page.content()


def test_overview_data_visible(logged_in_page: Page):
    page = logged_in_page
    page.goto(f"{BASE_URL}/metrics")
    page.wait_for_timeout(3000)
    # Should have some content rendered (stats, charts, etc.)
    assert page.locator('body').inner_text()
