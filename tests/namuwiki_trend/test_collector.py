"""Playwright Collector의 네트워크 비의존 경계 테스트."""

from unittest.mock import MagicMock

import pytest

from namuwiki_trend import collector
from namuwiki_trend.models import TrendItem


def _valid_raw_items() -> list[tuple[str, str]]:
    """Collector 테스트용 deterministic 원시 항목을 만든다."""
    items = [(f"keyword-{index}", f"/Go?q=keyword-{index}") for index in range(1, 11)]
    return [*items, items[0]]


def _mock_page(root_count: int = 1) -> MagicMock:
    """Collector 경계 테스트용 page mock을 만든다."""
    page = MagicMock()
    root = MagicMock()
    root.count.return_value = root_count
    page.locator.return_value = root
    return page


def _mock_playwright(page: MagicMock) -> tuple[MagicMock, MagicMock, MagicMock]:
    """Collector 실행과 cleanup 검증용 Playwright mock을 만든다."""
    playwright = MagicMock()
    browser = MagicMock()
    context = MagicMock()
    context.new_page.return_value = page
    browser.new_context.return_value = context
    playwright.chromium.launch.return_value = browser
    return playwright, browser, context


def test_collect_trends_returns_ten_ranked_items(monkeypatch: pytest.MonkeyPatch) -> None:
    """정상 원시 항목을 TrendItem 10개로 변환한다."""
    page = _mock_page()
    page.goto.return_value.status = 200
    playwright, browser, context = _mock_playwright(page)
    manager = MagicMock()
    manager.__enter__.return_value = playwright
    manager.__exit__.return_value = None
    monkeypatch.setattr(collector, "sync_playwright", lambda: manager)
    monkeypatch.setattr(collector, "_read_raw_items", lambda _: _valid_raw_items())

    result = collector.collect_trends()

    assert len(result) == 10
    assert all(isinstance(item, TrendItem) for item in result)
    assert [item.rank for item in result] == list(range(1, 11))
    context.close.assert_called_once()
    browser.close.assert_called_once()


@pytest.mark.parametrize("root_count", [0, 2])
def test_read_raw_items_rejects_invalid_root_count(root_count: int) -> None:
    """root가 정확히 하나가 아니면 실패한다."""
    with pytest.raises(RuntimeError, match="root 개수가 1이 아님"):
        collector._read_raw_items(_mock_page(root_count))


def test_read_raw_items_rejects_missing_anchor() -> None:
    """li에 직접 자식 anchor가 없으면 실패한다."""
    page = _mock_page()
    root = page.locator.return_value
    items = root.locator.return_value
    item = items.nth.return_value
    item.is_visible.return_value = True
    anchor = item.locator.return_value
    anchor.count.return_value = 0
    items.count.return_value = 1

    with pytest.raises(RuntimeError, match="anchor 개수가 1이 아님"):
        collector._read_raw_items(page)


def test_read_raw_items_rejects_missing_href() -> None:
    """anchor의 href를 읽지 못하면 실패한다."""
    page = _mock_page()
    root = page.locator.return_value
    items = root.locator.return_value
    item = items.nth.return_value
    item.is_visible.return_value = True
    anchor = item.locator.return_value
    anchor.count.return_value = 1
    anchor.get_attribute.return_value = None
    span = anchor.locator.return_value
    span.count.return_value = 1
    span.inner_text.return_value = "keyword-1"
    items.count.return_value = 1

    with pytest.raises(RuntimeError, match="href를 읽지 못함"):
        collector._read_raw_items(page)


def test_collect_trends_propagates_extraction_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """extraction validation 오류의 원인과 cleanup을 유지한다."""
    page = _mock_page()
    page.goto.return_value.status = 200
    playwright, browser, context = _mock_playwright(page)
    manager = MagicMock()
    manager.__enter__.return_value = playwright
    manager.__exit__.return_value = None
    monkeypatch.setattr(collector, "sync_playwright", lambda: manager)
    monkeypatch.setattr(collector, "_read_raw_items", lambda _: [("first", "/Go?q=first")])

    with pytest.raises(ValueError, match="항목이 부족함"):
        collector.collect_trends()

    context.close.assert_called_once()
    browser.close.assert_called_once()


def test_collect_trends_cleans_up_after_page_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """수집 중 예외가 발생해도 context와 browser를 종료한다."""
    page = _mock_page()
    page.goto.side_effect = RuntimeError("page failure")
    playwright, browser, context = _mock_playwright(page)
    manager = MagicMock()
    manager.__enter__.return_value = playwright
    manager.__exit__.return_value = None
    monkeypatch.setattr(collector, "sync_playwright", lambda: manager)

    with pytest.raises(RuntimeError, match="page failure"):
        collector.collect_trends()

    context.close.assert_called_once()
    browser.close.assert_called_once()
