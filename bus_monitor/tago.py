"""Production TAGO Station and bus-arrival provider."""

from __future__ import annotations

from typing import Any, Protocol
from urllib.parse import unquote

import requests

from bus_monitor.config import BusMonitorSettings
from bus_monitor.models import RealtimeArrival, StationCandidate

TAGO_STATION_ENDPOINT = (
    "https://apis.data.go.kr/1613000/BusSttnInfoInqireService/"
    "getCrdntPrxmtSttnList"
)
TAGO_ARRIVAL_ENDPOINT = (
    "https://apis.data.go.kr/1613000/ArvlInfoInqireService/"
    "getSttnAcctoArvlPrearngeInfoList"
)
SUCCESS_RESULT_CODE = "00"
DEFAULT_TIMEOUT_SECONDS = 10.0


class HttpResponse(Protocol):
    """Minimum response contract used by the TAGO provider."""

    def json(self) -> object:
        """Return the decoded JSON response body."""

    def raise_for_status(self) -> None:
        """Raise an HTTP error for non-successful responses."""


class HttpClient(Protocol):
    """Minimum HTTP client contract used by the TAGO provider."""

    def get(
        self,
        url: str,
        *,
        params: dict[str, str | float | int],
        timeout: float,
    ) -> HttpResponse:
        """Fetch one URL with query parameters and a timeout."""


class TagoProviderError(RuntimeError):
    """Base error for TAGO production-provider failures."""


class TagoConfigurationError(TagoProviderError):
    """Raised when the production TAGO service key is not configured."""


class TagoApiError(TagoProviderError):
    """Raised when TAGO returns a non-success result code."""


class TagoResponseError(TagoProviderError):
    """Raised when a TAGO success response cannot be normalized safely."""


def prepare_service_key(value: str | None) -> str:
    """Decode a portal-issued key once before ``requests`` serializes parameters."""
    if value is None or not value.strip():
        raise TagoConfigurationError("TAGO_SERVICE_KEY is not configured")
    return unquote(value.strip())


def _required_text(value: object, field_name: str) -> str:
    """Return a required text response field or raise a response error."""
    if value is None or not str(value).strip():
        raise TagoResponseError(f"TAGO response field {field_name} is missing or invalid")
    return str(value).strip()


def _required_non_negative_int(value: object, field_name: str) -> int:
    """Return a required non-negative integer response field."""
    try:
        normalized = int(value)
    except (TypeError, ValueError) as exc:
        raise TagoResponseError(f"TAGO response field {field_name} is missing or invalid") from exc
    if normalized < 0:
        raise TagoResponseError(f"TAGO response field {field_name} must not be negative")
    return normalized


def _required_float(value: object, field_name: str) -> float:
    """Return a required float response field or raise a response error."""
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise TagoResponseError(f"TAGO response field {field_name} is missing or invalid") from exc


def _coordinate(value: float, field_name: str, limit: float) -> float:
    """Validate a WGS84 request coordinate before making a provider request."""
    if not -limit <= value <= limit:
        raise ValueError(f"{field_name} must be a valid WGS84 coordinate")
    return value


