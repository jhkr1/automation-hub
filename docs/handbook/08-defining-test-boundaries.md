# Chapter 8. Fake, Integration Test와 Live Smoke Test의 경계를 정하기

Chapter 7에서는 외부 서비스가 실패하거나 데이터가 부족할 때 어떤 상태를 반환할지 정했습니다. 하지만 상태 계약을 문서에 적는 것만으로는 충분하지 않습니다. 그 계약이 외부 환경 없이도 지켜지는지, 실제 DB와 브라우저에서도 연결되는지 각각 확인해야 합니다.

`automation-hub`를 검증하면서 모든 테스트에 실제 API와 브라우저를 넣는 방법은 선택하지 않았습니다. 브라우저 DOM은 바뀔 수 있고, Google News RSS는 네트워크에 의존하며, Gemini는 인증과 quota의 영향을 받습니다. MySQL도 실행 중인 서버와 migration 상태를 요구합니다. 실제 호출은 느리고 결과가 매번 같다고 보장하기 어렵고, 무료 API 호출 자체가 비용과 제한을 만듭니다.

이번 Chapter의 질문은 다음과 같습니다.

> 외부 시스템에 의존하는 자동화를 어떤 수준에서는 Fake로 검증하고, 어떤 수준에서는 실제 DB·브라우저·API를 사용해 확인해야 하는가?

## 모든 것을 live로 검증할 수 없는 이유

자동화 코드에는 외부 시스템의 사실과 내부 규칙이 함께 들어갑니다. Google Finance의 현재 DOM이 실제로 가격을 보여주는지는 브라우저가 필요하지만, 두 가격의 차이가 상승인지 판단하는 규칙에는 브라우저가 필요하지 않습니다. 이 둘을 같은 테스트로 묶으면 작은 규칙을 확인할 때마다 브라우저와 네트워크를 기다려야 합니다.

`pytest`의 기본 실행이 외부 API에 의존하지 않도록 한 이유도 여기에 있습니다. 외부 상태 때문에 실패한 테스트는 코드 변경으로 생긴 회귀와 구분하기 어렵습니다. 따라서 테스트 수준을 나누는 것은 테스트 수를 줄이기 위한 방법이 아니라, 서로 다른 위험을 서로 다른 범위에서 확인하기 위한 선택입니다.

## 순수 규칙과 Application 판단을 빠르게 검증하기

가장 작은 범위에서 확인할 수 있는 규칙은 외부 시스템을 제거한 채 검증합니다. Google Finance의 `movement.py`가 대표적인 사례입니다. `detect_movement(latest, previous)`는 검증된 두 `StockPrice`만 받아 `Decimal` 가격 차이를 계산하고 상승·하락·변동 없음을 결정합니다.

이 테스트에는 DB, Gemini, Playwright가 필요하지 않습니다. `tests/google_finance/test_movement.py`는 방향 세 가지, 정확한 delta, symbol 불일치, 시간 순서 위반, 동일한 수집 시각을 확인합니다. 순수 함수가 입력을 변경하지 않는지도 검증합니다.

Namuwiki의 `extraction.py`도 비슷한 경계를 가집니다. 브라우저가 결과를 가져오는 일과 분리된 입력을 사용해 Top 10 개수, 순위, 링크와 목록의 끝을 확인합니다. 여기서 중요한 점은 브라우저를 흉내 내는 것이 아니라, 이미 얻은 값에 대해 내부 데이터 계약을 빠르게 검사하는 것입니다.

외부 시스템 없이 확인할 수 있는 규칙은 가장 작은 범위에서 검증합니다. 테스트가 작아질수록 실패 원인을 좁히기 쉽고, 외부 환경을 준비하지 않아도 반복 실행할 수 있습니다.

## Fake가 확인하는 것

이 Repository의 Fake는 외부 서비스를 정교하게 복제하려는 구현이 아닙니다. 상위 Application이 특정 입력과 실패에 어떻게 반응하는지 확인하기 위한 대체 객체입니다.

