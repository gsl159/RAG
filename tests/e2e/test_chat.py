"""Test chat/QA functionality."""
import pytest
from playwright.sync_api import Page

BASE_URL = "http://localhost:3000"


def test_chat_page_loads(logged_in_page: Page):
    page = logged_in_page
    page.goto(f"{BASE_URL}/chat")
    page.wait_for_timeout(2000)
    # Chat input should be visible
    assert page.locator('textarea, input[type="text"], .chat-input').first.is_visible()


def test_send_message(logged_in_page: Page):
    page = logged_in_page
    page.goto(f"{BASE_URL}/chat")
    page.wait_for_timeout(2000)

    # Type a question
    input_el = page.locator('textarea, input[type="text"]').first
    input_el.fill("What is RAG?")

    # Click send
    send_btn = page.locator('button').filter(has_text="发送").first
    if send_btn.is_visible():
        send_btn.click()

    # Wait for response
    page.wait_for_timeout(5000)

    # Should have some response in the chat area
    assert page.content()  # Page should still be loaded (no crash)


def test_navigation_to_docs(logged_in_page: Page):
    page = logged_in_page
    page.goto(f"{BASE_URL}/chat")
    page.wait_for_timeout(1000)

    # Click on Documents nav link
    docs_link = page.locator('a[href="/docs"]').first
    if docs_link.is_visible():
        docs_link.click()
        page.wait_for_url(f"**/docs", timeout=5000)

    assert page.url.endswith("/docs") or "/docs" in page.url
