"""Placeholder read model for the not-yet-persisted Google Finance insights."""

from dataclasses import dataclass
from pathlib import Path

from automation_dashboard.config import PROJECT_ROOT
from automation_dashboard.readers.namuwiki_insights import InsightStatus

DEFAULT_GOOGLE_FINANCE_INSIGHT_PATH = PROJECT_ROOT / "output" / "google_finance_insights.json"


@dataclass(frozen=True)
class GoogleFinanceInsightReadModel:
    """Future Google Finance insight reader contract without fabricated data."""

    status: InsightStatus
    path: Path
    message: str


def read_google_finance_insights(
    path: Path = DEFAULT_GOOGLE_FINANCE_INSIGHT_PATH,
) -> GoogleFinanceInsightReadModel:
    """Return the planned state; do not read or invent a Google Finance artifact."""
    return GoogleFinanceInsightReadModel(
        status=InsightStatus.PLANNED,
        path=path,
        message="Google Finance 분석 결과 artifact 저장 기능은 아직 구현되지 않았습니다.",
    )
