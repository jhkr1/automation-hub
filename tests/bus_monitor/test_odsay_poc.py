"""Unit tests for the isolated ODsay route-planning PoC."""

from typing import Any

import pytest

from bus_monitor.odsay_poc import (
    DESTINATION_LATITUDE,
    DESTINATION_LONGITUDE,
    ORIGIN_LATITUDE,
    ORIGIN_LONGITUDE,
    OdsayPocSettings,
    fetch_route_payload,
    get_route_request_parameters,
    normalize_routes,
)


def _payload() -> dict[str, Any]:
    return {
        "result": {
            "path": [
                {
                    "pathType": 2,
                    "info": {
                        "totalWalk": 243,
                        "totalTime": 33,
                        "totalDistance": 18531,
                        "busTransitCount": 1,
                        "subwayTransitCount": 0,
                    },
                    "subPath": [
                        {"trafficType": 3, "distance": 171, "sectionTime": 3},
                        {
                            "trafficType": 2,
                            "distance": 18288,
                            "sectionTime": 29,
                            "stationCount": 4,
                            "lane": [
                                {
                                    "busNo": "5600",
                                    "busID": 11024,
                                    "busLocalBlID": "228000184",
                                    "busCityCode": 1130,
                                    "busProviderCode": 2,
                                }
                            ],
                            "startName": "삼평교",
                            "endName": "롯데캐슬스카이.이안두드림.백남준아트센터",
                            "startLocalStationID": "206000542",
                            "endLocalStationID": "228000697",
                            "startStationCityCode": 1010,
                            "endStationCityCode": 1130,
                            "startStationProviderCode": 2,
                            "endStationProviderCode": 2,
                        },
                        {"trafficType": 3, "distance": 72, "sectionTime": 1},
                    ],
                }
            ]
        }
    }


def _settings() -> OdsayPocSettings:
    return OdsayPocSettings(odsay_api_key="test-key")


def test_route_request_uses_documented_wgs84_coordinate_order() -> None:
    """ODsay receives longitude as X and latitude as Y with a non-secret key."""
    assert get_route_request_parameters(_settings()) == {
        "apiKey": "test-key",
        "SX": ORIGIN_LONGITUDE,
        "SY": ORIGIN_LATITUDE,
        "EX": DESTINATION_LONGITUDE,
        "EY": DESTINATION_LATITUDE,
        "OPT": 0,
        "SearchType": 0,
        "SearchPathType": 0,
        "output": "json",
    }


def test_fetch_route_payload_does_not_expose_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The API key is passed only as a request parameter to ODsay."""
    calls: list[dict[str, object]] = []

    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, Any]:
            return _payload()

    def fake_get(*args: object, **kwargs: object) -> Response:
        calls.append({"args": args, "kwargs": kwargs})
        return Response()

    monkeypatch.setattr("bus_monitor.odsay_poc.requests.get", fake_get)
    assert fetch_route_payload(_settings()) == _payload()
    assert calls[0]["kwargs"]["timeout"] == 10.0


def test_normalize_routes_keeps_bus_station_and_bis_identifiers() -> None:
    """A documented bus path retains route and local station identifiers for review."""
    route = normalize_routes(_payload())[0]
    bus_leg = route.legs[1]

    assert route.total_time == 33
    assert route.total_walk_distance == 243
    assert bus_leg.start_name == "삼평교"
    assert bus_leg.end_name == "롯데캐슬스카이.이안두드림.백남준아트센터"
    assert bus_leg.start_local_station_id == "206000542"
    assert bus_leg.end_local_station_id == "228000697"
    assert bus_leg.buses[0].bus_number == "5600"
    assert bus_leg.buses[0].bus_local_bl_id == "228000184"
