"""운영 Collector를 실행하는 나무위키 Top10 PoC 진입점."""

from time import perf_counter

from namuwiki_trend.collector import collect_trends


def main() -> None:
    """Collector를 실행하고 수집 결과를 콘솔에 출력한다."""
    started_at = perf_counter()
    items = collect_trends()
    for item in items:
        print(f"rank={item.rank}, keyword={item.keyword}, href={item.href}")
    print(f"total_elapsed_ms={(perf_counter() - started_at) * 1000:.1f}")


if __name__ == "__main__":
    main()