Namuwiki Pipeline 테스트에는 `FakeCollector`와 `FakeEnricher`가 있습니다. 이를 통해 Collector가 한 번 호출되는지, 입력 순서가 유지되는지, enrichment 실패 뒤 다음 항목을 중단하는지를 확인합니다. `TrendEnricher` 테스트의 `FakeNewsProvider`와 `FakeReasonGenerator`는 뉴스가 없을 때 Generator가 호출되지 않는지, Provider나 Generator 예외가 전파되는지를 보여줍니다.

Google Finance도 같은 경계를 사용합니다. Storage 단위 테스트에는 session fake가 있고, Movement Application에는 Fake Storage가 있습니다. Watchlist Application은 `collect_one`, `save_one`, `analyze_one` callable을 주입받아 전체 종목 순서, 일부 실패 후 계속 실행, 상태 분류와 민감정보 제거를 검증합니다.

Gemini 오류도 실제 SDK를 매번 호출하지 않습니다. `tests/google_finance/test_analysis_generator.py`는 SDK `ClientError`와 일일 quota 정보를 담은 Fake 오류를 만들어 quota 분류와 원본 메시지 미노출을 확인합니다. 이 방식은 호출 순서, Generator 미호출, 예외 전파와 실패 격리를 빠르게 증명합니다.

따라서 Fake 테스트의 질문은 “가짜 서비스가 실제 서비스와 똑같은가?”가 아닙니다. “이 외부 의존성이 이런 결과를 반환하거나 실패했을 때 Application의 정책이 올바르게 실행되는가?”가 질문입니다.

## 격리된 테스트가 확인하지 못하는 것

순수 규칙 테스트와 Fake 기반 Application·CLI 테스트가 통과해도 다음 사실까지 증명하지는 못합니다.

- 현재 Google Finance DOM에서 selector가 유효한가
- 브라우저가 실제 rendered page를 받을 수 있는가
- Google News RSS가 현재 코드가 기대하는 형식인가
- Gemini model 접근 권한과 API key가 유효한가
- 실제 quota가 남아 있는가
- MySQL dialect, index와 migration이 실제 서버에서 일치하는가
- Docker network와 port가 실행 환경에서 연결되는가

Google Finance Collector 테스트의 Fake Playwright graph는 browser, context, page cleanup과 locator 경계를 확인합니다. 하지만 Google이 다음 날 DOM을 변경했는지는 알려주지 못합니다. Namuwiki의 RSS Fake도 XML parsing 계약은 확인하지만 실제 Google News 응답의 변화를 보장하지 않습니다.

이 한계를 인정해야 격리된 테스트의 통과를 실제 Provider의 정상 동작으로 과장하지 않게 됩니다. 반대로 모든 것을 live로 옮기면 작은 내부 규칙의 회귀도 외부 서비스가 준비되지 않아 확인할 수 없게 됩니다.

## 실제 DB 경계를 확인하는 Integration Test

Google Finance의 MySQL 테스트는 Fake Session 테스트와 다른 질문을 다룹니다. `tests/database/test_google_finance_integration.py`는 migration된 실제 테이블에 snapshot을 저장하고, 다시 읽어 `StockPrice`로 복원하는 저장·조회 계약을 확인합니다.

동일 시각의 정렬과 symbol 격리, Movement 연결도 실제 DB에서 확인합니다. 핵심은 여러 모듈을 묶는 데 있지 않고, Domain Model과 데이터베이스 사이의 저장 경계와 결정적인 조회 순서를 검증하는 데 있습니다.

기본 실행에서는 `RUN_DB_INTEGRATION=1`이 아닐 때 이 테스트를 skip합니다. 실행하려면 MySQL과 `DATABASE_URL`, migration 상태가 준비되어야 합니다. `scripts/verify.py`는 빠른 기본 검증을 유지하기 위해 이 조건을 자동으로 만들지 않습니다.

