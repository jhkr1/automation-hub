"""Pure matching of ODsay bus lanes to TAGO realtime arrivals."""

from __future__ import annotations

import re
import unicodedata

from bus_monitor.models import BusLane, RealtimeArrival

_WHITESPACE_PATTERN = re.compile(r"\s+")
_NUMERIC_SUFFIX_PATTERN = re.compile(r"(\d+)$")


def _normalize_route_number(value: str) -> str:
    """Normalize Unicode and whitespace without merging route variants in parentheses."""
    return _WHITESPACE_PATTERN.sub("", unicodedata.normalize("NFKC", value).casefold())


def _numeric_suffix(value: str) -> str | None:
    """Return an identifier's numeric suffix as auxiliary matching evidence."""
    match = _NUMERIC_SUFFIX_PATTERN.search(value)
    return match.group(1) if match else None


def _is_strong_match(lane: BusLane, arrival: RealtimeArrival) -> bool:
    """Require both displayed route number and non-contractual ID suffix agreement."""
    lane_suffix = _numeric_suffix(lane.local_route_id)
    arrival_suffix = _numeric_suffix(arrival.route_id)
    return (
        _normalize_route_number(lane.bus_number) == _normalize_route_number(arrival.route_number)
        and lane_suffix is not None
        and lane_suffix == arrival_suffix
    )


def match_arrivals(
    lanes: tuple[BusLane, ...],
    arrivals: tuple[RealtimeArrival, ...],
) -> tuple[RealtimeArrival, ...]:
    """Return every strongly matched arrival in TAGO's original response order.

    The ID suffix pattern is only accepted with an independently equal displayed route
    number, avoiding automatic matches from either signal in isolation.
    """
    return tuple(
        arrival
        for arrival in arrivals
        if any(_is_strong_match(lane, arrival) for lane in lanes)
    )
