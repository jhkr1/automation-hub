"""Unit tests for the production TAGO Station and Arrival provider."""

from typing import Any
from urllib.parse import urlsplit

import pytest
import requests

from bus_monitor.tago import (
    TAGO_ARRIVAL_ENDPOINT,
    TAGO_STATION_ENDPOINT,
    TagoApiError,
    TagoProvider,
    TagoProviderError,
    TagoResponseError,
    prepare_service_key,
)


class FakeResponse:
    """Minimal injectable response with optional HTTP failure."""

    def __init__(
        self,
        payload: object | None = None,
        *,
        http_error: requests.RequestException | None = None,
    ) -> None:
        self._payload = payload
        self._http_error = http_error

    def raise_for_status(self) -> None:
        """Raise the configured HTTP error, if any."""
        if self._http_error is not None:
            raise self._http_error

    def json(self) -> object:
        """Return the configured JSON payload."""
        return self._payload


class FakeHttpClient:
    """Return queued fake responses and record calls without network access."""

    def __init__(self, responses: list[FakeResponse]) -> None:
        self._responses = responses
        self.calls: list[dict[str, object]] = []

    def get(
        self,
        url: str,
        *,
        params: dict[str, str | float | int],
        timeout: float,
    ) -> FakeResponse:
        """Record a request and return its next configured response."""
        self.calls.append({"url": url, "params": params, "timeout": timeout})
        return self._responses.pop(0)


def _payload(items: object) -> dict[str, Any]:
    return {
        "response": {
            "header": {"resultCode": "00", "resultMsg": "OK"},
            "body": {"items": {"item": items}},
        }
    }


def _station_row(node_id: str = "GGB206000542") -> dict[str, str]:
    return {
        "nodeid": node_id,
        "nodenm": "삼평교",
        "citycode": "31020",
        "gpslati": "37.4039167",
        "gpslong": "127.1041667",
    }


def _arrival_row(route_id: str = "GGB204000007") -> dict[str, str]:
    return {
        "routeid": route_id,
        "routeno": "357",
        "vehicletp": "저상버스",
        "arrtime": "615",
        "arrprevstationcnt": "8",
    }


def _provider(*responses: FakeResponse) -> tuple[TagoProvider, FakeHttpClient]:
    client = FakeHttpClient(list(responses))
    return TagoProvider(client, service_key="configured"), client


def test_find_nearby_stations_normalizes_multiple_candidates() -> None:
    """All valid TAGO station rows remain available for a later Resolver decision."""
    provider, client = _provider(
        FakeResponse(_payload([_station_row(), _station_row("GGB206000566")]))
    )

    stations = provider.find_nearby_stations(127.102446246531, 37.4043389599242)

    assert [station.node_id for station in stations] == ["GGB206000542", "GGB206000566"]
    assert stations[0].name == "삼평교"
    assert stations[0].city_code == "31020"
    assert stations[0].latitude == 37.4039167
    assert stations[0].longitude == 127.1041667
    assert client.calls[0]["url"] == TAGO_STATION_ENDPOINT
    assert client.calls[0]["params"] == {
        "serviceKey": "configured",
        "gpsLati": 37.4043389599242,
        "gpsLong": 127.102446246531,
        "pageNo": 1,
        "numOfRows": 100,
        "_type": "json",
    }


def test_find_nearby_stations_normalizes_a_single_item_object() -> None:
    """A single object in ``items.item`` produces one station candidate."""
    provider, _ = _provider(FakeResponse(_payload(_station_row())))

    stations = provider.find_nearby_stations(127.1, 37.4)

    assert len(stations) == 1
    assert stations[0].node_id == "GGB206000542"


def test_find_nearby_stations_returns_empty_tuple_for_a_normal_empty_result() -> None:
    """An omitted ``items.item`` is a normal no-nearby-stations result."""
    provider, _ = _provider(FakeResponse(_payload(None)))

    assert provider.find_nearby_stations(127.1, 37.4) == ()


def test_get_arrivals_normalizes_multiple_rows() -> None:
    """All TAGO arrival rows are normalized without selecting a route lane."""
    provider, client = _provider(
        FakeResponse(_payload([_arrival_row(), _arrival_row("GGB204000073")]))
    )

    arrivals = provider.get_arrivals("31020", "GGB206000542")

    assert [arrival.route_id for arrival in arrivals] == ["GGB204000007", "GGB204000073"]
    assert arrivals[0].route_number == "357"
    assert arrivals[0].arrival_seconds == 615
    assert arrivals[0].remaining_stops == 8
    assert arrivals[0].vehicle_type == "저상버스"
    assert client.calls[0]["url"] == TAGO_ARRIVAL_ENDPOINT
    assert client.calls[0]["params"] == {
        "serviceKey": "configured",
        "cityCode": "31020",
        "nodeId": "GGB206000542",
        "pageNo": 1,
        "numOfRows": 100,
        "_type": "json",
    }


def test_get_arrivals_normalizes_a_single_item_object() -> None:
    """A single object in ``items.item`` produces one realtime arrival."""
    provider, _ = _provider(FakeResponse(_payload(_arrival_row())))

    arrivals = provider.get_arrivals("31020", "GGB206000542")

    assert len(arrivals) == 1
    assert arrivals[0].route_id == "GGB204000007"


def test_get_arrivals_returns_empty_tuple_for_a_normal_empty_result() -> None:
    """No realtime rows are a normal result, not a provider failure."""
    provider, _ = _provider(FakeResponse(_payload(None)))

    assert provider.get_arrivals("31020", "GGB206000542") == ()


def test_http_error_is_converted_to_a_provider_error() -> None:
    """Network and non-2xx failures do not leak raw requests exceptions."""
    provider, _ = _provider(FakeResponse(http_error=requests.Timeout("timeout")))

    with pytest.raises(TagoProviderError, match="HTTP request failed"):
        provider.find_nearby_stations(127.1, 37.4)


def test_tago_api_error_result_code_is_not_treated_as_an_empty_result() -> None:
    """A non-success TAGO result code is an API failure, not no station data."""
    provider, _ = _provider(
        FakeResponse(
            {
                "response": {
                    "header": {"resultCode": "30", "resultMsg": "not registered"},
                    "body": {},
                }
            }
        )
    )

    with pytest.raises(TagoApiError, match="resultCode 30"):
        provider.get_arrivals("31020", "GGB206000542")


def test_service_key_is_decoded_once_for_station_and_arrival_requests() -> None:
    """Both TAGO calls decode a portal key before requests serializes it once."""
    encoded_key = "ABC%2F123%2BXYZ%3D"
    client = FakeHttpClient(
        [
            FakeResponse(_payload(None)),
            FakeResponse(_payload(None)),
        ]
    )
    provider = TagoProvider(client, service_key=encoded_key)

    assert prepare_service_key(encoded_key) == "ABC/123+XYZ="
    provider.find_nearby_stations(127.1, 37.4)
    provider.get_arrivals("31020", "GGB206000542")

    for call in client.calls:
        query = urlsplit(
            requests.Request("GET", str(call["url"]), params=call["params"]).prepare().url
        ).query
        assert "serviceKey=ABC%2F123%2BXYZ%3D" in query
        assert "%25" not in query


def test_malformed_items_are_not_treated_as_normal_empty_results() -> None:
    """A malformed item scalar remains distinguishable from an omitted item."""
    provider, _ = _provider(FakeResponse(_payload("unexpected")))

    with pytest.raises(TagoResponseError, match="item is invalid"):
        provider.get_arrivals("31020", "GGB206000542")
