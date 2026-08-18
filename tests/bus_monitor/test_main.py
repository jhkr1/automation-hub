"""Unit tests for the production bus-monitor coordinate CLI."""

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy.exc import OperationalError

from bus_monitor.config import BusMonitorSettings
from bus_monitor.db_models import BusMonitoringTarget, BusRouteSnapshot
from bus_monitor.main import build_pipeline, main
from bus_monitor.models import (
    BusLane,
    BusLeg,
    BusRouteResult,
    RealtimeArrival,
    RealtimeStatus,
    ResolvedStation,
    RouteStation,
    RouteStatus,
    TransitRoute,
)
from bus_monitor.odsay import OdsayConfigurationError


def _route() -> tuple[TransitRoute, BusLeg]:
    bus_leg = BusLeg(
        start_station=RouteStation("삼평교", "206000542", 37.403789, 127.104252),
        end_station=RouteStation("도착정류장", "228000697", 37.271599, 127.108851),
        duration_minutes=29,
        station_count=4,
        lanes=(BusLane("5600", "204000007"), BusLane("9241", "204000073")),
    )
    return (
        TransitRoute(33, 243, 1, (bus_leg,)),
        bus_leg,
    )


def _resolved_station() -> ResolvedStation:
    return ResolvedStation("삼평교", "GGB206000542", "31020", 37.4039167, 127.1041667)


def _full_success_result() -> BusRouteResult:
    route, bus_leg = _route()
    return BusRouteResult(
        route_status=RouteStatus.SUCCESS,
        realtime_status=RealtimeStatus.SUCCESS,
        route=route,
        bus_leg=bus_leg,
        resolved_station=_resolved_station(),
        arrivals=(
            RealtimeArrival("GGB204000007", "5600", 615, 8, "저상버스"),
        ),
    )


class FakePipeline:
    """Return one configured result and record CLI coordinate inputs."""

    def __init__(self, result: BusRouteResult) -> None:
        self._result = result
        self.calls: list[tuple[float, float, float, float]] = []

    def run(
        self,
        origin_longitude: float,
        origin_latitude: float,
        destination_longitude: float,
        destination_latitude: float,
    ) -> BusRouteResult:
        """Record CLI inputs and return a configured pipeline result."""
        self.calls.append(
            (origin_longitude, origin_latitude, destination_longitude, destination_latitude)
        )
        return self._result


class FakeStorage:
    """Expose target lookup and snapshot save behavior without a database connection."""

    def __init__(
        self,
        target: BusMonitoringTarget | None,
        *,
        fail_on_save: bool = False,
    ) -> None:
        self.target = target
        self.fail_on_save = fail_on_save
        self.saved: list[tuple[int, BusRouteResult, datetime]] = []

    def get_target(self, target_id: int) -> BusMonitoringTarget | None:
        """Return the configured target only when its identifier matches."""
        if self.target is not None and self.target.id == target_id:
            return self.target
        return None

    def save_snapshot(
        self,
        target_id: int,
        result: BusRouteResult,
        *,
        collected_at: datetime,
    ) -> BusRouteSnapshot:
        """Record one save call or simulate a persistence-layer operational failure."""
        if self.fail_on_save:
            raise OperationalError("insert", {}, ValueError("forced failure"))
        self.saved.append((target_id, result, collected_at))
        return BusRouteSnapshot(id=91)


def _target(*, enabled: bool = True) -> BusMonitoringTarget:
    """Build a persisted target fixture with independently configurable coordinates."""
    return BusMonitoringTarget(
        id=7,
        name="퇴근길",
        origin_name="지식시스템",
        origin_latitude=Decimal("37.4043389599242"),
        origin_longitude=Decimal("127.102446246531"),
        destination_name="롯데마트 신갈점",
        destination_latitude=Decimal("37.27220279535416"),
        destination_longitude=Decimal("127.10856729001851"),
        enabled=enabled,
    )


