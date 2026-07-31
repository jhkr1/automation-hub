"""Playwright-based Google Finance quote collector."""

from __future__ import annotations

import re
from collections.abc import Callable
from urllib.parse import quote

from playwright.sync_api import Browser, Locator, Page, sync_playwright

from google_finance.config import get_logger
from google_finance.models import RawStockQuote

BASE_QUOTE_URL = "https://www.google.com/finance/quote/"
DEFAULT_LOCALE = "en-US"
PAGE_TIMEOUT_MS = 30_000
SYMBOL_PATTERN = re.compile(r"^[A-Za-z0-9._-]+:[A-Za-z0-9._-]+$")

def validate_symbol(symbol: str) -> str:
    """Validate and normalize an exchange-qualified symbol."""
    if not isinstance(symbol, str):
        raise TypeError("symbol must be a string")

    normalized = symbol.strip().upper()
    if not SYMBOL_PATTERN.fullmatch(normalized):
        raise ValueError("symbol must use EXCHANGE:TICKER format")
    return normalized


def build_quote_url(symbol: str) -> str:
    """Build a direct Google Finance quote URL for a validated symbol."""
    normalized = validate_symbol(symbol)
    return f"{BASE_QUOTE_URL}{quote(normalized, safe=':')}"


def _require_one(locator: Locator, description: str) -> Locator:
    """Return a locator only when exactly one DOM element matches."""
    count = locator.count()
    if count != 1:
        raise RuntimeError(f"Google Finance {description} locator matched {count} elements")
    return locator.first


def _wait_for_one(
    locator: Locator,
    description: str,
    *,
    timeout_ms: int = PAGE_TIMEOUT_MS,
) -> Locator:
    """Wait for one visible element and then enforce the exact-match contract."""
    locator.wait_for(state="visible", timeout=timeout_ms)
    return _require_one(locator, description)


def _quote_container(page: Page, symbol: str, *, timeout_ms: int) -> Locator:
    """Limit selectors to the quote area belonging to one symbol."""
    symbol_locator = _wait_for_one(
        page.locator(f'div.JV7gl[title="{symbol}"]'),
        "symbol",
        timeout_ms=timeout_ms,
    )
    return _require_one(
        symbol_locator.locator(
            "xpath=ancestor::*[.//div[contains(concat(' ', normalize-space(@class), ' '), "
            "' ujg0He ') ]][1]"
        ),
        "quote container",
    )


def _read_raw_quote(page: Page, symbol: str, *, timeout_ms: int) -> RawStockQuote:
    """Read raw displayed strings from a symbol-scoped quote container."""
    container = _quote_container(page, symbol, timeout_ms=timeout_ms)
    current_block = _wait_for_one(
        container.locator("div.ujg0He"), "current quote", timeout_ms=timeout_ms
    )
    current_price = _wait_for_one(
        current_block.locator("div.N6SYTe"), "current price", timeout_ms=timeout_ms
    )
    change_percent = _wait_for_one(
        current_block.locator('span[jsname="vY9t3b"]'),
        "change percent",
        timeout_ms=timeout_ms,
    )
    name = _wait_for_one(container.locator("div.gO24Ff"), "name", timeout_ms=timeout_ms)
    currency_metadata = _wait_for_one(
        container.locator("div.jZZ2de"),
        "currency metadata",
        timeout_ms=timeout_ms,
    )
    previous_close = _wait_for_one(
        container.locator("div.W28Ftf"),
        "previous close",
        timeout_ms=timeout_ms,
    )
    open_price = _wait_for_one(
        container.locator("div.KxsRFb:visible").filter(has_text="Open"),
        "open price",
        timeout_ms=timeout_ms,
    )

    return RawStockQuote(
        symbol=symbol,
        name_text=name.inner_text(),
        current_price_text=current_price.inner_text(),
        currency_text=currency_metadata.inner_text(),
        previous_close_text=previous_close.inner_text(),
        open_price_text=open_price.inner_text(),
        change_percent_text=change_percent.inner_text(),
    )


def collect_stock_quote(
    symbol: str,
    *,
    locale: str = DEFAULT_LOCALE,
    timeout_ms: int = PAGE_TIMEOUT_MS,
    playwright_factory: Callable[[], object] = sync_playwright,
) -> RawStockQuote:
    """Collect one rendered Google Finance quote as raw strings."""
    normalized = validate_symbol(symbol)
    if type(timeout_ms) is not int or timeout_ms <= 0:
        raise ValueError("timeout_ms must be a positive integer")
    if not isinstance(locale, str) or not locale.strip():
        raise ValueError("locale must not be empty")
    if locale != DEFAULT_LOCALE:
        raise ValueError(f"only {DEFAULT_LOCALE} locale is supported")

    url = build_quote_url(normalized)
    logger = get_logger(__name__)
    logger.info("Collecting Google Finance quote for %s", normalized)
    with playwright_factory() as playwright:
        browser: Browser = playwright.chromium.launch(headless=True)
        try:
            context = browser.new_context(locale=locale)
            try:
                page = context.new_page()
                response = page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                if response is None:
                    raise RuntimeError("Google Finance page returned no response")
                if response.status != 200:
                    raise RuntimeError(
                        f"Google Finance page returned HTTP status {response.status}"
                    )
                return _read_raw_quote(page, normalized, timeout_ms=timeout_ms)
            finally:
                context.close()
        finally:
            browser.close()
