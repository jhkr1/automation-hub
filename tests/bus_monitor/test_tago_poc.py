"""Unit tests for the isolated TAGO bus-arrival PoC."""

from typing import Any
from urllib.parse import urlsplit

import pytest
import requests

from bus_monitor.tago_poc import (
    SUCCESS_RESULT_CODE,
    TAGO_ARRIVAL_ENDPOINT,
    TAGO_STATION_ENDPOINT,
    TagoApiError,
    TagoConfigurationError,
    TagoHttpError,
    TagoPocSettings,
    TagoStationError,
    fetch_arrival_payload,
    fetch_station_payload,
    get_request_parameters,
    get_station_request_parameters,
    normalize_arrivals,
    normalize_nearby_stations,
    prepare_service_key,
    select_poc_station,
)


def _payload(items: object) -> dict[str, Any]:
    return {
        "response": {
            "header": {"resultCode": SUCCESS_RESULT_CODE, "resultMsg": "OK"},
            "body": {"items": {"item": items}},
        }
    }


def _settings(**overrides: str | None) -> TagoPocSettings:
    values = {
        "tago_arrival_service_key": "test-key",
        "tago_station_service_key": "station-test-key",
        "tago_latitude": 37.4043389599242,
        "tago_longitude": 127.102446246531,
        "tago_city_code": "25",
        "tago_node_id": "DJB8001793",
    }
    values.update(overrides)
    return TagoPocSettings(**values)


def test_request_parameters_require_service_key_without_exposing_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A missing key prevents an HTTP request and avoids exposing its value."""
    monkeypatch.setattr(
        "bus_monitor.tago_poc.requests.get",
        lambda *args, **kwargs: pytest.fail("HTTP must not run without a service key"),
    )
    with pytest.raises(
        TagoConfigurationError,
        match="TAGO_ARRIVAL_SERVICE_KEY is not configured",
    ):
        fetch_arrival_payload(_settings(tago_arrival_service_key=""))


def test_prepare_service_key_decodes_once_for_station_and_arrival_requests() -> None:
    """Encoded portal keys are decoded before requests serializes both API query strings."""
    encoded_key = "ABC%2F123%2BXYZ%3D"
    decoded_key = "ABC/123+XYZ="
    settings = _settings(
        tago_arrival_service_key=encoded_key,
        tago_station_service_key=encoded_key,
    )

    assert prepare_service_key(encoded_key, "TEST_SERVICE_KEY") == decoded_key
    assert get_station_request_parameters(settings)["serviceKey"] == decoded_key
    assert get_request_parameters(settings)["serviceKey"] == decoded_key

    for endpoint, parameters in (
        (TAGO_STATION_ENDPOINT, get_station_request_parameters(settings)),
        (TAGO_ARRIVAL_ENDPOINT, get_request_parameters(settings)),
    ):
        query = urlsplit(requests.Request("GET", endpoint, params=parameters).prepare().url).query
        assert "serviceKey=ABC%2F123%2BXYZ%3D" in query
        assert "%25" not in query


def test_fetch_arrival_payload_uses_documented_json_parameters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The PoC requests the TAGO endpoint with JSON and station parameters."""
    calls: list[dict[str, object]] = []

    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, Any]:
            return _payload([])

    def fake_get(*args: object, **kwargs: object) -> Response:
        calls.append({"args": args, "kwargs": kwargs})
        return Response()

    monkeypatch.setattr("bus_monitor.tago_poc.requests.get", fake_get)

    assert fetch_arrival_payload(_settings())["response"]["header"]["resultCode"] == "00"
    assert calls[0]["kwargs"] == {
        "params": {
            "serviceKey": "test-key",
            "_type": "json",
            "cityCode": "25",
            "nodeId": "DJB8001793",
            "pageNo": 1,
            "numOfRows": 100,
        },
        "timeout": 10.0,
    }


