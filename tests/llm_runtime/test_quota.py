import json
import multiprocessing
import stat
from datetime import datetime, timedelta, timezone

import pytest

import llm_runtime.quota as quota_module
from llm_runtime.exceptions import LlmBudgetExceededError, LlmLedgerError
from llm_runtime.models import LlmJob, LlmQuotaBudget
from llm_runtime.quota import LocalFileQuotaLedger, to_pacific_date

UTC = timezone.utc


def budget(daily=20, rpm=20, tpm=1_000) -> LlmQuotaBudget:
    return LlmQuotaBudget(daily, rpm, tpm)


def reserve(
    ledger,
    when=datetime(2026, 1, 2, 12, tzinfo=UTC),
    job=LlmJob.NAMUWIKI,
    estimated_tokens=1,
    quota_budget=None,
    project_profile="production",
    provider="gemini",
    model="model",
    **kwargs,
):
    return ledger.reserve(
        project_profile=project_profile,
        provider=provider,
        model=model,
        job=job,
        estimated_tokens=estimated_tokens,
        budget=quota_budget or budget(),
        now=when,
        **kwargs,
    )


def row_at(when, *, job="namuwiki", tokens=1, **extra):
    row = {
        "reservation_id": "existing",
        "timestamp_utc": when.astimezone(UTC).isoformat(),
        "pacific_date": to_pacific_date(when).isoformat(),
        "project_profile": "production",
        "provider": "gemini",
        "model": "model",
        "job": job,
        "estimated_tokens": tokens,
        "retry": False,
    }
    row.update(extra)
    return row


def write_payload(path, reservations):
    path.write_text(json.dumps({"version": 1, "reservations": reservations}))


def concurrent_reserve_worker(path, start, results):
    start.wait(10)
    try:
        reserve(
            LocalFileQuotaLedger(path),
            quota_budget=budget(daily=2, rpm=20, tpm=100),
        )
    except LlmBudgetExceededError:
        results.put("blocked")
    except Exception as exc:  # pragma: no cover - diagnostic for child failures
        results.put(f"error:{type(exc).__name__}")
    else:
        results.put("success")


def test_reserve_writes_safe_json(tmp_path):
    path = tmp_path / "q.json"
    reserve(LocalFileQuotaLedger(path))
    data = json.loads(path.read_text())
    assert data["version"] == 1 and "api_key" not in str(data)


def test_ledger_and_lock_permissions_are_private(tmp_path):
    path = tmp_path / "q.json"
    reserve(LocalFileQuotaLedger(path))
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.with_suffix(".lock").stat().st_mode) == 0o600


def test_daily_and_jobs_share(tmp_path):
    ledger = LocalFileQuotaLedger(tmp_path / "q")
    limited = budget(daily=2)
    reserve(ledger, quota_budget=limited)
    reserve(ledger, job=LlmJob.GOOGLE_FINANCE, quota_budget=limited)
    with pytest.raises(LlmBudgetExceededError, match="daily_requests"):
        reserve(ledger, quota_budget=limited)


def test_identity_and_pacific_date(tmp_path):
    ledger = LocalFileQuotaLedger(tmp_path / "q")
    reserve(ledger)
    reserve(ledger, quota_budget=budget(daily=1), project_profile="test")
    assert to_pacific_date(datetime(2026, 1, 2, tzinfo=UTC)).isoformat() == "2026-01-01"


def test_rpm_allows_limit_then_blocks(tmp_path):
    ledger = LocalFileQuotaLedger(tmp_path / "q")
    limited = budget(rpm=3)
    for offset in (3, 2, 1):
        reserve(
            ledger,
            when=datetime(2026, 1, 2, 12, tzinfo=UTC) - timedelta(seconds=offset),
            quota_budget=limited,
        )
    with pytest.raises(LlmBudgetExceededError, match="requests_per_minute"):
        reserve(ledger, quota_budget=limited)


