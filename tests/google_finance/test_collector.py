"""Google Finance collector boundary tests."""

from dataclasses import dataclass

import pytest

from google_finance.collector import (
    RawStockQuote,
    build_quote_url,
    collect_stock_quote,
    validate_symbol,
)


@dataclass
class FakeResponse:
    """Minimal page response fake."""

    status: int = 200


class FakeLocator:
    """Small locator fake covering the collector's public boundary."""

    def __init__(self, *, text: str = "", count: int = 1, children=None) -> None:
        self.text = text
        self._count = count
        self.children = children or {}

    @property
    def first(self) -> "FakeLocator":
        return self

    def count(self) -> int:
        return self._count

    def wait_for(self, **kwargs: object) -> None:
        return None

    def locator(self, selector: str) -> "FakeLocator":
        if selector.startswith("xpath=ancestor"):
            return self.children["ancestor"]
        if selector == "div.KxsRFb:visible":
            return self.children["div.KxsRFb"]
        return self.children[selector]

    def filter(self, *, has_text) -> "FakeLocator":
        return self.children["open"]

    def inner_text(self) -> str:
        return self.text


class FakePage:
    """Fake page that exposes one symbol and one quote container."""

    def __init__(self, container: FakeLocator) -> None:
        self.container = container
        self.goto_calls: list[tuple[str, dict[str, object]]] = []

    def goto(self, url: str, **kwargs: object) -> FakeResponse:
        self.goto_calls.append((url, kwargs))
        return FakeResponse()

    def locator(self, selector: str) -> FakeLocator:
        return FakeLocator(children={"ancestor": self.container})


class FakeContext:
    """Fake browser context."""

    def __init__(self, page: FakePage) -> None:
        self.page = page
        self.closed = False

    def new_page(self) -> FakePage:
        return self.page

    def close(self) -> None:
        self.closed = True


class FakeBrowser:
    """Fake browser that records cleanup."""

    def __init__(self, context: FakeContext) -> None:
        self.context = context
        self.closed = False

    def new_context(self, **kwargs: object) -> FakeContext:
        assert kwargs == {"locale": "en-US"}
        return self.context

    def close(self) -> None:
        self.closed = True


class FakeChromium:
    """Fake Chromium launcher."""

    def __init__(self, browser: FakeBrowser) -> None:
        self.browser = browser

    def launch(self, *, headless: bool) -> FakeBrowser:
        assert headless is True
        return self.browser


class FakePlaywright:
    """Fake sync_playwright context manager."""

    def __init__(self, browser: FakeBrowser) -> None:
        self.chromium = FakeChromium(browser)

    def __enter__(self) -> "FakePlaywright":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None


def _fake_runtime() -> tuple[FakePlaywright, FakePage, FakeBrowser, FakeContext]:
    """Create a fake Playwright object graph for one quote."""
    current = FakeLocator(
        children={
            "div.N6SYTe": FakeLocator(text="$338.19"),
            'span[jsname="vY9t3b"]': FakeLocator(text="-0.56%"),
        }
    )
    container = FakeLocator(
        text="Closed: Jul 29 · USD",
        children={
            "div.ujg0He": current,
            "div.gO24Ff": FakeLocator(text="Apple Inc"),
            "div.jZZ2de": FakeLocator(text="Closed: Jul 29 · USD"),
            "div.W28Ftf": FakeLocator(text="Prev. close $340.08"),
            "div.KxsRFb": FakeLocator(
                children={"open": FakeLocator(text="Open\n$339.73")}
            ),
        },
    )
    page = FakePage(container)
    context = FakeContext(page)
    browser = FakeBrowser(context)
    return FakePlaywright(browser), page, browser, context


@pytest.mark.parametrize("symbol", ["AAPL", "", " AAPL ", "AAPL:", ":NASDAQ", "AAPL/../NASDAQ"])
def test_validate_symbol_rejects_non_exchange_qualified_values(symbol: str) -> None:
    """Only exchange-qualified symbols are accepted."""
    with pytest.raises((TypeError, ValueError)):
        validate_symbol(symbol)


def test_validate_symbol_normalizes_case_and_builds_direct_url() -> None:
    """The URL contains the normalized exchange-qualified symbol."""
    assert validate_symbol(" aapl:nasdaq ") == "AAPL:NASDAQ"
    assert build_quote_url("aapl:nasdaq") == "https://www.google.com/finance/quote/AAPL:NASDAQ"


def test_collect_stock_quote_returns_raw_values_and_cleans_up() -> None:
    """Collector returns raw strings and closes context and browser."""
    fake, page, browser, context = _fake_runtime()

    result = collect_stock_quote("aapl:nasdaq", playwright_factory=lambda: fake)

    assert isinstance(result, RawStockQuote)
    assert result.symbol == "AAPL:NASDAQ"
    assert result.name_text == "Apple Inc"
    assert result.current_price_text == "$338.19"
    assert result.previous_close_text == "Prev. close $340.08"
    assert result.open_price_text == "Open\n$339.73"
    assert result.change_percent_text == "-0.56%"
    assert result.currency_text == "Closed: Jul 29 · USD"
    assert page.goto_calls[0][0] == build_quote_url("AAPL:NASDAQ")
    assert context.closed is True
    assert browser.closed is True


def test_collect_stock_quote_rejects_unverified_locale() -> None:
    """The English-only extraction contract rejects unsupported locales."""
    with pytest.raises(ValueError, match="only en-US locale is supported"):
        collect_stock_quote("AAPL:NASDAQ", locale="ko-KR")
