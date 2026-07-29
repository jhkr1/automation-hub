"""나무위키 실시간 검색어 원시 항목의 검증과 순위 변환."""

from collections.abc import Sequence

from namuwiki_trend.models import TrendItem

RawItem = tuple[object, object]

EXPECTED_ITEM_COUNT = 10
HREF_PREFIX = "/Go?q="


def _normalize_item(raw_item: RawItem, index: int) -> tuple[str, str]:
    """원시 항목의 keyword와 href를 검증하고 정규화한다."""
    if len(raw_item) != 2:
        raise ValueError(f"항목 {index + 1}의 필드 개수가 2가 아님: {len(raw_item)}개")

    raw_keyword, raw_href = raw_item
    if not isinstance(raw_keyword, str):
        raise ValueError(
            f"항목 {index + 1}의 keyword 타입이 str이 아님: {type(raw_keyword).__name__}"
        )

    keyword = raw_keyword.strip()
    if not keyword:
        raise ValueError(f"항목 {index + 1}의 keyword가 비어 있음")

    if not isinstance(raw_href, str) or not raw_href:
        raise ValueError(f"항목 {index + 1}의 href가 비어 있거나 문자열이 아님: {raw_href!r}")
    if not raw_href.startswith(HREF_PREFIX):
        raise ValueError(f"항목 {index + 1}의 href 형식이 잘못됨: {raw_href}")

    return keyword, raw_href


def validate_and_rank_items(raw_items: Sequence[RawItem]) -> list[TrendItem]:
    """원시 항목에서 sentinel을 제거하고 rank 1~10을 부여한다."""
    if len(raw_items) < 2:
        raise ValueError(f"sentinel 비교에 필요한 항목이 부족함: {len(raw_items)}개")

    normalized_items = [
        _normalize_item(raw_item, index) for index, raw_item in enumerate(raw_items)
    ]
    first_item = normalized_items[0]
    last_item = normalized_items[-1]
    if first_item != last_item:
        raise ValueError(
            "sentinel 규칙 불일치: "
            f"첫 항목={first_item!r}, 마지막 항목={last_item!r}"
        )

    data_items = normalized_items[:-1]
    if len(data_items) != EXPECTED_ITEM_COUNT:
        raise ValueError(
            "sentinel 제거 후 항목 수가 10개가 아님: "
            f"{len(data_items)}개"
        )

    return [
        TrendItem(rank=rank, keyword=keyword, href=href)
        for rank, (keyword, href) in enumerate(data_items, start=1)
    ]