@pytest.mark.parametrize(
    "age",
    [timedelta(seconds=60), timedelta(seconds=59, microseconds=999_999)],
)
def test_rpm_window_boundary(age, tmp_path):
    ledger = LocalFileQuotaLedger(tmp_path / "q")
    now = datetime(2026, 1, 2, 12, tzinfo=UTC)
    reserve(ledger, when=now - age, quota_budget=budget(rpm=1))
    if age == timedelta(seconds=60):
        reserve(ledger, when=now, quota_budget=budget(rpm=1))
    else:
        with pytest.raises(LlmBudgetExceededError, match="requests_per_minute"):
            reserve(ledger, when=now, quota_budget=budget(rpm=1))


def test_rpm_is_shared_by_jobs_but_not_identity(tmp_path):
    ledger = LocalFileQuotaLedger(tmp_path / "q")
    limited = budget(rpm=1)
    reserve(ledger, quota_budget=limited)
    with pytest.raises(LlmBudgetExceededError):
        reserve(ledger, job=LlmJob.GOOGLE_FINANCE, quota_budget=limited)
    reserve(ledger, quota_budget=budget(rpm=1), project_profile="test")


def test_tpm_allows_exact_sum_then_blocks(tmp_path):
    ledger = LocalFileQuotaLedger(tmp_path / "q")
    limited = budget(tpm=10)
    reserve(ledger, estimated_tokens=6, quota_budget=limited)
    reserve(ledger, estimated_tokens=4, quota_budget=limited)
    with pytest.raises(LlmBudgetExceededError, match="tokens_per_minute"):
        reserve(ledger, estimated_tokens=1, quota_budget=limited)


def test_tpm_ignores_old_reservations(tmp_path):
    ledger = LocalFileQuotaLedger(tmp_path / "q")
    now = datetime(2026, 1, 2, 12, tzinfo=UTC)
    reserve(ledger, when=now - timedelta(seconds=60), estimated_tokens=10)
    reserve(ledger, when=now, estimated_tokens=10, quota_budget=budget(tpm=10))


def test_tpm_includes_retry_reservations(tmp_path):
    ledger = LocalFileQuotaLedger(tmp_path / "q")
    limited = budget(tpm=10)
    reserve(ledger, estimated_tokens=10, retry=True, quota_budget=limited)
    with pytest.raises(LlmBudgetExceededError, match="tokens_per_minute"):
        reserve(ledger, estimated_tokens=1, quota_budget=limited)


def test_retention_keeps_seven_pacific_dates_and_saves_on_success(tmp_path):
    path = tmp_path / "q"
    now = datetime(2026, 8, 7, 12, tzinfo=UTC)
    write_payload(
        path,
        [
            row_at(now - timedelta(days=7)),
            row_at(now - timedelta(days=6)),
        ],
    )
    reserve(LocalFileQuotaLedger(path), when=now)
    rows = json.loads(path.read_text())["reservations"]
    assert [row["pacific_date"] for row in rows] == ["2026-08-01", "2026-08-07"]


def test_retention_uses_pacific_calendar_date(tmp_path):
    path = tmp_path / "q"
    now = datetime(2026, 8, 7, 6, tzinfo=UTC)
    write_payload(path, [row_at(datetime(2026, 8, 1, 6, tzinfo=UTC))])
    reserve(LocalFileQuotaLedger(path), when=now)
    rows = json.loads(path.read_text())["reservations"]
    assert len(rows) == 2


def test_budget_rejection_preserves_original_file(tmp_path):
    path = tmp_path / "q"
    now = datetime(2026, 8, 7, 12, tzinfo=UTC)
    write_payload(path, [row_at(now - timedelta(days=7)), row_at(now)])
    before = path.read_bytes()
    with pytest.raises(LlmBudgetExceededError):
        reserve(LocalFileQuotaLedger(path), when=now, quota_budget=budget(daily=1))
    assert path.read_bytes() == before


@pytest.mark.parametrize(
    "mutate",
    [
        lambda row: row.pop("model"),
        lambda row: row.update(reservation_id=""),
        lambda row: row.update(timestamp_utc="not-a-timestamp"),
        lambda row: row.update(timestamp_utc="2026-01-02T12:00:00"),
        lambda row: row.update(pacific_date="not-a-date"),
        lambda row: row.update(pacific_date="2026-01-01"),
        lambda row: row.update(job="unknown"),
        lambda row: row.update(estimated_tokens="1"),
        lambda row: row.update(estimated_tokens=0),
        lambda row: row.update(estimated_tokens=True),
        lambda row: row.update(retry="false"),
    ],
)
def test_corrupt_reservation_is_rejected_and_preserved(tmp_path, mutate):
    path = tmp_path / "q"
    row = row_at(datetime(2026, 1, 2, 12, tzinfo=UTC))
    mutate(row)
    write_payload(path, [row])
    before = path.read_bytes()
    with pytest.raises(LlmLedgerError):
        reserve(LocalFileQuotaLedger(path))
    assert path.read_bytes() == before