class TagoProvider:
    """Fetch TAGO station candidates and station-specific realtime arrivals."""

    def __init__(
        self,
        http_client: HttpClient | None = None,
        *,
        service_key: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        """Create a provider with an injectable HTTP client and TAGO service key."""
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        configured_key = (
            service_key if service_key is not None else BusMonitorSettings().tago_service_key
        )
        self._service_key = prepare_service_key(configured_key)
        self._http_client = http_client or requests.Session()
        self._timeout = timeout

    def find_nearby_stations(
        self,
        longitude: float,
        latitude: float,
    ) -> tuple[StationCandidate, ...]:
        """Return all TAGO candidates near one WGS84 coordinate without selecting one."""
        payload = self._fetch_payload(
            TAGO_STATION_ENDPOINT,
            {
                "serviceKey": self._service_key,
                "gpsLati": _coordinate(latitude, "latitude", 90.0),
                "gpsLong": _coordinate(longitude, "longitude", 180.0),
                "pageNo": 1,
                "numOfRows": 100,
                "_type": "json",
            },
        )
        return tuple(self._station_candidate(row) for row in self._item_rows(payload))

    def get_arrivals(
        self,
        city_code: str,
        node_id: str,
    ) -> tuple[RealtimeArrival, ...]:
        """Return all realtime TAGO rows for one station, including normal empties."""
        payload = self._fetch_payload(
            TAGO_ARRIVAL_ENDPOINT,
            {
                "serviceKey": self._service_key,
                "cityCode": _required_text(city_code, "cityCode"),
                "nodeId": _required_text(node_id, "nodeId"),
                "pageNo": 1,
                "numOfRows": 100,
                "_type": "json",
            },
        )
        return tuple(self._realtime_arrival(row) for row in self._item_rows(payload))

    def _fetch_payload(
        self,
        endpoint: str,
        params: dict[str, str | float | int],
    ) -> dict[str, Any]:
        """Fetch and validate one documented TAGO JSON response envelope."""
        try:
            response = self._http_client.get(endpoint, params=params, timeout=self._timeout)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise TagoProviderError(f"TAGO HTTP request failed: {type(exc).__name__}") from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise TagoResponseError("TAGO response is not valid JSON") from exc
        if not isinstance(payload, dict):
            raise TagoResponseError("TAGO response root must be an object")

        response_body = payload.get("response")
        if not isinstance(response_body, dict):
            raise TagoResponseError("TAGO response object is missing or invalid")
        header = response_body.get("header")
        if not isinstance(header, dict):
            raise TagoResponseError("TAGO response header is missing or invalid")
        result_code = str(header.get("resultCode", ""))
        if result_code != SUCCESS_RESULT_CODE:
            raise TagoApiError(f"TAGO API returned resultCode {result_code or 'missing'}")
        return payload

    def _item_rows(self, payload: dict[str, Any]) -> tuple[dict[str, Any], ...]:
        """Return valid item rows while treating documented empty item forms as normal."""
        response_body = payload["response"]
        body = response_body.get("body")
        if not isinstance(body, dict):
            raise TagoResponseError("TAGO response body is missing or invalid")
        items = body.get("items")
        if items is None or items == "":
            return ()
        if not isinstance(items, dict):
            raise TagoResponseError("TAGO response items is invalid")
        raw_items = items.get("item")
        if raw_items is None or raw_items == "":
            return ()
        if isinstance(raw_items, dict):
            return (raw_items,)
        if isinstance(raw_items, list) and all(isinstance(row, dict) for row in raw_items):
            return tuple(raw_items)
        raise TagoResponseError("TAGO response item is invalid")

    @staticmethod
    def _station_candidate(row: dict[str, Any]) -> StationCandidate:
        """Normalize one TAGO nearby-station row into an unresolved candidate."""
        try:
            return StationCandidate(
                name=_required_text(row.get("nodenm"), "nodenm"),
                node_id=_required_text(row.get("nodeid"), "nodeid"),
                city_code=_required_text(row.get("citycode"), "citycode"),
                latitude=_required_float(row.get("gpslati"), "gpslati"),
                longitude=_required_float(row.get("gpslong"), "gpslong"),
            )
        except ValueError as exc:
            raise TagoResponseError("TAGO station candidate is invalid") from exc

    @staticmethod
    def _realtime_arrival(row: dict[str, Any]) -> RealtimeArrival:
        """Normalize one TAGO arrival row into the production result contract."""
        try:
            return RealtimeArrival(
                route_id=_required_text(row.get("routeid"), "routeid"),
                route_number=_required_text(row.get("routeno"), "routeno"),
                vehicle_type=_required_text(row.get("vehicletp"), "vehicletp"),
                arrival_seconds=_required_non_negative_int(row.get("arrtime"), "arrtime"),
                remaining_stops=_required_non_negative_int(
                    row.get("arrprevstationcnt"),
                    "arrprevstationcnt",
                ),
            )
        except ValueError as exc:
            raise TagoResponseError("TAGO realtime arrival is invalid") from exc