def _arguments() -> list[str]:
    return [
        "--origin-longitude",
        "127.102446246531",
        "--origin-latitude",
        "37.4043389599242",
        "--destination-longitude",
        "127.10856729001851",
        "--destination-latitude",
        "37.27220279535416",
    ]


def test_main_prints_full_success_and_returns_zero(monkeypatch, capsys) -> None:
    """A successful route and arrival result is rendered with a zero exit code."""
    pipeline = FakePipeline(_full_success_result())
    monkeypatch.setattr("bus_monitor.main.build_pipeline", lambda: pipeline)

    assert main(_arguments()) == 0
    assert pipeline.calls == [
        (127.102446246531, 37.4043389599242, 127.10856729001851, 37.27220279535416)
    ]
    output = capsys.readouterr().out
    assert "Route Status: SUCCESS" in output
    assert "Realtime Status: SUCCESS" in output
    assert "Boarding Station: 삼평교" in output
    assert "Bus Candidates: 5600, 9241" in output
    assert "Arrival: 615 sec (about 10 min)" in output


def test_main_returns_zero_for_realtime_unavailability(monkeypatch, capsys) -> None:
    """Route success remains a successful process when realtime data is unavailable."""
    route, bus_leg = _route()
    result = BusRouteResult(
        route_status=RouteStatus.SUCCESS,
        realtime_status=RealtimeStatus.UNAVAILABLE,
        route=route,
        bus_leg=bus_leg,
    )
    monkeypatch.setattr("bus_monitor.main.build_pipeline", lambda: FakePipeline(result))

    assert main(_arguments()) == 0
    assert "Realtime information unavailable" in capsys.readouterr().out


def test_main_distinguishes_no_matching_arrival_from_provider_unavailability(
    monkeypatch,
    capsys,
) -> None:
    """A normal TAGO response with no strong lane match remains a zero exit outcome."""
    route, bus_leg = _route()
    result = BusRouteResult(
        route_status=RouteStatus.SUCCESS,
        realtime_status=RealtimeStatus.NO_MATCHING_ARRIVAL,
        route=route,
        bus_leg=bus_leg,
        resolved_station=_resolved_station(),
    )
    monkeypatch.setattr("bus_monitor.main.build_pipeline", lambda: FakePipeline(result))

    assert main(_arguments()) == 0
    assert "No matching realtime arrivals for route candidates" in capsys.readouterr().out


def test_main_returns_one_when_route_planning_fails(monkeypatch, capsys) -> None:
    """A route failure produces a non-zero process result and no realtime claim."""
    result = BusRouteResult(
        route_status=RouteStatus.FAILED,
        realtime_status=RealtimeStatus.NOT_REQUESTED,
    )
    monkeypatch.setattr("bus_monitor.main.build_pipeline", lambda: FakePipeline(result))

    assert main(_arguments()) == 1
    output = capsys.readouterr().out
    assert "Route planning failed." in output
    assert "Realtime Status: NOT_REQUESTED" in output


def test_main_returns_one_before_a_live_call_when_configuration_is_missing(
    monkeypatch,
    capsys,
) -> None:
    """Configuration failure stops before the CLI can invoke a pipeline."""
    monkeypatch.setattr(
        "bus_monitor.main.build_pipeline",
        lambda: (_ for _ in ()).throw(OdsayConfigurationError("key is not configured")),
    )

    assert main(_arguments()) == 1
    captured = capsys.readouterr()
    assert "Configuration error: key is not configured" in captured.err


def test_build_pipeline_wires_odsay_and_gyeonggi_without_a_tago_key(monkeypatch) -> None:
    """The route-enrichment CLI needs ODsay and Gyeonggi credentials only."""
    constructed: dict[str, object] = {}

    class FakeOdsayProvider:
        """Record the API key passed by CLI dependency wiring."""

        def __init__(self, *, api_key: str) -> None:
            constructed["odsay"] = api_key

    class FakeGyeonggiProvider:
        """Record the service key passed by CLI dependency wiring."""

        def __init__(self, *, service_key: str) -> None:
            constructed["gyeonggi"] = service_key

    monkeypatch.setattr("bus_monitor.main.OdsayRouteProvider", FakeOdsayProvider)
    monkeypatch.setattr("bus_monitor.main.GyeonggiProvider", FakeGyeonggiProvider)

    build_pipeline(
        BusMonitorSettings(
            odsay_api_key="odsay-configured",
            gyeonggi_service_key="gyeonggi-configured",
        )
    )

    assert constructed == {
        "odsay": "odsay-configured",
        "gyeonggi": "gyeonggi-configured",
    }


