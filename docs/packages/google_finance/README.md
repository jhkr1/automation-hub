# google_finance

Google Finance 관련 자동화를 위한 독립 패키지다.

## 현재 구현 상태

- **Implemented**: `config.py`의 `Settings`와 프로젝트 로거
- **Implemented**: `models.py`의 `StockPrice`, `StockReport`
- **Implemented**: Playwright 기반 단일 종목 Collector, 순수 추출·정규화 함수, Pipeline, CLI
- **Implemented**: 가격과 변동률은 `Decimal`, 수집 시각은 UTC-aware datetime으로 유지
- **Implemented**: Google Finance 전용 MySQL append-only snapshot Storage와 `--save-db` 옵션
- **Implemented**: `--show-movement` 옵션으로 저장된 최신 두 snapshot의 변동 결과 조회
- **Implemented**: `--analyze` 옵션으로 저장된 최신 두 snapshot과 Google News, Gemini를 연결한 CLI 분석 출력
- **Implemented**: Fake 기반 단위 테스트와 `AAPL:NASDAQ` 실제 CLI 검증
- **Not verified**: `en-US` 외 locale, 테스트하지 않은 거래소·종목의 DOM 차이, 장기적인 Google Finance selector 안정성
- **Not implemented**: 다중 종목 실행, Scheduler, DB 외 저장 형식, 분석 결과 저장, threshold, 상대 변동률

## 다음 범위

현재 CLI는 다음처럼 exchange-qualified symbol 하나를 받아 화면에 표시한다.

```bash
python -m google_finance.main AAPL:NASDAQ
python -m google_finance.main AAPL:NASDAQ --save-db
python -m google_finance.main AAPL:NASDAQ --show-movement
python -m google_finance.main AAPL:NASDAQ --analyze
```

현재 Collector와 parser는 검증된 영어 화면 계약에 따라 `en-US` locale만 허용한다.
Google Finance의 렌더링 DOM에서 수집한 문자열은 `extraction.py`에서 검증·정규화한 뒤
`StockPrice`로 변환한다. 내부 batchexecute/RPC 호출은 사용하지 않는다.

`--save-db`를 지정하면 기존 `DATABASE_URL` 설정으로 하나의 snapshot을 append한다.
기본 실행은 기존과 같이 stdout 출력만 수행하며 DB에 쓰지 않는다. 저장 테이블은
`stock_quote_snapshots`이고, 조회 계약은 `[newest, previous]` 순서의 최신 두 개 snapshot이다.

`--show-movement`는 새로운 quote를 수집하지 않고 저장된 최신 두 snapshot을 비교한다.
두 snapshot이 없거나 하나뿐이면 비교 불가 상태를 stdout에 표시하고 정상 종료한다.
`DATABASE_URL`이 필요하며, `--save-db`와 동시에 사용할 수 없다. 화면의
`change_percent`와 snapshot 사이의 movement는 서로 다른 의미이며, threshold와 상대 변동률은
지원하지 않는다.

`--analyze`도 새로운 quote를 수집하거나 저장하지 않고, 저장된 최신 두 snapshot을 비교한 뒤
회사명으로 Google News RSS를 조회한다. 뉴스가 없으면 Gemini를 호출하지 않고 근거 부족
메시지를 출력한다. 뉴스가 있으면 `GEMINI_API_KEY`로 `gemini-3.5-flash`를 호출해 공개 뉴스
기반의 최대 2문장·400자 이하 요약을 출력한다. 분석 결과는 이번 범위에서 JSON이나 DB에 저장하지 않으며,
투자 권유·목표 주가·매수/매도 판단을 생성하지 않는다.

Google Finance 데이터의 지연·정확성·사용 제한과 selector 변경 위험은 별도로 검토해야 한다.

상세 상태와 제안 구조는 [architecture.md](architecture.md)를 참고한다.
