"""OpenAI Responses API를 사용하는 TrendReason Generator."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping

from namuwiki_trend.daily_trend_news_service import DailyTrendNews
from namuwiki_trend.models import TrendReason
from namuwiki_trend.trend_reason_generator import (
    INSUFFICIENT_EVIDENCE_REASON,
    MAX_REASON_LENGTH,
    build_trend_reason_prompt,
)

OPENAI_API_KEY_ENV = "OPENAI_API_KEY"
OPENAI_MODEL_ENV = "OPENAI_MODEL"
DEFAULT_OPENAI_MODEL = "gpt-5.6-luna"
ALLOWED_CONFIDENCE = frozenset({"low", "medium", "high"})


class OpenAITrendReasonGenerator:
    """DailyTrendNews 하나를 OpenAI 응답 기반 TrendReason으로 변환한다."""

    def __init__(self, client: object | None = None, *, model: str | None = None) -> None:
        """Initialize with an injectable OpenAI client and configurable model."""
        selected_model = model or os.getenv(OPENAI_MODEL_ENV, DEFAULT_OPENAI_MODEL)
        if not selected_model:
            raise ValueError("OpenAI model이 비어 있음")
        if client is None:
            api_key = os.getenv(OPENAI_API_KEY_ENV)
            if not api_key:
                raise ValueError(f"환경 변수 {OPENAI_API_KEY_ENV}가 설정되지 않음")
            from openai import OpenAI

            client = OpenAI(api_key=api_key)
        self._client = client
        self._model = selected_model

    def generate(self, item: DailyTrendNews) -> TrendReason:
        """Generate and validate one TrendReason using the Responses API."""
        prompt = build_trend_reason_prompt(item)
        if not item.articles:
            return TrendReason(
                keyword=item.trend.keyword.strip(),
                reason=INSUFFICIENT_EVIDENCE_REASON,
                confidence="low",
                supporting_articles=(),
            )

        response = self._client.responses.create(
            model=self._model,
            input=prompt,
            text={"format": self._response_format()},
        )
        text = getattr(response, "output_text", None)
        if not isinstance(text, str) or not text.strip():
            raise ValueError("OpenAI 응답 output_text가 비어 있음")
        return self._parse_response(text, item)

    @staticmethod
    def _response_format() -> dict[str, object]:
        """Return the strict JSON Schema used by the Responses API."""
        return {
            "type": "json_schema",
            "name": "trend_reason",
            "strict": True,
            "schema": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "keyword": {"type": "string"},
                    "reason": {"type": "string"},
                    "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
                    "supporting_articles": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["keyword", "reason", "confidence", "supporting_articles"],
            },
        }

    @staticmethod
    def _parse_response(text: str, item: DailyTrendNews) -> TrendReason:
        """Parse and validate JSON against the domain contract."""
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError("OpenAI 응답이 올바른 JSON이 아님") from exc
        if not isinstance(payload, Mapping):
            raise ValueError("OpenAI 응답이 JSON 객체가 아님")

        keyword = payload.get("keyword")
        reason = payload.get("reason")
        confidence = payload.get("confidence")
        supporting = payload.get("supporting_articles")
        expected_keyword = item.trend.keyword.strip()
        input_urls = {article.url for article in item.articles}
        if keyword != expected_keyword:
            raise ValueError("OpenAI 응답 keyword가 입력 keyword와 다름")
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("OpenAI 응답 reason이 비어 있음")
        reason = reason.strip()
        if len(reason) > MAX_REASON_LENGTH:
            raise ValueError("OpenAI 응답 reason이 300자를 초과함")
        if confidence not in ALLOWED_CONFIDENCE:
            raise ValueError("OpenAI 응답 confidence가 허용값이 아님")
        if not isinstance(supporting, list) or not all(
            isinstance(article_url, str) and article_url in input_urls for article_url in supporting
        ):
            raise ValueError("OpenAI 응답 supporting_articles가 입력 URL subset이 아님")

        return TrendReason(
            keyword=keyword,
            reason=reason,
            confidence=confidence,
            supporting_articles=tuple(supporting),
        )
