"""나무위키 실시간 검색어 TrendItem의 CSV 저장."""

import csv
from collections.abc import Sequence
from pathlib import Path

from namuwiki_trend.models import TrendItem

CSV_HEADERS = ("rank", "keyword", "href")
CSV_ENCODING = "utf-8-sig"


def save_trends_to_csv(
    items: Sequence[TrendItem],
    output_path: str | Path,
) -> Path:
    """TrendItem 목록을 UTF-8 BOM CSV로 덮어써서 저장한다.

    부모 디렉터리가 없으면 생성하며, 기존 파일은 append하지 않고 덮어쓴다.
    """
    if not items:
        raise ValueError("저장할 TrendItem이 없음")

    for index, item in enumerate(items):
        if not isinstance(item, TrendItem):
            raise TypeError(f"항목 {index + 1}이 TrendItem이 아님: {type(item).__name__}")
        if type(item.rank) is not int:
            raise TypeError(f"항목 {index + 1}의 rank가 int가 아님: {type(item.rank).__name__}")
        if not isinstance(item.keyword, str):
            raise TypeError(
                f"항목 {index + 1}의 keyword가 str이 아님: {type(item.keyword).__name__}"
            )
        if not isinstance(item.href, str):
            raise TypeError(f"항목 {index + 1}의 href가 str이 아님: {type(item.href).__name__}")

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding=CSV_ENCODING, newline="") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(CSV_HEADERS)
        writer.writerows((item.rank, item.keyword, item.href) for item in items)

    return path
