# Chapter 4. Business Rule을 Infrastructure로부터 독립시키기

Google Finance의 저장 snapshot에 변동 조회 기능을 추가할 때, 처음부터 데이터베이스와 CLI를 하나의 함수에 넣지는 않았습니다. 이미 `movement.py`에는 두 `StockPrice`를 비교해 상승·하락·변동 없음을 판단하는 코드가 있었고, `movement_application.py`에는 저장된 최신 두 snapshot을 가져와 그 코드를 호출하는 흐름이 있었습니다. 마지막으로 `main.py`가 사용자의 옵션을 해석하고 결과를 출력했습니다.

이 구조를 따라가면 한 가지 질문이 생깁니다.

> 왜 Business Rule은 Infrastructure에 의존하지 않아야 하는가?

이 Chapter에서는 이 질문을 `automation-hub`의 실제 코드로만 살펴봅니다. 여기서 Business Rule은 데이터를 어떻게 판단할지 정하는 규칙이고, Domain은 그 규칙과 내부 데이터 계약을 표현하는 코드입니다. Infrastructure는 DB·브라우저·CLI처럼 외부 세계와 연결하며, Application Layer는 두 영역의 실행 순서를 조정합니다. 별도의 아키텍처 이론을 먼저 가져오는 대신, 같은 가격 비교 규칙이 데이터베이스나 CLI 없이도 실행되고 테스트될 수 있도록 만든 이유를 확인합니다.

## 이 프로젝트에서 Business Rule은 무엇인가

Business Rule은 프로젝트가 수집한 데이터를 어떻게 판단할지를 정하는 규칙입니다. 이 프로젝트의 Movement Detection에서는 “최신 snapshot의 가격에서 이전 snapshot의 가격을 뺀다”는 규칙이 핵심입니다.

```text
delta = latest.current_price - previous.current_price
```

delta가 양수면 `UP`, 음수면 `DOWN`, 0이면 `UNCHANGED`입니다. 두 snapshot의 symbol이 다르면 비교하지 않고, `latest.collected_at`이 `previous.collected_at`보다 빠르면 호출자의 순서 계약 위반으로 처리합니다. 같은 수집 시각은 허용합니다.

이 규칙은 MySQL의 테이블 이름이나 CLI 옵션을 알 필요가 없습니다. `movement.py`의 `detect_movement()`는 검증된 `StockPrice` 두 개를 `latest`, `previous` 순서로 받고 `MovementResult`를 반환합니다. 결과에는 symbol, 두 가격, Decimal delta, 두 수집 시각과 명시적인 `MovementDirection`이 들어 있습니다. 입력이 잘못되면 `MovementDetectionError`를 발생시키지만, 어디에서 데이터를 읽었는지는 묻지 않습니다.

`StockPrice`도 이 규칙이 사용하는 내부 데이터 계약입니다. `movement.py`는 문자열로 된 Google Finance 화면을 다시 해석하지 않으며, ORM row를 직접 다루지도 않습니다. 이미 내부 규칙을 통과한 `StockPrice`를 받아 가격 비교라는 한 가지 판단만 수행합니다.

## 우리 프로젝트의 Infrastructure

Infrastructure는 Business Rule이 실행될 수 있도록 외부 세계와 연결하는 코드입니다. 이 프로젝트에서는 역할이 서로 다르지만 다음 요소들이 여기에 해당합니다.

- `StockQuoteStorage`는 SQLAlchemy Session을 사용해 MySQL의 `stock_quote_snapshots`에 저장하고 조회합니다.
- `StockQuoteSnapshot`은 domain의 `StockPrice`를 데이터베이스 열과 UTC 저장 형식으로 바꾸는 persistence 모델입니다.
- `main.py`는 argparse로 symbol과 `--save-db`, `--show-movement`를 해석하고 stdout·stderr와 종료 코드를 관리합니다.
- `collector.py`는 Playwright로 Google Finance의 렌더링 페이지를 열고 DOM에서 원시 문자열을 읽습니다.
- `Settings`와 database Session은 환경변수와 연결 환경을 구성합니다.

이 요소들은 모두 필요한 코드이지만 가격이 올랐는지 판단하는 규칙 자체는 아닙니다. Google Finance의 DOM selector가 바뀌거나, MySQL 연결 방식이 바뀌거나, CLI가 다른 출력 형식을 사용하게 되어도 “101.00에서 100.00을 빼면 상승”이라는 규칙은 바뀌지 않아야 합니다.

이 프로젝트에서 항상 여러 계층을 만드는 것이 목표는 아닙니다. 중요한 규칙이 외부 연결과 다른 이유로 변경되고, 반복 실행과 검증이 필요할 때 분리를 선택할 근거가 생깁니다.

## Domain이 Infrastructure를 몰라야 하는 이유

`movement.py`의 import를 보면 표준 라이브러리와 `google_finance.models.StockPrice`만 사용합니다. SQLAlchemy, MySQL, `StockQuoteStorage`, Playwright, `Settings`, argparse와 CLI 모듈을 import하지 않습니다. 이 제한은 단순히 파일을 깔끔하게 보이기 위한 규칙이 아닙니다.

