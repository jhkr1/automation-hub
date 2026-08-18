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


@dataclass(frozen=True)
class StatusPresentation:
    """Accessible text and a semantic tone for one raw application status."""

    label: str
    tone: str


_STATUS_PRESENTATIONS: dict[str, StatusPresentation] = {
    "SUCCESS": StatusPresentation("정상", "success"),
    "Healthy": StatusPresentation("정상", "success"),
    "Fresh": StatusPresentation("정상", "success"),
    "FAILED": StatusPresentation("실패", "error"),
    "UNAVAILABLE": StatusPresentation("실시간 정보 사용 불가", "warning"),
    "Unavailable": StatusPresentation("사용 불가", "error"),
    "NO_MATCHING_ARRIVAL": StatusPresentation("도착 예정 차량 없음", "neutral"),
    "NOT_REQUESTED": StatusPresentation("조회하지 않음", "neutral"),
    "Stale": StatusPresentation("업데이트 지연", "warning"),
    "No Data": StatusPresentation("데이터 없음", "neutral"),
    "Invalid Artifact": StatusPresentation("데이터 오류", "error"),
    "Planned": StatusPresentation("예정", "neutral"),
    "Loading": StatusPresentation("조회 중", "neutral"),
    "Attention Needed": StatusPresentation("주의 필요", "warning"),
    "Unknown": StatusPresentation("상태 확인 필요", "warning"),
}


def status_presentation(status: str) -> StatusPresentation:
    """Convert an explicit raw status into accessible semantic presentation data."""
    return _STATUS_PRESENTATIONS.get(status, StatusPresentation("상태 확인 필요", "warning"))


def bus_monitor_state(
    route_status: str | None,
    realtime_status: str | None,
) -> DisplayState:
    """Classify the latest persisted Bus Monitor result without clock-based staleness."""
    if route_status is None:
        return DisplayState("No Data", "저장된 Bus Monitor Snapshot이 없습니다.")
    if route_status == "FAILED":
        return DisplayState("FAILED", "경로 정보를 확인할 수 없습니다.")
    if realtime_status == "UNAVAILABLE":
        return DisplayState("UNAVAILABLE", "실시간 버스 정보를 불러올 수 없습니다.")
    if realtime_status == "NO_MATCHING_ARRIVAL":
        return DisplayState("NO_MATCHING_ARRIVAL", "현재 도착 예정 차량이 없습니다.")
    if realtime_status == "NOT_REQUESTED":
        return DisplayState("NOT_REQUESTED", "실시간 정보 조회를 요청하지 않았습니다.")
    if route_status == "SUCCESS" and realtime_status == "SUCCESS":
        return DisplayState("SUCCESS", "최근 수집 결과가 정상입니다.")
    return DisplayState("Unknown", "수집 결과 상태를 확인하세요.")


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
