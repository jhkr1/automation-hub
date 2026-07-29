"""Playwright 기반 나무위키 실시간 검색어 운영 수집기."""

from playwright.sync_api import Browser, Page, sync_playwright

from namuwiki_trend.extraction import HREF_PREFIX, RawItem, validate_and_rank_items
from namuwiki_trend.models import TrendItem

TARGET_URL = "https://namu.wiki/"
ROOT_LOCATOR = f'ul:has(> li > a[href^="{HREF_PREFIX}"])'
PAGE_TIMEOUT_MS = 30_000


def _read_raw_item(page: Page, index: int) -> RawItem:
    """페이지의 visible 항목에서 keyword와 href 원시값을 읽는다."""
    item = page.locator(ROOT_LOCATOR).locator(":scope > li").nth(index)
    anchor = item.locator(":scope > a")
    if anchor.count() != 1:
        raise RuntimeError(f"항목 {index + 1}의 직접 자식 anchor 개수가 1이 아님: {anchor.count()}")

    span = anchor.locator(":scope > span")
    if span.count() != 1:
        raise RuntimeError(f"항목 {index + 1}의 keyword span 개수가 1이 아님: {span.count()}")

    keyword = span.inner_text()
    href = anchor.get_attribute("href")
    if not keyword.strip():
        raise RuntimeError(f"항목 {index + 1}의 keyword를 읽지 못함")
    if href is None:
        raise RuntimeError(f"항목 {index + 1}의 href를 읽지 못함")

    return keyword, href


def _read_raw_items(page: Page) -> list[RawItem]:
    """root의 직접 자식 중 visible 항목의 원시값을 수집한다."""
    root = page.locator(ROOT_LOCATOR)
    root_count = root.count()
    if root_count != 1:
        raise RuntimeError(f"실시간 검색어 root 개수가 1이 아님: {root_count}")

    items = root.locator(":scope > li")
    raw_items = [
        _read_raw_item(page, index)
        for index in range(items.count())
        if items.nth(index).is_visible()
    ]
    if not raw_items:
        raise RuntimeError("visible li를 읽지 못함")

    return raw_items


def collect_trends() -> list[TrendItem]:
    """Headless Chromium으로 나무위키 실시간 검색어 Top10을 수집한다."""
    with sync_playwright() as playwright:
        browser: Browser = playwright.chromium.launch(headless=True)
        try:
            context = browser.new_context()
            try:
                page = context.new_page()
                response = page.goto(
                    TARGET_URL,
                    wait_until="domcontentloaded",
                    timeout=PAGE_TIMEOUT_MS,
                )
                if response is None:
                    raise RuntimeError("페이지 응답을 받지 못함")
                if response.status != 200:
                    raise RuntimeError(f"페이지 접속 상태 코드가 200이 아님: {response.status}")

                page.locator(ROOT_LOCATOR).first.wait_for(
                    state="visible",
                    timeout=PAGE_TIMEOUT_MS,
                )
                raw_items = _read_raw_items(page)
                return validate_and_rank_items(raw_items)
            finally:
                context.close()
        finally:
            browser.close()
