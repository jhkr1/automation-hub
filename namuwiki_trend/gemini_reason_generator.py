"""LlmRuntime을 사용한 나무위키 실시간 검색어 등재 이유 생성."""

import json
import logging
from collections.abc import Mapping, Sequence
from math import ceil

from llm_runtime.models import KeyProfile, LlmJob, LlmResponseFormat
from llm_runtime.runtime import LlmRuntime
from namuwiki_trend.models import NewsArticle, TrendItem

MAX_REASON_LENGTH = 300
MAX_PROMPT_LENGTH = 12_000
INSUFFICIENT_EVIDENCE_REASON = "제공된 기사만으로는 정확한 이유를 확인하기 어렵다."

BATCH_MAX_OUTPUT_TOKENS = 4096
LOGGER = logging.getLogger(__name__)
NAMUWIKI_RESPONSE_SCHEMA: dict[str, object] = {
    "type": "OBJECT",
    "properties": {
        "items": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "rank": {"type": "INTEGER"},
                    "keyword": {"type": "STRING"},
                    "reason": {"type": "STRING"},
                },
                "required": ["rank", "keyword", "reason"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["items"],
    "additionalProperties": False,
}


class BatchAnalysisError(ValueError):
    """Batch 분석 응답이 안전하게 해석되지 않을 때 발생하는 오류."""


class BatchResponseError(BatchAnalysisError):
    """Batch 응답의 JSON 또는 필드 계약이 잘못되었을 때 발생하는 오류."""


class BatchMappingError(BatchAnalysisError):
    """Batch 응답을 입력 분석 대상에 매핑할 수 없을 때 발생하는 오류."""


BatchInput = tuple[TrendItem, list[NewsArticle]]
BatchKey = tuple[int, str]


def _validate_batch_inputs(items: Sequence[BatchInput]) -> list[BatchInput]:
    """Batch 입력의 rank와 keyword 식별자가 유일한지 확인한다."""
    if not isinstance(items, Sequence) or isinstance(items, (str, bytes)):
        raise TypeError(f"items가 Sequence가 아님: {type(items).__name__}")
    normalized: list[BatchInput] = []
    ranks: set[int] = set()
    keywords: set[str] = set()
    for index, pair in enumerate(items, start=1):
        if not isinstance(pair, tuple) or len(pair) != 2:
            raise TypeError(f"items[{index}]가 (TrendItem, articles) 쌍이 아님")
        trend, articles = pair
        if not isinstance(trend, TrendItem):
            raise TypeError(f"items[{index}]의 trend가 TrendItem이 아님")
        if not isinstance(articles, list):
            raise TypeError(f"items[{index}]의 articles가 list가 아님")
        if type(trend.rank) is not int or trend.rank <= 0:
            raise BatchMappingError("입력 rank가 유효하지 않음")
        keyword = trend.keyword.strip()
        if not keyword:
            raise BatchMappingError("입력 keyword가 비어 있음")
        if trend.rank in ranks:
            raise BatchMappingError("입력 rank가 중복됨")
        if keyword in keywords:
            raise BatchMappingError("입력 keyword가 중복됨")
        ranks.add(trend.rank)
        keywords.add(keyword)
        normalized.append((trend, articles))
    if not normalized:
        raise BatchMappingError("Batch 분석 대상이 없음")
    return normalized


def build_batch_reason_prompt(items: Sequence[BatchInput]) -> str:
    """뉴스가 있는 검색어들의 Batch 분석 Prompt를 만든다."""
    validated = _validate_batch_inputs(items)
    blocks: list[str] = []
    for trend, articles in validated:
        article_blocks: list[str] = []
        for index, article in enumerate(articles, start=1):
            if not isinstance(article, NewsArticle):
                raise TypeError(f"{trend.keyword} articles[{index}]가 NewsArticle가 아님")
            title = article.title.strip()
            if not title:
                raise ValueError(f"{trend.keyword} articles[{index}]의 title이 비어 있음")
            source = article.source.strip() if article.source else "확인되지 않음"
            published_at = (
                article.published_at.isoformat() if article.published_at else "확인되지 않음"
            )
            article_blocks.append(
                f"- 제목: {title}\n- 출처: {source}\n- 게시 시각: {published_at}"
            )
        blocks.append(
            f"[분석 대상]\n- rank: {trend.rank}\n- keyword: {trend.keyword}\n"
            f"뉴스 문맥:\n{chr(10).join(article_blocks)}"
        )

    prompt = (
        "당신은 실시간 검색어의 발생 배경을 제공된 뉴스 문맥에만 근거해\n"
        "짧고 신중하게 설명하는 분석가다.\n\n"
        f"분석 대상:\n{chr(10).join(blocks)}\n\n"
        "규칙:\n"
        "- 입력된 rank와 keyword를 그대로 유지한다.\n"
        "- 입력에 없는 keyword나 rank를 만들지 않는다.\n"
        "- 각 대상마다 한국어 2~3문장으로 작성한다.\n"
        "- 각 reason은 300자 이하로 작성한다.\n"
        "- 제공된 뉴스 근거 안에서만 설명한다.\n"
        "- 사실 확인이 불가능한 원인을 단정하지 않는다.\n"
        "- 광고성 문구와 투자 조언을 포함하지 않는다.\n\n"
        "출력:\n"
        "- 정확한 JSON 객체 하나만 반환한다.\n"
        "- Markdown code fence를 사용하지 않는다.\n"
        "- 모든 분석 대상에 대해 items 배열의 item을 하나씩 반환한다.\n"
        '- 형식: {"items": [{"rank": 1, "keyword": "...", "reason": "..."}]}'
    )
    if len(prompt) > MAX_PROMPT_LENGTH:
        raise ValueError(
            f"Batch Prompt가 최대 길이를 초과함: {len(prompt)}자, 최대 {MAX_PROMPT_LENGTH}자"
        )
    return prompt


def _strip_json_code_fence(text: str) -> tuple[str, bool]:
    """응답 전체를 감싼 단일 JSON code fence만 제거한다."""
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped, False
    lines = stripped.splitlines()
    if len(lines) < 3 or lines[0] not in {"```", "```json"} or lines[-1] != "```":
        raise BatchResponseError("malformed_code_fence")
    return "\n".join(lines[1:-1]).strip(), True


def _finish_reason_name(finish_reason: object) -> str | None:
    """SDK enum 또는 문자열 finish reason을 안전한 이름으로 변환한다."""
    if finish_reason is None:
        return None
    value = getattr(finish_reason, "value", finish_reason)
    return value if isinstance(value, str) else type(finish_reason).__name__


def _log_response_diagnostics(
    text: str,
    *,
    finish_reason: object,
    output_tokens: int | None,
    has_json_fence: bool,
) -> tuple[str, bool, bool]:
    """응답 본문을 노출하지 않고 JSON 경계 진단 정보를 기록한다."""
    stripped = text.strip()
    first = stripped[0] if stripped else None
    last = stripped[-1] if stripped else None
    starts_json = stripped.startswith("{")
    ends_json = stripped.endswith("}")
    LOGGER.debug(
        "Namuwiki batch response: chars=%s first=%r last=%r has_json_fence=%s "
        "starts_json=%s ends_json=%s finish_reason=%s output_tokens=%s",
        len(text),
        first,
        last,
        has_json_fence,
        starts_json,
        ends_json,
        _finish_reason_name(finish_reason),
        output_tokens,
    )
    return stripped, starts_json, ends_json


def parse_batch_reason_response(
    text: str,
    items: Sequence[BatchInput],
    *,
    finish_reason: object = None,
    output_tokens: int | None = None,
) -> dict[BatchKey, str]:
    """Strict JSON Batch 응답을 입력 rank와 keyword에 매핑한다."""
    validated = _validate_batch_inputs(items)
    if not isinstance(text, str):
        raise BatchResponseError("response_text_not_string")
    stripped = text.strip()
    has_json_fence = stripped.startswith("```")
    if _finish_reason_name(finish_reason) == "MAX_TOKENS":
        _log_response_diagnostics(
            text,
            finish_reason=finish_reason,
            output_tokens=output_tokens,
            has_json_fence=has_json_fence,
        )
        raise BatchResponseError("truncated_json")
    try:
        json_text, has_json_fence = _strip_json_code_fence(text)
        _, starts_json, ends_json = _log_response_diagnostics(
            json_text,
            finish_reason=finish_reason,
            output_tokens=output_tokens,
            has_json_fence=has_json_fence,
        )
        payload = json.loads(json_text)
    except BatchResponseError:
        raise
    except json.JSONDecodeError as exc:
        LOGGER.debug(
            "Namuwiki batch JSON decode failure: line=%s column=%s position=%s",
            exc.lineno,
            exc.colno,
            exc.pos,
        )
        if starts_json and (
            exc.pos >= len(json_text.rstrip()) - 1
            or exc.msg == "Unterminated string starting at"
        ):
            raise BatchResponseError("truncated_json") from exc
        raise BatchResponseError("malformed_json") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
        raise BatchResponseError("items_array_required")

    expected: set[BatchKey] = {(trend.rank, trend.keyword) for trend, _ in validated}
    expected_ranks = {rank for rank, _ in expected}
    expected_keywords = {keyword for _, keyword in expected}
    result: dict[BatchKey, str] = {}
    for item in payload["items"]:
        if not isinstance(item, dict):
            raise BatchResponseError("item_object_required")
        if set(item) != {"rank", "keyword", "reason"}:
            raise BatchResponseError("unexpected_item_field")
        rank = item["rank"]
        keyword = item["keyword"]
        reason = item["reason"]
        if type(rank) is not int or rank <= 0:
            raise BatchResponseError("rank_must_be_positive_int")
        if not isinstance(keyword, str) or not keyword.strip():
            raise BatchResponseError("keyword_must_be_non_empty_string")
        if not isinstance(reason, str) or not reason.strip():
            raise BatchResponseError("reason_must_be_non_empty_string")
        if rank not in expected_ranks:
            raise BatchMappingError("unknown_rank")
        if keyword not in expected_keywords:
            raise BatchMappingError("unknown_keyword")
        key = (rank, keyword)
        if key not in expected:
            raise BatchMappingError("rank_keyword_pair_mismatch")
        if key in result:
            raise BatchMappingError("duplicate_item")
        normalized_reason = reason.strip()
        if len(normalized_reason) > MAX_REASON_LENGTH:
            raise BatchResponseError("reason_too_long")
        result[key] = normalized_reason

    if expected - set(result):
        raise BatchMappingError("missing_item")
    return result
def build_reason_prompt(trend: TrendItem, articles: list[NewsArticle]) -> str:
    """TrendItem과 뉴스 문맥을 grounding한 등재 이유 생성 Prompt를 만든다."""
    if not isinstance(trend, TrendItem):
        raise TypeError(f"trend가 TrendItem이 아님: {type(trend).__name__}")
    if not isinstance(articles, list):
        raise TypeError(f"articles가 list가 아님: {type(articles).__name__}")

    keyword = trend.keyword.strip()
    if not keyword:
        raise ValueError("keyword가 비어 있음")

    article_blocks: list[str] = []
    for index, article in enumerate(articles, start=1):
        if not isinstance(article, NewsArticle):
            raise TypeError(f"articles[{index}]가 NewsArticle가 아님: {type(article).__name__}")

        title = article.title.strip()
        if not title:
            raise ValueError(f"articles[{index}]의 title이 비어 있음")

        source = article.source.strip() if article.source else "확인되지 않음"
        published_at = article.published_at.isoformat() if article.published_at else "확인되지 않음"
        article_blocks.append(
            f"[기사 {index}]\n"
            f"- 제목: {title}\n"
            f"- 출처: {source}\n"
            f"- 게시 시각: {published_at}"
        )

    articles_text = "\n\n".join(article_blocks) or "제공된 기사가 없음"
    prompt = f"""당신은 실시간 검색어의 발생 배경을 최신 뉴스 문맥에 근거해
짧고 신중하게 설명하는 분석가다.

입력:
- 검색어: {keyword}

뉴스 문맥:
{articles_text}

근거 사용 규칙:
- 검색어가 기사의 핵심 주제인 경우에만 그 기사를 근거로 사용한다.
- 단순 언급 기사나 비교 기사만으로 등재 이유를 확정하지 않는다.
- 여러 기사에서 반복되는 공통 사건을 우선한다.
- 제공된 기사끼리 내용이 충돌하면 상충하는 보도가 존재한다고 명시하고
  어느 한쪽을 사실로 단정하지 않는다.
- 뉴스만으로 인기 원인을 확인할 수 없거나 사건의 진위를 판단할 수 없으면 근거 부족으로 답한다.
- 제공된 기사 밖의 사실을 추측하거나 보완하지 않는다.
- 확인되지 않은 날짜, 인물, 계약, 이적 등을 만들어내지 않는다.
- 검색어가 인기 있는 이유만 설명하고 인물이나 사건의 진위를 임의로 판정하지 않는다.
- 공통 사건이 없거나 기사 문맥이 부족하면 "{INSUFFICIENT_EVIDENCE_REASON}"라고 답한다.

출력 규칙:
- 한국어 1~2문장으로 설명한다.
- 설명만 출력하고 제목, 목록, Markdown을 사용하지 않는다.
- 검색어와 직접 관련이 없는 기사를 근거로 삼지 않는다."""

    if len(prompt) > MAX_PROMPT_LENGTH:
        raise ValueError(
            f"Gemini Prompt가 최대 길이를 초과함: {len(prompt)}자, 최대 {MAX_PROMPT_LENGTH}자"
        )
    return prompt


class GeminiReasonGenerator:
    """LlmRuntime으로 TrendItem 하나의 등재 이유를 생성한다."""

    def __init__(self, *, runtime: LlmRuntime, profile: KeyProfile) -> None:
        self._runtime = runtime
        self._profile = KeyProfile(profile)

    @staticmethod
    def estimate_input_tokens(prompt: str) -> int:
        """문자 수 기반의 보수적인 입력 token 추정치를 반환한다."""
        return max(1, ceil(len(prompt) / 3))

    def generate_reason(self, trend: TrendItem, articles: list[NewsArticle]) -> str:
        """TrendItem과 뉴스 문맥에 대한 짧은 설명을 생성한다."""
        prompt = build_reason_prompt(trend, articles)
        response = self._runtime.generate(
            job=LlmJob.NAMUWIKI,
            profile=self._profile,
            prompt=prompt,
            estimated_input_tokens=self.estimate_input_tokens(prompt),
            max_output_tokens=None,
        )

        text = response.text
        if not isinstance(text, str):
            raise RuntimeError("Gemini 응답 text가 문자열이 아님")

        reason = text.strip()
        if not reason:
            raise RuntimeError("Gemini 응답 text가 비어 있음")
        if len(reason) > MAX_REASON_LENGTH:
            raise ValueError(
                f"Gemini 응답이 최대 길이를 초과함: {len(reason)}자, 최대 {MAX_REASON_LENGTH}자"
            )

        return reason

    def generate_reasons(self, items: Sequence[BatchInput]) -> Mapping[BatchKey, str]:
        """뉴스가 있는 여러 검색어의 reason을 Runtime 한 번으로 생성한다."""
        validated = _validate_batch_inputs(items)
        prompt = build_batch_reason_prompt(validated)
        response = self._runtime.generate(
            job=LlmJob.NAMUWIKI,
            profile=self._profile,
            prompt=prompt,
            estimated_input_tokens=self.estimate_input_tokens(prompt),
            max_output_tokens=BATCH_MAX_OUTPUT_TOKENS,
            response_format=LlmResponseFormat(
                response_mime_type="application/json",
                response_schema=NAMUWIKI_RESPONSE_SCHEMA,
            ),
        )
        response_text = getattr(response, "text", None)
        if not isinstance(response_text, str):
            raise BatchResponseError("response_text_missing")
        return parse_batch_reason_response(
            response_text,
            validated,
            finish_reason=getattr(response, "finish_reason", None),
            output_tokens=getattr(response, "output_tokens", None),
        )
