"""Read-only summaries of the local LLM quota ledger."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from automation_dashboard.config import PROJECT_ROOT
from automation_dashboard.queries.google_finance import SEOUL_TZ
from automation_dashboard.readers.namuwiki_insights import InsightStatus

DEFAULT_QUOTA_LEDGER_PATH = PROJECT_ROOT / ".state" / "llm" / "quota-ledger.json"
PACIFIC = ZoneInfo("America/Los_Angeles")


@dataclass(frozen=True)
class LlmProfileUsage:
    """Request totals for one non-secret project profile label."""

    project_profile: str
    requests_today: int


@dataclass(frozen=True)
class LlmUsageReadModel:
    """Safe ledger metadata for the Operations Dashboard."""

    status: InsightStatus
    path: Path
    profiles: tuple[LlmProfileUsage, ...]
    retry_count: int
    last_request_at_kst: datetime | None
    message: str | None = None


def read_llm_usage(
    path: Path = DEFAULT_QUOTA_LEDGER_PATH,
    *,
    now: datetime | None = None,
) -> LlmUsageReadModel:
    """Read counts and timestamps without exposing keys, prompts, or responses."""
    if not path.is_file():
        return _empty(path, InsightStatus.NO_DATA, "LLM quota ledger가 없습니다.")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        rows = payload["reservations"]
        if payload.get("version") != 1 or not isinstance(rows, list):
            raise ValueError("invalid ledger")
        current = _to_utc(now or datetime.now(timezone.utc))
        pacific_date = current.astimezone(PACIFIC).date()
        profiles: dict[str, int] = {}
        retries = 0
        timestamps: list[datetime] = []
        for row in rows:
            if not isinstance(row, dict):
                raise TypeError("invalid reservation")
            profile = row["project_profile"]
            timestamp = datetime.fromisoformat(row["timestamp_utc"])
            if not isinstance(profile, str) or not profile.strip():
                raise TypeError("invalid project profile")
            timestamp = _to_utc(timestamp)
            if row["pacific_date"] == pacific_date.isoformat():
                profiles[profile] = profiles.get(profile, 0) + 1
            if row["retry"] is True and row["pacific_date"] == pacific_date.isoformat():
                retries += 1
            timestamps.append(timestamp)
    except (OSError, json.JSONDecodeError, TypeError, ValueError, KeyError):
        return _empty(path, InsightStatus.UNAVAILABLE, "LLM quota ledger를 확인할 수 없습니다.")

    if not rows:
        return _empty(path, InsightStatus.NO_DATA, "오늘 LLM 요청 기록이 없습니다.")
    return LlmUsageReadModel(
        status=InsightStatus.HEALTHY,
        path=path,
        profiles=tuple(
            LlmProfileUsage(profile, count)
            for profile, count in sorted(profiles.items())
        ),
        retry_count=retries,
        last_request_at_kst=max(timestamps).astimezone(SEOUL_TZ),
    )


def _empty(path: Path, status: InsightStatus, message: str) -> LlmUsageReadModel:
    return LlmUsageReadModel(status, path, (), 0, None, message)


def _to_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
