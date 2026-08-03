"""Gemini generator for evidence-based Google Finance movement analysis."""

from __future__ import annotations

import os

from google import genai

from google_finance.models import (
    MAX_STOCK_INSIGHT_SUMMARY_LENGTH,
    MAX_STOCK_INSIGHT_SUMMARY_SENTENCES,
    StockNewsArticle,
    StockPrice,
    count_stock_insight_sentences,
)
from google_finance.movement import MovementResult

DEFAULT_MODEL = "gemini-3.5-flash"
GEMINI_API_KEY_ENV = "GEMINI_API_KEY"
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
    """Generate one bounded stock movement summary with Gemini."""

    def __init__(
        self,
        client: genai.Client | None = None,
        *,
        api_key: str | None = None,
        model: str = DEFAULT_MODEL,
    ) -> None:
        if not model:
            raise ValueError("Gemini model must not be empty")

        self._client = client
        self._api_key = api_key
        self._model = model

    def _get_client(self) -> genai.Client:
        """Create the SDK client only when a non-empty news request needs it."""
        if self._client is None:
            selected_key = self._api_key or os.getenv(GEMINI_API_KEY_ENV)
            if not selected_key:
                raise ValueError(f"environment variable {GEMINI_API_KEY_ENV} is not set")
            self._client = genai.Client(api_key=selected_key)
        return self._client

    def _generate_content(self, prompt: str) -> object:
        """Call Gemini once and propagate provider errors to the application boundary."""
        return self._get_client().models.generate_content(
            model=self._model,
            contents=prompt,
        )

    def generate_summary(
        self,
        stock_price: StockPrice,
        movement: MovementResult,
        articles: list[StockNewsArticle],
    ) -> str:
        """Generate a validated summary, or a fallback without an API call."""
        if not articles:
            return INSUFFICIENT_EVIDENCE_REASON
        response = self._generate_content(build_analysis_prompt(stock_price, movement, articles))
        text = getattr(response, "text", None)
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
