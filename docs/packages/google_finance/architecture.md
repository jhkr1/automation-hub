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
- **Implemented**: `db_models.py`의 `StockQuoteSnapshot`과 `storage.py`의 append-only MySQL
  Storage를 제공한다.
- **Implemented**: `get_latest(symbol)`과 `get_latest_two(symbol)`은 collected_at DESC,
  id DESC의 결정적 순서를 사용한다.
- **Implemented**: `main.py --save-db`만 DB 저장을 활성화하며 기본 CLI 출력 동작은 유지한다.
- **Implemented**: Fake 기반 단위 테스트와 `AAPL:NASDAQ` 실제 CLI 실행을 검증했다.
- **Implemented**: 검증된 두 `StockPrice`의 최신·이전 가격을 비교하는 순수 Movement Detection 도메인 로직을 제공한다.
- **Implemented**: `get_latest_two()` 조회 결과를 Movement Detection에 연결하고, snapshot이
  2개 미만이면 명시적인 비교 불가 결과를 반환한다.
- **Proposed**: 다중 종목 순회와 Scheduler는 별도 Sprint에서 요구사항을 확인한 뒤 결정한다.
- **Not verified**: 테스트하지 않은 시장의 DOM 차이, Google Finance selector의 장기 안정성,
  운영·상업적 사용 적합성.
- **Not implemented**: News, LLM 분석, Scheduler, Excel/CSV/SQLite 저장, 내부 RPC 호출.

## Snapshot Storage

## Movement Detection

Movement Detection은 저장된 snapshot을 조회하지 않고, 호출자가 순서를 보장해 전달한 두
`StockPrice`만 비교한다. 입력은 `latest`, `previous` 순서이며 symbol이 같고
`latest.collected_at`이 `previous.collected_at`보다 빠르지 않아야 한다. 동일한 수집 시각은
허용한다.

가격 차이는 다음과 같이 계산한다.

```text
delta = latest.current_price - previous.current_price
```

`delta`가 양수면 `UP`, 음수면 `DOWN`, 0이면 `UNCHANGED`다. 비교는 `Decimal`의 exact
comparison을 사용하며 threshold와 상대 변동률은 지원하지 않는다. Google Finance 화면의
`change_percent`는 화면이 제공한 기준 시점의 변동률이고, Movement Detection의 delta는
저장된 두 snapshot 사이의 가격 차이이므로 같은 값으로 취급하지 않는다.

두 snapshot이 없거나 하나뿐인 경우를 처리하는 application 흐름, DB 조회와 CLI 연결은
`MovementUnavailable` 결과로 표현한다. DB 오류는 이 결과로 숨기지 않고 호출자에게 전달한다.
CLI 연결은 후속 PR의 범위다.

`StockQuoteSnapshot`은 기존 `StockPrice`의 persistence 전용 표현이다. ORM row에는 `id`와
`created_at`을 두지만 domain model에는 추가하지 않는다. 가격과 변동률은 MySQL
`DECIMAL`로 저장하고, `collected_at`과 `created_at`은 기존 DB convention에 따라 naive UTC
`DATETIME`으로 저장한다. ORM 변환 경계에서 domain timestamp는 timezone-aware UTC로 복원한다.
현재 price와 percent의 scale은 모두 8이며, 8자리 초과 Decimal은 저장 전에 명시적으로
거부한다. 따라서 DB의 암묵적 반올림에 의존하지 않는다.

`stock_quote_snapshots`는 기존 `trend_snapshots`와 분리된 Google Finance 전용 테이블이다.
`(symbol, collected_at)` 인덱스를 사용하며, timestamp 정밀도와 재실행 정책이 확정되지 않은
상태에서 강한 unique constraint는 추가하지 않았다. 저장은 update/upsert/delete 없이
append-only insert만 수행한다.

Storage transaction은 `SessionLocal.begin()`을 사용한다. 성공 시 commit하고 DB 예외는
호출자에게 전달되어 rollback되며, Storage는 Collector·Movement Detection·News·LLM을
호출하지 않는다.

필요한 환경변수는 기존 `DATABASE_URL`이다. 기본 CLI에는 DB 설정이 필요하지 않고,
`--save-db`를 사용할 때만 기존 database Session 인프라를 lazy import한다.

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
