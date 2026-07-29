"""나무위키 실시간 검색어 순수 추출 규칙 테스트."""

import pytest

from namuwiki_trend.extraction import validate_and_rank_items


def _valid_raw_items(count: int = 10) -> list[tuple[str, str]]:
    """테스트용 deterministic 원시 항목을 만든다."""
    items = [(f"keyword-{index}", f"/Go?q=keyword-{index}") for index in range(1, count + 1)]
    return [*items, items[0]]


def test_validate_and_rank_items_removes_sentinel_and_preserves_order() -> None:
    """10개 항목과 sentinel에서 rank와 순서를 보존한다."""
    result = validate_and_rank_items(_valid_raw_items())

    assert len(result) == 10
    assert [item.rank for item in result] == list(range(1, 11))
    assert [item.keyword for item in result] == [f"keyword-{index}" for index in range(1, 11)]
    assert all(item.keyword != "keyword-0" for item in result)


def test_validate_and_rank_items_strips_keyword_whitespace() -> None:
    """keyword 앞뒤 공백을 제거한다."""
    raw_items = _valid_raw_items()
    raw_items[0] = ("  keyword-1  ", raw_items[0][1])
    raw_items[-1] = (" keyword-1 ", raw_items[-1][1])

    result = validate_and_rank_items(raw_items)

    assert result[0].keyword == "keyword-1"


def test_validate_and_rank_items_rejects_sentinel_mismatch() -> None:
    """마지막 항목이 첫 항목과 다르면 실패한다."""
    raw_items = _valid_raw_items()
    raw_items[-1] = ("different", "/Go?q=different")

    with pytest.raises(ValueError, match="sentinel 규칙 불일치"):
        validate_and_rank_items(raw_items)


@pytest.mark.parametrize("count", [9, 11])
def test_validate_and_rank_items_rejects_wrong_data_count(count: int) -> None:
    """sentinel 제거 후 실제 항목이 10개가 아니면 실패한다."""
    with pytest.raises(ValueError, match="항목 수가 10개가 아님"):
        validate_and_rank_items(_valid_raw_items(count))


def test_validate_and_rank_items_rejects_blank_keyword() -> None:
    """공백만 있는 keyword를 거부한다."""
    raw_items = _valid_raw_items()
    raw_items[3] = ("  ", raw_items[3][1])

    with pytest.raises(ValueError, match="keyword가 비어 있음"):
        validate_and_rank_items(raw_items)


def test_validate_and_rank_items_rejects_invalid_href() -> None:
    """Go 검색 경로가 아닌 href를 거부한다."""
    raw_items = _valid_raw_items()
    raw_items[2] = (raw_items[2][0], "/wiki/keyword-3")

    with pytest.raises(ValueError, match="href 형식이 잘못됨"):
        validate_and_rank_items(raw_items)


@pytest.mark.parametrize(
    ("position", "invalid_item"),
    [
        (0, ("keyword-1", "")),
        (0, ("keyword-1", None)),
        (0, ("keyword-1", 123)),
        (-1, ("keyword-1", "")),
        (-1, ("keyword-1", None)),
        (-1, ("keyword-1", 123)),
    ],
)
def test_validate_and_rank_items_rejects_invalid_first_or_last_data(
    position: int,
    invalid_item: tuple[object, object],
) -> None:
    """첫 항목 또는 sentinel의 href 이상을 거부한다."""
    raw_items = _valid_raw_items()
    raw_items[position] = invalid_item

    with pytest.raises(ValueError, match="href가 비어 있거나 문자열이 아님"):
        validate_and_rank_items(raw_items)


def test_validate_and_rank_items_rejects_too_few_items() -> None:
    """sentinel 비교가 불가능한 입력을 거부한다."""
    with pytest.raises(ValueError, match="항목이 부족함"):
        validate_and_rank_items([])
