"""Google Finance Gemini analysis tests."""

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest
from google.genai.errors import ClientError

from google_finance.analysis_generator import (
    DEFAULT_MODEL,
    INSUFFICIENT_EVIDENCE_REASON,
    MAX_SUMMARY_LENGTH,
    GeminiDailyQuotaExhaustedError,
    GeminiStockInsightGenerator,
    build_analysis_prompt,
)
from google_finance.models import StockNewsArticle, StockPrice
from google_finance.movement import MovementDirection, MovementResult


class FakeModels:
    def __init__(self, response: object) -> None:
        self.response = response
        self.calls: list[dict[str, str]] = []

    def generate_content(self, *, model: str, contents: str) -> object:
        self.calls.append({"model": model, "contents": contents})
        return self.response


class RaisingModels(FakeModels):
    def generate_content(self, *, model: str, contents: str) -> object:
        self.calls.append({"model": model, "contents": contents})
        raise self.response


def _quote() -> StockPrice:
    return StockPrice(
        symbol="AAPL:NASDAQ",
        name="Apple Inc",
        current_price=Decimal("101.25"),
        previous_close=Decimal("100.00"),
        open_price=Decimal("100.50"),
        change_percent=Decimal("1.25"),
        currency="USD",
        collected_at=datetime(2026, 7, 30, 6, tzinfo=timezone.utc),
    )


def _movement() -> MovementResult:
    return MovementResult(
        direction=MovementDirection.UP,
        symbol="AAPL:NASDAQ",
        latest_price=Decimal("101.25"),
        previous_price=Decimal("100.00"),
        price_delta=Decimal("1.25"),
        latest_collected_at=datetime(2026, 7, 30, 6, tzinfo=timezone.utc),
        previous_collected_at=datetime(2026, 7, 30, 5, tzinfo=timezone.utc),
    )


def _article() -> StockNewsArticle:
    return StockNewsArticle(title="Apple news", url="https://news.example/apple", source="Example")


def test_build_analysis_prompt_distinguishes_two_price_change_contracts() -> None:
    prompt = build_analysis_prompt(_quote(), _movement(), [_article()])

    assert "Google Finance change_percent" in prompt
    assert "Snapshot Movement" in prompt
    assert "가격 차이: 1.25" in prompt
    assert "Apple news" in prompt
    assert "상충하는 보도" in prompt
    assert "매수" in prompt and "매도" in prompt
    assert "최대 2문장" in prompt


def test_generator_returns_trimmed_summary_and_uses_fixed_model() -> None:
    client = SimpleNamespace(models=FakeModels(SimpleNamespace(text="  요약입니다.  ")))
    generator = GeminiStockInsightGenerator(client=client)

    assert generator.generate_summary(_quote(), _movement(), [_article()]) == "요약입니다."
    assert client.models.calls[0]["model"] == DEFAULT_MODEL


def test_generator_does_not_call_gemini_for_empty_news() -> None:
    models = FakeModels(SimpleNamespace(text="should not be used"))
    generator = GeminiStockInsightGenerator(client=SimpleNamespace(models=models))

    assert generator.generate_summary(_quote(), _movement(), []) == INSUFFICIENT_EVIDENCE_REASON
    assert models.calls == []


def test_generator_requires_api_key_only_when_news_needs_gemini(monkeypatch) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    generator = GeminiStockInsightGenerator()

    assert generator.generate_summary(_quote(), _movement(), []) == INSUFFICIENT_EVIDENCE_REASON
    with pytest.raises(ValueError, match="GEMINI_API_KEY"):
        generator.generate_summary(_quote(), _movement(), [_article()])


def test_generator_rejects_empty_response() -> None:
    generator = GeminiStockInsightGenerator(
        client=SimpleNamespace(models=FakeModels(SimpleNamespace(text="  "))),
    )

    with pytest.raises(RuntimeError, match="empty or invalid"):
        generator.generate_summary(_quote(), _movement(), [_article()])


def test_generator_accepts_summary_at_contract_limit() -> None:
    generator = GeminiStockInsightGenerator(
        client=SimpleNamespace(
            models=FakeModels(SimpleNamespace(text="가" * MAX_SUMMARY_LENGTH))
        )
    )

    assert len(generator.generate_summary(_quote(), _movement(), [_article()])) == 400


def test_generator_rejects_summary_over_contract_limit() -> None:
    generator = GeminiStockInsightGenerator(
        client=SimpleNamespace(
            models=FakeModels(SimpleNamespace(text="가" * (MAX_SUMMARY_LENGTH + 1)))
        )
    )

    with pytest.raises(ValueError, match="400 characters"):
        generator.generate_summary(_quote(), _movement(), [_article()])


def test_generator_rejects_summary_over_sentence_limit() -> None:
    generator = GeminiStockInsightGenerator(
        client=SimpleNamespace(
            models=FakeModels(SimpleNamespace(text="첫 문장. 둘째 문장. 셋째 문장."))
        )
    )

    with pytest.raises(ValueError, match="2 sentences"):
        generator.generate_summary(_quote(), _movement(), [_article()])


def test_generator_classifies_daily_quota_without_exposing_provider_details() -> None:
    quota_error = ClientError(
        429,
        {
            "error": {
                "status": "RESOURCE_EXHAUSTED",
                "message": "sensitive project details",
                "details": [
                    {
                        "quotaMetric": (
                            "generativelanguage.googleapis.com/"
                            "generate_content_free_tier_requests"
                        ),
                        "quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier",
                    }
                ],
            }
        },
    )
    models = RaisingModels(quota_error)
    generator = GeminiStockInsightGenerator(client=SimpleNamespace(models=models))

    with pytest.raises(GeminiDailyQuotaExhaustedError) as raised:
        generator.generate_summary(_quote(), _movement(), [_article()])

    assert str(raised.value) == "Gemini daily request quota exhausted"
    assert len(models.calls) == 1


def test_generator_keeps_non_daily_client_error_as_provider_failure() -> None:
    error = ClientError(
        429,
        {"error": {"status": "RESOURCE_EXHAUSTED", "message": "temporary limit"}},
    )
    generator = GeminiStockInsightGenerator(
        client=SimpleNamespace(models=RaisingModels(error)),
    )

    with pytest.raises(ClientError) as raised:
        generator.generate_summary(_quote(), _movement(), [_article()])

    assert raised.value is error
