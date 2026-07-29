"""Gemini를 사용한 나무위키 실시간 검색어 등재 이유 생성."""

import os
import re
import time
from collections.abc import Callable

from google import genai
from google.genai import errors

from namuwiki_trend.models import NewsArticle, TrendItem

DEFAULT_MODEL = "gemini-3.5-flash"
GEMINI_API_KEY_ENV = "GEMINI_API_KEY"
MAX_REASON_LENGTH = 300
MAX_PROMPT_LENGTH = 12_000
INSUFFICIENT_EVIDENCE_REASON = "제공된 기사만으로는 정확한 이유를 확인하기 어렵다."
DEFAULT_MIN_REQUEST_INTERVAL_SECONDS = 12.0
DEFAULT_MAX_RETRIES = 2
DEFAULT_RETRY_BACKOFF_SECONDS = 1.0
Clock = Callable[[], float]
Sleeper = Callable[[float], None]


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
- 제공된 기사 밖의 사실을 추측하거나 보완하지 않는다.
- 확인되지 않은 날짜, 인물, 계약, 이적 등을 만들어내지 않는다.
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
    """Gemini API로 TrendItem 하나의 등재 이유를 생성한다."""

    def __init__(
        self,
        client: genai.Client | None = None,
        *,
        model: str = DEFAULT_MODEL,
        min_request_interval_seconds: float = DEFAULT_MIN_REQUEST_INTERVAL_SECONDS,
        max_retries: int = DEFAULT_MAX_RETRIES,
        retry_backoff_seconds: float = DEFAULT_RETRY_BACKOFF_SECONDS,
        clock: Clock = time.monotonic,
        sleeper: Sleeper = time.sleep,
    ) -> None:
        if not model:
            raise ValueError("Gemini model이 비어 있음")
        if min_request_interval_seconds < 0:
            raise ValueError("min_request_interval_seconds는 0 이상이어야 함")
        if type(max_retries) is not int or max_retries < 0:
            raise ValueError("max_retries는 0 이상의 정수여야 함")
        if retry_backoff_seconds <= 0:
            raise ValueError("retry_backoff_seconds는 양수여야 함")

        if client is None:
            api_key = os.getenv(GEMINI_API_KEY_ENV)
            if not api_key:
                raise ValueError(f"환경 변수 {GEMINI_API_KEY_ENV}가 설정되지 않음")
            client = genai.Client(api_key=api_key)

        self._client = client
        self._model = model
        self._min_request_interval_seconds = min_request_interval_seconds
        self._max_retries = max_retries
        self._retry_backoff_seconds = retry_backoff_seconds
        self._clock = clock
        self._sleeper = sleeper
        self._last_request_at: float | None = None

    def _wait_for_request_interval(self) -> None:
        """직전 Gemini 요청 이후 최소 간격이 지나도록 대기한다."""
        now = self._clock()
        if self._last_request_at is not None:
            remaining = self._min_request_interval_seconds - (now - self._last_request_at)
            if remaining > 0:
                self._sleeper(remaining)
        self._last_request_at = self._clock()

    @staticmethod
    def _retry_delay_seconds(error: errors.ClientError) -> float | None:
        """SDK 오류의 RetryInfo retryDelay를 초 단위로 읽는다."""
        details = error.details
        if not isinstance(details, dict):
            return None
        error_body = details.get("error", {})
        if not isinstance(error_body, dict):
            return None
        error_details = error_body.get("details", [])
        if not isinstance(error_details, list):
            return None
        for detail in error_details:
            if not isinstance(detail, dict):
                continue
            if detail.get("@type", "").endswith("RetryInfo"):
                retry_delay = detail.get("retryDelay")
                if isinstance(retry_delay, str):
                    match = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)s", retry_delay)
                    if match:
                        return float(match.group(1))
        return None

    def _generate_content(self, prompt: str) -> object:
        """Rate limit과 제한된 quota retry를 적용해 SDK를 호출한다."""
        for retry_index in range(self._max_retries + 1):
            self._wait_for_request_interval()
            try:
                return self._client.models.generate_content(
                    model=self._model,
                    contents=prompt,
                )
            except errors.ClientError as exc:
                is_quota_error = exc.code == 429 and exc.status == "RESOURCE_EXHAUSTED"
                if not is_quota_error or retry_index == self._max_retries:
                    raise
                delay = self._retry_delay_seconds(exc)
                if delay is None:
                    delay = self._retry_backoff_seconds * (2**retry_index)
                self._sleeper(delay)
        raise AssertionError("unreachable")

    def generate_reason(self, trend: TrendItem, articles: list[NewsArticle]) -> str:
        """TrendItem과 뉴스 문맥에 대한 짧은 설명을 생성한다."""
        prompt = build_reason_prompt(trend, articles)
        response = self._generate_content(prompt)

        if response is None:
            raise RuntimeError("Gemini 응답 객체가 없음")

        text = getattr(response, "text", None)
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
