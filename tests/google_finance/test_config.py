"""Google Finance Watchlist configuration contract tests."""

import pytest

from google_finance.config import Settings


def _settings(value: str) -> Settings:
    """Build settings without reading the repository .env file."""
    return Settings(_env_file=None, stock_symbols=value)


def test_get_symbol_list_parses_and_canonicalizes_symbols() -> None:
    settings = _settings(" nvda:nasdaq , PLTR:NASDAQ ")

    assert settings.get_symbol_list() == ["NVDA:NASDAQ", "PLTR:NASDAQ"]


def test_get_symbol_list_deduplicates_canonical_symbols_and_preserves_order() -> None:
    settings = _settings("PLTR:NASDAQ,nvda:nasdaq, PLTR:NASDAQ , NVDA:NASDAQ")

    assert settings.get_symbol_list() == ["PLTR:NASDAQ", "NVDA:NASDAQ"]


@pytest.mark.parametrize(
    "value",
    [
        "NVDA:NASDAQ,,PLTR:NASDAQ",
        "NVDA:NASDAQ,",
        " , ",
        "",
    ],
)
def test_get_symbol_list_rejects_empty_items_or_empty_watchlist(value: str) -> None:
    settings = _settings(value)

    with pytest.raises(ValueError, match="STOCK_SYMBOLS"):
        settings.get_symbol_list()


def test_get_symbol_list_rejects_invalid_symbol() -> None:
    settings = _settings("NVDA,PLTR:NASDAQ")

    with pytest.raises(ValueError, match="EXCHANGE:TICKER"):
        settings.get_symbol_list()


def test_get_symbol_list_keeps_same_company_symbols_on_different_exchanges() -> None:
    settings = _settings("AAPL:NASDAQ,AAPL:NYSE")

    assert settings.get_symbol_list() == ["AAPL:NASDAQ", "AAPL:NYSE"]


def test_default_settings_requires_watchlist_when_requested() -> None:
    settings = _settings("")

    with pytest.raises(ValueError, match="STOCK_SYMBOLS"):
        settings.get_symbol_list()


def test_confirmed_default_watchlist_example_is_valid() -> None:
    settings = _settings("NVDA:NASDAQ,PLTR:NASDAQ,005930:KRX,000660:KRX")

    assert settings.get_symbol_list() == [
        "NVDA:NASDAQ",
        "PLTR:NASDAQ",
        "005930:KRX",
        "000660:KRX",
    ]
