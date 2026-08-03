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
- **Implemented**: `STOCK_SYMBOLS` Watchlist를 순차 수집·저장·분석하는 `watchlist_main.py` CLI
- **Implemented**: Fake 기반 단위 테스트와 `AAPL:NASDAQ` 실제 CLI 검증
- **Not verified**: `en-US` 외 locale, 테스트하지 않은 거래소·종목의 DOM 차이, 장기적인 Google Finance selector 안정성
- **Not implemented**: Scheduler, DB 외 저장 형식, 분석 결과 저장, threshold, 상대 변동률

## 다음 범위

현재 CLI는 다음처럼 exchange-qualified symbol 하나를 받아 화면에 표시한다.

```bash
python -m google_finance.main AAPL:NASDAQ
python -m google_finance.main AAPL:NASDAQ --save-db
python -m google_finance.main AAPL:NASDAQ --show-movement
python -m google_finance.main AAPL:NASDAQ --analyze
```

Watchlist는 `.env`의 `STOCK_SYMBOLS`를 사용한다. 쉼표로 구분한 symbol을 검증하고
canonicalization한 뒤 입력 순서를 유지하여 순차 실행한다. 이 값은 코드에 내장된 기본 목록이
아니라 사용자가 수정하는 설정이다.

```env
STOCK_SYMBOLS=NVDA:NASDAQ,PLTR:NASDAQ,005930:KRX,000660:KRX
```

```bash
python -m google_finance.watchlist_main --collect
python -m google_finance.watchlist_main --analyze
```

`--collect`는 기존 단일 종목 Pipeline과 Storage를 각 symbol에 재사용한다. `--analyze`는
기존 snapshot 조회, Movement, Google News, Gemini 분석 흐름을 각 symbol에 재사용한다.
한 symbol의 실패가 다음 symbol을 막지는 않지만 하나라도 실패하면 종료 코드는 1이다.
Movement에 필요한 snapshot이 부족한 경우는 정상적인 `MOVEMENT_UNAVAILABLE` 상태로 출력되고
종료 코드는 0이다. 수집은 `DATABASE_URL`만 필요하고, 분석은 여기에 `GEMINI_API_KEY`가
추가로 필요하다.

Gemini 무료 계정의 일일 요청 quota가 소진되면 Watchlist는 재시도하지 않는다. 첫 quota 오류
이후 같은 실행의 후속 Gemini 호출을 중단하고 각 종목을 `ANALYSIS_UNAVAILABLE`로 출력한다.
가격·Movement·뉴스를 확보한 첫 종목의 일부 분석 정보는 보존하지만, 이 상태가 있으면 종료
코드는 1이다. Batch 요청이나 분석 결과 캐시는 현재 지원하지 않는다.

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
