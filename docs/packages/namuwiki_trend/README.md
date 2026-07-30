# namuwiki_trend

나무위키 실시간 검색어 Top 10을 수집하고 뉴스·LLM enrichment와 snapshot 조회에 활용하는
자동화 패키지다.

## 현재 구현

- Playwright 기반 Top 10 Collector
- `TrendItem`과 rank 보존
- CSV 및 JSON 저장
- Google News RSS 문맥 수집
- Gemini·OpenAI reason Generator
- Trend Pipeline과 DB snapshot 저장
- Daily Trend 조회 CLI

실행 명령과 운영 절차는 루트 [README](../../../README.md)와
[운영 문서](../../operations/README.md)를 참고한다. 상세 설계는
[architecture.md](architecture.md)에 기록한다.

## 제한사항

외부 네트워크, 브라우저, API quota와 MySQL 환경에 따라 Live 실행 결과가 달라질 수 있다.
기본 단위 테스트는 외부 시스템에 의존하지 않는다.
