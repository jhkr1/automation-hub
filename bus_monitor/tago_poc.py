"""Minimal CLI PoC for the Ministry of Land TAGO bus-arrival API.

This module intentionally does not implement route planning, persistence, scheduling,
or alternate providers. It calls one documented TAGO station-arrival endpoint only.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import unquote

import requests
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent

TAGO_ARRIVAL_ENDPOINT = (
    "https://apis.data.go.kr/1613000/ArvlInfoInqireService/"
    "getSttnAcctoArvlPrearngeInfoList"
)
TAGO_STATION_ENDPOINT = (
    "https://apis.data.go.kr/1613000/BusSttnInfoInqireService/"
    "getCrdntPrxmtSttnList"
)
SUCCESS_RESULT_CODE = "00"
REQUEST_TIMEOUT_SECONDS = 10.0
NOT_PROVIDED_BY_TAGO = "NOT_PROVIDED_BY_TAGO"
POC_STATION_NAME_HINTS = ("삼평교", "이노밸리", "포스코DX", "SK플래닛", "판교디지털센터")
POC_ORIGIN_NAME = "지식시스템"


class TagoPocSettings(BaseSettings):
    """Load only the TAGO PoC inputs from environment variables or ``.env``."""

    tago_arrival_service_key: str | None = None
    tago_station_service_key: str | None = None
    tago_latitude: float | None = None
    tago_longitude: float | None = None
    tago_city_code: str | None = None
    tago_node_id: str | None = None

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        extra="ignore",
    )


class TagoPocError(RuntimeError):
    """Base error for a safe, human-readable TAGO PoC failure."""


class TagoConfigurationError(TagoPocError):
    """Raised before a request when a required PoC environment value is missing."""


class TagoHttpError(TagoPocError):
    """Raised when the HTTP request cannot return a successful response."""


class TagoApiError(TagoPocError):
    """Raised when TAGO returns a non-success ``resultCode`` response."""


class TagoResponseError(TagoPocError):
    """Raised when a success response does not match the documented JSON shape."""


class TagoStationError(TagoPocError):
    """Base error for the TAGO nearby-station request."""


@dataclass(frozen=True)
class BusArrival:
    """One TAGO arrival row normalized from documented response fields."""

    city_code: str
    station_id: str
    station_name: str
    route_id: str
    route_number: str
    vehicle_type: str
    arrival_seconds: int
    remaining_stops: int
    occupancy: None = None
    occupancy_status: str = NOT_PROVIDED_BY_TAGO


@dataclass(frozen=True)
class NearbyStation:
    """One nearby station row returned by TAGO's documented GPS operation."""

    station_id: str
    station_name: str
    city_code: str
    latitude: float
    longitude: float


def _required_setting(value: str | None, environment_name: str) -> str:
    """Return a non-empty setting without exposing its value in error output."""
    if value is None or not value.strip():
        raise TagoConfigurationError(f"{environment_name} is not configured.")
    return value.strip()


def prepare_service_key(value: str | None, environment_name: str) -> str:
    """Decode a portal-issued key once before ``requests`` encodes query parameters."""
    return unquote(_required_setting(value, environment_name))


def get_request_parameters(
    settings: TagoPocSettings,
    *,
    city_code: str | None = None,
    node_id: str | None = None,
) -> dict[str, str | int]:
    """Build documented TAGO request parameters after validating local settings."""
    return {
        "serviceKey": prepare_service_key(
            settings.tago_arrival_service_key,
            "TAGO_ARRIVAL_SERVICE_KEY",
        ),
        "_type": "json",
        "cityCode": _required_setting(
            city_code if city_code is not None else settings.tago_city_code,
            "TAGO_CITY_CODE",
        ),
        "nodeId": _required_setting(
            node_id if node_id is not None else settings.tago_node_id,
            "TAGO_NODE_ID",
        ),
        "pageNo": 1,
        "numOfRows": 100,
    }


