"""Unit tests for the production Gyeonggi official-bus provider."""

from typing import Any
from urllib.parse import urlsplit

import pytest
import requests

from bus_monitor.gyeonggi import (
    GYEONGGI_ARRIVAL_ENDPOINT,
    GYEONGGI_STATION_ENDPOINT,
    GYEONGGI_STATION_ROUTE_ENDPOINT,
    GYEONGGI_VEHICLE_LOCATION_ENDPOINT,
    GyeonggiApiError,
    GyeonggiConfigurationError,
    GyeonggiProvider,
    GyeonggiProviderError,
    GyeonggiResponseError,
)


class FakeResponse:
    """Minimal injectable response with an optional HTTP failure."""

    def __init__(
        self,
        payload: object | None = None,
        *,
        http_error: requests.RequestException | None = None,
    ) -> None:
        self._payload = payload
        self._http_error = http_error

    def raise_for_status(self) -> None:
        """Raise the configured HTTP failure, when present."""
        if self._http_error is not None:
            raise self._http_error

    def json(self) -> object:
        """Return the configured JSON payload."""
        return self._payload


class FakeHttpClient:
    """Return queued fake responses and record calls without using the network."""

    def __init__(self, responses: list[FakeResponse]) -> None:
        self._responses = responses
        self.calls: list[dict[str, object]] = []

    def get(
        self,
        url: str,
        *,
        params: dict[str, str],
        timeout: float,
    ) -> FakeResponse:
        """Record one request and return the next configured response."""
        self.calls.append({"url": url, "params": params, "timeout": timeout})
        return self._responses.pop(0)


def _payload(body: dict[str, Any], result_code: int = 0) -> dict[str, Any]:
    return {
        "response": {
            "msgHeader": {"resultCode": result_code, "resultMessage": "정상"},
            "msgBody": body,
        }
    }


def _station_row() -> dict[str, object]:
    return {
        "stationId": 206000542,
        "stationName": "삼평교",
        "mobileNo": " 07498",
        "regionName": "성남",
        "x": 127.1041667,
        "y": 37.4039167,
    }


def _route_row(
    route_id: int = 228000184,
    route_name: str = "5600",
    station_order: int = 90,
) -> dict[str, object]:
    return {
        "routeId": route_id,
        "routeName": route_name,
        "routeTypeCd": 11,
        "routeTypeName": "직행좌석형시내버스",
        "staOrder": station_order,
        "regionName": "용인",
    }


def _arrival_row() -> dict[str, object]:
    return {
        "routeId": 228000184,
        "routeName": "5600",
        "predictTime1": 5,
        "predictTime2": 31,
        "predictTimeSec1": 322,
        "predictTimeSec2": 1894,
        "locationNo1": 4,
        "locationNo2": 21,
        "plateNo1": "경기78아1127",
        "plateNo2": "경기78아1253",
        "remainSeatCnt1": 41,
        "remainSeatCnt2": 39,
        "crowded1": 1,
        "crowded2": 1,
        "lowPlate1": 0,
        "lowPlate2": 0,
        "flag": "PASS",
        "stateCd1": 1,
        "stateCd2": 2,
    }


def _no_current_arrival_row() -> dict[str, object]:
    return {
        "routeId": 228000442,
        "routeName": "9241",
        "predictTime1": "",
        "predictTime2": "",
        "predictTimeSec1": "",
        "predictTimeSec2": "",
        "locationNo1": "",
        "locationNo2": "",
        "plateNo1": "",
        "plateNo2": "",
        "remainSeatCnt1": "",
        "remainSeatCnt2": "",
        "crowded1": "",
        "crowded2": "",
        "lowPlate1": "",
        "lowPlate2": "",
        "flag": "PASS",
        "stateCd1": 2,
        "stateCd2": 2,
    }


def _vehicle_row(vehicle_id: int = 228000131) -> dict[str, object]:
    return {
        "routeId": 228000184,
        "stationId": 204000037,
        "stationSeq": 86,
        "vehId": vehicle_id,
        "plateNo": "경기78아1127",
        "remainSeatCnt": 41,
        "crowded": 1,
        "stateCd": 2,
    }


def _provider(*responses: FakeResponse) -> tuple[GyeonggiProvider, FakeHttpClient]:
    client = FakeHttpClient(list(responses))
    return GyeonggiProvider(client, service_key="configured"), client


def test_get_station_normalizes_the_official_station_detail() -> None:
    """Station detail keeps the Gyeonggi station ID and WGS84 coordinates."""
    provider, client = _provider(FakeResponse(_payload({"busStationInfo": _station_row()})))

    station = provider.get_station("206000542")

    assert station is not None
    assert station.station_id == "206000542"
    assert station.name == "삼평교"
    assert station.mobile_number == "07498"
    assert station.region_name == "성남"
    assert station.latitude == 37.4039167
    assert station.longitude == 127.1041667
    assert client.calls[0]["url"] == GYEONGGI_STATION_ENDPOINT
    assert client.calls[0]["params"] == {
        "serviceKey": "configured",
        "format": "json",
        "stationId": "206000542",
    }


def test_get_station_routes_normalizes_multiple_authoritative_routes() -> None:
    """5600 and 9241 remain distinct station-serving route records."""
    provider, client = _provider(
        FakeResponse(
            _payload(
                {
                    "busRouteList": [
                        _route_row(),
                        _route_row(228000442, "9241", 27),
                    ]
                }
            )
        )
    )

    routes = provider.get_station_routes("206000542")

    assert [(route.route_number, route.route_id) for route in routes] == [
        ("5600", "228000184"),
        ("9241", "228000442"),
    ]
    assert routes[0].route_type_code == 11
    assert routes[0].route_type_name == "직행좌석형시내버스"
    assert routes[1].station_order == 27
    assert client.calls[0]["url"] == GYEONGGI_STATION_ROUTE_ENDPOINT