선택 실행은 실제 계약을 포기한다는 뜻이 아닙니다. 개발자의 로컬 환경마다 Docker, port와 데이터베이스가 다를 수 있기 때문에, 환경이 없는 상황을 코드 결함으로 오해하지 않기 위한 경계입니다. 다만 skip된 테스트는 실제 MySQL 동작을 증명하지 않습니다. DB 변경이나 저장 계약을 다룬 뒤에는 별도로 Integration Test를 실행하고 결과를 확인해야 합니다.

## 외부 경로를 확인하는 Live Smoke Test

Live Smoke Test는 모든 입력과 실패 조합을 증명하는 테스트가 아닙니다. 실행 시점의 외부 경로가 최소 한 번 끝까지 연결되는지 확인하는 점검입니다.

Google Finance에서는 실제 quote를 수집하고 snapshot을 저장한 뒤 Movement를 조회합니다. 이후 Google News RSS와 Gemini를 연결해 `StockInsight`까지 만드는 단일 종목 흐름을 확인할 수 있습니다. Watchlist collect와 analyze의 quota 정책은 특정 실행 시점의 live 점검에서 확인된 사실이며, 이후에도 항상 동일하게 성공한다는 보장은 아닙니다.

Namuwiki에서는 rendered page에서 Top 10을 수집하고 Google News RSS를 거쳐 Gemini reason을 만든 뒤 JSON Storage에 저장하는 흐름이 대상입니다. 현재 DEV_LOG에는 Namuwiki의 단일 Gemini live 호출이 Free Tier 일일 quota 초과로 실패한 기록이 있습니다. 이 기록은 Top 10 전체 production flow의 결과가 아니라, 당시 외부 조건에서 해당 호출이 완료되지 않았다는 사실로 한정해 읽어야 합니다.

Live 테스트는 다음 날에도 같은 결과를 보장하지 않습니다. DOM, RSS, model access, API quota와 네트워크가 변할 수 있기 때문입니다. 그러므로 live 성공은 실행 시점의 외부 연결을 확인하는 증거이지, 영구적인 품질 보증이 아닙니다.

## 실패 계약을 테스트하기

Chapter 7에서 정의한 실패 계약은 정상 경로보다 오히려 Fake와 선택적 Integration Test에서 더 구체적으로 확인할 수 있습니다.

Google Finance 테스트는 snapshot 부족을 `MovementUnavailable`로 반환하고, 뉴스 0건에서 Generator를 호출하지 않으며, 일일 quota 오류 뒤 후속 Gemini 호출을 생략하는지를 확인합니다. Watchlist CLI 테스트는 정상 결과를 stdout에, 실제 실패를 stderr에 출력하는지와 exit code를 확인합니다. Fake 오류에 API key나 traceback을 넣어도 안전한 요약에 포함되지 않는지도 검증합니다.

Namuwiki 테스트는 뉴스가 없을 때 fallback reason을 만들고 Generator를 호출하지 않는지, Pipeline이 Collector와 Enricher 오류에서 fail-fast하는지 확인합니다. Gemini Generator 테스트는 429 `RESOURCE_EXHAUSTED`와 RetryInfo가 있는 상황에서 제한된 재시도 경계를 확인합니다. JSON Storage 테스트는 저장 실패가 조용히 성공으로 바뀌지 않는지 확인합니다.

이 테스트들은 오류가 발생했다는 사실만 확인하지 않습니다. 그 오류를 unavailable로 반환할지, 다음 항목을 계속할지, 사용자에게 어떤 종료 코드와 출력으로 전달할지를 검증합니다.

## 테스트 결과를 해석하기

이 프로젝트의 검증 명령은 서로 다른 범위를 가집니다.

