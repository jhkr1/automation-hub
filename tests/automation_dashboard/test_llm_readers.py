"""Read-only contracts for Dashboard LLM artifact and ledger adapters."""

import json
from datetime import datetime, timezone

from automation_dashboard.readers.google_finance_insights import (
    read_google_finance_insights,
)
from automation_dashboard.readers.llm_usage import read_llm_usage
from automation_dashboard.readers.namuwiki_insights import (
    InsightStatus,
    read_namuwiki_insights,
)


def _artifact(generated_at: str = "2026-08-04T00:00:00+00:00") -> dict[str, object]:
    return {
        "schema_version": 1,
        "generated_at": generated_at,
        "insights": [
            {
                "trend": {"rank": 1, "keyword": "Python", "href": "https://example.test"},
                "reason": "뉴스 근거가 있는 요약",
                "articles": [{"title": "제목", "url": "https://example.test/news"}],
            }
        ],
    }


def _google_artifact(
    generated_at: str = "2026-08-04T00:00:00+00:00",
    symbols: tuple[str, ...] = ("NVDA:NASDAQ", "PLTR:NASDAQ", "005930:KRX", "000660:KRX"),
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "generated_at": generated_at,
        "profile": "production",
        "model": "gemini-3.5-flash",
        "items": [
            {
                "symbol": symbol,
                "company_name": f"Company {symbol}",
                "status": "SUCCESS",
                "summary": f"Summary for {symbol}",
                "price": "100.00",
                "currency": "USD",
                "snapshot_movement": "UNCHANGED",
                "snapshot_delta": "0.00",
                "snapshot_change_percent": "0.00",
                "google_finance_change_percent": "1.00",
                "news_count": 1,
                "analyzed_at": generated_at,
            }
            for symbol in symbols
        ],
    }


def test_namuwiki_reader_maps_artifact_and_converts_generated_time(tmp_path) -> None:
    """The reader exposes detached rows and article counts in KST."""
    path = tmp_path / "trend_insights.json"
    payload = _artifact()
    payload["api_key"] = "do-not-display"
    payload["prompt"] = "do-not-display"
    path.write_text(json.dumps(payload), encoding="utf-8")

    result = read_namuwiki_insights(
        path,
        now=datetime(2026, 8, 4, 1, 0, tzinfo=timezone.utc),
    )

    assert result.status is InsightStatus.HEALTHY
    assert result.generated_at_kst.isoformat() == "2026-08-04T09:00:00+09:00"
    assert result.rows[0].keyword == "Python"
    assert result.rows[0].article_count == 1
    assert "do-not-display" not in repr(result)


def test_namuwiki_reader_marks_old_artifact_stale(tmp_path) -> None:
    """An artifact older than the 24-hour policy is never shown as healthy."""
    path = tmp_path / "trend_insights.json"
    path.write_text(json.dumps(_artifact()), encoding="utf-8")

    result = read_namuwiki_insights(
        path,
        now=datetime(2026, 8, 5, 1, 0, tzinfo=timezone.utc),
    )

    assert result.status is InsightStatus.STALE
    assert result.rows[0].status is InsightStatus.STALE


def test_namuwiki_reader_returns_safe_states_for_missing_and_invalid_files(tmp_path) -> None:
    """Missing and malformed files become user-safe states without raw payloads."""
    missing = read_namuwiki_insights(tmp_path / "missing.json")
    assert missing.status is InsightStatus.NO_DATA

    invalid_path = tmp_path / "invalid.json"
    invalid_path.write_text("not json", encoding="utf-8")
    invalid = read_namuwiki_insights(invalid_path)
    assert invalid.status is InsightStatus.INVALID_ARTIFACT
    assert "not json" not in (invalid.message or "")


def test_namuwiki_reader_rejects_unsupported_schema_and_naive_timestamp(tmp_path) -> None:
    """The adapter does not guess a schema or timezone that storage did not provide."""
    path = tmp_path / "invalid.json"
    payload = _artifact()
    payload["schema_version"] = 99
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert read_namuwiki_insights(path).status is InsightStatus.INVALID_ARTIFACT

    payload = _artifact(generated_at="2026-08-04T00:00:00")
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert read_namuwiki_insights(path).status is InsightStatus.INVALID_ARTIFACT


def test_google_finance_reader_maps_exact_symbols_and_kst_time(tmp_path) -> None:
    """The reader exposes only exact artifact symbols and detached metadata."""
    path = tmp_path / "google.json"
    path.write_text(json.dumps(_google_artifact()), encoding="utf-8")

    result = read_google_finance_insights(
        path,
        now=datetime(2026, 8, 4, 1, 0, tzinfo=timezone.utc),
    )

    assert result.status is InsightStatus.HEALTHY
    assert [row.symbol for row in result.rows] == [
        "NVDA:NASDAQ",
        "PLTR:NASDAQ",
        "005930:KRX",
        "000660:KRX",
    ]
    assert result.row_for_symbol("NVDA:NASDAQ").summary == "Summary for NVDA:NASDAQ"
    assert result.row_for_symbol("AAPL:NASDAQ") is None
    assert result.generated_at_kst.isoformat() == "2026-08-04T09:00:00+09:00"


