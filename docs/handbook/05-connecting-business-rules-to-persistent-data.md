# Chapter 5. Business Rule을 영속 데이터와 연결하기

Chapter 4에서는 Google Finance의 가격 변동 규칙이 데이터베이스나 CLI를 직접 알지 않도록 분리한 이유를 살펴보았습니다. 그러나 메모리 안에서 두 `StockPrice`를 비교하는 것만으로는 실제 자동화가 완성되지 않습니다. 프로그램을 한 번 실행하고 종료하면, 다음 실행에서 이전 가격을 다시 알 수 없기 때문입니다.

Google Finance의 quote 수집은 실행할 때마다 새로운 값을 만듭니다. 이 값을 저장하지 않으면 현재 가격은 확인할 수 있어도 “이전 실행보다 올랐는가”라는 질문에는 답할 수 없습니다. 따라서 이 프로젝트에서는 Business Rule을 독립적으로 유지하면서도, 그 규칙이 사용할 데이터를 여러 실행 사이에 보존해야 했습니다.

이 Chapter의 질문은 다음과 같습니다.

> Business Rule이 데이터베이스에 의존하지 않으면서도, 영속 데이터와 어떻게 연결되어야 하는가?

여기서 영속 데이터(Persistence)는 프로그램이 종료된 뒤에도 남아 다시 읽을 수 있는 데이터입니다. 이 프로젝트에서는 Google Finance의 quote를 snapshot으로 저장하고, 다음 실행에서 같은 종목의 최신 두 snapshot을 읽어 Movement Detection에 전달합니다. 중요한 점은 저장되는 표현과 Business Rule이 사용하는 표현을 분리하되, 둘 사이의 계약을 잃지 않는 것입니다.

## 왜 Persistence가 필요한가

현재 가격만 수집하는 작업이라면 메모리 안에서 `StockPrice`를 만들고 출력하는 것으로 끝낼 수 있습니다. 실제로 기본 Google Finance 실행 흐름은 설정을 읽고 `StockPricePipeline`을 실행한 뒤 quote를 출력합니다. 이 경로에는 데이터베이스가 필수가 아닙니다.

하지만 `--save-db`를 사용하면 수집한 `StockPrice`를 `StockQuoteSnapshot`으로 바꾸어 저장합니다. 저장은 업데이트가 아니라 새로운 snapshot을 추가하는 방식입니다. 이렇게 해야 같은 종목에 대해 여러 시점의 결과가 남고, 나중에 최신 값과 이전 값을 비교할 수 있습니다. `--show-movement` 실행에서는 이 저장 이력을 읽어 변동을 계산합니다.

따라서 Persistence는 Business Rule을 대신하는 기능이 아닙니다. Persistence가 하는 일은 Business Rule이 다음 실행에서도 사용할 수 있도록 입력 데이터를 보존하는 것입니다. 가격이 올랐는지 판단하는 규칙은 여전히 `movement.py`에 있고, 데이터베이스는 그 판단에 필요한 이력을 제공하는 위치에 있습니다.

## 두 가지 데이터 표현

이 연결을 이해하려면 `StockPrice`와 `StockQuoteSnapshot`을 같은 객체로 보지 않아야 합니다. 둘은 비슷한 값을 담지만 변경 이유와 책임이 다릅니다.

`google_finance.models.StockPrice`는 내부 업무 흐름에서 사용하는 데이터 계약입니다. symbol, 종목명, 현재 가격, 이전 종가, 시가, 변동률, 통화, 수집 시각을 검증된 값으로 표현합니다. 가격은 `Decimal`이고, 수집 시각은 timezone-aware datetime입니다. 이 모델에는 데이터베이스 id나 SQLAlchemy 열 정보가 없으며, 수집된 가격의 의미만 남아 있습니다.

반면 `google_finance.db_models.StockQuoteSnapshot`은 저장소가 사용하는 Persistence Model입니다. SQLAlchemy의 `Base`를 상속하고 `stock_quote_snapshots` 테이블의 열, 제약 조건, 인덱스를 표현합니다. 데이터베이스에서 여러 행을 구분하기 위한 `id`와 저장 시각인 `created_at`도 여기에 있습니다. 이 정보는 저장과 조회에는 필요하지만, 두 가격의 차이를 계산하는 Business Rule에는 필요하지 않습니다.

두 표현 사이에는 명시적인 변환이 있습니다. `StockQuoteSnapshot.from_domain()`은 `StockPrice`를 저장 행으로 바꿉니다. 이 과정에서 symbol을 저장과 조회에 사용할 canonical form으로 정리하고, 통화를 대문자로 맞추며, UTC 수집 시각을 데이터베이스 표현으로 변환합니다. 고정된 소수점 자릿수보다 많은 Decimal 값은 데이터베이스가 조용히 반올림하지 않도록 저장 전에 거부합니다.

조회할 때는 반대 방향의 변환이 일어납니다. `StockQuoteSnapshot.to_domain()`은 저장 행을 다시 `StockPrice`로 만들고, 데이터베이스에 저장된 UTC 시각을 timezone-aware UTC datetime으로 복원합니다. 그 결과 `movement.py`는 ORM 객체를 직접 처리하지 않고, 수집 결과와 같은 내부 계약을 다시 입력으로 받습니다.

