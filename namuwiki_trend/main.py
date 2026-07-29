"""나무위키 실시간 검색어 enrichment 전체 실행 Entry Point."""

from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from namuwiki_trend.collector import collect_trends
from namuwiki_trend.enricher import TrendEnricher
from namuwiki_trend.gemini_reason_generator import GeminiReasonGenerator
from namuwiki_trend.insight_storage import JsonTrendInsightStorage
from namuwiki_trend.models import TrendInsight
from namuwiki_trend.news_context_provider import NewsContextProvider
from namuwiki_trend.pipeline import TrendPipeline

DEFAULT_OUTPUT_PATH = Path("output/trend_insights.json")


class InsightStorage(Protocol):
    """Application Entry Point가 사용하는 저장소 계약."""

    def save(self, insights: Sequence[TrendInsight], path: str | Path) -> Path:
        """Insight 목록을 지정한 경로에 저장한다."""


class InsightPipeline(Protocol):
    """Application Entry Point가 사용하는 Pipeline 계약."""

    def run(self) -> list[TrendInsight]:
        """TrendInsight 목록을 반환한다."""


def build_pipeline() -> TrendPipeline:
    """운영용 Collector와 Enricher를 생성해 Pipeline을 조립한다."""
    news_provider = NewsContextProvider()
    reason_generator = GeminiReasonGenerator()
    enricher = TrendEnricher(news_provider, reason_generator)
    return TrendPipeline(collect_trends, enricher)


def run_application(
    pipeline: InsightPipeline,
    storage: InsightStorage,
    output_path: str | Path = DEFAULT_OUTPUT_PATH,
) -> Path:
    """Pipeline을 실행하고 결과 Insight를 JSON으로 저장한다."""
    insights = pipeline.run()
    return storage.save(insights, output_path)


def main() -> int:
    """전체 Application Pipeline을 실행하고 종료 코드를 반환한다."""
    try:
        output_path = run_application(build_pipeline(), JsonTrendInsightStorage())
    except Exception as exc:  # noqa: BLE001 - process boundary converts failure to exit code
        print(f"[namuwiki_trend] 실행 실패: {exc}")
        return 1

    print(f"[namuwiki_trend] 결과 저장 완료: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
