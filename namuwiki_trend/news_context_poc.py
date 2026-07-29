"""검색어 하나의 Google News RSS 문맥을 직접 확인하는 수동 PoC."""

from time import perf_counter

from namuwiki_trend.news_context_provider import NewsContextProvider


def main() -> None:
    """손흥민 검색 결과를 출력한다."""
    started_at = perf_counter()
    articles = NewsContextProvider().search("손흥민", limit=5)
    elapsed = perf_counter() - started_at

    print(f"검색 결과 개수: {len(articles)}")
    for article in articles:
        print(f"제목: {article.title}")
        print(f"출처: {article.source or '없음'}")
        print(f"게시 시각: {article.published_at or '없음'}")
        print(f"URL: {article.url}")
    print(f"호출 시간: {elapsed:.3f}초")


if __name__ == "__main__":
    main()
