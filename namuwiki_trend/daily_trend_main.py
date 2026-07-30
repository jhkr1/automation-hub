"""Daily Trend 집계 결과를 터미널에 표시하는 CLI 진입점."""

import argparse
import sys
from datetime import date, datetime
from zoneinfo import ZoneInfo

from database.daily_trend_query import DailyTrendQueryService

SEOUL_TZ = ZoneInfo("Asia/Seoul")


def _parse_date(value: str) -> date:
    """Parse a CLI date in ISO calendar format."""
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("date must use YYYY-MM-DD format") from exc


def _build_parser() -> argparse.ArgumentParser:
    """Create the Daily Trend argument parser."""
    parser = argparse.ArgumentParser(description="Display daily trend rankings.")
    parser.add_argument("--date", type=_parse_date, help="KST date in YYYY-MM-DD format")
    parser.add_argument("--limit", type=int, default=10, help="number of results to display")
    return parser


def _default_date(now: datetime | None = None) -> date:
    """Return today's date in Asia/Seoul without using the system timezone."""
    current = now if now is not None else datetime.now(SEOUL_TZ)
    if current.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    return current.astimezone(SEOUL_TZ).date()


def _print_results(target_date: date, results: list[object]) -> None:
    """Print query results in the service-provided order."""
    print(f"Daily trends for {target_date} KST")
    if not results:
        print(f"No daily trends found for {target_date} KST.")
        return

    print("Rank  Keyword                 Count  Best  Average  Score")
    for rank, result in enumerate(results, start=1):
        print(
            f"{rank:<5}{result.keyword:<24}{result.appearance_count:<7}"
            f"{result.best_rank:<6}{result.average_rank:<9.2f}{result.rank_score}"
        )


def main(
    argv: list[str] | None = None,
    service: DailyTrendQueryService | None = None,
    now: datetime | None = None,
) -> int:
    """Query and display Daily Trend results, returning a process exit code."""
    args = _build_parser().parse_args(argv)
    if args.limit <= 0:
        _build_parser().error("--limit must be greater than zero")

    target_date = args.date if args.date is not None else _default_date(now)
    query_service = service if service is not None else DailyTrendQueryService()
    results = query_service.query(target_date, limit=args.limit)
    _print_results(target_date, results)
    return 0


if __name__ == "__main__":
    sys.exit(main())