def test_google_finance_reader_returns_symbol_not_analyzed_by_exact_lookup(tmp_path) -> None:
    """A missing AAPL row cannot fall back to another symbol's summary."""
    path = tmp_path / "google.json"
    path.write_text(json.dumps(_google_artifact(symbols=("NVDA:NASDAQ",))), encoding="utf-8")

    result = read_google_finance_insights(path)

    assert result.row_for_symbol("AAPL:NASDAQ") is None
    assert result.row_for_symbol("NVDA:NASDAQ").symbol == "NVDA:NASDAQ"


def test_google_finance_read_model_lookup_covers_first_middle_last_and_empty_rows(
    tmp_path,
) -> None:
    """ReadModel lookup returns only the requested first, middle, or last row."""
    path = tmp_path / "google.json"
    path.write_text(json.dumps(_google_artifact()), encoding="utf-8")
    result = read_google_finance_insights(path)

    assert result.row_for_symbol("NVDA:NASDAQ").symbol == "NVDA:NASDAQ"
    assert result.row_for_symbol("005930:KRX").symbol == "005930:KRX"
    assert result.row_for_symbol("000660:KRX").symbol == "000660:KRX"
    assert result.row_for_symbol("NVDA") is None
    assert result.row_for_symbol("nvda:nasdaq") is None

    empty_path = tmp_path / "empty.json"
    payload = _google_artifact(symbols=("NVDA:NASDAQ",))
    payload["items"] = []
    empty_path.write_text(json.dumps(payload), encoding="utf-8")
    empty = read_google_finance_insights(empty_path)
    assert empty.status is InsightStatus.INVALID_ARTIFACT
    assert empty.rows == ()


def test_google_finance_reader_rejects_duplicate_symbols(tmp_path) -> None:
    """Duplicate artifact symbols are invalid instead of selecting the first row."""
    path = tmp_path / "duplicate.json"
    path.write_text(
        json.dumps(_google_artifact(symbols=("NVDA:NASDAQ", "NVDA:NASDAQ"))),
        encoding="utf-8",
    )

    result = read_google_finance_insights(path)

    assert result.status is InsightStatus.INVALID_ARTIFACT
    assert result.rows == ()


def test_google_finance_reader_marks_old_artifact_stale(tmp_path) -> None:
    """An artifact older than the shared freshness policy is stale."""
    path = tmp_path / "google.json"
    path.write_text(json.dumps(_google_artifact()), encoding="utf-8")

    result = read_google_finance_insights(
        path,
        now=datetime(2026, 8, 5, 1, 0, tzinfo=timezone.utc),
    )

    assert result.status is InsightStatus.STALE


def test_google_finance_reader_rejects_invalid_schema_and_naive_timestamp(tmp_path) -> None:
    """The reader rejects unsupported schema and timezone-less timestamps."""
    path = tmp_path / "google.json"
    payload = _google_artifact()
    payload["schema_version"] = 99
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert read_google_finance_insights(path).status is InsightStatus.INVALID_ARTIFACT

    payload = _google_artifact(generated_at="2026-08-04T00:00:00")
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert read_google_finance_insights(path).status is InsightStatus.INVALID_ARTIFACT


def test_google_finance_reader_handles_missing_malformed_and_sensitive_free_payload(
    tmp_path,
) -> None:
    """Missing or malformed artifacts become safe states without raw contents."""
    missing = read_google_finance_insights(tmp_path / "missing.json")
    assert missing.status is InsightStatus.NO_DATA

    path = tmp_path / "broken.json"
    path.write_text("{broken", encoding="utf-8")
    broken = read_google_finance_insights(path)
    assert broken.status is InsightStatus.INVALID_ARTIFACT
    assert "broken" not in (broken.message or "")


def test_llm_usage_reader_reports_profiles_retries_and_last_request(tmp_path) -> None:
    """Ledger metadata is summarized without exposing credentials or prompts."""
    path = tmp_path / "quota-ledger.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "reservations": [
                    {
                        "project_profile": "production",
                        "timestamp_utc": "2026-08-05T00:00:00+00:00",
                        "pacific_date": "2026-08-04",
                        "retry": False,
                        "api_key": "do-not-display",
                        "prompt": "do-not-display",
                    },
                    {
                        "project_profile": "test",
                        "timestamp_utc": "2026-08-05T01:00:00+00:00",
                        "pacific_date": "2026-08-04",
                        "retry": True,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    result = read_llm_usage(
        path,
        now=datetime(2026, 8, 5, 1, 30, tzinfo=timezone.utc),
    )

    assert result.status is InsightStatus.HEALTHY
    assert [(item.project_profile, item.requests_today) for item in result.profiles] == [
        ("production", 1),
        ("test", 1),
    ]
    assert result.retry_count == 1
    assert result.last_request_at_kst.isoformat() == "2026-08-05T10:00:00+09:00"
    assert "do-not-display" not in repr(result)


def test_llm_usage_reader_handles_empty_and_malformed_ledgers(tmp_path) -> None:
    """Operations receives explicit empty or unavailable states."""
    missing = read_llm_usage(tmp_path / "missing.json")
    assert missing.status is InsightStatus.NO_DATA

    path = tmp_path / "broken.json"
    path.write_text("{broken", encoding="utf-8")
    broken = read_llm_usage(path)
    assert broken.status is InsightStatus.UNAVAILABLE
    assert "broken" not in (broken.message or "")
