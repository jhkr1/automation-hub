"""TrendInsight 목록을 버전이 있는 JSON 파일로 저장하는 Storage Layer."""

import json
import os
import tempfile
from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from pathlib import Path

from namuwiki_trend.models import NewsArticle, TrendInsight, TrendItem

SCHEMA_VERSION = 1
JsonClock = Callable[[], datetime]


def _utc_now() -> datetime:
    """현재 UTC timezone-aware 시각을 반환한다."""
    return datetime.now(timezone.utc)


def _serialize_datetime(value: datetime | None) -> str | None:
    """datetime을 ISO 8601 문자열로 변환한다."""
    return value.isoformat() if value is not None else None


def _serialize_trend(trend: TrendItem) -> dict[str, object]:
    """TrendItem의 외부 저장 필드를 명시적으로 매핑한다."""
    if not isinstance(trend, TrendItem):
        raise TypeError(f"trend가 TrendItem이 아님: {type(trend).__name__}")
    return {
        "rank": trend.rank,
        "keyword": trend.keyword,
        "href": trend.href,
    }


def _serialize_article(article: NewsArticle) -> dict[str, object]:
    """NewsArticle의 외부 저장 필드를 명시적으로 매핑한다."""
    if not isinstance(article, NewsArticle):
        raise TypeError(f"article이 NewsArticle이 아님: {type(article).__name__}")
    return {
        "title": article.title,
        "url": article.url,
        "source": article.source,
        "published_at": _serialize_datetime(article.published_at),
    }


def _serialize_insight(insight: TrendInsight) -> dict[str, object]:
    """TrendInsight를 JSON 저장 계약의 단일 객체로 변환한다."""
    if not isinstance(insight, TrendInsight):
        raise TypeError(f"insight가 TrendInsight가 아님: {type(insight).__name__}")
    if not isinstance(insight.reason, str):
        raise TypeError(f"reason이 문자열이 아님: {type(insight.reason).__name__}")
    return {
        "trend": _serialize_trend(insight.trend),
        "reason": insight.reason,
        "articles": [_serialize_article(article) for article in insight.articles],
    }


class JsonTrendInsightStorage:
    """TrendInsight 목록을 UTF-8 JSON으로 원자적으로 저장한다."""

    def __init__(self, clock: JsonClock = _utc_now) -> None:
        self._clock = clock

    def save(
        self,
        insights: Sequence[TrendInsight],
        path: str | Path,
    ) -> Path:
        """Insight 목록을 저장하고 실제 저장 경로를 반환한다."""
        if not isinstance(insights, Sequence) or isinstance(insights, (str, bytes)):
            raise TypeError(f"insights가 TrendInsight Sequence가 아님: {type(insights).__name__}")
        output_path = Path(path)
        generated_at = self._clock()
        if generated_at.tzinfo is None or generated_at.utcoffset() is None:
            raise ValueError("generated_at은 timezone-aware datetime이어야 함")

        payload = {
            "schema_version": SCHEMA_VERSION,
            "generated_at": generated_at.isoformat(),
            "insights": [_serialize_insight(insight) for insight in insights],
        }

        output_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        try:
            file_descriptor, temporary_name = tempfile.mkstemp(
                dir=output_path.parent,
                prefix=f".{output_path.name}.",
                suffix=".tmp",
            )
            temporary_path = Path(temporary_name)
            with os.fdopen(file_descriptor, "w", encoding="utf-8") as output_file:
                json.dump(payload, output_file, ensure_ascii=False, indent=2)
                output_file.write("\n")
                output_file.flush()
                os.fsync(output_file.fileno())
            temporary_path.replace(output_path)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

        return output_path
