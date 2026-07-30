"""Daily Trend News 한 건에서 근거 기반 Gemini 설명을 생성한다."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from datetime import datetime
from typing import Protocol

from google import genai

from namuwiki_trend.daily_trend_news_service import DailyTrendNews
from namuwiki_trend.models import TrendReason

DEFAULT_MODEL = "gemini-3.5-flash"
GEMINI_API_KEY_ENV = "GEMINI_API_KEY"
MAX_REASON_LENGTH = 300
INSUFFICIENT_EVIDENCE_REASON = "제공된 기사만으로는 정확한 이유를 확인하기 어렵다."
ALLOWED_CONFIDENCE = frozenset({"low", "medium", "high"})


class LLMModels(Protocol):
    """Gemini models 객체에서 사용하는 최소 호출 계약."""

    def generate_content(self, *, model: str, contents: str) -> object:
        """Return a model response for the prompt."""


class LLMClient(Protocol):
    """Gemini client에서 사용하는 최소 호출 계약."""

    models: LLMModels


def _format_published_at(value: datetime | None) -> str:
    """Format an optional publication time without inventing a value."""
    return value.isoformat() if value is not None else "확인되지 않음"


def build_trend_reason_prompt(item: DailyTrendNews) -> str:
    """Build a grounded JSON-output prompt from one DailyTrendNews."""
    if not isinstance(item, DailyTrendNews):
        raise TypeError(f"item이 DailyTrendNews가 아님: {type(item).__name__}")

    keyword = item.trend.keyword.strip()
    if not keyword:
        raise ValueError("keyword가 비어 있음")

    article_blocks = []
    for index, article in enumerate(item.articles, start=1):
        title = article.title.strip()
        if not title:
            raise ValueError(f"articles[{index}]의 title이 비어 있음")
        article_blocks.append(
            f"[기사 {index}]\n"
            f"- 제목: {title}\n"
            f"- 출처: {article.source or '확인되지 않음'}\n"
            f"- 게시 시각: {_format_published_at(article.published_at)}\n"
            f"- URL: {article.url}"
        )

    articles_text = "\n\n".join(article_blocks) or "제공된 기사가 없음"
    output_format = (
        '필수 형식: {"keyword": "...", "reason": "...", '
        '"confidence": "low|medium|high", "supporting_articles": ["https://..."]}'
    )
    return f"""당신은 실시간 검색어 상승 배경을 뉴스 근거만으로 분석하는 시스템이다.

검색어: {keyword}
집계 정보:
- 등장 횟수: {item.trend.appearance_count}
- 최고 순위: {item.trend.best_rank}
- 평균 순위: {item.trend.average_rank}
- 순위 점수: {item.trend.rank_score}

뉴스 문맥:
{articles_text}

규칙:
- 기사 제목과 메타데이터만 사용한다. 기사 전문이나 URL 내용을 읽었다고 주장하지 않는다.
- 검색어가 기사의 핵심 주제인 경우에만 근거로 사용한다.
- 기사 밖의 사실, 날짜, 인물 관계, 계약, 이적을 추측하거나 만들어내지 않는다.
- 광고성·무관·단순 언급 기사는 근거로 삼지 않는다.
- 근거가 부족하면 reason에 "{INSUFFICIENT_EVIDENCE_REASON}"를 사용한다.
- confidence는 low, medium, high 중 하나만 사용한다.
- supporting_articles에는 근거로 사용한 기사 URL만 넣는다.

JSON 객체만 출력한다. Markdown이나 설명을 추가하지 않는다.
{output_format}"""


class TrendReasonGenerator:
    """DailyTrendNews 하나를 구조화된 Gemini 설명으로 변환한다."""

    def __init__(self, client: LLMClient | None = None, *, model: str = DEFAULT_MODEL) -> None:
        """Initialize the generator with an injectable Gemini client."""
        if not model:
            raise ValueError("Gemini model이 비어 있음")
        if client is None:
            api_key = os.getenv(GEMINI_API_KEY_ENV)
            if not api_key:
                raise ValueError(f"환경 변수 {GEMINI_API_KEY_ENV}가 설정되지 않음")
            client = genai.Client(api_key=api_key)
        self._client = client
        self._model = model

    def generate(self, item: DailyTrendNews) -> TrendReason:
        """Generate and validate one grounded trend reason."""
        prompt = build_trend_reason_prompt(item)
        if not item.articles:
            return TrendReason(
                keyword=item.trend.keyword.strip(),
                reason=INSUFFICIENT_EVIDENCE_REASON,
                confidence="low",
                supporting_articles=(),
            )

        response = self._client.models.generate_content(model=self._model, contents=prompt)
        text = getattr(response, "text", None)
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Gemini 응답 text가 비어 있음")
        return self._parse_response(text, item)

    @staticmethod
    def _parse_response(text: str, item: DailyTrendNews) -> TrendReason:
        """Parse and validate the model's JSON response."""
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError("Gemini 응답이 올바른 JSON이 아님") from exc
        if not isinstance(payload, Mapping):
            raise ValueError("Gemini 응답이 JSON 객체가 아님")

        keyword = payload.get("keyword")
        reason = payload.get("reason")
        confidence = payload.get("confidence")
        supporting = payload.get("supporting_articles")
        expected_keyword = item.trend.keyword.strip()
        if keyword != expected_keyword:
            raise ValueError("Gemini 응답 keyword가 입력 keyword와 다름")
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("Gemini 응답 reason이 비어 있음")
        reason = reason.strip()
        if len(reason) > MAX_REASON_LENGTH:
            raise ValueError("Gemini 응답 reason이 300자를 초과함")
        if confidence not in ALLOWED_CONFIDENCE:
            raise ValueError("Gemini 응답 confidence가 허용값이 아님")
        if not isinstance(supporting, list) or not all(
            isinstance(article_url, str) and article_url.strip() for article_url in supporting
        ):
            raise ValueError("Gemini 응답 supporting_articles가 올바르지 않음")

        return TrendReason(
            keyword=keyword,
            reason=reason,
            confidence=confidence,
            supporting_articles=tuple(supporting),
        )
