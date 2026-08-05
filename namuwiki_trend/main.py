"""나무위키 실시간 검색어 enrichment 전체 실행 Entry Point."""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from llm_runtime.models import KeyProfile
from llm_runtime.providers.gemini import GeminiProvider
from llm_runtime.quota import LocalFileQuotaLedger
from llm_runtime.runtime import LlmRuntime
from namuwiki_trend.collector import collect_trends
from namuwiki_trend.enricher import TrendEnricher
from namuwiki_trend.gemini_reason_generator import GeminiReasonGenerator
from namuwiki_trend.insight_storage import JsonTrendInsightStorage
from namuwiki_trend.models import TrendInsight
from namuwiki_trend.news_context_provider import NewsContextProvider
from namuwiki_trend.pipeline import TrendPipeline

DEFAULT_OUTPUT_PATH = Path("output/trend_insights.json")
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_QUOTA_LEDGER_PATH = REPOSITORY_ROOT / ".state" / "llm" / "quota-ledger.json"


class InsightStorage(Protocol):
    """Application Entry Point가 사용하는 저장소 계약."""

    def save(self, insights: Sequence[TrendInsight], path: str | Path) -> Path:
        """Insight 목록을 지정한 경로에 저장한다."""


class InsightPipeline(Protocol):
    """Application Entry Point가 사용하는 Pipeline 계약."""

    def run(self) -> list[TrendInsight]:
        """TrendInsight 목록을 반환한다."""


def build_llm_runtime() -> LlmRuntime:
    """Repository 운영 의존성으로 LlmRuntime을 조립한다."""
    return LlmRuntime(
        provider=GeminiProvider(),
        ledger=LocalFileQuotaLedger(DEFAULT_QUOTA_LEDGER_PATH),
    )


def build_pipeline(profile: KeyProfile) -> TrendPipeline:
    """운영용 Collector와 Enricher를 생성해 Pipeline을 조립한다."""
    news_provider = NewsContextProvider()
    reason_generator = GeminiReasonGenerator(
        runtime=build_llm_runtime(),
        profile=profile,
    )
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


def _parse_args(argv: Sequence[str]) -> KeyProfile:
    parser = argparse.ArgumentParser(description="Namuwiki trend enrichment")
    parser.add_argument(
        "--key-profile",
        choices=(KeyProfile.PRODUCTION.value, KeyProfile.TEST.value),
        required=True,
    )
    args = parser.parse_args(argv)
    return KeyProfile(args.key_profile)


def main(argv: Sequence[str] | None = None) -> int:
    """전체 Application Pipeline을 실행하고 종료 코드를 반환한다."""
    profile = _parse_args(sys.argv[1:] if argv is None else argv)
    try:
        output_path = run_application(
            build_pipeline(profile), JsonTrendInsightStorage()
        )
    except Exception as exc:  # noqa: BLE001 - process boundary converts failure to exit code
        print(f"[namuwiki_trend] 실행 실패: {exc}", file=sys.stderr)
        return 1

    print(f"[namuwiki_trend] 결과 저장 완료: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