만약 `detect_movement()`가 Storage를 직접 호출했다면, 함수는 먼저 symbol을 받아 DB에서 snapshot을 찾아야 했을 것입니다. 그러면 가격 비교 규칙을 확인하려 해도 DB Session, 연결 설정과 테이블 상태가 필요합니다. 저장 방식이 바뀌면 Business Rule 파일도 함께 수정해야 합니다. 또한 DB에서 반환된 행의 순서가 잘못되었을 때, 도메인 규칙과 조회 문제를 한 함수 안에서 구분하기 어려워집니다.

현재는 `StockQuoteStorage.get_latest_two()`가 `[newest, previous]`를 만들고, application 흐름이 그 목록을 `detect_movement(latest=snapshots[0], previous=snapshots[1])`에 전달합니다. Storage가 조회 순서를 책임지고 domain은 전달받은 순서가 맞는지 시간 계약을 확인합니다. 각 모듈이 자신이 책임지는 실패를 분명히 알 수 있는 이유입니다.

Domain이 CLI를 몰라야 하는 이유도 같습니다. `MovementResult`는 “Movement: UP”이라는 문장을 만들지 않습니다. `MovementDirection.UP`이라는 의미를 보존한 결과를 만들고, 화면 표현은 `main.py`가 담당합니다. 나중에 CLI 대신 다른 호출자가 생겨도 계산 함수는 그대로 사용할 수 있습니다.

## Application Layer가 연결을 담당하는 이유

Infrastructure와 Business Rule을 분리하면 두 세계를 연결할 위치가 필요합니다. 이 프로젝트에서는 `movement_application.py`의 `lookup_movement()`가 그 역할을 합니다.

실제 흐름은 다음과 같습니다.

```text
symbol
  ↓
lookup_movement()
  ↓
StockQuoteStorage.get_latest_two()
  ↓
MovementResult 또는 MovementUnavailable
  ↓
detect_movement(latest, previous)
```

`lookup_movement()`는 기존 symbol 검증 정책을 사용하고 Storage에 canonical symbol을 전달합니다. 조회 결과가 0개 또는 1개이면 이것은 Business Rule 위반이 아니라 아직 비교할 이력이 부족한 application 상태이므로 `MovementUnavailable`을 반환합니다. 두 개가 있으면 Storage가 보장한 순서대로 domain 함수를 호출합니다.

이 흐름에서 Storage는 Movement를 계산하지 않습니다. Storage의 책임은 append-only snapshot을 저장하고, 특정 symbol의 최신 두 snapshot을 반환하는 것입니다. 반대로 domain은 DB 오류나 snapshot 조회 방법을 알지 못합니다. `lookup_movement()`가 둘을 연결하기 때문에 각 책임이 지나치게 커지지 않습니다.

CLI도 application 흐름을 직접 재구현하지 않습니다. `main.py --show-movement`는 Movement 모드에서만 Storage와 application을 lazy import하고, 결과의 종류에 따라 출력합니다. 기본 quote 실행은 기존처럼 `StockPricePipeline`을 통해 Collector와 Extraction을 실행하며, Movement application을 호출하지 않습니다. `--save-db`와 `--show-movement`를 동시에 허용하지 않는 것도 두 실행 흐름의 의미가 다르기 때문입니다.

여기서 application이 모든 외부 코드를 모르는 것은 아닙니다. 현재 `movement_application.py`는 기존 symbol 검증 정책을 재사용하기 위해 `collector.py`의 `validate_symbol()`을 import합니다. 하지만 Collector를 실행하거나 Playwright 페이지를 열지는 않습니다. 이 차이는 중요합니다. application은 입력 계약을 재사용할 수 있지만, 가격 비교의 Business Rule이 화면 수집 과정에 들어가지는 않습니다. 현재 repository에서 확인되는 실제 의존성을 숨기지 않으면서도, 변경 이유가 다른 책임을 분리한 것입니다.

독립은 고립을 뜻하지도 않습니다. `movement.py`는 `StockPrice`라는 내부 모델을 알아야 하고, application은 Storage와 domain 함수를 알아야 합니다. 문제는 어떤 의존성이 허용되는가입니다. domain이 내부 데이터 계약을 알고 계산하는 것은 규칙에 필요한 의존성입니다. 반면 domain이 SQLAlchemy Session이나 argparse를 알아야 하는 것은 가격 비교에 필요하지 않은 의존성입니다. 이 구분을 기준으로 보면 계층의 목적을 이름이 아니라 변경 이유로 판단할 수 있습니다.

## 실제 dependency 방향

현재 코드의 방향은 하나의 직선으로만 설명되지 않습니다. quote 수집과 저장 snapshot 비교가 서로 다른 실행 흐름을 가지기 때문입니다. 아래 diagram은 실행 흐름을 보여주는 것이며, 모든 Python import 관계를 완전히 나열한 모듈 graph는 아닙니다. 실제로 `movement_application.py`는 symbol 검증을 위해 `collector.validate_symbol`도 import합니다.

