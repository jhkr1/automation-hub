"""Read-only Bus Monitor snapshot dashboard page."""

from datetime import datetime, timedelta

import pandas as pd
import plotly.express as px
import streamlit as st

from automation_dashboard.config import DashboardConfigurationError
from automation_dashboard.queries.bus_monitor import (
    LaneRow,
    MonitoringTargetRow,
    RealtimeRow,
    RouteSnapshotRow,
    TodaySnapshotRow,
    list_enabled_targets,
    list_snapshot_lanes,
    list_snapshot_realtime,
    list_today_snapshots,
    load_latest_route_snapshot,
)
from automation_dashboard.session import DashboardDatabaseError, dashboard_session
from automation_dashboard.ui.components import (
    apply_dashboard_theme,
    render_chart_card,
    render_empty_state,
    render_metadata_card,
    render_metric_card,
    render_page_hero,
    render_section_title,
    render_selection_panel,
    render_status_badge,
    render_table_card,
)
from automation_dashboard.ui.formatting import format_integer, format_kst_datetime, format_kst_time
from automation_dashboard.ui.layout import render_sidebar_context
from automation_dashboard.ui.states import render_database_error


@st.cache_data(ttl=60, show_spinner=False)
def _load_targets() -> list[MonitoringTargetRow]:
    """Cache detached enabled-target choices for a short dashboard interval."""
    with dashboard_session() as session:
        return list_enabled_targets(session)


@st.cache_data(ttl=60, show_spinner=False)
def _load_latest(target_id: int) -> RouteSnapshotRow | None:
    """Cache one target's detached latest route snapshot."""
    with dashboard_session() as session:
        return load_latest_route_snapshot(session, target_id)


@st.cache_data(ttl=60, show_spinner=False)
def _load_lanes(snapshot_id: int) -> list[LaneRow]:
    """Cache ordered lane candidates for one snapshot."""
    with dashboard_session() as session:
        return list_snapshot_lanes(session, snapshot_id)


@st.cache_data(ttl=60, show_spinner=False)
def _load_realtime(snapshot_id: int) -> list[RealtimeRow]:
    """Cache approaching vehicle rows for one snapshot."""
    with dashboard_session() as session:
        return list_snapshot_realtime(session, snapshot_id)


@st.cache_data(ttl=60, show_spinner=False)
def _load_today(target_id: int) -> list[TodaySnapshotRow]:
    """Cache bounded KST-today history for one selected target."""
    with dashboard_session() as session:
        return list_today_snapshots(session, target_id)


def _target_label(target: MonitoringTargetRow) -> str:
    """Format a target selector option without hardcoding an ID."""
    return f"{target.name} · {target.origin_name} → {target.destination_name}"


def _eta_text(seconds: int) -> str:
    """Format canonical arrival seconds as a concise Korean ETA."""
    minutes = seconds // 60
    return f"약 {minutes}분" if minutes else "1분 이내"


def _estimated_arrival_at(collected_at: datetime, arrival_seconds: int) -> datetime:
    """Calculate a KST display-only arrival clock from one normalized ETA."""
    return collected_at + timedelta(seconds=arrival_seconds)


def _realtime_rows(
    rows: list[RealtimeRow],
    *,
    collected_at: datetime,
) -> list[dict[str, object]]:
    """Map realtime rows to the RPA-oriented presentation order without plate numbers."""
    return [
        {
            "Collected At": format_kst_datetime(collected_at),
            "Remaining Time": _eta_text(row.arrival_seconds),
            "Remaining Stops": row.remaining_stops,
            "Remaining Seats": row.remaining_seats if row.remaining_seats is not None else "—",
            "Estimated Arrival": format_kst_time(
                _estimated_arrival_at(collected_at, row.arrival_seconds)
            ),
        }
        for row in rows
    ]


def _history_rows(rows: list[TodaySnapshotRow]) -> list[dict[str, object]]:
    """Map today snapshots to one chronological table with optional fastest vehicle data."""
    return [
        {
            "Collected At": format_kst_datetime(row.snapshot.collected_at),
            "Remaining Time": (
                _eta_text(row.fastest_arrival.arrival_seconds)
                if row.fastest_arrival
                else "—"
            ),
            "Remaining Stops": (
                row.fastest_arrival.remaining_stops if row.fastest_arrival else "—"
            ),
            "Remaining Seats": (
                row.fastest_arrival.remaining_seats
                if row.fastest_arrival and row.fastest_arrival.remaining_seats is not None
                else "—"
            ),
            "Estimated Arrival": (
                format_kst_time(
                    _estimated_arrival_at(
                        row.snapshot.collected_at,
                        row.fastest_arrival.arrival_seconds,
                    )
                )
                if row.fastest_arrival
                else "—"
            ),
        }
        for row in rows
    ]


