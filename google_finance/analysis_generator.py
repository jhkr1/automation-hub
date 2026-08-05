"""Gemini generator for evidence-based Google Finance movement analysis."""

from __future__ import annotations

from math import ceil

from google_finance.models import (
    MAX_STOCK_INSIGHT_SUMMARY_LENGTH,
    MAX_STOCK_INSIGHT_SUMMARY_SENTENCES,
    StockNewsArticle,
    StockPrice,
    count_stock_insight_sentences,
)
from google_finance.movement import MovementResult
from llm_runtime.models import KeyProfile, LlmJob
from llm_runtime.runtime import LlmRuntime

MAX_SUMMARY_LENGTH = MAX_STOCK_INSIGHT_SUMMARY_LENGTH
INSUFFICIENT_EVIDENCE_REASON = (
    "관련 뉴스 근거가 부족해 최근 가격 변동의 가능한 배경을 확인할 수 없습니다."
)
def build_analysis_prompt(
    stock_price: StockPrice,
    movement: MovementResult,
    articles: list[StockNewsArticle],
) -> str:
    """Build a bounded prompt from quote, movement, and news contracts."""
    if not isinstance(stock_price, StockPrice):
        raise TypeError("stock_price must be a StockPrice")
    if not isinstance(movement, MovementResult):
        raise TypeError("movement must be a MovementResult")
    if not isinstance(articles, list):
        raise TypeError("articles must be a list")
    if not articles:
        raise ValueError("articles must not be empty")

    article_blocks = []
    for index, article in enumerate(articles, start=1):
        if not isinstance(article, StockNewsArticle):
            raise TypeError(f"articles[{index}] must be a StockNewsArticle")
        article_blocks.append(
            f"[기사 {index}]\n"
            f"- 제목: {article.title}\n"
            f"- 출처: {article.source or '확인되지 않음'}\n"
            "- 게시 시각: "
            f"{article.published_at.isoformat() if article.published_at else '확인되지 않음'}"
        )

    prompt = f"""당신은 주가 변동을 공개 뉴스 근거로만 신중하게 요약하는 분석가다.

종목 정보:
- symbol: {stock_price.symbol}
- 회사명: {stock_price.name}
- 통화: {stock_price.currency}
- 현재 가격: {stock_price.current_price}
- 이전 종가: {stock_price.previous_close}
- 시가: {stock_price.open_price}
- Google Finance change_percent: {stock_price.change_percent}%

Snapshot Movement:
- 방향: {movement.direction.value}
- 최신 snapshot 가격: {movement.latest_price}
- 이전 snapshot 가격: {movement.previous_price}
- 가격 차이: {movement.price_delta}
- 최신 수집 시각: {movement.latest_collected_at.isoformat()}
- 이전 수집 시각: {movement.previous_collected_at.isoformat()}

관련 뉴스:
{chr(10).join(article_blocks)}

규칙:
- change_percent는 Google Finance가 제공한 시장 기준 변동률이고,
  Snapshot Movement는 두 수집 시점 사이의 가격 차이임을 구분한다.
- 뉴스와 가격 변화는 동시에 관찰된 사실일 뿐 인과관계가 확인된 것으로 단정하지 않는다.
- 제공된 뉴스 밖의 사실, 재무 정보, 전망을 추측하지 않는다.
- 상충하는 보도가 있으면 어느 한쪽을 사실로 확정하지 않고 상충 사실을 명시한다.
- 매수, 매도, 투자 권고, 목표 주가 또는 수익 전망을 제시하지 않는다.
- 근거가 부족하면 가능한 배경을 확인할 수 없다고 설명한다.
- 한국어 최대 2문장으로만 요약하고 Markdown이나 목록을 사용하지 않는다."""
    if len(prompt) > 12_000:
        raise ValueError("analysis prompt exceeds the maximum length")
    return prompt


class GeminiStockInsightGenerator:
    """Generate one bounded stock movement summary through LlmRuntime."""

    def __init__(self, *, runtime: LlmRuntime, profile: KeyProfile) -> None:
        self._runtime = runtime
        self._profile = KeyProfile(profile)

    @staticmethod
    def estimate_input_tokens(prompt: str) -> int:
        """Return a conservative character-based input token estimate."""
        return max(1, ceil(len(prompt) / 3))

    def generate_summary(
        self,
        stock_price: StockPrice,
        movement: MovementResult,
        articles: list[StockNewsArticle],
    ) -> str:
        """Generate a validated summary, or a fallback without an API call."""
        if not articles:
            return INSUFFICIENT_EVIDENCE_REASON
        prompt = build_analysis_prompt(stock_price, movement, articles)
        response = self._runtime.generate(
            job=LlmJob.GOOGLE_FINANCE,
            profile=self._profile,
            prompt=prompt,
            estimated_input_tokens=self.estimate_input_tokens(prompt),
            max_output_tokens=None,
        )
        text = response.text
        if not isinstance(text, str) or not text.strip():
            raise RuntimeError("Gemini response text is empty or invalid")
        summary = text.strip()
        if len(summary) > MAX_SUMMARY_LENGTH:
            raise ValueError(
                f"Gemini summary exceeds {MAX_SUMMARY_LENGTH} characters"
            )
        if count_stock_insight_sentences(summary) > MAX_STOCK_INSIGHT_SUMMARY_SENTENCES:
            raise ValueError(
                f"Gemini summary exceeds {MAX_STOCK_INSIGHT_SUMMARY_SENTENCES} sentences"
            )
        return summary
