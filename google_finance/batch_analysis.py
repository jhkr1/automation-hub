"""Batch analysis contracts for Google Finance Watchlist insights."""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from math import ceil

from google_finance.collector import validate_symbol
from google_finance.models import (
    MAX_STOCK_INSIGHT_SUMMARY_SENTENCES,
    StockNewsArticle,
    count_stock_insight_sentences,
)
from google_finance.movement import MovementDirection
from llm_runtime.models import KeyProfile, LlmJob, LlmResponseFormat
from llm_runtime.runtime import LlmRuntime

MAX_BATCH_SUMMARY_LENGTH = 300
BATCH_MAX_OUTPUT_TOKENS = 4096
LOGGER = logging.getLogger(__name__)

GOOGLE_FINANCE_RESPONSE_SCHEMA: dict[str, object] = {
    "type": "OBJECT",
    "properties": {
        "items": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "symbol": {"type": "STRING"},
                    "summary": {"type": "STRING"},
                },
                "required": ["symbol", "summary"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["items"],
    "additionalProperties": False,
}


class StockBatchAnalysisError(ValueError):
    """Base error for a Google Finance Batch contract failure."""


class StockBatchResponseError(StockBatchAnalysisError):
    """Raised when a Batch response is not valid JSON or field data."""


class StockBatchMappingError(StockBatchAnalysisError):
    """Raised when response symbols do not map exactly to the Batch input."""


@dataclass(frozen=True)
class StockAnalysisBatchItem:
    """All non-LLM context needed to analyze one canonical symbol."""

    symbol: str
    company_name: str
    price: Decimal
    currency: str
    snapshot_delta: Decimal
    snapshot_change_percent: Decimal | None
    snapshot_movement: MovementDirection
    google_finance_change_percent: Decimal
    articles: tuple[StockNewsArticle, ...]

    def __post_init__(self) -> None:
        """Validate the context before it enters the Batch prompt."""
        if validate_symbol(self.symbol) != self.symbol:
            raise ValueError("symbol must be canonical")
        if not isinstance(self.company_name, str) or not self.company_name.strip():
            raise ValueError("company_name must not be empty")
        if not isinstance(self.currency, str) or not self.currency.strip():
            raise ValueError("currency must not be empty")
        numeric_values = (
            self.price,
            self.snapshot_delta,
            self.google_finance_change_percent,
        )
        if not all(isinstance(value, Decimal) and value.is_finite() for value in numeric_values):
            raise TypeError("Batch numeric fields must be finite Decimal values")
        if self.snapshot_change_percent is not None and (
            not isinstance(self.snapshot_change_percent, Decimal)
            or not self.snapshot_change_percent.is_finite()
        ):
            raise TypeError("snapshot_change_percent must be a finite Decimal")
        if not isinstance(self.snapshot_movement, MovementDirection):
            raise TypeError("snapshot_movement must be a MovementDirection")
        if not isinstance(self.articles, tuple) or not self.articles:
            raise ValueError("articles must be a non-empty tuple")
        if not all(isinstance(article, StockNewsArticle) for article in self.articles):
            raise TypeError("articles must contain StockNewsArticle values")


def _validate_batch_items(
    items: Sequence[StockAnalysisBatchItem],
) -> tuple[StockAnalysisBatchItem, ...]:
    """Return validated items while rejecting duplicate canonical symbols."""
    if not isinstance(items, Sequence) or isinstance(items, (str, bytes)):
        raise TypeError("items must be a sequence")
    materialized = tuple(items)
    if not materialized:
        raise StockBatchMappingError("Batch items must not be empty")
    if not all(isinstance(item, StockAnalysisBatchItem) for item in materialized):
        raise TypeError("items must contain StockAnalysisBatchItem values")
    symbols = [item.symbol for item in materialized]
    if len(symbols) != len(set(symbols)):
        raise StockBatchMappingError("input symbol is duplicated")
    return materialized


def build_batch_analysis_prompt(items: Sequence[StockAnalysisBatchItem]) -> str:
    """Build one prompt with clearly separated symbol contexts."""
    validated = _validate_batch_items(items)
    blocks: list[str] = []
    for item in validated:
        article_blocks = []
        for index, article in enumerate(item.articles, start=1):
            article_blocks.append(
                f"- 제목 {index}: {article.title}\n"
                f"- 출처: {article.source or '확인되지 않음'}\n"
                "- 게시 시각: "
                f"{article.published_at.isoformat() if article.published_at else '확인되지 않음'}"
            )
        snapshot_change = (
            f"{item.snapshot_change_percent}%"
            if item.snapshot_change_percent is not None
            else "계산 불가"
        )
        blocks.append(
            f"[symbol 분석 대상: {item.symbol}]\n"
            f"- 회사명: {item.company_name}\n"
            f"- 현재 가격: {item.price} {item.currency}\n"
            f"- Snapshot 가격 차이: {item.snapshot_delta}\n"
            f"- Snapshot change_percent: {snapshot_change}\n"
            f"- Snapshot movement: {item.snapshot_movement.value}\n"
            f"- Google Finance change_percent: {item.google_finance_change_percent}%\n"
            f"뉴스 문맥:\n{chr(10).join(article_blocks)}"
        )

    prompt = (
        "당신은 Google Finance Watchlist의 가격 움직임을 공개 뉴스 근거로만 "
        "신중하게 요약하는 분석가다.\n\n"
        f"{chr(10).join(blocks)}\n\n"
        "규칙:\n"
        "- 각 symbol은 입력된 canonical symbol을 그대로 유지한다.\n"
        "- Snapshot change는 최근 두 수집 시점 사이의 변화이고, "
        "Google Finance change는 페이지가 제공한 별도 기준임을 구분한다.\n"
        "- 두 변동률을 같은 의미로 설명하지 않는다.\n"
        "- Snapshot movement가 UNCHANGED이면 '최근 두 차례 자동 수집 시점 사이에는 "
        "추가 가격 변동이 없었습니다'처럼 수집 구간을 명시한다.\n"
        "- Snapshot movement가 UP 또는 DOWN이면 최근 두 차례 자동 수집 사이의 "
        "가격 변화와 방향을 설명한다.\n"
        "- Google Finance change를 오늘 또는 전일 대비라고 단정하지 않는다.\n"
        "- 뉴스와 가격 움직임이 직접 연결되지 않으면 근거 부족을 명시한다.\n"
        "- 제공된 뉴스 밖의 사실이나 인과관계를 추측하지 않는다.\n"
        "- 매수, 매도, 투자 조언, 목표 가격을 제시하지 않는다.\n"
        "- summary는 한국어 최대 2문장, 300자 이하로 작성한다.\n"
        "- 정확한 JSON 객체 하나만 반환하고 Markdown code fence를 사용하지 않는다.\n"
        '- 형식: {"items": [{"symbol": "NVDA:NASDAQ", "summary": "..."}]}\n'
    )
    if len(prompt) > 12_000:
        raise ValueError("Batch analysis prompt exceeds the maximum length")
    return prompt


def _strip_json_code_fence(text: str) -> str:
    """Strip only one complete JSON code fence, matching Namuwiki policy."""
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    if len(lines) < 3 or lines[0] not in {"```", "```json"} or lines[-1] != "```":
        raise StockBatchResponseError("malformed_code_fence")
    return "\n".join(lines[1:-1]).strip()


def _finish_reason_name(finish_reason: object) -> str | None:
    """Return a safe finish reason name for truncation classification."""
    if finish_reason is None:
        return None
    value = getattr(finish_reason, "value", finish_reason)
    return value if isinstance(value, str) else type(finish_reason).__name__


def _looks_truncated_json(text: str, error_message: str) -> bool:
    """Identify incomplete JSON delimiters without attempting to repair them."""
    stripped = text.rstrip()
    return stripped.lstrip().startswith("{") and (
        not stripped.endswith("}")
        or stripped.count("{") != stripped.count("}")
        or stripped.count("[") != stripped.count("]")
        or error_message == "Unterminated string starting at"
    )


def parse_batch_analysis_response(
    text: str,
    symbols: Sequence[str],
    *,
    finish_reason: object = None,
    output_tokens: int | None = None,
) -> dict[str, str]:
    """Strictly parse and map one complete Batch response by canonical symbol."""
    if not isinstance(text, str):
        raise StockBatchResponseError("response_text_not_string")
    expected = tuple(symbols)
    if not expected or len(expected) != len(set(expected)):
        raise StockBatchMappingError("input symbols must be unique and non-empty")
    if any(validate_symbol(symbol) != symbol for symbol in expected):
        raise StockBatchMappingError("input symbols must be canonical")

    stripped = text.strip()
    has_json_fence = stripped.startswith("```")
    if _finish_reason_name(finish_reason) == "MAX_TOKENS":
        LOGGER.debug(
            "Google Finance Batch response truncated: chars=%s has_json_fence=%s "
            "finish_reason=%s output_tokens=%s",
            len(text),
            has_json_fence,
            _finish_reason_name(finish_reason),
            output_tokens,
        )
        raise StockBatchResponseError("truncated_json")

    try:
        json_text = _strip_json_code_fence(text)
        payload = json.loads(json_text)
    except StockBatchResponseError:
        raise
    except json.JSONDecodeError as exc:
        LOGGER.debug(
            "Google Finance Batch JSON decode failure: chars=%s line=%s column=%s position=%s",
            len(text),
            exc.lineno,
            exc.colno,
            exc.pos,
        )
        if _looks_truncated_json(json_text, exc.msg):
            raise StockBatchResponseError("truncated_json") from exc
        raise StockBatchResponseError("malformed_json") from exc

    if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
        raise StockBatchResponseError("items_array_required")

    result: dict[str, str] = {}
    expected_set = set(expected)
    for item in payload["items"]:
        if not isinstance(item, dict) or set(item) != {"symbol", "summary"}:
            raise StockBatchResponseError("unexpected_item_field")
        symbol = item["symbol"]
        summary = item["summary"]
        if not isinstance(symbol, str) or not symbol.strip():
            raise StockBatchResponseError("symbol_must_be_non_empty_string")
        if not isinstance(summary, str) or not summary.strip():
            raise StockBatchResponseError("summary_must_be_non_empty_string")
        if symbol not in expected_set:
            raise StockBatchMappingError("unknown_symbol")
        if symbol in result:
            raise StockBatchMappingError("duplicate_symbol")
        normalized_summary = summary.strip()
        if len(normalized_summary) > MAX_BATCH_SUMMARY_LENGTH:
            raise StockBatchResponseError("summary_too_long")
        if count_stock_insight_sentences(normalized_summary) > MAX_STOCK_INSIGHT_SUMMARY_SENTENCES:
            raise StockBatchResponseError("summary_too_many_sentences")
        result[symbol] = normalized_summary

    missing = expected_set - set(result)
    if missing:
        raise StockBatchMappingError("missing_symbol")
    return result


class GeminiStockInsightBatchGenerator:
    """Generate all eligible Google Finance summaries in one Runtime request."""

    def __init__(self, *, runtime: LlmRuntime, profile: KeyProfile) -> None:
        self._runtime = runtime
        self._profile = KeyProfile(profile)

    @staticmethod
    def estimate_input_tokens(prompt: str) -> int:
        """Return a conservative character-based token estimate."""
        return max(1, ceil(len(prompt) / 3))

    def generate_summaries(
        self,
        items: Sequence[StockAnalysisBatchItem],
    ) -> dict[str, str]:
        """Generate and strictly map all summaries with one Runtime call."""
        validated = _validate_batch_items(items)
        prompt = build_batch_analysis_prompt(validated)
        response = self._runtime.generate(
            job=LlmJob.GOOGLE_FINANCE,
            profile=self._profile,
            prompt=prompt,
            estimated_input_tokens=self.estimate_input_tokens(prompt),
            max_output_tokens=BATCH_MAX_OUTPUT_TOKENS,
            response_format=LlmResponseFormat(
                response_mime_type="application/json",
                response_schema=GOOGLE_FINANCE_RESPONSE_SCHEMA,
            ),
        )
        if not isinstance(response.text, str) or not response.text.strip():
            raise StockBatchResponseError("response_text_empty")
        return parse_batch_analysis_response(
            response.text,
            [item.symbol for item in validated],
            finish_reason=response.finish_reason,
            output_tokens=response.output_tokens,
        )
