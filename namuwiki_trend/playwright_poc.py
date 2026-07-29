"""Playwright 기반 나무위키 실시간 검색어 Top10 추출 검증 코드."""

from time import perf_counter

from playwright.sync_api import Browser, Page, sync_playwright

from namuwiki_trend.extraction import RawItem, validate_and_rank_items
from namuwiki_trend.models import TrendItem

TARGET_URL = "https://namu.wiki/"
ROOT_LOCATOR = 'ul:has(> li > a[href^="/Go?q="])'


def _read_raw_item(page: Page, index: int) -> RawItem:
    """페이지의 root에서 지정한 visible 항목의 원시 값을 읽는다."""
    item = page.locator(ROOT_LOCATOR).locator(":scope > li").nth(index)
    anchor = item.locator(":scope > a")
    span = anchor.locator(":scope > span")

    keyword = span.inner_text() if span.count() == 1 else ""
    href = anchor.get_attribute("href") if anchor.count() == 1 else None
    return keyword, href


def extract_top10(page: Page) -> list[TrendItem]:
    """검증된 DOM 규칙으로 실시간 검색어 Top10을 추출한다."""
    root = page.locator(ROOT_LOCATOR)
    root_count = root.count()
    if root_count != 1:
        raise RuntimeError(f"실시간 검색어 root 개수가 1이 아님: {root_count}")

    items = root.locator(":scope > li")
    visible_indexes = [index for index in range(items.count()) if items.nth(index).is_visible()]
    if len(visible_indexes) < 2:
        raise RuntimeError(f"visible li가 부족함: {len(visible_indexes)}개")

    raw_items = [_read_raw_item(page, index) for index in visible_indexes]
    return validate_and_rank_items(raw_items)


def run_poc() -> list[TrendItem]:
    """Headless Chromium으로 페이지에 접속하고 Top10을 추출한다."""
    with sync_playwright() as playwright:
        browser: Browser = playwright.chromium.launch(headless=True)
        context = browser.new_context()
        try:
            page = context.new_page()
            response = page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=30_000)
            if response is None:
                raise RuntimeError("페이지 응답을 받지 못함")
            if response.status != 200:
                raise RuntimeError(f"페이지 접속 상태 코드가 200이 아님: {response.status}")

            page.locator(ROOT_LOCATOR).first.wait_for(state="visible", timeout=30_000)
            return extract_top10(page)
        finally:
            context.close()
            browser.close()


def main() -> None:
    """PoC를 실행하고 rank, keyword, href를 콘솔에 출력한다."""
    started_at = perf_counter()
    items = run_poc()
    for item in items:
        print(f"rank={item.rank}, keyword={item.keyword}, href={item.href}")
    print(f"total_elapsed_ms={(perf_counter() - started_at) * 1000:.1f}")


if __name__ == "__main__":
    main()
