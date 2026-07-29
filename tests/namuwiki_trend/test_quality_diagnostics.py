"""InsightQualityAnalyzer의 네트워크 비의존 테스트."""

from datetime import datetime, timezone

from namuwiki_trend.models import NewsArticle, TrendInsight, TrendItem
from namuwiki_trend.quality_diagnostics import InsightQualityAnalyzer

FIXED_TIME = datetime(2026, 7, 29, tzinfo=timezone.utc)


def _insight(
    rank: int = 1,
    keyword: str = "Alpha",
    reason: str = "설명",
    articles: tuple[NewsArticle, ...] = (),
) -> TrendInsight:
    """테스트용 TrendInsight를 만든다."""
    return TrendInsight(
        trend=TrendItem(rank=rank, keyword=keyword, href=f"/Go?q={rank}"),
        reason=reason,
        articles=articles,
    )


def _article(title: str, url: str = "https://news.example/1") -> NewsArticle:
    """테스트용 NewsArticle을 만든다."""
    return NewsArticle(title=title, url=url, published_at=FIXED_TIME)


def test_analyze_empty_list() -> None:
    """빈 입력은 모든 개수 지표가 0인 정상 Report를 반환한다."""
    report = InsightQualityAnalyzer().analyze([])

    assert report.insight_count == 0
    assert report.article_counts == ()
    assert report.no_keyword_title_match_ranks == ()
    assert not report.rank_order_anomaly


def test_analyze_fallback_and_empty_articles() -> None:
    """fallback reason과 기사 없는 Insight를 각각 센다."""
    report = InsightQualityAnalyzer().analyze(
        [
            _insight(reason="제공된 기사만으로는 정확한 이유를 확인하기 어렵다."),
            _insight(rank=2),
        ]
    )

    assert report.fallback_reason_count == 1
    assert report.empty_article_insight_count == 2
    assert report.article_counts == (0, 0)


def test_analyze_keyword_title_match_is_case_insensitive_heuristic() -> None:
    """title keyword 포함 여부를 대소문자 무시 heuristic으로 계산한다."""
    articles = (
        _article("alpha 관련 기사", "https://news.example/1"),
        _article("다른 주제", "https://news.example/2"),
    )

    report = InsightQualityAnalyzer().analyze([_insight(articles=articles)])

    assert report.keyword_title_match_count == 1
    assert report.no_keyword_title_match_ranks == ()


def test_analyze_records_insights_without_keyword_title_match() -> None:
    """기사 제목에 keyword가 없는 Insight의 rank를 기록한다."""
    report = InsightQualityAnalyzer().analyze(
        [_insight(articles=(_article("관련 없는 제목"),)), _insight(rank=2)]
    )

    assert report.no_keyword_title_match_ranks == (1, 2)


def test_analyze_counts_distinct_duplicate_article_urls() -> None:
    """실행 전체에서 두 번 이상 등장한 서로 다른 URL 수를 계산한다."""
    duplicate = "https://news.example/duplicate"
    insights = [
        _insight(articles=(_article("Alpha", duplicate), _article("Alpha 후속", duplicate))),
        _insight(rank=2, keyword="Beta", articles=(_article("Beta", duplicate),)),
    ]

    report = InsightQualityAnalyzer().analyze(insights)

    assert report.duplicate_article_url_count == 1


def test_analyze_detects_duplicate_missing_and_out_of_order_ranks() -> None:
    """rank가 1..N 순서가 아니면 이상으로 판정한다."""
    analyzer = InsightQualityAnalyzer()

    assert analyzer.analyze([_insight(rank=1), _insight(rank=1)]).rank_order_anomaly
    assert analyzer.analyze([_insight(rank=1), _insight(rank=3)]).rank_order_anomaly
    assert analyzer.analyze([_insight(rank=2), _insight(rank=1)]).rank_order_anomaly


def test_analyze_counts_empty_keyword_and_reason_without_mutating_input() -> None:
    """빈 문자열 지표를 계산하며 입력 목록과 모델을 변경하지 않는다."""
    insights = [_insight(keyword="  ", reason="  ")]
    original = insights.copy()

    report = InsightQualityAnalyzer().analyze(insights)

    assert report.empty_keyword_count == 1
    assert report.empty_reason_count == 1
    assert insights == original
