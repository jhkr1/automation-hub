"""Read and classify the persisted Google Finance insight artifact."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from automation_dashboard.config import PROJECT_ROOT
from automation_dashboard.queries.google_finance import SEOUL_TZ
from automation_dashboard.readers.namuwiki_insights import InsightStatus

DEFAULT_GOOGLE_FINANCE_INSIGHT_PATH = PROJECT_ROOT / "output" / "google_finance_insights.json"
INSIGHT_SCHEMA_VERSION = 1
INSIGHT_STALE_AFTER = timedelta(hours=24)
ALLOWED_ITEM_STATUSES = {"SUCCESS", "MOVEMENT_UNAVAILABLE", "ANALYSIS_UNAVAILABLE", "FAILED"}


@dataclass(frozen=True)
class GoogleFinanceInsightRow:
    """One detached Google Finance artifact item."""

    symbol: str
    company_name: str | None
    status: str
    summary: str | None
    price: str | None
    currency: str | None
    snapshot_movement: str | None
    snapshot_delta: str | None
    snapshot_change_percent: str | None
    google_finance_change_percent: str | None
    news_count: int | None
    analyzed_at_kst: datetime


@dataclass(frozen=True)
class GoogleFinanceInsightReadModel:
    """Read-only artifact result with safe status and detached rows."""

    status: InsightStatus
    path: Path
    profile: str | None
    model: str | None
    generated_at_kst: datetime | None
    modified_at_kst: datetime | None
    age: timedelta | None
    rows: tuple[GoogleFinanceInsightRow, ...]
    message: str | None = None

    def row_for_symbol(self, symbol: str) -> GoogleFinanceInsightRow | None:
        """Return only an exact canonical-symbol match."""
        return next((row for row in self.rows if row.symbol == symbol), None)


def read_google_finance_insights(
    path: Path = DEFAULT_GOOGLE_FINANCE_INSIGHT_PATH,
    *,
    now: datetime | None = None,
    stale_after: timedelta = INSIGHT_STALE_AFTER,
) -> GoogleFinanceInsightReadModel:
    """Read a strict artifact without modifying it or calling an LLM."""
    if not path.is_file():
        return _empty_result(
            path,
            InsightStatus.NO_DATA,
            "저장된 Google Finance Insight가 없습니다.",
        )

    try:
        modified_at = _to_kst(datetime.fromtimestamp(path.stat().st_mtime, timezone.utc))
        payload = json.loads(path.read_text(encoding="utf-8"))
        generated_at = _parse_generated_at(payload)
        profile, model, rows = _parse_payload(payload, generated_at)
    except (OSError, json.JSONDecodeError, TypeError, ValueError, KeyError):
        return _empty_result(
            path,
            InsightStatus.INVALID_ARTIFACT,
            "Google Finance Insight artifact 형식을 확인할 수 없습니다.",
        )

    current = _aware_datetime(now or datetime.now(timezone.utc))
    age = current - generated_at
    status = InsightStatus.HEALTHY if age <= stale_after else InsightStatus.STALE
    return GoogleFinanceInsightReadModel(
        status=status,
        path=path,
        profile=profile,
        model=model,
        generated_at_kst=generated_at,
        modified_at_kst=modified_at,
        age=age,
        rows=rows,
    )


def _parse_payload(
    payload: Any,
    generated_at: datetime,
) -> tuple[str, str, tuple[GoogleFinanceInsightRow, ...]]:
    if not isinstance(payload, dict) or payload.get("schema_version") != INSIGHT_SCHEMA_VERSION:
        raise ValueError("unsupported Google Finance artifact schema")
    profile = payload["profile"]
    model = payload["model"]
    items = payload["items"]
    if (
        not isinstance(profile, str)
        or profile not in {"production", "test"}
        or not isinstance(model, str)
        or not model.strip()
        or not isinstance(items, list)
        or not items
    ):
        raise TypeError("invalid Google Finance artifact metadata")

    rows: list[GoogleFinanceInsightRow] = []
    symbols: set[str] = set()
    for item in items:
        row = _parse_item(item, generated_at)
        if row.symbol in symbols:
            raise ValueError("duplicate Google Finance artifact symbol")
        symbols.add(row.symbol)
        rows.append(row)
    return profile, model, tuple(rows)


def _parse_item(item: Any, generated_at: datetime) -> GoogleFinanceInsightRow:
    if not isinstance(item, dict):
        raise TypeError("artifact item must be an object")
    required = {
        "symbol",
        "company_name",
        "status",
        "summary",
        "price",
        "currency",
        "snapshot_movement",
        "snapshot_delta",
        "snapshot_change_percent",
        "google_finance_change_percent",
        "news_count",
        "analyzed_at",
    }
    if set(item) != required:
        raise ValueError("invalid Google Finance artifact item fields")
    symbol = item["symbol"]
    status = item["status"]
    if not isinstance(symbol, str) or not symbol.strip() or symbol != symbol.strip():
        raise ValueError("invalid artifact symbol")
    if not isinstance(status, str) or status not in ALLOWED_ITEM_STATUSES:
        raise ValueError("invalid artifact item status")
    for field in (
        "company_name",
        "summary",
        "price",
        "currency",
        "snapshot_movement",
        "snapshot_delta",
        "snapshot_change_percent",
        "google_finance_change_percent",
    ):
        if item[field] is not None and not isinstance(item[field], str):
            raise TypeError(f"{field} must be text or null")
    news_count = item["news_count"]
    if news_count is not None and (
        isinstance(news_count, bool) or not isinstance(news_count, int) or news_count < 0
    ):
        raise ValueError("invalid artifact news_count")
    analyzed_at = _parse_timestamp(item["analyzed_at"])
    return GoogleFinanceInsightRow(
        symbol=symbol,
        company_name=item["company_name"],
        status=status,
        summary=item["summary"],
        price=item["price"],
        currency=item["currency"],
        snapshot_movement=item["snapshot_movement"],
        snapshot_delta=item["snapshot_delta"],
        snapshot_change_percent=item["snapshot_change_percent"],
        google_finance_change_percent=item["google_finance_change_percent"],
        news_count=news_count,
        analyzed_at_kst=_to_kst(analyzed_at),
    )


def _parse_generated_at(payload: Any) -> datetime:
    if not isinstance(payload, dict):
        raise TypeError("artifact root must be an object")
    return _to_kst(_parse_timestamp(payload["generated_at"]))


def _parse_timestamp(value: Any) -> datetime:
    if not isinstance(value, str):
        raise TypeError("artifact timestamp must be text")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("artifact timestamp must be timezone-aware")
    return parsed


def _empty_result(path: Path, status: InsightStatus, message: str) -> GoogleFinanceInsightReadModel:
    return GoogleFinanceInsightReadModel(
        status=status,
        path=path,
        profile=None,
        model=None,
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
