"""Production ODsay public-transit route provider."""

from __future__ import annotations

from typing import Any, Protocol

import requests

from bus_monitor.config import BusMonitorSettings
from bus_monitor.models import BusLane, BusLeg, RouteStation, TransitRoute

ODSAY_ROUTE_ENDPOINT = "https://api.odsay.com/v1/api/searchPubTransPathT"
DEFAULT_TIMEOUT_SECONDS = 10.0
BUS_TRAFFIC_TYPE = 2


class HttpResponse(Protocol):
    """Minimum response contract used by the ODsay provider."""

    def json(self) -> object:
        """Return the decoded JSON response body."""

    def raise_for_status(self) -> None:
        """Raise an HTTP error for non-successful responses."""


class HttpClient(Protocol):
    """Minimum HTTP client contract used by the ODsay provider."""

    def get(
        self,
        url: str,
        *,
        params: dict[str, str | float | int],
        timeout: float,
    ) -> HttpResponse:
        """Fetch one URL with query parameters and a timeout."""


class OdsayProviderError(RuntimeError):
    """Base error for ODsay production-provider failures."""


class OdsayConfigurationError(OdsayProviderError):
    """Raised when ODsay credentials are not configured."""


class OdsayApiError(OdsayProviderError):
    """Raised when ODsay returns an API-level error payload."""


class OdsayRouteNotFoundError(OdsayProviderError):
    """Raised when ODsay returns no usable route option."""


class OdsayBusLegNotFoundError(OdsayProviderError):
    """Raised when the selected ODsay route contains no bus segment."""


def _required_text(value: object, field_name: str) -> str:
    """Return a required response text field or raise a provider error."""
    if not isinstance(value, str) or not value.strip():
        raise OdsayProviderError(f"ODsay response field {field_name} is missing or invalid")
    return value.strip()


def _required_int(value: object, field_name: str) -> int:
    """Return a required integer response field or raise a provider error."""
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise OdsayProviderError(
            f"ODsay response field {field_name} is missing or invalid"
        ) from exc


def _required_float(value: object, field_name: str) -> float:
    """Return a required float response field or raise a provider error."""
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise OdsayProviderError(
            f"ODsay response field {field_name} is missing or invalid"
        ) from exc


class OdsayRouteProvider:
    """Fetch and normalize ODsay's first valid bus route option."""

    def __init__(
        self,
        http_client: HttpClient | None = None,
        *,
        api_key: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        """Create a provider with an injectable HTTP client and ODsay credential."""
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        configured_key = api_key if api_key is not None else BusMonitorSettings().odsay_api_key
        if configured_key is None or not configured_key.strip():
            raise OdsayConfigurationError("ODSAY_API_KEY is not configured")

        self._http_client = http_client or requests.Session()
        self._api_key = configured_key.strip()
        self._timeout = timeout

    def search_route(
        self,
        origin_longitude: float,
        origin_latitude: float,
        destination_longitude: float,
        destination_latitude: float,
    ) -> TransitRoute:
        """Return ODsay's first route option normalized to one first bus leg."""
        params: dict[str, str | float | int] = {
            "apiKey": self._api_key,
            "SX": origin_longitude,
            "SY": origin_latitude,
            "EX": destination_longitude,
            "EY": destination_latitude,
            "OPT": 0,
            "SearchType": 0,
        }
        try:
            response = self._http_client.get(
                ODSAY_ROUTE_ENDPOINT,
                params=params,
                timeout=self._timeout,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise OdsayProviderError(f"ODsay HTTP request failed: {type(exc).__name__}") from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise OdsayProviderError("ODsay response is not valid JSON") from exc
        if not isinstance(payload, dict):
            raise OdsayProviderError("ODsay response root must be an object")

        error = payload.get("error")
        if isinstance(error, dict):
            code = error.get("code", "unknown")
            raise OdsayApiError(f"ODsay API returned error code {code}")

        return self._normalize_first_route(payload)

    def _normalize_first_route(self, payload: dict[str, Any]) -> TransitRoute:
        """Normalize the first ODsay route option without changing provider order."""
        result = payload.get("result")
        if not isinstance(result, dict):
            raise OdsayProviderError("ODsay response result is missing or invalid")
        paths = result.get("path")
        if not isinstance(paths, list):
            raise OdsayProviderError("ODsay response path is missing or invalid")
        if not paths:
            raise OdsayRouteNotFoundError("ODsay returned no route options")

        first_path = paths[0]
        if not isinstance(first_path, dict):
            raise OdsayProviderError("ODsay first route option is invalid")
        info = first_path.get("info")
        sub_paths = first_path.get("subPath")
        if not isinstance(info, dict) or not isinstance(sub_paths, list):
            raise OdsayProviderError("ODsay first route details are missing or invalid")

        bus_leg = self._first_bus_leg(sub_paths)
        return TransitRoute(
            total_time_minutes=_required_int(info.get("totalTime"), "totalTime"),
            walk_distance_meters=_required_int(info.get("totalWalk"), "totalWalk"),
            transfer_count=(
                _required_int(info.get("busTransitCount"), "busTransitCount")
                + _required_int(info.get("subwayTransitCount"), "subwayTransitCount")
            ),
            bus_legs=(bus_leg,),
        )

    def _first_bus_leg(self, sub_paths: list[object]) -> BusLeg:
        """Return the first documented ODsay bus sub-path as a ``BusLeg``."""
        for sub_path in sub_paths:
            if not isinstance(sub_path, dict):
                raise OdsayProviderError("ODsay subPath item is invalid")
            if _required_int(sub_path.get("trafficType"), "trafficType") != BUS_TRAFFIC_TYPE:
                continue
            return BusLeg(
                start_station=RouteStation(
                    name=_required_text(sub_path.get("startName"), "startName"),
                    local_station_id=_required_text(
                        sub_path.get("startLocalStationID"),
                        "startLocalStationID",
                    ),
                    latitude=_required_float(sub_path.get("startY"), "startY"),
                    longitude=_required_float(sub_path.get("startX"), "startX"),
                ),
                end_station=RouteStation(
                    name=_required_text(sub_path.get("endName"), "endName"),
                    local_station_id=_required_text(
                        sub_path.get("endLocalStationID"),
                        "endLocalStationID",
                    ),
                    latitude=_required_float(sub_path.get("endY"), "endY"),
                    longitude=_required_float(sub_path.get("endX"), "endX"),
                ),
                duration_minutes=_required_int(sub_path.get("sectionTime"), "sectionTime"),
                station_count=_required_int(sub_path.get("stationCount"), "stationCount"),
                lanes=self._normalize_lanes(sub_path.get("lane")),
            )
        raise OdsayBusLegNotFoundError("ODsay route contains no bus segment")

    def _normalize_lanes(self, value: object) -> tuple[BusLane, ...]:
        """Normalize all ODsay lane candidates without changing their order."""
        if not isinstance(value, list):
            raise OdsayProviderError("ODsay bus lane is missing or invalid")
        lanes: list[BusLane] = []
        for lane in value:
            if not isinstance(lane, dict):
                raise OdsayProviderError("ODsay bus lane item is invalid")
            lanes.append(
                BusLane(
                    bus_number=_required_text(lane.get("busNo"), "busNo"),
                    local_route_id=_required_text(lane.get("busLocalBlID"), "busLocalBlID"),
                )
            )
        return tuple(lanes)
