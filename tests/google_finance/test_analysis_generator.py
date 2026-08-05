"""Google Finance Runtime-based analysis generator tests."""

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest

from google_finance.analysis_generator import (
    INSUFFICIENT_EVIDENCE_REASON,
    MAX_SUMMARY_LENGTH,
    GeminiStockInsightGenerator,
    build_analysis_prompt,
)
from google_finance.models import StockNewsArticle, StockPrice
from google_finance.movement import MovementDirection, MovementResult
from llm_runtime.exceptions import LlmDailyQuotaExceededError, LlmRateLimitError
from llm_runtime.models import KeyProfile, LlmJob


class FakeRuntime:
    """Runtime 호출 인자를 기록하는 Fake."""

    def __init__(self, response=None, error=None) -> None:
        self.response = response or SimpleNamespace(text="  요약입니다.  ")
        self.error = error
        self.calls: list[dict[str, object]] = []

    def generate(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.response


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


def test_generator_returns_trimmed_summary_and_uses_runtime_contract() -> None:
    runtime = FakeRuntime()
    generator = GeminiStockInsightGenerator(runtime=runtime, profile=KeyProfile.TEST)

    assert generator.generate_summary(_quote(), _movement(), [_article()]) == "요약입니다."
    call = runtime.calls[0]
    assert call["job"] is LlmJob.GOOGLE_FINANCE
    assert call["profile"] is KeyProfile.TEST
    assert "AAPL:NASDAQ" in call["prompt"]
    assert call["estimated_input_tokens"] == max(1, (len(call["prompt"]) + 2) // 3)
    assert call["max_output_tokens"] is None


def test_generator_does_not_call_runtime_for_empty_news() -> None:
    runtime = FakeRuntime()
    generator = GeminiStockInsightGenerator(runtime=runtime, profile=KeyProfile.TEST)

    assert generator.generate_summary(_quote(), _movement(), []) == INSUFFICIENT_EVIDENCE_REASON
    assert runtime.calls == []


def test_generator_propagates_runtime_error_without_package_retry() -> None:
    error = LlmRateLimitError("rate limited")
    runtime = FakeRuntime(error=error)
    generator = GeminiStockInsightGenerator(runtime=runtime, profile=KeyProfile.TEST)

    with pytest.raises(LlmRateLimitError) as raised:
        generator.generate_summary(_quote(), _movement(), [_article()])
    assert raised.value is error
    assert len(runtime.calls) == 1


def test_generator_preserves_daily_quota_error_contract() -> None:
    runtime = FakeRuntime(error=LlmDailyQuotaExceededError("daily quota"))
    generator = GeminiStockInsightGenerator(runtime=runtime, profile=KeyProfile.PRODUCTION)

    with pytest.raises(LlmDailyQuotaExceededError):
        generator.generate_summary(_quote(), _movement(), [_article()])


def test_generator_accepts_summary_at_contract_limit() -> None:
    runtime = FakeRuntime(response=SimpleNamespace(text="가" * MAX_SUMMARY_LENGTH))
    generator = GeminiStockInsightGenerator(runtime=runtime, profile=KeyProfile.TEST)

    assert len(generator.generate_summary(_quote(), _movement(), [_article()])) == 400


def test_generator_rejects_summary_over_contract_limit() -> None:
    runtime = FakeRuntime(response=SimpleNamespace(text="가" * (MAX_SUMMARY_LENGTH + 1)))
    generator = GeminiStockInsightGenerator(runtime=runtime, profile=KeyProfile.TEST)

    with pytest.raises(ValueError, match="400 characters"):
        generator.generate_summary(_quote(), _movement(), [_article()])


def test_generator_rejects_summary_over_sentence_limit() -> None:
    runtime = FakeRuntime(response=SimpleNamespace(text="첫 문장. 둘째 문장. 셋째 문장."))
    generator = GeminiStockInsightGenerator(runtime=runtime, profile=KeyProfile.TEST)

    with pytest.raises(ValueError, match="2 sentences"):
        generator.generate_summary(_quote(), _movement(), [_article()])


@pytest.mark.parametrize("response", [SimpleNamespace(text=None), SimpleNamespace(text="  ")])
def test_generator_rejects_invalid_runtime_response(response) -> None:
    generator = GeminiStockInsightGenerator(
        runtime=FakeRuntime(response=response), profile=KeyProfile.TEST
    )
    with pytest.raises(RuntimeError, match="empty or invalid"):
        generator.generate_summary(_quote(), _movement(), [_article()])