def test_get_arrivals_flattens_first_and_second_approaching_vehicles() -> None:
    """One 5600 route row becomes two independently matchable arrivals."""
    provider, client = _provider(FakeResponse(_payload({"busArrivalList": [_arrival_row()]})))

    arrivals = provider.get_arrivals("206000542")

    assert [(arrival.route_id, arrival.arrival_seconds) for arrival in arrivals] == [
        ("228000184", 322),
        ("228000184", 1894),
    ]
    assert [arrival.remaining_stops for arrival in arrivals] == [4, 21]
    assert [arrival.plate_number for arrival in arrivals] == ["경기78아1127", "경기78아1253"]
    assert [arrival.remaining_seats for arrival in arrivals] == [41, 39]
    assert [arrival.crowded for arrival in arrivals] == [1, 1]
    assert [arrival.state_code for arrival in arrivals] == [1, 2]
    assert [arrival.vehicle_type for arrival in arrivals] == ["일반버스", "일반버스"]
    assert all(arrival.operating_status == "PASS" for arrival in arrivals)
    assert client.calls[0]["url"] == GYEONGGI_ARRIVAL_ENDPOINT


def test_get_arrivals_treats_a_supported_route_without_eta_as_normal_empty_data() -> None:
    """A 9241 route row without current vehicles is not a provider failure."""
    provider, _ = _provider(
        FakeResponse(_payload({"busArrivalList": [_no_current_arrival_row()]}))
    )

    assert provider.get_arrivals("206000542") == ()


def test_get_vehicle_locations_normalizes_multiple_vehicles_and_seat_counts() -> None:
    """Vehicle-location results retain route, station, vehicle, and occupancy data."""
    provider, client = _provider(
        FakeResponse(_payload({"busLocationList": [_vehicle_row(), _vehicle_row(228000182)]}))
    )

    locations = provider.get_vehicle_locations("228000184")

    assert [location.vehicle_id for location in locations] == ["228000131", "228000182"]
    assert locations[0].route_id == "228000184"
    assert locations[0].station_id == "204000037"
    assert locations[0].station_sequence == 86
    assert locations[0].remaining_seats == 41
    assert locations[0].crowded == 1
    assert client.calls[0]["url"] == GYEONGGI_VEHICLE_LOCATION_ENDPOINT
    assert client.calls[0]["params"] == {
        "serviceKey": "configured",
        "format": "json",
        "routeId": "228000184",
    }


def test_single_item_objects_are_normalized_for_routes_and_locations() -> None:
    """Documented one-object response shapes do not require list-only parsing."""
    provider, _ = _provider(
        FakeResponse(_payload({"busRouteList": _route_row()})),
        FakeResponse(_payload({"busLocationList": _vehicle_row()})),
    )

    assert provider.get_station_routes("206000542")[0].route_number == "5600"
    assert provider.get_vehicle_locations("228000184")[0].vehicle_id == "228000131"


def test_normal_empty_results_return_none_or_empty_tuples() -> None:
    """Documented empty station, route, arrival, and vehicle data are normal outcomes."""
    provider, _ = _provider(
        FakeResponse(_payload({"busStationInfo": ""})),
        FakeResponse(_payload({"busRouteList": ""})),
        FakeResponse(_payload({"busArrivalList": ""})),
        FakeResponse(_payload({"busLocationList": ""})),
    )

    assert provider.get_station("206000542") is None
    assert provider.get_station_routes("206000542") == ()
    assert provider.get_arrivals("206000542") == ()
    assert provider.get_vehicle_locations("228000184") == ()


def test_http_and_api_failures_are_distinguishable() -> None:
    """Network failures and documented result-code failures keep separate error types."""
    provider, _ = _provider(FakeResponse(http_error=requests.Timeout("timeout")))

    with pytest.raises(GyeonggiProviderError, match="HTTP request failed"):
        provider.get_station("206000542")

    provider, _ = _provider(FakeResponse(_payload({}, result_code=4)))
    with pytest.raises(GyeonggiApiError, match="resultCode 4"):
        provider.get_station_routes("206000542")


def test_malformed_success_response_is_not_treated_as_empty_data() -> None:
    """A successful envelope with a malformed collection remains an explicit error."""
    provider, _ = _provider(FakeResponse(_payload({"busRouteList": "unexpected"})))

    with pytest.raises(GyeonggiResponseError, match="busRouteList is invalid"):
        provider.get_station_routes("206000542")


def test_decoding_service_key_is_passed_to_requests_without_transformation() -> None:
    """The provider gives a decoding key directly to requests query serialization."""
    decoding_key = "ABC/123+XYZ="
    client = FakeHttpClient([FakeResponse(_payload({"busStationInfo": ""}))])
    provider = GyeonggiProvider(client, service_key=decoding_key)

    provider.get_station("206000542")

    params = client.calls[0]["params"]
    assert isinstance(params, dict)
    assert params["serviceKey"] == decoding_key
    query = urlsplit(
        requests.Request("GET", str(client.calls[0]["url"]), params=params).prepare().url
    ).query
    assert "serviceKey=ABC%2F123%2BXYZ%3D" in query
    assert "%25" not in query


def test_missing_service_key_fails_before_a_request() -> None:
    """Configuration errors never expose a service key or make a network call."""
    with pytest.raises(GyeonggiConfigurationError, match="GYEONGGI_SERVICE_KEY"):
        GyeonggiProvider(service_key="")
