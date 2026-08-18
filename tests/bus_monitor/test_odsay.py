"""Unit tests for the production ODsay route provider."""

from typing import Any

import pytest
import requests

from bus_monitor.odsay import (
    ODSAY_ROUTE_ENDPOINT,
    OdsayApiError,
    OdsayBusLegNotFoundError,
    OdsayProviderError,
    OdsayRouteNotFoundError,
    OdsayRouteProvider,
)


class FakeResponse:
    """Minimal injectable response with optional HTTP or JSON failures."""

    def __init__(
        self,
        payload: object | None = None,
        *,
        http_error: requests.RequestException | None = None,
        json_error: ValueError | None = None,
    ) -> None:
        self._payload = payload
        self._http_error = http_error
        self._json_error = json_error

    def raise_for_status(self) -> None:
        """Raise the configured HTTP error, if any."""
        if self._http_error is not None:
            raise self._http_error

    def json(self) -> object:
        """Return the configured payload or raise its configured JSON error."""
        if self._json_error is not None:
            raise self._json_error
        return self._payload


class FakeHttpClient:
    """Record HTTP calls and return a predefined response without network access."""

    def __init__(self, response: FakeResponse) -> None:
        self.response = response
        self.calls: list[dict[str, object]] = []

    def get(
        self,
        url: str,
        *,
        params: dict[str, str | float | int],
        timeout: float,
    ) -> FakeResponse:
        """Record an ODsay request and return the configured fake response."""
        self.calls.append({"url": url, "params": params, "timeout": timeout})
        return self.response


def _path(*, include_bus: bool = True) -> dict[str, Any]:
    sub_paths: list[dict[str, Any]] = [
        {"trafficType": 3, "distance": 171, "sectionTime": 3},
    ]
    if include_bus:
        sub_paths.append(
            {
                "trafficType": 2,
                "distance": 18288,
                "sectionTime": 29,
                "stationCount": 4,
                "startName": "삼평교",
                "startLocalStationID": "206000542",
                "startX": 127.104252,
                "startY": 37.403789,
                "endName": "롯데캐슬스카이.이안두드림.백남준아트센터",
                "endLocalStationID": "228000697",
                "endX": 127.108851,
                "endY": 37.271599,
                "lane": [
                    {"busNo": "5600", "busLocalBlID": "228000184"},
                    {"busNo": "9241", "busLocalBlID": "228000442"},
                    {"busNo": "5600(예약.평일운행)", "busLocalBlID": "228000420"},
                    {"busNo": "5600(급행하행)", "busLocalBlID": "228000463"},
                ],
            }
        )
    return {
        "pathType": 2,
        "info": {
            "totalWalk": 243,
            "totalTime": 33,
            "busTransitCount": 1,
            "subwayTransitCount": 0,
        },
        "subPath": sub_paths,
    }


def _payload(*, include_bus: bool = True) -> dict[str, Any]:
    return {"result": {"path": [_path(include_bus=include_bus)]}}


def _provider(response: FakeResponse) -> tuple[OdsayRouteProvider, FakeHttpClient]:
    client = FakeHttpClient(response)
    return OdsayRouteProvider(client, api_key="configured"), client


def test_search_route_normalizes_the_first_odsay_bus_route() -> None:
    """A valid ODsay response becomes the production route contract."""
    provider, client = _provider(FakeResponse(_payload()))

    route = provider.search_route(
        127.102446246531,
        37.4043389599242,
        127.10856729001851,
        37.27220279535416,
    )

    assert route.total_time_minutes == 33
    assert route.walk_distance_meters == 243
    assert route.transfer_count == 1
    assert client.calls == [
        {
            "url": ODSAY_ROUTE_ENDPOINT,
            "params": {
                "apiKey": "configured",
                "SX": 127.102446246531,
                "SY": 37.4043389599242,
                "EX": 127.10856729001851,
                "EY": 37.27220279535416,
                "OPT": 0,
                "SearchType": 0,
            },
            "timeout": 10.0,
        }
    ]


def test_search_route_preserves_all_bus_lanes_in_provider_order() -> None:
    """A selected bus leg retains every ODsay lane candidate in order."""
    provider, _ = _provider(FakeResponse(_payload()))

    bus_leg = provider.search_route(127.1, 37.4, 127.2, 37.3).bus_legs[0]

    assert bus_leg.start_station.name == "삼평교"
    assert bus_leg.start_station.local_station_id == "206000542"
    assert bus_leg.start_station.latitude == 37.403789
    assert bus_leg.start_station.longitude == 127.104252
    assert bus_leg.end_station.local_station_id == "228000697"
    assert [lane.bus_number for lane in bus_leg.lanes] == [
        "5600",
        "9241",
        "5600(예약.평일운행)",
        "5600(급행하행)",
    ]
    assert [lane.local_route_id for lane in bus_leg.lanes] == [
        "228000184",
        "228000442",
        "228000420",
        "228000463",
    ]


def test_search_route_converts_http_failure_to_provider_error() -> None:
    """HTTP failures do not leak an unclassified requests exception."""
    provider, _ = _provider(FakeResponse(http_error=requests.HTTPError("not exposed")))

    with pytest.raises(OdsayProviderError, match="HTTP request failed"):
        provider.search_route(127.1, 37.4, 127.2, 37.3)


def test_search_route_rejects_odsay_api_error_payload() -> None:
    """HTTP 200 API error payloads cannot be mistaken for routes."""
    provider, _ = _provider(FakeResponse({"error": {"code": -8, "msg": "invalid"}}))

    with pytest.raises(OdsayApiError, match="error code -8"):
        provider.search_route(127.1, 37.4, 127.2, 37.3)


def test_search_route_rejects_an_empty_route_list() -> None:
    """A successful envelope with no path raises a route-not-found error."""
    provider, _ = _provider(FakeResponse({"result": {"path": []}}))

    with pytest.raises(OdsayRouteNotFoundError, match="no route options"):
        provider.search_route(127.1, 37.4, 127.2, 37.3)


def test_search_route_rejects_a_route_without_a_bus_leg() -> None:
    """A route containing only non-bus sub-paths is not usable in this sprint."""
    provider, _ = _provider(FakeResponse(_payload(include_bus=False)))

    with pytest.raises(OdsayBusLegNotFoundError, match="no bus segment"):
        provider.search_route(127.1, 37.4, 127.2, 37.3)
