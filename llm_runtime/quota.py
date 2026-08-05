"""Local JSON quota reservations for the LLM runtime."""

from __future__ import annotations

import fcntl
import json
import os
import tempfile
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import cast
from zoneinfo import ZoneInfo

from llm_runtime.exceptions import (
    InvalidLlmConfigurationError,
    LlmBudgetExceededError,
    LlmLedgerError,
)
from llm_runtime.models import LlmJob, LlmQuotaBudget, LlmQuotaReservation

PACIFIC = ZoneInfo("America/Los_Angeles")
RETENTION_DAYS = 7
WINDOW_SECONDS = 60


def to_pacific_date(now: datetime) -> date:
    """Return the Pacific calendar date for an aware datetime."""
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    return now.astimezone(PACIFIC).date()


class LocalFileQuotaLedger:
    """Reserve request and token budget in a local JSON ledger."""

    def __init__(self, path: Path, retention_days: int = RETENTION_DAYS) -> None:
        if type(retention_days) is not int or retention_days <= 0:
            raise InvalidLlmConfigurationError(
                "retention_days must be a positive integer"
            )
        self._path = path
        self._lock_path = path.with_suffix(".lock")
        self._retention_days = retention_days

    def reserve(
        self,
        *,
        project_profile: str,
        provider: str,
        model: str,
        job: LlmJob,
        estimated_tokens: int,
        budget: LlmQuotaBudget,
        retry: bool = False,
        now: datetime | None = None,
    ) -> LlmQuotaReservation:
        """Reserve one request if all configured budgets have capacity."""
        self._validate_request(
            project_profile,
            provider,
            model,
            job,
            estimated_tokens,
            retry,
        )
        self._validate_budget(budget)
        current = now or datetime.now(timezone.utc)
        day = to_pacific_date(current)
        with self._exclusive_lock():
            rows = self._load()
            retained = self._retain(rows, day)
            identity_rows = self._identity_rows(
                retained, project_profile, provider, model
            )
            if (
                sum(row["pacific_date"] == day.isoformat() for row in identity_rows)
                >= budget.daily_requests
            ):
                raise LlmBudgetExceededError("daily_requests budget exceeded")

            cutoff = current.astimezone(timezone.utc) - timedelta(
                seconds=WINDOW_SECONDS
            )
            recent = [
                row for row in identity_rows if self._timestamp(row) > cutoff
            ]
            if len(recent) + 1 > budget.requests_per_minute:
                raise LlmBudgetExceededError("requests_per_minute budget exceeded")
            recent_tokens = sum(
                cast(int, row["estimated_tokens"]) for row in recent
            )
            if recent_tokens + estimated_tokens > budget.tokens_per_minute:
                raise LlmBudgetExceededError("tokens_per_minute budget exceeded")

            item = {
                "reservation_id": str(uuid.uuid4()),
                "timestamp_utc": current.astimezone(timezone.utc).isoformat(),
                "pacific_date": day.isoformat(),
                "project_profile": project_profile,
                "provider": provider,
                "model": model,
                "job": job.value,
                "estimated_tokens": estimated_tokens,
                "retry": retry,
            }
            retained.append(item)
            self._save(retained)
            return LlmQuotaReservation(
                item["reservation_id"],
                current,
                day,
                project_profile,
                provider,
                model,
                job,
                estimated_tokens,
                retry,
            )

    @contextmanager
    def _exclusive_lock(self) -> Iterator[None]:
        self._lock_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            lock_file = self._lock_path.open("a+")
            os.fchmod(lock_file.fileno(), 0o600)
        except OSError as exc:
            raise LlmLedgerError("unable to open quota ledger lock") from exc
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        except OSError as exc:
            raise LlmLedgerError("unable to lock quota ledger") from exc
        finally:
            lock_file.close()

    def _load(self) -> list[dict[str, object]]:
        if not self._path.exists():
            return []
        try:
            payload = json.loads(self._path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            raise LlmLedgerError("invalid quota ledger") from exc
        if not isinstance(payload, dict):
            raise LlmLedgerError("invalid quota ledger root")
        if payload.get("version") != 1 or not isinstance(
            payload.get("reservations"), list
        ):
            raise LlmLedgerError("invalid quota ledger")
        rows = payload["reservations"]
        for index, row in enumerate(rows):
            self._validate_reservation(row, index)
        return cast(list[dict[str, object]], rows)

    def _save(self, rows: list[dict[str, object]]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{self._path.name}.",
            dir=self._path.parent,
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as temporary:
                json.dump(
                    {"version": 1, "reservations": rows},
                    temporary,
                    ensure_ascii=False,
                    sort_keys=True,
                    indent=2,
                )
                temporary.flush()
                os.fsync(temporary.fileno())
            os.chmod(temporary_name, 0o600)
            os.replace(temporary_name, self._path)
        except (OSError, TypeError, ValueError) as exc:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass
            raise LlmLedgerError("unable to write quota ledger") from exc

    def _retain(
        self, rows: list[dict[str, object]], current_day: date
    ) -> list[dict[str, object]]:
        first_day = current_day - timedelta(days=self._retention_days - 1)
        return [
            row
            for row in rows
            if date.fromisoformat(cast(str, row["pacific_date"])) >= first_day
        ]

    @staticmethod
    def _identity_rows(
        rows: list[dict[str, object]],
        project_profile: str,
        provider: str,
        model: str,
    ) -> list[dict[str, object]]:
        return [
            row
            for row in rows
            if row["project_profile"] == project_profile
            and row["provider"] == provider
            and row["model"] == model
        ]

    @staticmethod
    def _timestamp(row: dict[str, object]) -> datetime:
        return datetime.fromisoformat(cast(str, row["timestamp_utc"])).astimezone(
            timezone.utc
        )

    @staticmethod
    def _validate_request(
        project_profile: str,
        provider: str,
        model: str,
        job: LlmJob,
        estimated_tokens: int,
        retry: bool,
    ) -> None:
        if any(
            not isinstance(value, str) or not value.strip()
            for value in (project_profile, provider, model)
        ):
            raise ValueError("quota identity must not be empty")
        if not isinstance(job, LlmJob):
            raise TypeError("job must be LlmJob")
        if type(estimated_tokens) is not int or estimated_tokens <= 0:
            raise ValueError("estimated_tokens must be a positive integer")
        if type(retry) is not bool:
            raise TypeError("retry must be bool")

    @staticmethod
    def _validate_reservation(row: object, index: int) -> None:
        if not isinstance(row, dict):
            raise LlmLedgerError(f"invalid reservation at index {index}")
        required = {
            "reservation_id",
            "timestamp_utc",
            "pacific_date",
            "project_profile",
            "provider",
            "model",
            "job",
            "estimated_tokens",
            "retry",
        }
        if not required.issubset(row):
            raise LlmLedgerError(f"invalid reservation at index {index}")
        string_fields = (
            "reservation_id",
            "timestamp_utc",
            "pacific_date",
            "project_profile",
            "provider",
            "model",
        )
        if any(
            not isinstance(row[field], str) or not row[field].strip()
            for field in string_fields
        ):
            raise LlmLedgerError(f"invalid reservation at index {index}")
        timestamp = LocalFileQuotaLedger._parse_timestamp(row["timestamp_utc"], index)
        try:
            stored_day = date.fromisoformat(cast(str, row["pacific_date"]))
        except ValueError as exc:
            raise LlmLedgerError(f"invalid pacific_date at index {index}") from exc
        if (
            stored_day.isoformat() != row["pacific_date"]
            or to_pacific_date(timestamp) != stored_day
        ):
            raise LlmLedgerError(f"pacific_date mismatch at index {index}")
        try:
            LlmJob(cast(str, row["job"]))
        except ValueError as exc:
            raise LlmLedgerError(f"invalid job at index {index}") from exc
        if type(row["estimated_tokens"]) is not int or row["estimated_tokens"] <= 0:
            raise LlmLedgerError(f"invalid estimated_tokens at index {index}")
        if type(row["retry"]) is not bool:
            raise LlmLedgerError(f"invalid retry at index {index}")

    @staticmethod
    def _parse_timestamp(value: object, index: int) -> datetime:
        try:
            timestamp = datetime.fromisoformat(cast(str, value))
        except (TypeError, ValueError) as exc:
            raise LlmLedgerError(f"invalid timestamp_utc at index {index}") from exc
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise LlmLedgerError(f"invalid timestamp_utc at index {index}")
        return timestamp

    @staticmethod
    def _validate_budget(budget: LlmQuotaBudget) -> None:
        for value in (
            budget.daily_requests,
            budget.requests_per_minute,
            budget.tokens_per_minute,
        ):
            if type(value) is not int or value <= 0:
                raise InvalidLlmConfigurationError(
                    "quota budget values must be positive integers"
                )
