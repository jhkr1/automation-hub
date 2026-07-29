"""JsonTrendInsightStorage의 네트워크 비의존 계약 테스트."""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from namuwiki_trend.insight_storage import JsonTrendInsightStorage
from namuwiki_trend.models import NewsArticle, TrendInsight, TrendItem

FIXED_TIME = datetime(2026, 7, 29, 12, 30, tzinfo=timezone.utc)


def _insight(rank: int = 1, keyword: str = "손흥민") -> TrendInsight:
    """테스트용 TrendInsight를 만든다."""
    trend = TrendItem(rank=rank, keyword=keyword, href=f"/Go?q={rank}")
    articles = (
        NewsArticle(
            title=f"{keyword} 관련 기사",
            url=f"https://news.example/{rank}",
            source="테스트뉴스",
            published_at=FIXED_TIME,
        ),
        NewsArticle(
            title=f"{keyword} 추가 기사",
            url=f"https://news.example/{rank}/2",
        ),
    )
    return TrendInsight(trend=trend, reason=f"{keyword}에 대한 설명", articles=articles)


def _storage() -> JsonTrendInsightStorage:
    """고정 시각을 사용하는 Storage를 만든다."""
    return JsonTrendInsightStorage(clock=lambda: FIXED_TIME)


def test_save_preserves_json_contract_and_returns_path(tmp_path: Path) -> None:
    """단일 Insight의 계약 필드와 저장 경로를 보존한다."""
    path = tmp_path / "nested" / "insights.json"

    result = _storage().save([_insight()], path)
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert result == path
    assert payload["schema_version"] == 1
    assert payload["generated_at"] == "2026-07-29T12:30:00+00:00"
    assert payload["insights"][0] == {
        "trend": {"rank": 1, "keyword": "손흥민", "href": "/Go?q=1"},
        "reason": "손흥민에 대한 설명",
        "articles": [
            {
                "title": "손흥민 관련 기사",
                "url": "https://news.example/1",
                "source": "테스트뉴스",
                "published_at": "2026-07-29T12:30:00+00:00",
            },
            {
                "title": "손흥민 추가 기사",
                "url": "https://news.example/1/2",
                "source": None,
                "published_at": None,
            },
        ],
    }
    assert "손흥민" in path.read_text(encoding="utf-8")


def test_save_preserves_insight_and_article_order(tmp_path: Path) -> None:
    """여러 Insight와 기사 목록의 입력 순서를 보존한다."""
    insights = [_insight(2, "두 번째"), _insight(1, "첫 번째")]

    _storage().save(insights, tmp_path / "insights.json")
    payload = json.loads((tmp_path / "insights.json").read_text(encoding="utf-8"))

    assert [item["trend"]["keyword"] for item in payload["insights"]] == ["두 번째", "첫 번째"]
    assert [item["title"] for item in payload["insights"][0]["articles"]] == [
        "두 번째 관련 기사",
        "두 번째 추가 기사",
    ]


def test_save_allows_empty_list(tmp_path: Path) -> None:
    """빈 목록도 유효한 JSON으로 저장한다."""
    path = tmp_path / "empty.json"

    _storage().save([], path)

    assert json.loads(path.read_text(encoding="utf-8")) == {
        "schema_version": 1,
        "generated_at": "2026-07-29T12:30:00+00:00",
        "insights": [],
    }


def test_save_overwrites_existing_file(tmp_path: Path) -> None:
    """기존 파일을 새 payload로 overwrite한다."""
    path = tmp_path / "insights.json"
    path.write_text('{"old": true}', encoding="utf-8")

    _storage().save([_insight()], path)

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert "old" not in payload
    assert payload["insights"][0]["reason"] == "손흥민에 대한 설명"


def test_save_does_not_mutate_input_models(tmp_path: Path) -> None:
    """저장 과정에서 입력 모델과 목록을 변경하지 않는다."""
    insights = [_insight()]
    original = insights.copy()
    original_articles = insights[0].articles

    _storage().save(insights, tmp_path / "insights.json")

    assert insights == original
    assert insights[0].articles == original_articles


@pytest.mark.parametrize("invalid", [None, ["invalid"], [object()]])
def test_save_rejects_invalid_insight_items(tmp_path: Path, invalid: object) -> None:
    """TrendInsight 목록에 다른 타입이 있으면 저장하지 않는다."""
    with pytest.raises(TypeError, match="TrendInsight"):
        _storage().save(invalid, tmp_path / "invalid.json")  # type: ignore[arg-type]


def test_save_rejects_naive_generated_at(tmp_path: Path) -> None:
    """generated_at clock이 naive datetime을 반환하면 실패한다."""
    storage = JsonTrendInsightStorage(clock=lambda: datetime(2026, 7, 29))

    with pytest.raises(ValueError, match="timezone-aware"):
        storage.save([], tmp_path / "invalid-time.json")