def test_fetch_arrival_payload_separates_http_and_tago_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """HTTP failures and a TAGO non-success result code remain distinguishable."""
    def failing_get(*args: object, **kwargs: object) -> None:
        raise requests.Timeout("timeout")

    monkeypatch.setattr("bus_monitor.tago_poc.requests.get", failing_get)
    with pytest.raises(TagoHttpError, match="HTTP_ERROR"):
        fetch_arrival_payload(_settings())

    class ErrorResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, Any]:
            return {
                "response": {
                    "header": {"resultCode": "30", "resultMsg": "SERVICE_KEY_IS_NOT_REGISTERED"}
                }
            }

    monkeypatch.setattr(
        "bus_monitor.tago_poc.requests.get",
        lambda *args, **kwargs: ErrorResponse(),
    )
    with pytest.raises(TagoApiError, match="TAGO_API_ERROR: resultCode=30"):
        fetch_arrival_payload(_settings())


def test_station_request_uses_gps_coordinates_and_normalizes_all_candidates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The documented GPS operation uses the station key and preserves all rows."""
    calls: list[dict[str, object]] = []

    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, Any]:
            return _payload(
                [
                    {
                        "nodeid": "GGB123",
                        "nodenm": "이노밸리/포스코DX",
                        "citycode": "31010",
                        "gpslati": "37.4043",
                        "gpslong": "127.1024",
                    },
                    {
                        "nodeid": "GGB124",
                        "nodenm": "다른정류장",
                        "citycode": "31010",
                        "gpslati": "37.4044",
                        "gpslong": "127.1025",
                    },
                ]
            )

    def fake_get(*args: object, **kwargs: object) -> Response:
        calls.append({"args": args, "kwargs": kwargs})
        return Response()

    monkeypatch.setattr("bus_monitor.tago_poc.requests.get", fake_get)
    stations = normalize_nearby_stations(fetch_station_payload(_settings()))

    assert len(stations) == 2
    assert select_poc_station(stations) == stations[0]
    assert calls[0]["kwargs"] == {
        "params": {
            "serviceKey": "station-test-key",
            "_type": "json",
            "gpsLati": 37.4043389599242,
            "gpsLong": 127.102446246531,
            "pageNo": 1,
            "numOfRows": 100,
        },
        "timeout": 10.0,
    }


def test_station_request_requires_config_before_http_and_arrival_accepts_runtime_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Station configuration is checked locally and arrival IDs may come from TAGO rows."""
    monkeypatch.setattr(
        "bus_monitor.tago_poc.requests.get",
        lambda *args, **kwargs: pytest.fail("HTTP must not run without coordinates"),
    )
    with pytest.raises(TagoStationError, match="STATION_CONFIG_ERROR"):
        fetch_station_payload(_settings(tago_latitude=None))

    calls: list[dict[str, object]] = []

    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, Any]:
            return _payload([])

    def fake_get(*args: object, **kwargs: object) -> Response:
        calls.append({"args": args, "kwargs": kwargs})
        return Response()

    monkeypatch.setattr("bus_monitor.tago_poc.requests.get", fake_get)
    fetch_arrival_payload(
        _settings(tago_city_code=None, tago_node_id=None),
        city_code="31",
        node_id="GGB1",
    )

    assert calls[0]["kwargs"] == {
        "params": {
            "serviceKey": "test-key",
            "_type": "json",
            "cityCode": "31",
            "nodeId": "GGB1",
            "pageNo": 1,
            "numOfRows": 100,
        },
        "timeout": 10.0,
    }


def test_normalize_arrivals_keeps_documented_fields_and_marks_occupancy_unprovided() -> None:
    """A real-shape TAGO row becomes one normalized PoC arrival object."""
    arrivals = normalize_arrivals(
        _payload(
            {
                "nodeid": "DJB8001793",
                "nodenm": "북대전농협",
                "routeid": "DJB30300002",
                "routeno": "5",
                "vehicletp": "저상버스",
                "arrtime": "816",
                "arrprevstationcnt": "15",
            }
        ),
        city_code="25",
    )

    assert len(arrivals) == 1
    assert arrivals[0].route_number == "5"
    assert arrivals[0].arrival_seconds == 816
    assert arrivals[0].remaining_stops == 15
    assert arrivals[0].occupancy is None
    assert arrivals[0].occupancy_status == "NOT_PROVIDED_BY_TAGO"


def test_normalize_arrivals_returns_empty_for_success_without_items() -> None:
    """A successful response without item rows is normal no-arrival data."""
    payload = {
        "response": {
            "header": {"resultCode": "00", "resultMsg": "OK"},
            "body": {"items": {}},
        }
    }
    assert normalize_arrivals(payload, city_code="25") == []
