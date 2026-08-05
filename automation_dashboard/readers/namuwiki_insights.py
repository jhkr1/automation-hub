"""Read and classify the persisted Namuwiki insight artifact."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any

from automation_dashboard.config import PROJECT_ROOT
from automation_dashboard.queries.google_finance import SEOUL_TZ

DEFAULT_INSIGHT_PATH = PROJECT_ROOT / "output" / "trend_insights.json"
INSIGHT_SCHEMA_VERSION = 1
INSIGHT_STALE_AFTER = timedelta(hours=24)


class InsightStatus(StrEnum):
    """Text status used by read-only insight views."""

    HEALTHY = "Healthy"
    STALE = "Stale"
    NO_DATA = "No Data"
    UNAVAILABLE = "Unavailable"
    INVALID_ARTIFACT = "Invalid Artifact"
    PLANNED = "Planned"


@dataclass(frozen=True)
class NamuwikiInsightRow:
    """One dashboard row detached from the stored JSON structure."""

    rank: int
    keyword: str
    reason: str
    generated_at_kst: datetime
    article_count: int
    status: InsightStatus


@dataclass(frozen=True)
class NamuwikiInsightReadModel:
    """Read-only artifact result with safe status and metadata."""

    status: InsightStatus
    path: Path
    generated_at_kst: datetime | None
    modified_at_kst: datetime | None
    age: timedelta | None
    rows: tuple[NamuwikiInsightRow, ...]
    message: str | None = None


def read_namuwiki_insights(
    path: Path = DEFAULT_INSIGHT_PATH,
    *,
    now: datetime | None = None,
    stale_after: timedelta = INSIGHT_STALE_AFTER,
) -> NamuwikiInsightReadModel:
    """Read an insight artifact without modifying it or calling an LLM."""
    if not path.is_file():
        return _empty_result(path, InsightStatus.NO_DATA, "저장된 LLM Insight artifact가 없습니다.")

    try:
        modified_at = _to_kst(datetime.fromtimestamp(path.stat().st_mtime, timezone.utc))
        payload = json.loads(path.read_text(encoding="utf-8"))
        generated_at = _parse_generated_at(payload)
        rows = _parse_rows(payload, generated_at)
    except (OSError, json.JSONDecodeError, TypeError, ValueError, KeyError):
        return _empty_result(
            path,
            InsightStatus.INVALID_ARTIFACT,
            "LLM Insight artifact 형식을 확인할 수 없습니다.",
        )

    current = _aware_datetime(now or datetime.now(timezone.utc))
    age = current - generated_at
    status = InsightStatus.HEALTHY if age <= stale_after else InsightStatus.STALE
    status_rows = tuple(
        NamuwikiInsightRow(
            rank=row.rank,
            keyword=row.keyword,
            reason=row.reason,
            generated_at_kst=row.generated_at_kst,
            article_count=row.article_count,
            status=status,
        )
        for row in rows
    )
    return NamuwikiInsightReadModel(
        status=status,
        path=path,
        generated_at_kst=generated_at,
        modified_at_kst=modified_at,
        age=age,
        rows=status_rows,
    )


def _parse_generated_at(payload: Any) -> datetime:
    if not isinstance(payload, dict) or payload.get("schema_version") != INSIGHT_SCHEMA_VERSION:
        raise ValueError("unsupported insight schema")
    value = payload["generated_at"]
    if not isinstance(value, str):
        raise TypeError("generated_at must be text")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("generated_at must be timezone-aware")
    return _to_kst(parsed)


def _parse_rows(payload: dict[str, Any], generated_at: datetime) -> tuple[NamuwikiInsightRow, ...]:
    insights = payload["insights"]
    if not isinstance(insights, list):
        raise TypeError("insights must be a list")
    rows: list[NamuwikiInsightRow] = []
    for item in insights:
        if not isinstance(item, dict):
            raise TypeError("insight must be an object")
        trend = item["trend"]
        articles = item["articles"]
        if not isinstance(trend, dict) or not isinstance(articles, list):
            raise TypeError("invalid insight fields")
        rank = trend["rank"]
        keyword = trend["keyword"]
        reason = item["reason"]
        if isinstance(rank, bool) or not isinstance(rank, int):
            raise TypeError("rank must be an integer")
        if not isinstance(keyword, str) or not keyword.strip():
            raise ValueError("keyword must not be empty")
        if not isinstance(reason, str):
            raise TypeError("reason must be text")
        rows.append(
            NamuwikiInsightRow(
                rank=rank,
                keyword=keyword,
                reason=reason,
                generated_at_kst=generated_at,
                article_count=len(articles),
                status=InsightStatus.HEALTHY,
            )
        )
    return tuple(rows)


def _empty_result(path: Path, status: InsightStatus, message: str) -> NamuwikiInsightReadModel:
    return NamuwikiInsightReadModel(
        status=status,
        path=path,
        generated_at_kst=None,
        modified_at_kst=None,
        age=None,
        rows=(),
        message=message,
    )


def _aware_datetime(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _to_kst(value: datetime) -> datetime:
    return _aware_datetime(value).astimezone(SEOUL_TZ)
