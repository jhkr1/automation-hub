"""Text-first dashboard states for data availability and freshness."""

from dataclasses import dataclass
from datetime import datetime, timedelta

import streamlit as st

from automation_dashboard.queries.google_finance import SEOUL_TZ
from automation_dashboard.ui.formatting import format_duration

GOOGLE_FRESHNESS_THRESHOLD = timedelta(hours=2)
NAMUWIKI_FRESHNESS_THRESHOLD = timedelta(hours=3)


@dataclass(frozen=True)
class DisplayState:
    """A textual status label and concise explanation for a dashboard metric."""

    label: str
    detail: str


def freshness_state(
    last_updated: datetime | None,
    *,
    threshold: timedelta,
    now: datetime | None = None,
) -> DisplayState:
    """Classify persisted data using a documented collection schedule threshold."""
    if last_updated is None:
        return DisplayState("No Data", "저장된 데이터가 없습니다.")
    reference_now = now or datetime.now(SEOUL_TZ)
    localized_updated = last_updated.astimezone(SEOUL_TZ)
    elapsed = reference_now.astimezone(SEOUL_TZ) - localized_updated
    detail = f"{format_duration(elapsed)} 전"
    if elapsed <= threshold:
        return DisplayState("Healthy", detail)
    return DisplayState("Stale", detail)


def availability_state(value: bool | None) -> DisplayState:
    """Map a known availability result to a text status without relying on color."""
    if value is True:
        return DisplayState("Healthy", "조회 가능")
    if value is False:
        return DisplayState("Unavailable", "확인할 수 없습니다.")
    return DisplayState("Unknown", "상태를 확인할 수 없습니다.")


def render_empty_state(message: str) -> None:
    """Render a consistent informational empty state."""
    st.info(message)


def render_database_error() -> None:
    """Render a safe database failure message without connection details."""
    st.error("데이터베이스 연결에 실패했습니다. Operations 로그와 DATABASE_URL 설정을 확인하세요.")
