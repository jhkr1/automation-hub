from datetime import datetime, timezone

import pytest

from database.models import TrendSnapshot


def snapshot(**overrides: object) -> TrendSnapshot:
    values: dict[str, object] = {
        "collected_at": datetime(2026, 7, 30, 16, 0, tzinfo=timezone.utc),
        "rank_position": 1,
        "keyword": "  example  ",
    }
    values.update(overrides)
    return TrendSnapshot(**values)


def test_snapshot_normalizes_keyword_and_calculates_seoul_date() -> None:
    item = snapshot()

    assert item.keyword == "example"
    assert item.collection_date.isoformat() == "2026-07-31"
    assert item.collected_at.tzinfo is None


@pytest.mark.parametrize("rank", [0, 11])
def test_rank_out_of_range_is_rejected(rank: int) -> None:
    with pytest.raises(ValueError, match="rank_position"):
        snapshot(rank_position=rank)


@pytest.mark.parametrize("keyword", ["", "   "])
def test_empty_keyword_is_rejected(keyword: str) -> None:
    with pytest.raises(ValueError, match="keyword"):
        snapshot(keyword=keyword)


def test_naive_collected_at_is_rejected() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        snapshot(collected_at=datetime(2026, 7, 30, 15, 0))
