"""나무위키 TrendItem CSV 저장 테스트."""

import csv

import pytest

from namuwiki_trend.csv_storage import CSV_ENCODING, save_trends_to_csv
from namuwiki_trend.models import TrendItem


def _items() -> list[TrendItem]:
    """CSV 저장 테스트용 TrendItem 목록을 만든다."""
    return [
        TrendItem(1, "검색어,테스트", '/Go?q=검색어,테스트'),
        TrendItem(2, '검색어 "테스트"', '/Go?q=검색어%20"테스트"'),
    ]


def _read_rows(path) -> list[dict[str, str]]:
    """CSV parser로 저장 결과를 읽는다."""
    with path.open(encoding=CSV_ENCODING, newline="") as csv_file:
        return list(csv.DictReader(csv_file))


def test_save_trends_to_csv_writes_header_and_rows(tmp_path) -> None:
    """헤더 순서와 TrendItem 행 순서를 보존한다."""
    output_path = tmp_path / "nested" / "trends.csv"

    result_path = save_trends_to_csv(_items(), output_path)

    assert result_path == output_path
    assert output_path.exists()
    assert _read_rows(output_path) == [
        {"rank": "1", "keyword": "검색어,테스트", "href": "/Go?q=검색어,테스트"},
        {"rank": "2", "keyword": '검색어 "테스트"', "href": '/Go?q=검색어%20"테스트"'},
    ]


def test_save_trends_to_csv_writes_utf8_bom(tmp_path) -> None:
    """한국어 보존과 Excel 호환을 위한 BOM을 확인한다."""
    output_path = tmp_path / "trends.csv"

    save_trends_to_csv([TrendItem(1, "나무위키", "/Go?q=나무위키")], output_path)

    assert output_path.read_bytes().startswith(b"\xef\xbb\xbf")
    assert _read_rows(output_path)[0]["keyword"] == "나무위키"


def test_save_trends_to_csv_overwrites_existing_file(tmp_path) -> None:
    """기존 파일을 append하지 않고 새 내용으로 덮어쓴다."""
    output_path = tmp_path / "trends.csv"
    output_path.write_text("old,data\n", encoding="utf-8")

    save_trends_to_csv([TrendItem(1, "새 값", "/Go?q=새 값")], output_path)

    assert _read_rows(output_path) == [{"rank": "1", "keyword": "새 값", "href": "/Go?q=새 값"}]


def test_save_trends_to_csv_rejects_empty_items(tmp_path) -> None:
    """빈 입력을 거부하고 파일을 생성하지 않는다."""
    output_path = tmp_path / "trends.csv"

    with pytest.raises(ValueError, match="저장할 TrendItem이 없음"):
        save_trends_to_csv([], output_path)

    assert not output_path.exists()


def test_save_trends_to_csv_rejects_invalid_item_type(tmp_path) -> None:
    """TrendItem이 아닌 입력을 거부한다."""
    output_path = tmp_path / "trends.csv"

    with pytest.raises(TypeError, match="TrendItem이 아님"):
        save_trends_to_csv(["invalid"], output_path)  # type: ignore[list-item]

    assert not output_path.exists()


def test_save_trends_to_csv_propagates_filesystem_error(tmp_path) -> None:
    """파일 경로가 디렉터리이면 파일 시스템 예외를 전달한다."""
    output_path = tmp_path / "directory"
    output_path.mkdir()

    with pytest.raises(IsADirectoryError):
        save_trends_to_csv([TrendItem(1, "검색어", "/Go?q=검색어")], output_path)