이 분리는 같은 값을 두 번 정의하려는 목적이 아닙니다. Domain Model은 “이 데이터가 업무 흐름에서 어떤 의미를 갖는가”를 표현하고, Persistence Model은 “이 값을 어떻게 저장하고 다시 읽을 것인가”를 표현합니다. 둘을 하나로 합치면 저장을 위해 필요한 id, 열 타입, 데이터베이스 제약이 Business Rule의 입력으로 흘러갈 수 있습니다.

## Storage의 책임

`google_finance.storage.StockQuoteStorage`는 두 표현을 연결하는 저장 경계입니다. `save()`는 `StockPrice`를 `StockQuoteSnapshot.from_domain()`으로 변환하고 하나의 트랜잭션 안에서 행을 추가합니다. `get_latest()`와 `get_latest_two()`는 특정 symbol의 저장 행을 조회한 뒤 `to_domain()`을 통해 `StockPrice`로 돌려줍니다.

조회 순서도 Storage의 계약에 포함됩니다. `get_latest_two()`는 같은 symbol만 대상으로 하며 `collected_at DESC`, 그리고 수집 시각이 같을 때 `id DESC` 순서를 적용합니다. 호출자는 결과를 `[newest, previous]`로 받을 수 있습니다. 이 순서가 있기 때문에 application 흐름은 데이터베이스의 정렬 문장을 다시 알 필요가 없습니다.

그러나 Storage가 하지 않는 일도 분명합니다. Storage는 두 가격을 비교하지 않고, 상승·하락을 판단하지 않으며, CLI 문장을 만들지 않습니다. DB 연결 오류를 정상적인 “비교 불가” 결과로 바꾸지도 않습니다. 이러한 책임을 Storage에 넣으면 저장 방식의 변경과 Business Rule의 변경이 같은 이유로 묶이게 됩니다.

현재 공통 SQLAlchemy `Base`와 Session은 루트 `database/`에 있습니다. Google Finance 전용 Persistence Model과 변환은 패키지 안의 `db_models.py`에 있고, 실제 Google Finance 테이블 생성 migration은 `alembic/versions/0003_create_stock_quote_snapshots_table.py`에 있습니다. 이 구조는 저장 기반과 패키지별 저장 의미가 완전히 같은 위치에 있다는 뜻이 아닙니다. 실제 책임이 나뉜 위치를 그대로 인정하면서, Storage가 호출자에게 일관된 `StockPrice` 계약을 제공하는 것이 핵심입니다.

## Persistence Contract

Persistence Contract는 저장했다가 다시 읽었을 때 Business Rule이 기대하는 의미가 유지된다는 약속입니다. 이 프로젝트의 흐름은 다음과 같이 요약할 수 있습니다.

```text
StockPrice
    ↓ from_domain()
StockQuoteSnapshot
    ↓ database row
StockQuoteSnapshot
    ↓ to_domain()
StockPrice
```

첫 번째 계약은 symbol입니다. 저장과 조회는 `strip()`과 대문자 변환을 사용하는 같은 canonical 정책을 따릅니다. 따라서 `aapl:nasdaq`로 저장한 값은 `AAPL:NASDAQ` 조회로 찾을 수 있습니다. 이 정책이 한쪽에만 적용되면 저장된 데이터가 있어도 조회하지 못하는 오류가 생깁니다.

두 번째 계약은 숫자의 의미입니다. 가격과 변동률은 `Decimal`로 유지되며, 현재 스키마가 허용하는 소수점 여덟 자리를 넘는 값은 저장 전에 명시적으로 거부됩니다. 이것은 정밀도를 무한히 보장한다는 뜻이 아니라, 현재 Storage 계약 밖의 값을 암묵적으로 반올림하지 않는다는 뜻입니다.

세 번째 계약은 시간입니다. Domain의 수집 시각은 timezone-aware UTC로 다루고, 현재 데이터베이스 열은 UTC를 나타내는 naive 값으로 저장합니다. 조회 시 다시 UTC 정보가 붙은 시간으로 복원해야 합니다. 시간대 정보가 사라진 채 Business Rule에 전달되면 최신과 이전의 순서를 안정적으로 판단하기 어렵습니다.

네 번째 계약은 순서와 append-only 기록입니다. 저장할 때 기존 snapshot을 덮어쓰지 않고 새 행을 추가합니다. 조회는 같은 symbol을 걸러내고 최신 두 행을 결정적인 순서로 반환합니다. 동일한 수집 시각도 허용하되, 이 경우 database id를 보조 순서로 사용합니다. 시간과 순서를 조용히 추측하지 않고 Storage 계약으로 고정했기 때문에, application은 반환 목록의 의미를 신뢰할 수 있습니다.

## Business Rule과 Persistence의 연결

