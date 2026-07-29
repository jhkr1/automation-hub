"""TrendInsight 결과의 데이터 품질 지표를 계산하는 진단 계층."""

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

from namuwiki_trend.gemini_reason_generator import INSUFFICIENT_EVIDENCE_REASON
from namuwiki_trend.models import TrendInsight


@dataclass(frozen=True)
class InsightQualityReport:
    """TrendInsight 목록에서 계산한 품질 진단 결과."""

    insight_count: int
    fallback_reason_count: int
    empty_article_insight_count: int
    article_counts: tuple[int, ...]
    keyword_title_match_count: int
    no_keyword_title_match_ranks: tuple[int, ...]
    duplicate_article_url_count: int
    rank_order_anomaly: bool
    empty_keyword_count: int
    empty_reason_count: int


class InsightQualityAnalyzer:
    """외부 호출 없이 TrendInsight 품질 heuristic을 계산한다."""

    def analyze(self, insights: Sequence[TrendInsight]) -> InsightQualityReport:
        """Insight 목록을 분석하고 immutable 품질 Report를 반환한다."""
        if not isinstance(insights, Sequence) or isinstance(insights, (str, bytes)):
            raise TypeError(f"insights가 TrendInsight Sequence가 아님: {type(insights).__name__}")

        for index, insight in enumerate(insights, start=1):
            if not isinstance(insight, TrendInsight):
                raise TypeError(
                    f"insights[{index}]가 TrendInsight가 아님: {type(insight).__name__}"
                )

        article_counts = tuple(len(insight.articles) for insight in insights)
        fallback_reason_count = sum(
            insight.reason.strip() == INSUFFICIENT_EVIDENCE_REASON for insight in insights
        )
        empty_article_insight_count = sum(count == 0 for count in article_counts)
        keyword_title_match_count = 0
        no_keyword_title_match_ranks: list[int] = []
        article_urls: list[str] = []
        empty_keyword_count = 0
        empty_reason_count = 0

        for insight in insights:
            keyword = insight.trend.keyword.strip()
            if not keyword:
                empty_keyword_count += 1
            if not insight.reason.strip():
                empty_reason_count += 1

            normalized_keyword = keyword.casefold()
            insight_has_match = False
            for article in insight.articles:
                article_urls.append(article.url)
                if normalized_keyword and normalized_keyword in article.title.casefold():
                    keyword_title_match_count += 1
                    insight_has_match = True
            if not insight_has_match:
                no_keyword_title_match_ranks.append(insight.trend.rank)

        duplicate_article_url_count = sum(
            count > 1 for count in Counter(article_urls).values()
        )
        ranks = [insight.trend.rank for insight in insights]
        expected_ranks = list(range(1, len(insights) + 1))

        return InsightQualityReport(
            insight_count=len(insights),
            fallback_reason_count=fallback_reason_count,
            empty_article_insight_count=empty_article_insight_count,
            article_counts=article_counts,
            keyword_title_match_count=keyword_title_match_count,
            no_keyword_title_match_ranks=tuple(no_keyword_title_match_ranks),
            duplicate_article_url_count=duplicate_article_url_count,
            rank_order_anomaly=ranks != expected_ranks,
            empty_keyword_count=empty_keyword_count,
            empty_reason_count=empty_reason_count,
        )