def fetch_arrival_payload(
    settings: TagoPocSettings,
    *,
    city_code: str | None = None,
    node_id: str | None = None,
) -> dict[str, Any]:
    """Call TAGO once, validate HTTP/result codes, and return its JSON payload."""
    try:
        response = requests.get(
            TAGO_ARRIVAL_ENDPOINT,
            params=get_request_parameters(settings, city_code=city_code, node_id=node_id),
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except requests.HTTPError as exc:
        status_code = exc.response.status_code if exc.response is not None else "unknown"
        raise TagoHttpError(f"ARRIVAL_HTTP_ERROR: status={status_code}") from exc
    except requests.RequestException as exc:
        raise TagoHttpError(f"ARRIVAL_HTTP_ERROR: {type(exc).__name__}") from exc

    try:
        payload: Any = response.json()
    except ValueError as exc:
        raise TagoResponseError("TAGO_RESPONSE_ERROR: response is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise TagoResponseError("TAGO_RESPONSE_ERROR: JSON root must be an object")

    response_body = payload.get("response")
    if not isinstance(response_body, dict):
        raise TagoResponseError("TAGO_RESPONSE_ERROR: response object is missing")
    header = response_body.get("header")
    if not isinstance(header, dict):
        raise TagoResponseError("TAGO_RESPONSE_ERROR: response header is missing")

    result_code = str(header.get("resultCode", ""))
    if result_code != SUCCESS_RESULT_CODE:
        message = header.get("resultMsg")
        safe_message = message if isinstance(message, str) and message.strip() else "unknown error"
        raise TagoApiError(
            f"ARRIVAL_TAGO_API_ERROR: resultCode={result_code or 'missing'} ({safe_message})"
        )
    return payload


def _required_coordinate(value: float | None, environment_name: str, limit: float) -> float:
    """Validate one configured WGS84 coordinate without logging its source settings."""
    if value is None or not -limit <= value <= limit:
        raise TagoStationError(f"STATION_CONFIG_ERROR: {environment_name} is not configured.")
    return value


def get_station_request_parameters(settings: TagoPocSettings) -> dict[str, str | int | float]:
    """Build parameters for TAGO's documented GPS nearby-station operation."""
    return {
        "serviceKey": prepare_service_key(
            settings.tago_station_service_key,
            "TAGO_STATION_SERVICE_KEY",
        ),
        "_type": "json",
        "gpsLati": _required_coordinate(settings.tago_latitude, "TAGO_LATITUDE", 90.0),
        "gpsLong": _required_coordinate(settings.tago_longitude, "TAGO_LONGITUDE", 180.0),
        "pageNo": 1,
        "numOfRows": 100,
    }


def fetch_station_payload(settings: TagoPocSettings) -> dict[str, Any]:
    """Call TAGO's GPS nearby-station operation once and validate its result code."""
    try:
        response = requests.get(
            TAGO_STATION_ENDPOINT,
            params=get_station_request_parameters(settings),
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except TagoConfigurationError as exc:
        raise TagoStationError(f"STATION_CONFIG_ERROR: {exc}") from exc
    except requests.HTTPError as exc:
        status_code = exc.response.status_code if exc.response is not None else "unknown"
        raise TagoStationError(f"STATION_HTTP_ERROR: status={status_code}") from exc
    except requests.RequestException as exc:
        raise TagoStationError(f"STATION_HTTP_ERROR: {type(exc).__name__}") from exc

    try:
        payload: Any = response.json()
    except ValueError as exc:
        raise TagoStationError("STATION_RESPONSE_ERROR: response is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise TagoStationError("STATION_RESPONSE_ERROR: JSON root must be an object")

    response_body = payload.get("response")
    if not isinstance(response_body, dict):
        raise TagoStationError("STATION_RESPONSE_ERROR: response object is missing")
    header = response_body.get("header")
    if not isinstance(header, dict):
        raise TagoStationError("STATION_RESPONSE_ERROR: response header is missing")
    result_code = str(header.get("resultCode", ""))
    if result_code != SUCCESS_RESULT_CODE:
        message = header.get("resultMsg")
        safe_message = message if isinstance(message, str) and message.strip() else "unknown error"
        raise TagoStationError(
            f"STATION_TAGO_API_ERROR: resultCode={result_code or 'missing'} ({safe_message})"
        )
    return payload


def _required_text(row: dict[str, Any], field_name: str) -> str:
    """Read one documented text field from a TAGO item."""
    value = row.get(field_name)
    if value is None or not str(value).strip():
        raise TagoResponseError(f"TAGO_RESPONSE_ERROR: {field_name} is missing")
    return str(value).strip()


def _required_non_negative_integer(row: dict[str, Any], field_name: str) -> int:
    """Read one documented non-negative integer field from a TAGO item."""
    value = row.get(field_name)
    try:
        normalized = int(value)
    except (TypeError, ValueError) as exc:
        raise TagoResponseError(f"TAGO_RESPONSE_ERROR: {field_name} is invalid") from exc
    if normalized < 0:
        raise TagoResponseError(f"TAGO_RESPONSE_ERROR: {field_name} is negative")
    return normalized


def _required_float(row: dict[str, Any], field_name: str) -> float:
    """Read one documented coordinate field from a TAGO station row."""
    try:
        return float(_required_text(row, field_name))
    except ValueError as exc:
        raise TagoStationError(f"STATION_RESPONSE_ERROR: {field_name} is invalid") from exc


def normalize_nearby_stations(payload: dict[str, Any]) -> list[NearbyStation]:
    """Convert documented GPS nearby-station rows into immutable PoC rows."""
    response_body = payload.get("response")
    if not isinstance(response_body, dict):
        raise TagoStationError("STATION_RESPONSE_ERROR: response object is missing")
    body = response_body.get("body")
    if not isinstance(body, dict):
        raise TagoStationError("STATION_RESPONSE_ERROR: response body is missing")
    items = body.get("items")
    if not isinstance(items, dict):
        return []
    raw_items = items.get("item")
    if raw_items is None:
        return []
    rows = raw_items if isinstance(raw_items, list) else [raw_items]
    if not all(isinstance(row, dict) for row in rows):
        raise TagoStationError("STATION_RESPONSE_ERROR: item must be an object")

    return [
        NearbyStation(
            station_id=_required_text(row, "nodeid"),
            station_name=_required_text(row, "nodenm"),
            city_code=_required_text(row, "citycode"),
            latitude=_required_float(row, "gpslati"),
            longitude=_required_float(row, "gpslong"),
        )
        for row in rows
    ]


def select_poc_station(stations: list[NearbyStation]) -> NearbyStation | None:
    """Choose one known nearby-name match for this PoC, never for production routing."""
    for station in stations:
        if any(hint in station.station_name for hint in POC_STATION_NAME_HINTS):
            return station
    return None


def normalize_arrivals(payload: dict[str, Any], *, city_code: str) -> list[BusArrival]:
    """Convert documented TAGO arrival items into minimal immutable domain rows."""
    response_body = payload.get("response")
    if not isinstance(response_body, dict):
        raise TagoResponseError("TAGO_RESPONSE_ERROR: response object is missing")
    body = response_body.get("body")
    if not isinstance(body, dict):
        raise TagoResponseError("TAGO_RESPONSE_ERROR: response body is missing")
    items = body.get("items")
    if not isinstance(items, dict):
        return []
    raw_items = items.get("item")
    if raw_items is None:
        return []
    rows = raw_items if isinstance(raw_items, list) else [raw_items]
    if not all(isinstance(row, dict) for row in rows):
        raise TagoResponseError("TAGO_RESPONSE_ERROR: item must be an object")

    return [
        BusArrival(
            city_code=city_code,
            station_id=_required_text(row, "nodeid"),
            station_name=_required_text(row, "nodenm"),
            route_id=_required_text(row, "routeid"),
            route_number=_required_text(row, "routeno"),
            vehicle_type=_required_text(row, "vehicletp"),
            arrival_seconds=_required_non_negative_integer(row, "arrtime"),
            remaining_stops=_required_non_negative_integer(row, "arrprevstationcnt"),
        )
        for row in rows
    ]


def _format_minutes(arrival_seconds: int) -> str:
    """Render an arrival duration in whole minutes while retaining seconds separately."""
    return f"about {arrival_seconds // 60} min"


def print_arrivals(arrivals: list[BusArrival]) -> None:
    """Print only normalized TAGO data in a concise terminal layout."""
    if not arrivals:
        print("NO_ARRIVAL_DATA: TAGO returned no arrival rows.")
        return

    print("Realtime Arrivals")
    print("-----------------")
    for index, arrival in enumerate(arrivals, start=1):
        print()
        print(f"Arrival #{index}")
        print(f"Station: {arrival.station_name} ({arrival.station_id})")
        print(f"City Code: {arrival.city_code}")
        print(f"Bus: {arrival.route_number} ({arrival.route_id})")
        print(f"Vehicle Type: {arrival.vehicle_type}")
        print(
            f"Arrival: {arrival.arrival_seconds} sec "
            f"({_format_minutes(arrival.arrival_seconds)})"
        )
        print(f"Remaining Stops: {arrival.remaining_stops}")
        print(f"Occupancy: {arrival.occupancy_status}")


def print_nearby_stations(stations: list[NearbyStation]) -> None:
    """Print all GPS nearby-station candidates before a PoC station is selected."""
    print("Nearby Stations")
    for index, station in enumerate(stations, start=1):
        print()
        print(f"[{index}]")
        print(f"Name: {station.station_name}")
        print(f"Node ID: {station.station_id}")
        print(f"City Code: {station.city_code}")
        print(f"Latitude: {station.latitude}")
        print(f"Longitude: {station.longitude}")


def main() -> int:
    """Execute the GPS station-to-arrival TAGO PoC once and return its exit code."""
    settings = TagoPocSettings()
    try:
        station_payload = fetch_station_payload(settings)
        stations = normalize_nearby_stations(station_payload)
        if not stations:
            print("NO_NEARBY_STATIONS: TAGO returned no nearby station rows.", file=sys.stderr)
            return 1
        print("=== TAGO Station → Arrival Live PoC ===")
        print()
        print(f"Origin: {POC_ORIGIN_NAME}")
        print("Coordinates")
        print(f"Latitude: {settings.tago_latitude}")
        print(f"Longitude: {settings.tago_longitude}")
        print()
        print_nearby_stations(stations)
        station = select_poc_station(stations)
        if station is None:
            print("STATION_SELECTION_REQUIRED: no known PoC station name matched.", file=sys.stderr)
            return 1
        print()
        print("Selected Station")
        print(f"Name: {station.station_name}")
        print(f"City Code: {station.city_code}")
        print(f"Node ID: {station.station_id}")
        payload = fetch_arrival_payload(
            settings,
            city_code=station.city_code,
            node_id=station.station_id,
        )
        arrivals = normalize_arrivals(payload, city_code=station.city_code)
    except TagoPocError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print_arrivals(arrivals)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
