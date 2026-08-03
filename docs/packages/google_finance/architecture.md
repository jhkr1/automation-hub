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
- **Implemented**: `--show-movement`에서 저장된 snapshot의 Movement 결과를 출력하며, 기본
  quote 실행과 `--save-db` 모드의 동작을 유지한다.
- **Implemented**: Google Finance 전용 `StockNewsArticle`, Google News RSS Provider,
  `GeminiStockInsightGenerator`, 불변 `StockInsight`를 추가했다.
- **Implemented**: `analysis_application.py`가 저장된 최신 두 snapshot을 Movement Detection,
  뉴스 조회, Gemini 요약 생성과 연결하고 `--analyze`가 그 결과를 CLI로 출력한다.
- **Implemented**: 뉴스가 없으면 Gemini를 호출하지 않고 근거 부족 결과를 반환한다. 분석 결과는
  이번 범위에서 JSON이나 DB에 저장하지 않는다.
- **Proposed**: 다중 종목 순회와 Scheduler는 별도 Sprint에서 요구사항을 확인한 뒤 결정한다.
- **Not verified**: 테스트하지 않은 시장의 DOM 차이, Google Finance selector의 장기 안정성,
  운영·상업적 사용 적합성.
- **Not implemented**: Scheduler, Excel/CSV/SQLite 저장, 분석 결과 저장, 내부 RPC 호출.

## Analysis Application

분석 흐름은 새 quote를 수집하거나 저장하지 않고 기존 snapshot을 사용한다.

```text
main.py --analyze
    → StockQuoteStorage.get_latest_two()
    → detect_movement()
    → GoogleFinanceNewsProvider
    → GeminiStockInsightGenerator
    → StockInsight
    → stdout
```

`StockNewsArticle`, Provider, Generator는 Google Finance 패키지 안에 있으며
`namuwiki_trend`의 모델이나 Provider를 import하지 않는다. `StockInsight`는 symbol, 회사명,
가격, Google Finance `change_percent`, snapshot Movement, 뉴스와 요약을 보존하는 불변 출력
모델이다. `change_percent`는 화면이 제공한 기준 변동률이고 Movement는 두 저장 시점의
가격 차이이므로 Prompt에서도 두 의미를 구분한다.

뉴스가 0건이면 정상적인 근거 부족 상태로 처리하고 Gemini 호출을 생략한다. snapshot이
2개 미만이면 기존 `MovementUnavailable` 계약을 유지한다. DB 오류와 뉴스·Gemini 오류는
분석 결과로 숨기지 않고 CLI 실패로 전달한다. Gemini 요약은 공개 뉴스에 근거한 한국어
일반 텍스트이며 최대 2문장·400자 이하로 제한한다. 인과관계를 단정하거나 투자
권유·목표 주가·매수/매도 판단을 생성하지 않도록 요청한다.

## Watchlist Application

Watchlist CLI는 설정된 symbol을 입력 순서대로 하나씩 실행한다. CLI는 흐름을 조립하고 결과를
출력하며, 실제 수집·저장·분석은 기존 단일 종목 API에 위임한다.

```text
STOCK_SYMBOLS
    → Settings.get_symbol_list()
    → watchlist_main.py
        ├─ --collect → StockPricePipeline → StockQuoteStorage.save()
        └─ --analyze → get_latest_two() → Movement → News → Gemini → StockInsight
```

`watchlist_application.py`는 종목별 결과를 불변 결과 객체로 모으고 한 종목의 실패를 다음
종목에 전파하지 않는다. 수집 결과는 성공 또는 수집·저장 실패를, 분석 결과는 성공,
`MOVEMENT_UNAVAILABLE`, 분석 실패를 구분한다. 외부 예외의 민감한 본문과 traceback은 결과에
보존하지 않고 예외 타입과 안전한 단계 요약만 남긴다. 하나 이상의 실패가 있으면 Watchlist
CLI는 종료 코드 1을 반환한다.

수집 모드에서는 News Provider와 Gemini를 생성하지 않으며, 분석 모드에서는 브라우저 수집을
실행하지 않는다. 두 모드 모두 기존 단일 종목 흐름을 재사용하고, retry·sleep·parallel 실행은
지원하지 않는다.

Gemini의 `429 RESOURCE_EXHAUSTED`가 일일 무료 요청 quota인 것으로 확인되면, 해당 분석 실행의
application 범위에서만 quota 상태를 기억한다. 첫 실패는 `ANALYSIS_UNAVAILABLE`과
`DAILY_QUOTA_EXHAUSTED` reason으로 표현하고, 이후 symbol은 Gemini를 호출하지 않고 같은
상태로 반환한다. 첫 실패 시점에 계산된 Movement와 뉴스 개수는 결과에 보존할 수 있으며,
원본 SDK 오류·API key·traceback은 CLI 출력에 포함하지 않는다. 일일 quota가 아닌 429는
이번 범위에서 자동 재시도하지 않고 기존 분석 실패 계약을 유지한다.

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
CLI의 `--show-movement`는 이 application 흐름을 호출하고, 결과를 stdout에 출력한다.

## Snapshot Storage

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

Movement 조회는 별도 흐름을 사용한다.

```text
main.py --show-movement
    → StockQuoteStorage
    → lookup_movement()
    → detect_movement()
    → stdout
```

분석 조회는 다음 별도 application 흐름을 사용한다.

```text
main.py --analyze
    → StockQuoteStorage
    → analyze_stored_quote()
    → detect_movement()
    → GoogleFinanceNewsProvider
    → GeminiStockInsightGenerator
    → StockInsight
    → stdout
```

기본 quote 실행에서는 DB 설정과 Storage를 로드하지 않는다. DB 관련 import와 Session 생성은
`--save-db`, `--show-movement` 또는 `--analyze` 분기에서만 발생한다. 세 옵션은 서로 다른
실행 의미를 가지므로 동시에 사용할 수 없다.

Collector는 symbol locator로 시작한 뒤 해당 symbol의 quote container ancestor로 범위를 제한한다.
현재가·변동률은 current quote block 안에서 읽고, 전일 종가·시가는 container 안에서 읽는다.
클래스와 `jsname`은 Google의 공개 API 계약으로 간주하지 않으므로 selector 변경 위험이 남아 있다.

## 오류 정책

잘못된 symbol, HTTP 비정상 응답, locator 0개·복수 매칭, 비어 있거나 잘못된 숫자·통화·퍼센트는
예외로 전달한다. CLI의 process boundary가 오류 메시지를 출력하고 종료 코드 1을 반환한다.
Collector와 extraction은 서로 직접 호출하지 않고, Pipeline이 두 경계를 조정한다.