def _render_charts(rows: list[TodaySnapshotRow]) -> None:
    """Render travel-time and fastest-ETA charts from bounded persisted history."""
    travel_rows = [row for row in rows if row.snapshot.total_time_minutes is not None]
    if travel_rows:
        frame = pd.DataFrame(
            {
                "Collected At": [row.snapshot.collected_at for row in travel_rows],
                "Travel Time": [row.snapshot.total_time_minutes for row in travel_rows],
            }
        )
        render_chart_card(
            "Travel Time Today",
            px.line(frame, x="Collected At", y="Travel Time"),
            x_title="Collected At (KST)",
            y_title="Minutes",
        )
    else:
        render_empty_state("오늘 예상 이동시간이 있는 Snapshot이 없습니다.")

    eta_rows = [row for row in rows if row.fastest_arrival is not None]
    if eta_rows:
        frame = pd.DataFrame(
            {
                "Collected At": [row.snapshot.collected_at for row in eta_rows],
                "Waiting Time": [
                    row.fastest_arrival.arrival_seconds / 60 for row in eta_rows
                ],
            }
        )
        render_chart_card(
            "Bus Waiting Time Today",
            px.line(frame, x="Collected At", y="Waiting Time"),
            x_title="Collected At (KST)",
            y_title="Minutes",
        )
    else:
        render_empty_state("오늘 realtime 차량 정보가 있는 Snapshot이 없습니다.")

    seat_rows = [
        row
        for row in eta_rows
        if row.fastest_arrival is not None and row.fastest_arrival.remaining_seats is not None
    ]
    if seat_rows:
        frame = pd.DataFrame(
            {
                "Collected At": [row.snapshot.collected_at for row in seat_rows],
                "Remaining Seats": [
                    row.fastest_arrival.remaining_seats for row in seat_rows
                ],
            }
        )
        render_chart_card(
            "Remaining Seats Today",
            px.line(frame, x="Collected At", y="Remaining Seats"),
            x_title="Collected At (KST)",
            y_title="Seats",
        )
    else:
        render_empty_state("오늘 잔여좌석 정보가 있는 Snapshot이 없습니다.")


def main() -> None:
    """Render a read-only latest and KST-today Bus Monitor view."""
    apply_dashboard_theme()
    render_sidebar_context()
    try:
        targets = _load_targets()
    except (DashboardConfigurationError, DashboardDatabaseError):
        render_page_hero(
            "Bus Monitor",
            "저장된 통근 경로 Snapshot을 조회합니다.",
            status="Unavailable",
        )
        render_database_error()
        return
    if not targets:
        render_page_hero("Bus Monitor", "저장된 통근 경로 Snapshot을 조회합니다.", status="No Data")
        render_empty_state("활성화된 Bus Monitor target이 없습니다.")
        return

    selected_id = render_selection_panel(
        "Monitoring Target",
        [target.id for target in targets],
        format_func=lambda target_id: _target_label(
            next(item for item in targets if item.id == target_id)
        ),
        key="bus-monitor-target",
    )
    if selected_id is None:
        return
    target = next(item for item in targets if item.id == selected_id)
    try:
        latest = _load_latest(target.id)
        today = _load_today(target.id)
    except (DashboardConfigurationError, DashboardDatabaseError):
        render_database_error()
        return

    render_page_hero(
        "Bus Monitor",
        f"{target.origin_name} → {target.destination_name}의 저장된 통근 Snapshot을 조회합니다.",
        primary_entity=target.name,
        status=latest.route_status if latest else "No Data",
        last_updated=latest.collected_at if latest else None,
    )
    if latest is None:
        render_empty_state("선택한 target의 저장된 Snapshot이 없습니다.")
        return

    render_section_title("Latest Route")
    status_columns = st.columns(2)
    status_columns[0].caption("Route Status")
    render_status_badge(latest.route_status, container=status_columns[0])
    status_columns[1].caption("Realtime Status")
    render_status_badge(latest.realtime_status, container=status_columns[1])
    render_metadata_card(
        "Route Summary",
        {
            "Travel Time": (
                f"{latest.total_time_minutes} min"
                if latest.total_time_minutes is not None
                else "—"
            ),
            "Walking": (
                f"{latest.walk_distance_meters} m"
                if latest.walk_distance_meters is not None
                else "—"
            ),
            "Transfers": format_integer(latest.transfer_count),
            "Boarding": latest.boarding_station_name or "—",
            "Alighting": latest.alighting_station_name or "—",
        },
    )
    try:
        lanes = _load_lanes(latest.id)
        realtime = _load_realtime(latest.id)
    except (DashboardConfigurationError, DashboardDatabaseError):
        render_database_error()
        return
    render_section_title("Latest Commute")
    if realtime:
        fastest = realtime[0]
        estimated_arrival = _estimated_arrival_at(latest.collected_at, fastest.arrival_seconds)
        metric_columns = st.columns(5)
        metrics = (
            (
                "예상 이동시간",
                f"{latest.total_time_minutes}분" if latest.total_time_minutes is not None else "—",
            ),
            ("남은 시간", _eta_text(fastest.arrival_seconds)),
            ("남은 정거장", f"{fastest.remaining_stops}정거장"),
            (
                "남은 좌석",
                f"{fastest.remaining_seats}석" if fastest.remaining_seats is not None else "—",
            ),
            ("예상 도착", format_kst_time(estimated_arrival)),
        )
        for column, (label, value) in zip(metric_columns, metrics, strict=True):
            with column:
                render_metric_card(label, value)
        render_table_card(
            "Approaching Buses",
            pd.DataFrame(_realtime_rows(realtime, collected_at=latest.collected_at)),
        )
    else:
        render_empty_state(f"Realtime 상태: {latest.realtime_status}")

    render_section_title("Latest Bus Candidates")
    if lanes:
        render_table_card(
            "ODsay Lanes",
            pd.DataFrame(
                [{"Bus": lane.bus_number, "Route ID": lane.local_route_id} for lane in lanes]
            ),
        )
    else:
        render_empty_state("저장된 버스 후보가 없습니다.")

    render_section_title("Today History")
    if today:
        render_table_card("Snapshots", pd.DataFrame(_history_rows(today)))
    else:
        render_empty_state("오늘 저장된 Snapshot이 없습니다.")
    render_section_title("Today Charts")
    _render_charts(today)


if __name__ == "__main__":
    main()