두 계층을 실제 실행 흐름으로 연결하는 위치는 `movement_application.py`입니다. `lookup_movement()`는 symbol을 검증하고 Storage에 최신 두 snapshot을 요청합니다. 결과가 0개 또는 1개라면 비교할 이력이 부족한 정상적인 application 상태이므로 `MovementUnavailable`을 반환합니다. 두 개가 있으면 `[newest, previous]` 순서를 유지한 채 `detect_movement()`를 호출합니다.

```text
main.py --show-movement
    ↓
lookup_movement()
    ↓
StockQuoteStorage.get_latest_two()
    ↓
StockPrice[ newest, previous ]
    ↓
detect_movement()
    ↓
MovementResult 또는 MovementUnavailable
```

이 흐름에서 `movement.py`는 Storage를 import하지 않습니다. `movement_application.py`가 저장 조회와 계산 호출을 조정하기 때문에, Business Rule은 데이터가 MySQL에서 왔는지 Fake에서 왔는지 알 필요가 없습니다. 반대로 Storage도 Movement를 직접 호출하지 않습니다. 저장소는 조회 계약을 지키고, application이 그 결과를 도메인 규칙에 전달합니다.

`main.py`는 사용자의 명령과 결과 표현을 담당합니다. `--show-movement`에서만 관련 Storage와 application 흐름을 활성화하고 결과를 출력합니다. 이 연결은 Persistence를 Business Rule 안에 넣는 방식이 아니라, Business Rule의 입력 계약을 Storage가 복원하고 application이 두 영역을 이어 주는 방식입니다.

## 테스트가 증명하는 것

저장 계약은 여러 수준의 테스트로 확인됩니다. `tests/google_finance/test_storage.py`는 Domain Model과 Persistence Model 사이의 변환, Decimal 정밀도, UTC 복원, symbol 정규화, 저장 트랜잭션과 기본 조회 계약을 검사합니다. Fake session을 사용하므로 이 테스트는 SQL 서버 자체보다 Storage의 변환과 호출 경계를 빠르게 확인합니다.

`tests/database/test_google_finance_integration.py`는 `RUN_DB_INTEGRATION=1`일 때 실제 MySQL 환경에서 migration된 `stock_quote_snapshots` 테이블과 인덱스를 확인합니다. 여러 snapshot을 저장한 뒤 최신 두 개의 순서, 다른 symbol 제외, 동일 수집 시각에서 id 기준 정렬, 한 개와 0개의 이력 상태를 검증합니다. 실제 DB에서 Domain으로 돌아온 값으로 Movement도 계산해 저장과 Business Rule의 연결을 확인합니다.

한편 `tests/google_finance/test_movement_application.py`는 DB가 아니라 Storage Fake를 사용합니다. 이 테스트는 application이 2개 데이터를 계산 함수에 전달하고, 부족한 snapshot을 `MovementUnavailable`으로 표현하며, Storage 오류와 Domain 오류를 숨기지 않는지 검증합니다. 저장 테스트와 application 테스트가 서로 다른 계약을 확인하기 때문에, DB 문제와 비교 규칙 문제를 한 테스트 결과로 섞지 않습니다.

## 얻은 것과 감수한 것

이 구조의 가장 큰 이점은 Domain을 보호한다는 점입니다. 저장 열이나 DB Session이 바뀌어도 `detect_movement()`의 입력과 계산 규칙을 바로 수정할 필요가 없습니다. 변환 경계가 분명하므로 DB 없이 Business Rule을 테스트할 수 있고, 다른 저장 방식을 검토하더라도 영향 범위를 좁힐 수 있습니다.

대신 같은 데이터를 표현하는 모델이 두 개이고, `from_domain()`과 `to_domain()` 변환 코드가 필요합니다. Storage, Domain, application으로 파일과 계층도 늘어납니다. 작은 스크립트에서 현재 가격 하나만 출력한다면 이 구조는 과할 수 있습니다. 이 프로젝트에서는 여러 실행의 snapshot을 보존하고 이전 값과 비교해야 했기 때문에, 변환과 경계를 유지하는 비용을 받아들였습니다.

## 짧은 회고

Persistence를 붙이면서 배운 점은 “데이터베이스에 저장할 수 있으면 끝”이 아니라는 사실입니다. 저장 전과 조회 후에도 Business Rule이 이해할 수 있는 데이터 계약이 같아야 합니다. 특히 시간, 숫자 정밀도, symbol과 순서는 저장 기술의 세부사항처럼 보이지만, 실제로는 다음 판단의 의미를 지키는 조건이었습니다.

## 마무리

이 프로젝트에서 `StockPrice`와 `StockQuoteSnapshot`은 같은 값을 서로 다른 목적으로 표현합니다. `StockQuoteStorage`는 두 표현 사이를 변환하고 append-only 이력을 조회하며, 저장된 값은 다시 `StockPrice` 계약으로 복원됩니다. 이 변환과 저장·조회 순서가 유지되어야 다음 실행에서도 동일한 내부 데이터를 사용할 수 있습니다.

이제 데이터가 저장되고 다시 읽히는 경계까지 만들었습니다. 다음에는 이 흐름을 한 번의 명령으로 끝내지 않고, 어떤 방식으로 반복 실행하고 운영 자동화할 것인지 질문해야 합니다.
