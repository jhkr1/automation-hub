"""Minimal CLI PoC for ODsay public-transit route planning.

This module verifies one fixed Origin-to-Destination route-planning request only.
It does not call TAGO, persist data, or choose a route beyond ODsay's returned order.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ODSAY_ROUTE_ENDPOINT = "https://api.odsay.com/v1/api/searchPubTransPathT"
REQUEST_TIMEOUT_SECONDS = 10.0
ORIGIN_NAME = "지식시스템"
DESTINATION_NAME = "롯데마트 신갈점"
ORIGIN_LONGITUDE = 127.102446246531
ORIGIN_LATITUDE = 37.4043389599242
DESTINATION_LONGITUDE = 127.10856729001851
DESTINATION_LATITUDE = 37.27220279535416


class OdsayPocSettings(BaseSettings):
    """Load the ODsay API key from environment variables or ``.env``."""

    odsay_api_key: str | None = None

    model_config = SettingsConfigDict(env_file=PROJECT_ROOT / ".env", extra="ignore")


class OdsayPocError(RuntimeError):
    """Base error for concise ODsay PoC failures."""


class OdsayConfigurationError(OdsayPocError):
    """Raised before a request when the ODsay API key is not configured."""


class OdsayHttpError(OdsayPocError):
    """Raised when the ODsay HTTP request cannot succeed."""


class OdsayApiError(OdsayPocError):
    """Raised when ODsay returns an API-level error payload."""


class OdsayResponseError(OdsayPocError):
    """Raised when a success response lacks the documented route structure."""


@dataclass(frozen=True)
class BusLane:
    """One bus candidate on an ODsay bus sub-path."""

    bus_number: str
    bus_id: int | None
    bus_local_bl_id: str | None
    bus_city_code: int | None
    bus_provider_code: int | None


@dataclass(frozen=True)
class TransitLeg:
    """One walk, bus, or subway segment from ODsay's ``subPath`` response."""

    traffic_type: int
    section_time: int
    distance: float
    station_count: int | None
    start_name: str | None
    end_name: str | None
    start_local_station_id: str | None
    end_local_station_id: str | None
    start_station_city_code: int | None
    end_station_city_code: int | None
    start_station_provider_code: int | None
    end_station_provider_code: int | None
    buses: tuple[BusLane, ...]


@dataclass(frozen=True)
class TransitRoute:
    """One ODsay route option in the provider's original result order."""

    path_type: int
    total_time: int
    total_walk_distance: int
    total_distance: float
    bus_transit_count: int
    subway_transit_count: int
    legs: tuple[TransitLeg, ...]


def _required_setting(value: str | None) -> str:
    """Return a non-empty key without exposing it in an exception."""
    if value is None or not value.strip():
        raise OdsayConfigurationError("ODSAY_API_KEY is not configured.")
    return value.strip()


def get_route_request_parameters(settings: OdsayPocSettings) -> dict[str, str | float | int]:
    """Build the documented ODsay v1.8 city-route query parameters."""
    return {
        "apiKey": _required_setting(settings.odsay_api_key),
        "SX": ORIGIN_LONGITUDE,
        "SY": ORIGIN_LATITUDE,
        "EX": DESTINATION_LONGITUDE,
        "EY": DESTINATION_LATITUDE,
        "OPT": 0,
        "SearchType": 0,
        "SearchPathType": 0,
        "output": "json",
    }


