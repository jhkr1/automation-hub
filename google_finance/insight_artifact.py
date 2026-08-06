"""Profile-scoped, atomic JSON storage for Google Finance insights."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from google_finance.models import StockInsight
from google_finance.movement import MovementResult
from google_finance.movement_application import MovementUnavailable
from google_finance.watchlist_application import (
    WatchlistAnalysisResult,
    WatchlistAnalysisStatus,
)
from llm_runtime.models import KeyProfile

SCHEMA_VERSION = 1
DEFAULT_ARTIFACT_ROOT = Path(__file__).resolve().parents[1] / "output"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _decimal(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None


def _snapshot_change_percent(movement: MovementResult) -> Decimal | None:
    if movement.previous_price == 0:
        return None
    return movement.price_delta / movement.previous_price * Decimal("100")


def _movement_fields(movement: MovementResult) -> dict[str, str | None]:
    return {
        "snapshot_movement": movement.direction.value,
        "snapshot_delta": _decimal(movement.price_delta),
        "snapshot_change_percent": _decimal(_snapshot_change_percent(movement)),
    }


@dataclass(frozen=True)
class GoogleFinanceInsightArtifactItem:
    """JSON-safe representation of one Watchlist analysis result."""

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
    analyzed_at: str


@dataclass(frozen=True)
class GoogleFinanceInsightArtifact:
    """Validated top-level artifact payload."""

    generated_at: str
    profile: str
    model: str
    items: tuple[GoogleFinanceInsightArtifactItem, ...]
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError("unsupported Google Finance artifact schema")
        if self.profile not in {profile.value for profile in KeyProfile}:
            raise ValueError("invalid artifact profile")
        if not self.model.strip():
            raise ValueError("artifact model must not be empty")
        if not self.items:
            raise ValueError("artifact items must not be empty")

    def to_payload(self) -> dict[str, object]:
        """Return the explicit JSON payload without domain or ORM objects."""
        return {
            "schema_version": self.schema_version,
            "generated_at": self.generated_at,
            "profile": self.profile,
            "model": self.model,
            "items": [asdict(item) for item in self.items],
        }


def _item_from_result(
    result: WatchlistAnalysisResult,
    analyzed_at: str,
) -> GoogleFinanceInsightArtifactItem:
    """Convert every CLI result state into one safe artifact row."""
    if result.status is WatchlistAnalysisStatus.SUCCESS:
        assert isinstance(result.analysis, StockInsight)
        movement_fields = _movement_fields(result.analysis.movement)
        return GoogleFinanceInsightArtifactItem(
            symbol=result.symbol,
            company_name=result.analysis.company_name,
            status=result.status.value,
            summary=result.analysis.summary,
            price=_decimal(result.analysis.current_price),
            currency=result.analysis.currency,
            **movement_fields,
            google_finance_change_percent=_decimal(result.analysis.change_percent),
            news_count=len(result.analysis.news),
            analyzed_at=result.analysis.generated_at.isoformat(),
        )

    movement = result.movement
    movement_fields = _movement_fields(movement) if movement is not None else {
        "snapshot_movement": None,
        "snapshot_delta": None,
        "snapshot_change_percent": None,
    }
    company_name = None
    if isinstance(result.analysis, MovementUnavailable):
        company_name = None
    return GoogleFinanceInsightArtifactItem(
        symbol=result.symbol,
        company_name=company_name,
        status=result.status.value,
        summary=None,
        price=_decimal(movement.latest_price) if movement is not None else None,
        currency=None,
        **movement_fields,
        google_finance_change_percent=None,
        news_count=result.news_count,
        analyzed_at=analyzed_at,
    )


def build_insight_artifact(
    results: list[WatchlistAnalysisResult],
    *,
    profile: KeyProfile,
    model: str,
    clock: Callable[[], datetime] = _utc_now,
) -> GoogleFinanceInsightArtifact:
    """Build a validated artifact while preserving Watchlist result order."""
    generated_at = clock()
    if generated_at.tzinfo is None or generated_at.utcoffset() is None:
        raise ValueError("artifact generated_at must be timezone-aware")
    timestamp = generated_at.astimezone(timezone.utc).isoformat()
    return GoogleFinanceInsightArtifact(
        generated_at=timestamp,
        profile=KeyProfile(profile).value,
        model=model,
        items=tuple(_item_from_result(result, timestamp) for result in results),
    )


def artifact_path(
    profile: KeyProfile,
    *,
    root: Path = DEFAULT_ARTIFACT_ROOT,
) -> Path:
    """Return the explicit production or test artifact path."""
    selected = KeyProfile(profile)
    filename = (
        "google_finance_insights.json"
        if selected is KeyProfile.PRODUCTION
        else "test/google_finance_insights.json"
    )
    return root / filename


class JsonGoogleFinanceInsightStorage:
    """Persist one Google Finance artifact with an atomic replace."""

    def save(
        self,
        artifact: GoogleFinanceInsightArtifact,
        path: str | Path,
    ) -> Path:
        """Write a validated artifact and preserve the old file on failure."""
        if not isinstance(artifact, GoogleFinanceInsightArtifact):
            raise TypeError("artifact must be GoogleFinanceInsightArtifact")
        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        try:
            descriptor, temporary_name = tempfile.mkstemp(
                dir=output_path.parent,
                prefix=f".{output_path.name}.",
                suffix=".tmp",
            )
            temporary_path = Path(temporary_name)
            os.chmod(temporary_path, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as output_file:
                json.dump(artifact.to_payload(), output_file, ensure_ascii=False, indent=2)
                output_file.write("\n")
                output_file.flush()
                os.fsync(output_file.fileno())
            os.replace(temporary_path, output_path)
        except (OSError, TypeError, ValueError) as exc:
            raise OSError("unable to write Google Finance insight artifact") from exc
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
        return output_path
