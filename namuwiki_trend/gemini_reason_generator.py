"""LlmRuntime을 사용한 나무위키 실시간 검색어 등재 이유 생성."""

from math import ceil

from llm_runtime.models import KeyProfile, LlmJob
from llm_runtime.runtime import LlmRuntime
from namuwiki_trend.models import NewsArticle, TrendItem

MAX_REASON_LENGTH = 300
MAX_PROMPT_LENGTH = 12_000
INSUFFICIENT_EVIDENCE_REASON = "제공된 기사만으로는 정확한 이유를 확인하기 어렵다."
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