def test_target_mode_runs_target_pipeline_and_persists_full_success(monkeypatch, capsys) -> None:
    """An enabled target supplies coordinates and saves a complete pipeline result."""
    storage = FakeStorage(_target())
    pipeline = FakePipeline(_full_success_result())
    monkeypatch.setattr("bus_monitor.main.build_storage", lambda: storage)
    monkeypatch.setattr("bus_monitor.main.build_pipeline", lambda: pipeline)

    assert main(["--target-id", "7"]) == 0

    assert pipeline.calls == [
        (127.102446246531, 37.4043389599242, 127.10856729001851, 37.27220279535416)
    ]
    assert len(storage.saved) == 1
    assert storage.saved[0][0] == 7
    assert storage.saved[0][2].tzinfo == timezone.utc
    output = capsys.readouterr().out
    assert "Target: 퇴근길 (ID: 7)" in output
    assert "Snapshot ID: 91" in output
    assert "Lane Count: 2" in output
    assert "Realtime Row Count: 1" in output


@pytest.mark.parametrize(
    "result",
    [
        pytest.param(
            lambda: _partial_target_result(RealtimeStatus.UNAVAILABLE),
            id="partial-success",
        ),
        pytest.param(
            lambda: BusRouteResult(RouteStatus.FAILED, RealtimeStatus.NOT_REQUESTED),
            id="route-failure",
        ),
    ],
)
def test_target_mode_persists_partial_and_failed_route_results(
    monkeypatch,
    result,
) -> None:
    """Persisted target mode separates an observed domain failure from process failure."""
    storage = FakeStorage(_target())
    monkeypatch.setattr("bus_monitor.main.build_storage", lambda: storage)
    monkeypatch.setattr("bus_monitor.main.build_pipeline", lambda: FakePipeline(result()))

    assert main(["--target-id", "7"]) == 0
    assert storage.saved[0][1].route_status in {RouteStatus.SUCCESS, RouteStatus.FAILED}


def test_target_mode_rejects_missing_or_disabled_target(monkeypatch, capsys) -> None:
    """A target configuration issue stops before a provider or persistence call."""
    missing_storage = FakeStorage(None)
    monkeypatch.setattr("bus_monitor.main.build_storage", lambda: missing_storage)

    assert main(["--target-id", "7"]) == 1
    assert "Target not found: 7" in capsys.readouterr().err

    disabled_storage = FakeStorage(_target(enabled=False))
    monkeypatch.setattr("bus_monitor.main.build_storage", lambda: disabled_storage)

    assert main(["--target-id", "7"]) == 1
    assert "Target is disabled: 7" in capsys.readouterr().err


def test_target_mode_returns_one_when_snapshot_save_fails(monkeypatch, capsys) -> None:
    """A persistence failure is an operational process failure even with a valid route."""
    storage = FakeStorage(_target(), fail_on_save=True)
    monkeypatch.setattr("bus_monitor.main.build_storage", lambda: storage)
    monkeypatch.setattr(
        "bus_monitor.main.build_pipeline",
        lambda: FakePipeline(_full_success_result()),
    )

    assert main(["--target-id", "7"]) == 1
    assert "Storage error: OperationalError" in capsys.readouterr().err


def _partial_target_result(status: RealtimeStatus) -> BusRouteResult:
    """Create a target-mode partial route result without realtime vehicle rows."""
    route, bus_leg = _route()
    return BusRouteResult(
        route_status=RouteStatus.SUCCESS,
        realtime_status=status,
        route=route,
        bus_leg=bus_leg,
    )