```text
pytest
    → 내부 규칙과 Application 계약

Ruff
    → 정적 규칙과 코드 품질 검사

compileall
    → Python 문법과 컴파일 가능성

git diff --check
    → whitespace 오류

RUN_DB_INTEGRATION=1 pytest
    → 실제 MySQL 저장·조회 경계

Live Smoke Test
    → 실행 시점의 브라우저·RSS·Gemini 연결
```

앞의 네 명령은 모두 같은 의미의 계약 테스트가 아닙니다. `pytest`가 통과했다는 것은 Fake와 내부 규칙, Application 분기가 계약에 맞는다는 뜻입니다. DB Integration Test가 통과하면 실제 MySQL에서 migration, 저장, 조회와 변환이 맞았다는 근거가 추가되고, Live Smoke Test가 성공하면 해당 시점의 외부 경로가 연결되었다는 근거가 됩니다.

반대로 live 실패가 곧 코드 결함은 아닙니다. API quota, DNS, 네트워크 권한, credential, model access, DOM 변경과 migration 미적용이 모두 가능한 원인입니다. 실제 실패를 코드 문제와 환경 문제로 나누려면, 먼저 기본 자동화 테스트와 필요한 Integration Test의 결과를 함께 봐야 합니다.

## Test Pyramid를 억지로 적용하지 않기

현재 Repository의 테스트 수와 실행 빈도는 각 위험에 맞춰 다릅니다. 이 비율을 일반 공식에 맞추는 것이 목표는 아닙니다.

중요한 것은 위험과 테스트 범위의 대응입니다. 외부 의존성이 없는 규칙은 격리된 테스트로, DB 저장 계약은 실제 MySQL로, Provider와 브라우저의 현재 연결은 제한된 live 점검으로 확인합니다. 테스트 층의 비율보다 어떤 사실을 어느 수준에서 확인할지 결정하는 일이 우선입니다.

## 얻은 것과 감수한 것

이 경계를 두면서 기본 검증은 빠르게 유지하고, 외부 서비스 없이 Application 정책을 반복해서 확인할 수 있게 되었습니다. 동시에 실제 DB 계약과 live Provider 연결도 별도의 증거로 확보할 수 있습니다. 실패 상태, 후속 호출 중단, 안전한 출력 같은 운영 계약을 회귀 테스트로 남길 수 있다는 점도 얻었습니다.

대신 Fake와 production wiring 사이의 차이는 남습니다. Integration 환경을 준비하는 비용이 있고, live 결과는 비결정적이며 quota를 소비합니다. 모든 외부 조합을 자동으로 검증할 수도 없습니다. 특히 skip된 DB 테스트는 실제 DB 동작을 증명하지 않으므로, 실행하지 않은 검증을 통과한 것처럼 해석해서는 안 됩니다.

## 짧은 회고

처음에는 테스트를 많이 작성하면 자동화가 신뢰할 수 있게 된다고 생각하기 쉽습니다. 실제로는 테스트 수보다 각 테스트가 어떤 위험을 확인하는지가 더 중요했습니다. 외부 시스템 없이 확인할 수 있는 규칙은 작게 고정하고, 외부 시스템의 현재 상태는 별도의 Integration과 Live 경계에서 확인해야 했습니다.

## Handbook을 마치며

이 Handbook은 업무 자동화를 Python 시스템으로 다시 설계하는 문제에서 시작해 Package Boundary, 내부 데이터 계약, Business Rule, Persistence, Provider Orchestration, 실패 계약과 테스트 경계까지 이어졌습니다. 두 Package는 같은 구조를 복사하기 위한 예제가 아니라, 서로 다른 외부 문제에서 설계 판단을 연습하기 위한 사례였습니다.

자동화 시스템의 신뢰성은 테스트를 많이 작성하는 데서 끝나지 않습니다. 어떤 사실을 어느 테스트 수준에서 확인할지 선택하고, 각 결과가 증명하는 범위를 과장하지 않는 데서 만들어집니다.