@pytest.mark.parametrize("payload", [[], {"version": 1, "reservations": "bad"}])
def test_corrupt_ledger_root_is_rejected(tmp_path, payload):
    path = tmp_path / "q"
    path.write_text(json.dumps(payload))
    with pytest.raises(LlmLedgerError):
        reserve(LocalFileQuotaLedger(path))


def test_unknown_reservation_fields_are_allowed(tmp_path):
    path = tmp_path / "q"
    row = row_at(datetime(2026, 1, 2, 12, tzinfo=UTC), future_field="kept")
    write_payload(path, [row])
    reserve(LocalFileQuotaLedger(path))
    rows = json.loads(path.read_text())["reservations"]
    assert rows[0]["future_field"] == "kept"


def test_naive_datetime_input_is_invalid(tmp_path):
    with pytest.raises(ValueError):
        reserve(
            LocalFileQuotaLedger(tmp_path / "q"),
            when=datetime(2026, 1, 2),
        )


def test_invalid_retry_input_is_rejected(tmp_path):
    with pytest.raises(TypeError):
        reserve(LocalFileQuotaLedger(tmp_path / "q"), retry="false")


def test_invalid_budget_is_rejected(tmp_path):
    with pytest.raises(ValueError):
        LocalFileQuotaLedger(tmp_path / "q", retention_days=0)


def test_atomic_replace_failure_preserves_ledger_and_cleans_temp(
    tmp_path, monkeypatch
):
    path = tmp_path / "q"
    ledger = LocalFileQuotaLedger(path)
    reserve(ledger)
    before = path.read_bytes()

    def fail_replace(source, destination):
        raise OSError("injected replace failure")

    monkeypatch.setattr(quota_module.os, "replace", fail_replace)
    with pytest.raises(LlmLedgerError, match="unable to write"):
        reserve(ledger)
    assert path.read_bytes() == before
    assert list(tmp_path.glob(f".{path.name}.*")) == []

    monkeypatch.undo()
    reserve(ledger)


def test_budget_error_releases_lock(tmp_path):
    path = tmp_path / "q"
    ledger = LocalFileQuotaLedger(path)
    now = datetime(2026, 1, 2, 12, tzinfo=UTC)
    limited = budget(daily=2, rpm=1, tpm=100)
    reserve(ledger, when=now, quota_budget=limited)
    with pytest.raises(LlmBudgetExceededError):
        reserve(ledger, when=now, quota_budget=limited)
    reserve(ledger, when=now + timedelta(seconds=60), quota_budget=limited)


def test_corruption_error_releases_lock(tmp_path):
    path = tmp_path / "q"
    path.write_text("{")
    ledger = LocalFileQuotaLedger(path)
    with pytest.raises(LlmLedgerError):
        reserve(ledger)
    write_payload(path, [])
    reserve(ledger)


def test_concurrent_reservations_are_serialized(tmp_path):
    context = multiprocessing.get_context("fork")
    path = tmp_path / "q"
    start = context.Event()
    results = context.Queue()
    processes = [
        context.Process(
            target=concurrent_reserve_worker,
            args=(path, start, results),
        )
        for _ in range(4)
    ]
    for process in processes:
        process.start()
    start.set()
    outcomes = [results.get(timeout=10) for _ in processes]
    for process in processes:
        process.join(timeout=10)
        if process.is_alive():
            process.terminate()
            process.join(timeout=5)
        assert process.exitcode == 0
    results.close()
    results.join_thread()

    assert sorted(outcomes) == ["blocked", "blocked", "success", "success"]
    payload = json.loads(path.read_text())
    reservations = payload["reservations"]
    assert len(reservations) == 2
    assert len({row["reservation_id"] for row in reservations}) == 2