def fetch_route_payload(settings: OdsayPocSettings) -> dict[str, Any]:
    """Call ODsay once and return its validated JSON payload."""
    try:
        response = requests.get(
            ODSAY_ROUTE_ENDPOINT,
            params=get_route_request_parameters(settings),
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except requests.HTTPError as exc:
        status_code = exc.response.status_code if exc.response is not None else "unknown"
        raise OdsayHttpError(f"ODSAY_HTTP_ERROR: status={status_code}") from exc
    except requests.RequestException as exc:
        raise OdsayHttpError(f"ODSAY_HTTP_ERROR: {type(exc).__name__}") from exc

    try:
        payload: Any = response.json()
    except ValueError as exc:
        raise OdsayResponseError("ODSAY_RESPONSE_ERROR: response is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise OdsayResponseError("ODSAY_RESPONSE_ERROR: JSON root must be an object")
    error = payload.get("error")
    if isinstance(error, dict):
        code = error.get("code", "missing")
        message = error.get("msg", "unknown error")
        raise OdsayApiError(f"ODSAY_API_ERROR: code={code} ({message})")
    return payload


def _required_int(value: object, field_name: str) -> int:
    """Read one required integer field from an ODsay response object."""
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise OdsayResponseError(f"ODSAY_RESPONSE_ERROR: {field_name} is invalid") from exc


def _optional_int(value: object) -> int | None:
    """Read an optional integer field from an ODsay response object."""
    return None if value is None else _required_int(value, "optional integer")


def _optional_text(value: object) -> str | None:
    """Read an optional non-empty text field from an ODsay response object."""
    return None if value is None or not str(value).strip() else str(value).strip()


def _parse_bus_lanes(value: object) -> tuple[BusLane, ...]:
    """Normalize the documented ``lane`` list for one bus segment."""
    if not isinstance(value, list):
        raise OdsayResponseError("ODSAY_RESPONSE_ERROR: bus lane is missing")
    lanes: list[BusLane] = []
    for row in value:
        if not isinstance(row, dict):
            raise OdsayResponseError("ODSAY_RESPONSE_ERROR: bus lane item is invalid")
        bus_number = _optional_text(row.get("busNo"))
        if bus_number is None:
            raise OdsayResponseError("ODSAY_RESPONSE_ERROR: busNo is missing")
        lanes.append(
            BusLane(
                bus_number=bus_number,
                bus_id=_optional_int(row.get("busID")),
                bus_local_bl_id=_optional_text(row.get("busLocalBlID")),
                bus_city_code=_optional_int(row.get("busCityCode")),
                bus_provider_code=_optional_int(row.get("busProviderCode")),
            )
        )
    return tuple(lanes)


def _parse_leg(row: dict[str, Any]) -> TransitLeg:
    """Normalize one documented ODsay ``subPath`` row."""
    traffic_type = _required_int(row.get("trafficType"), "trafficType")
    try:
        distance = float(row.get("distance"))
    except (TypeError, ValueError) as exc:
        raise OdsayResponseError("ODSAY_RESPONSE_ERROR: distance is invalid") from exc
    return TransitLeg(
        traffic_type=traffic_type,
        section_time=_required_int(row.get("sectionTime"), "sectionTime"),
        distance=distance,
        station_count=_optional_int(row.get("stationCount")),
        start_name=_optional_text(row.get("startName")),
        end_name=_optional_text(row.get("endName")),
        start_local_station_id=_optional_text(row.get("startLocalStationID")),
        end_local_station_id=_optional_text(row.get("endLocalStationID")),
        start_station_city_code=_optional_int(row.get("startStationCityCode")),
        end_station_city_code=_optional_int(row.get("endStationCityCode")),
        start_station_provider_code=_optional_int(row.get("startStationProviderCode")),
        end_station_provider_code=_optional_int(row.get("endStationProviderCode")),
        buses=_parse_bus_lanes(row.get("lane")) if traffic_type == 2 else (),
    )


def normalize_routes(payload: dict[str, Any]) -> list[TransitRoute]:
    """Normalize ODsay routes without changing their provider-supplied order."""
    result = payload.get("result")
    if not isinstance(result, dict):
        raise OdsayResponseError("ODSAY_RESPONSE_ERROR: result is missing")
    paths = result.get("path")
    if not isinstance(paths, list):
        raise OdsayResponseError("ODSAY_RESPONSE_ERROR: path is missing")

    routes: list[TransitRoute] = []
    for path in paths:
        if not isinstance(path, dict):
            raise OdsayResponseError("ODSAY_RESPONSE_ERROR: path item is invalid")
        info = path.get("info")
        sub_paths = path.get("subPath")
        if not isinstance(info, dict) or not isinstance(sub_paths, list):
            raise OdsayResponseError("ODSAY_RESPONSE_ERROR: path details are missing")
        if not all(isinstance(sub_path, dict) for sub_path in sub_paths):
            raise OdsayResponseError("ODSAY_RESPONSE_ERROR: subPath item is invalid")
        routes.append(
            TransitRoute(
                path_type=_required_int(path.get("pathType"), "pathType"),
                total_time=_required_int(info.get("totalTime"), "totalTime"),
                total_walk_distance=_required_int(info.get("totalWalk"), "totalWalk"),
                total_distance=float(info.get("totalDistance")),
                bus_transit_count=_required_int(info.get("busTransitCount"), "busTransitCount"),
                subway_transit_count=_required_int(
                    info.get("subwayTransitCount"),
                    "subwayTransitCount",
                ),
                legs=tuple(_parse_leg(sub_path) for sub_path in sub_paths),
            )
        )
    return routes


def _traffic_label(traffic_type: int) -> str:
    """Return ODsay's documented Korean label for a transit segment type."""
    return {1: "Subway", 2: "Bus", 3: "Walk"}.get(traffic_type, "Unknown")


def _first_bus_leg(route: TransitRoute) -> TransitLeg | None:
    """Return the first bus segment in an ODsay route, if present."""
    return next((leg for leg in route.legs if leg.traffic_type == 2), None)


def print_routes(routes: list[TransitRoute]) -> None:
    """Print up to three ODsay options and the first provider-recommended route."""
    if not routes:
        print("NO_ROUTE_DATA: ODsay returned no route options.")
        return

    print("=== ODsay Route Planning PoC ===")
    print()
    print(f"Origin: {ORIGIN_NAME}")
    print(f"Destination: {DESTINATION_NAME}")
    print()
    print("Route Options")
    for index, route in enumerate(routes[:3], start=1):
        bus_leg = _first_bus_leg(route)
        buses = ", ".join(bus.bus_number for bus in bus_leg.buses) if bus_leg else "-"
        print(
            f"[{index}] {route.total_time} min, walk {route.total_walk_distance} m, "
            f"transfers {route.bus_transit_count + route.subway_transit_count}, "
            f"bus {buses}"
        )

    primary = routes[0]
    print()
    print("Route")
    print("-----------------")
    for leg in primary.legs:
        label = _traffic_label(leg.traffic_type)
        if leg.traffic_type == 2:
            buses = ", ".join(bus.bus_number for bus in leg.buses)
            print(f"Boarding Station: {leg.start_name}")
            print(f"Bus: {buses}")
            print(f"Alighting Station: {leg.end_name}")
            print(f"Bus Time: {leg.section_time} min")
            print(f"Station Count: {leg.station_count}")
            print(f"ODsay Boarding Station ID: {leg.start_local_station_id}")
            print(f"ODsay Alighting Station ID: {leg.end_local_station_id}")
            print(
                "ODsay Station Codes: "
                f"city={leg.start_station_city_code}, "
                f"provider={leg.start_station_provider_code}"
            )
            for bus in leg.buses:
                print(
                    f"ODsay Bus Route ID ({bus.bus_number}): {bus.bus_local_bl_id} "
                    f"(city={bus.bus_city_code}, provider={bus.bus_provider_code})"
                )
        else:
            print(f"{label}: {leg.section_time} min ({int(leg.distance)} m)")


def main() -> int:
    """Execute the ODsay route-planning PoC once and return its exit code."""
    try:
        routes = normalize_routes(fetch_route_payload(OdsayPocSettings()))
    except OdsayPocError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print_routes(routes)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
