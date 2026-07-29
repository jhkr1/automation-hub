"""Gemini를 사용한 나무위키 실시간 검색어 등재 이유 생성."""

import os

from google import genai

from namuwiki_trend.models import TrendItem

DEFAULT_MODEL = "gemini-3.5-flash"
GEMINI_API_KEY_ENV = "GEMINI_API_KEY"
MAX_REASON_LENGTH = 300


def build_reason_prompt(trend: TrendItem) -> str:
    """TrendItem의 keyword만 사용해 등재 이유 생성 Prompt를 만든다."""
    if not isinstance(trend, TrendItem):
        raise TypeError(f"trend가 TrendItem이 아님: {type(trend).__name__}")

    keyword = trend.keyword.strip()
    if not keyword:
        raise ValueError("keyword가 비어 있음")

    return f"""당신은 실시간 검색어의 발생 배경을 짧고 신중하게 설명하는 분석가다.

입력:
- 검색어: {keyword}

출력 규칙:
- 한국어 1~2문장으로 설명한다.
- 설명만 출력하고 제목, 목록, Markdown을 사용하지 않는다.
- 확인되지 않은 사건, 인물, 날짜를 사실처럼 만들지 않는다.
- 제공된 검색어만으로 정확한 이유를 판단할 수 없으면 추측하지 않는다.
- 정보가 부족하면 "현재 제공된 정보만으로는 정확한 등재 이유를 확인하기 어렵습니다."라고 답한다.
- 검색어를 불필요하게 반복하거나 과도한 배경을 설명하지 않는다."""


class GeminiReasonGenerator:
    """Gemini API로 TrendItem 하나의 등재 이유를 생성한다."""

    def __init__(
        self,
        client: genai.Client | None = None,
        *,
        model: str = DEFAULT_MODEL,
    ) -> None:
        if not model:
            raise ValueError("Gemini model이 비어 있음")

        if client is None:
            api_key = os.getenv(GEMINI_API_KEY_ENV)
            if not api_key:
                raise ValueError(f"환경 변수 {GEMINI_API_KEY_ENV}가 설정되지 않음")
            client = genai.Client(api_key=api_key)

        self._client = client
        self._model = model

    def generate_reason(self, trend: TrendItem) -> str:
        """TrendItem의 keyword에 대한 짧은 설명을 생성한다."""
        prompt = build_reason_prompt(trend)
        response = self._client.models.generate_content(
            model=self._model,
            contents=prompt,
        )

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
