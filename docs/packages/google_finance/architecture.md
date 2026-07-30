# google_finance 아키텍처

## 현재 상태

- **Implemented**: `Settings`는 `STOCK_SYMBOLS`, `GOOGLE_FINANCE_LOCALE`, `LOG_LEVEL`을
  제공하며, unrelated `.env` 항목은 무시한다.
- **Implemented**: `StockPrice`는 UTC-aware `collected_at`과 명시적인 `currency`를 포함한다.
  가격과 변동률은 `Decimal`로 보존한다.
  `StockReport`는 기존 계약을 유지한다.
- **Implemented**: `collector.py`가 exchange-qualified symbol을 검증하고 Playwright로
  `https://www.google.com/finance/quote/{EXCHANGE:TICKER}`의 렌더링 결과를 수집한다.
- **Implemented**: `extraction.py`가 가격·퍼센트·통화 문자열을 검증하고 `StockPrice`로 변환한다.
- **Implemented**: `pipeline.py`는 Collector callable을 주입받아 한 종목을 변환한다.
- **Implemented**: `main.py`는 단일 symbol CLI와 출력 경계를 제공한다.
- **Implemented**: 현재 영어 화면 파싱 계약에 맞춰 `en-US` locale만 허용한다.
- **Implemented**: Fake 기반 단위 테스트와 `AAPL:NASDAQ` 실제 CLI 실행을 검증했다.
- **Proposed**: 다중 종목 순회, Storage, Scheduler는 별도 Sprint에서 요구사항을 확인한 뒤 결정한다.
- **Not verified**: 테스트하지 않은 시장의 DOM 차이, Google Finance selector의 장기 안정성,
  운영·상업적 사용 적합성.
- **Not implemented**: DB·Excel 저장, 다중 종목 실행, Scheduler, LLM 분석, 내부 RPC 호출.

## 데이터 흐름

`main.py` → `StockPricePipeline` → `collect_stock_quote()` → Playwright rendered DOM
→ `RawStockQuote` → `parse_stock_quote()` → `StockPrice` → stdout

Collector는 symbol locator로 시작한 뒤 해당 symbol의 quote container ancestor로 범위를 제한한다.
현재가·변동률은 current quote block 안에서 읽고, 전일 종가·시가는 container 안에서 읽는다.
클래스와 `jsname`은 Google의 공개 API 계약으로 간주하지 않으므로 selector 변경 위험이 남아 있다.

## 오류 정책

잘못된 symbol, HTTP 비정상 응답, locator 0개·복수 매칭, 비어 있거나 잘못된 숫자·통화·퍼센트는
예외로 전달한다. CLI의 process boundary가 오류 메시지를 출력하고 종료 코드 1을 반환한다.
Collector와 extraction은 서로 직접 호출하지 않고, Pipeline이 두 경계를 조정한다.