```text
기본 quote
main.py
  ↓
StockPricePipeline
  ↓
collect_stock_quote()
  ↓
Playwright rendered DOM
  ↓
RawStockQuote → parse_stock_quote() → StockPrice
```

```text
stored movement
main.py --show-movement
  ↓
movement_application.lookup_movement()
  ↓
StockQuoteStorage
  ↓
StockPrice 목록
  ↓
movement.detect_movement()
  ↓
MovementResult
```

두 흐름에서 `StockPrice`는 내부 데이터 계약의 역할을 합니다. Collector와 Extraction은 외부 값을 이 계약으로 바꾸고, Storage는 이 계약을 저장하고 복원하며, Movement domain은 이 계약을 입력으로 판단합니다. 그러나 Storage가 domain을 import해 계산하지 않고, domain이 Storage를 import하지 않는다는 점이 중요합니다. 의존성이 한 방향으로만 흐르도록 유지했기 때문입니다.

## 테스트가 증명하는 것

이 경계는 테스트 구조에도 나타납니다. `tests/google_finance/test_movement.py`는 DB, Playwright와 CLI 없이 두 `StockPrice`를 직접 만들어 상승·하락·변동 없음, Decimal delta, symbol 불일치와 시간 순서를 검증합니다. Business Rule이 Infrastructure에 묶여 있지 않기 때문에 가능한 테스트입니다.

`tests/google_finance/test_movement_application.py`는 실제 DB 대신 Storage 경계의 Fake를 사용해 0개·1개·2개 snapshot 계약, canonical symbol 전달, Storage 예외와 `MovementDetectionError` 전파를 확인합니다. 이 테스트는 domain 계산 자체보다 application이 두 책임을 올바르게 연결하는지를 증명합니다.

반면 `tests/google_finance/test_storage.py`와 `tests/database/test_google_finance_integration.py`는 persistence 계약을 확인합니다. MySQL integration에서는 실제 snapshot 정렬과 동일 timestamp의 `id DESC` 순서를 검증하지만, Movement 계산 규칙의 모든 경우를 DB 테스트에 맡기지는 않습니다. 각 테스트가 자신이 증명할 책임을 나누어 가지는 구조입니다.

## 얻은 것과 감수한 것

가장 큰 이점은 테스트 용이성입니다. 가격 비교는 DB나 브라우저 없이 즉시 확인할 수 있고, Storage 문제가 Movement 규칙 테스트를 막지 않습니다. 같은 domain 함수를 CLI, 이후 다른 application 흐름이나 다른 입출력 경계에서도 재사용할 수 있습니다. 또한 MySQL, selector, CLI 출력 형식 중 하나가 바뀌어도 변경 영향이 해당 계층에 머물 가능성이 커집니다.

대신 파일과 계층이 늘어났습니다. 단순한 스크립트라면 한 함수에서 조회하고 계산하고 출력할 수도 있지만, 현재는 `movement.py`, `movement_application.py`, `storage.py`, `main.py`가 나뉘어 있습니다. 작은 프로젝트에서는 이런 구조가 처음부터 과한 것처럼 보일 수 있고, 어떤 코드를 어느 계층에 둘지 판단하는 초기 시간도 필요합니다.

이 프로젝트에서는 snapshot 비교 규칙을 DB 조회와 CLI 출력에서 분리해 반복 실행하고 검증해야 했기 때문에, 늘어난 경계를 감수할 이유가 있었습니다.

## 짧은 회고

이번 구조에서 배운 점은 “domain 파일은 작게 유지해야 한다”가 아닙니다. 더 중요한 것은 변경 이유가 다른 코드를 같은 함수에 넣지 않는 것입니다. 가격 비교가 바뀌는 이유와 DB 조회가 바뀌는 이유, CLI 출력이 바뀌는 이유가 다르다면 그 차이를 코드 경계로 남겨야 이후의 판단도 분명해집니다.

## 마무리

`automation-hub`에서 Business Rule은 두 `StockPrice`의 의미를 비교하는 `movement.py`에 남아 있습니다. Storage는 snapshot을 조회하고, application은 조회와 계산을 연결하며, CLI는 사용자의 입력과 결과 표현을 담당합니다. 이 구조는 거대한 프레임워크를 도입한 결과가 아니라, 실제로 서로 다른 변경 이유를 분리한 결과입니다.

Business Rule이 Infrastructure를 몰라야 하는 이유는 Infrastructure가 중요하지 않아서가 아닙니다. 오히려 DB, 브라우저와 CLI가 바뀔 수 있기 때문에, 바뀌지 않아야 할 판단 규칙을 그 변화로부터 보호해야 합니다.

이제 다음 질문이 남습니다. 내부 Business Rule과 Infrastructure의 경계를 정했다면, 그 경계가 실제 운영 데이터와 함께 오래 유지되도록 Persistence 계약을 어떻게 설계해야 하는가?
