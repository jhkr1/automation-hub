# Chapter 7. 외부 서비스 실패와 API 제한을 운영 가능한 상태로 다루기

Chapter 6에서는 Browser, News Provider, Gemini, Storage를 하나의 Application Flow로 연결했습니다. 그러나 흐름이 연결되었다고 해서 운영 문제가 사라지는 것은 아닙니다. 브라우저가 페이지를 읽지 못할 수도 있고, 뉴스는 정상적으로 조회했지만 결과가 없을 수도 있습니다. Gemini는 호출 자체가 실패하거나, 무료 사용량 한도를 모두 사용했을 수도 있습니다.

이때 모든 상황을 같은 Exception으로 처리하면 사용자는 무엇을 다시 시도해야 하는지 알 수 없습니다. 반대로 모든 상황을 성공으로 표시하면 불완전한 결과가 정상 결과처럼 보입니다. 이번 Chapter의 질문은 다음과 같습니다.

unavailable은 하나의 동일한 성공 상태가 아닙니다. 데이터 부족처럼 정상 종료되는 상태와, 분석 목적을 달성하지 못해 실패 코드로 종료되는 상태가 함께 존재합니다.

> 외부 서비스가 실패하거나 데이터가 부족할 때, 어떤 상황을 정상적인 unavailable 상태로 표현하고 어떤 상황을 시스템 실패로 처리해야 하는가?

## 모든 실패를 하나의 Exception으로 다룰 수 없는 이유

`automation-hub`에서 “결과를 만들 수 없다”는 말은 여러 상황을 가리킵니다. Google Finance에 snapshot이 하나뿐인 경우와 DB 연결이 끊긴 경우는 모두 분석 결과를 만들지 못하지만, 첫 번째는 아직 이력이 부족한 상태이고 두 번째는 시스템이나 외부 환경의 실패입니다.

이 차이를 판단할 때는 오류 이름보다 실행 과정 전체를 봐야 합니다.

- 요청과 입력이 정상적으로 처리되었는가
- 결과를 만들기 위한 데이터가 충분한가
- 외부 Provider가 정상 응답했는가
- 결과를 만들 수 없는 상태가 예상 가능한가
- 재실행이나 사용자 조치가 필요한가

이 질문을 기준으로 현재 Repository의 상태를 세 범주로 나눌 수 있습니다. 정상적으로 처리했지만 조건이 부족한 `unavailable`, 잘못된 입력이나 설정 오류, 그리고 외부 시스템 또는 코드의 실제 실패입니다. 세 범주는 같은 Enum으로 통합되지 않지만, 운영자는 서로 다른 대응을 선택할 수 있어야 합니다.

## 정상적인 unavailable 상태

### MovementUnavailable

Google Finance의 Movement 계산에는 같은 종목의 최신 snapshot과 이전 snapshot이 모두 필요합니다. `get_latest_two()`가 0개 또는 1개를 반환하면 비교할 데이터가 부족합니다. 이때 `movement_application.py`는 예외를 발생시키지 않고 `MovementUnavailable(symbol, snapshot_count)`를 반환합니다.

두 개 이상이면 `[newest, previous]` 순서로 `detect_movement()`를 호출합니다. 따라서 snapshot이 부족한 상태와 Movement 계산 중 symbol 불일치나 시간 순서 위반이 발생한 상태는 다릅니다. 전자는 정상적인 Application 상태이고, 후자는 계약 위반에 가까운 실패입니다.

단일 종목 CLI의 `--show-movement`는 `MovementUnavailable`을 stdout에 안내하고 exit code 0으로 종료합니다. Watchlist에서도 같은 상태를 실패 종목으로 세지 않습니다. 아직 비교할 이력이 없다는 사실이 곧 프로그램 실행 실패를 의미하지 않기 때문입니다.

### 뉴스 0건

뉴스 0건은 명시적인 unavailable 결과가 아닙니다. Namuwiki의 `TrendEnricher`와 Google Finance의 `analyze_stored_quote()`는 뉴스 Provider 요청이 성공했지만 목록이 비어 있는 경우, Gemini를 호출하지 않고 근거 부족 fallback으로 정상 결과 모델을 만듭니다. Google Finance에서는 `StockInsight`, Namuwiki에서는 `TrendInsight`가 생성됩니다.

뉴스 0건은 네트워크 오류나 RSS 파싱 오류와 다릅니다. 요청은 끝났고, 현재 분석에 사용할 문맥이 없다는 결과를 받았기 때문입니다. 근거 없이 LLM을 호출하지 않으면 불필요한 비용과 추측성 응답을 줄일 수 있습니다. 반대로 Provider가 HTTP 오류를 내거나 XML을 파싱하지 못하면 현재 코드에서는 예외가 호출자에게 전달됩니다.

## 사용자·설정 오류와 시스템 실패

잘못된 symbol, 빈 Watchlist, `DATABASE_URL` 누락, `GEMINI_API_KEY` 누락은 사용자가 실행 환경을 고쳐야 하는 설정 문제입니다. argparse 옵션을 충돌시킨 경우에는 Python의 argument parser가 사용 오류로 처리하고 exit code 2를 반환합니다. Watchlist의 설정 오류는 안전한 설정 오류 메시지와 exit code 1로 처리합니다.

Collector 실패, DB 연결 실패, News Provider 네트워크 오류, RSS 파싱 오류, Gemini의 일반 `ClientError`, JSON 저장 실패는 시스템 또는 외부 Provider 실패입니다. 이 경우 결과를 정상적인 unavailable로 바꾸면 원인을 숨기게 됩니다. 특히 DB에 접근하지 못한 것을 “snapshot이 없다”고 표시하면 사용자는 데이터가 정말 없는지 연결이 실패한 것인지 구분할 수 없습니다.

## 일일 quota를 재시도로 해결할 수 없는 이유

Google Finance Watchlist에서 확인한 일일 Gemini quota 오류는 단순히 요청 사이에 잠시 기다리면 해결되는 종류가 아닙니다. 실제 분류 조건은 HTTP 429, `RESOURCE_EXHAUSTED`, 그리고 `GenerateRequestsPerDayPerProjectPerModel-FreeTier` 같은 일일 요청 제한 정보입니다.

이 오류가 발생하면 Watchlist는 자동 재시도하지 않습니다. 첫 종목에서 Gemini 호출이 일일 quota 오류를 반환하면 `analyze_watchlist()`는 실행 범위 안에서 quota 상태를 기억합니다. 현재 종목은 일일 quota로 분석할 수 없는 구조화된 상태로 반환하고, 이후 종목은 Gemini를 호출하지 않은 채 같은 unavailable 상태로 반환합니다.

```text
첫 quota 오류
    ↓
ANALYSIS_UNAVAILABLE / DAILY_QUOTA_EXHAUSTED
    ↓
현재 실행의 gemini_available = False
    ↓
후속 Gemini 호출 생략
```

첫 실패 종목은 이미 계산한 Movement와 뉴스 개수를 결과에 보존할 수 있습니다. 후속 종목은 호출을 생략하는 시점이 더 이르므로, 해당 정보가 없는 unavailable 결과가 됩니다. Google Finance Watchlist는 원본 SDK 오류, API key, URL과 traceback을 사용자 출력에 포함하지 않고 안전한 요약만 보여줍니다.

모든 429를 일일 quota로 단정하지도 않습니다. Retry-After나 retry delay가 있다고 해서 이번 실행에서 자동 재시도해야 한다는 뜻은 아닙니다. 일일 quota가 아닌 429와 일반 ClientError는 현재 Watchlist의 일반 분석 실패 정책을 따르며, 복잡한 retry framework는 구현하지 않습니다.

Namuwiki의 `GeminiReasonGenerator`는 일부 429 `RESOURCE_EXHAUSTED`에 대해 제한적인 재시도를 수행합니다. SDK의 `RetryInfo`에 있는 지연 시간이나 설정된 backoff를 사용하고, 재시도 횟수도 제한합니다. 그러나 Google Finance처럼 일일 quota marker를 별도로 판별하지 않으므로, Namuwiki에서는 일일 quota 소진도 일반적인 429 재시도 경로에 들어갈 수 있습니다. 두 Package의 정책을 억지로 통합하지 않고, Provider와 사용 목적에 따라 실패 계약을 따로 유지하는 이유입니다.

## fail-fast와 종목별 실패 격리

Namuwiki의 기본 `TrendPipeline`은 수집한 목록을 순차적으로 `TrendEnricher`에 전달합니다. 한 항목에서 Enricher 오류가 발생하면 리스트 생성이 중단되고, `namuwiki_trend.main`은 stderr에 오류를 출력하며 exit code 1을 반환합니다. 전체 Top 10 중 일부만 JSON에 저장하는 부분 성공은 현재 구현되어 있지 않습니다.

이 fail-fast 선택은 결과 전체가 하나의 완전한 묶음이어야 할 때 의미가 있습니다. 불완전한 Top 10을 정상 파일로 남기지 않고, 실패 위치를 빠르게 확인할 수 있기 때문입니다. 대신 한 검색어의 오류가 전체 실행과 저장을 막는 비용이 있습니다.

Google Finance Watchlist는 다른 판단을 합니다. 종목별 결과가 독립적으로 가치가 있으므로 한 종목의 Collector, Storage, News 또는 Gemini 실패 후에도 다음 종목을 계속 실행합니다. 성공 결과는 유지되고 각 종목의 상태가 집계됩니다. 다만 하나 이상의 실제 실패가 있으면 전체 exit code는 1입니다. 부분 결과를 보여주는 것과 전체 명령이 성공했다는 것은 다른 판단이기 때문입니다.

어느 정책이 항상 옳은 것은 아닙니다. 결과가 완전한 묶음이어야 하는지, 항목별 결과를 독립적으로 사용할 수 있는지, 부분 결과를 안전하게 설명할 수 있는지에 따라 실패 영향 범위를 정해야 합니다.

## stdout, stderr와 exit code 계약

CLI에서 출력 위치와 종료 코드는 서로 다른 정보를 전달합니다. 정상적인 quote, Movement 결과, `MovementUnavailable`, Watchlist의 `ANALYSIS_UNAVAILABLE` 상태는 사용자가 읽을 수 있는 결과이므로 stdout으로 출력합니다. DB 오류나 Collector 실패처럼 명령 자체가 실패한 경우는 stderr로 보냅니다.

`ANALYSIS_UNAVAILABLE`은 stdout에 상태와 reason을 보여주지만 exit code는 1입니다. 상태는 구조화된 결과로 사용자에게 설명할 수 있지만, `--analyze` 명령의 핵심 결과인 `StockInsight`가 생성되지 않았기 때문입니다. 반면 `MovementUnavailable`은 분석을 시도할 이력이 부족한 정상 상태이므로 exit code 0을 유지합니다.

argparse의 사용법 오류는 exit code 2이고, 설정 오류와 실행 중 실패는 현재 각 CLI 계약에 따라 non-zero code를 반환합니다. 이 구분을 두면 운영 스크립트는 화면 문장을 해석하지 않고도 명령 성공 여부를 판단할 수 있습니다.

## 오류 정보를 어디까지 보여줄 것인가

외부 SDK 오류를 그대로 출력하면 API key, 요청 URL, 내부 프로젝트 정보, credential 일부가 메시지에 포함될 수 있습니다. 또한 SDK의 원본 응답은 사용자에게 필요한 정보보다 훨씬 많은 내부 진단 정보를 담을 수 있습니다.

현재 Google Finance Watchlist는 종목, 단계, 예외 타입처럼 안전한 요약만 결과에 보존합니다. quota 오류도 원본 `ClientError` 전문 대신 `DAILY_QUOTA_EXHAUSTED`라는 명시적 reason으로 표현합니다. 개발자가 별도 진단을 수행하는 경로와 일반 사용자가 보는 CLI 출력을 나누는 방식입니다.

Namuwiki와 Google Finance의 process boundary는 모두 stderr와 non-zero exit code를 사용하지만, 오류 문자열을 숨기는 정도는 완전히 같지 않습니다. 단일 Google Finance CLI와 Namuwiki CLI에서는 일부 예외 문자열이 그대로 stderr에 출력될 수 있으며, Watchlist와 같은 안전한 요약 계약은 전역 적용되지 않았습니다. 따라서 패키지와 CLI별 실제 출력 계약을 따로 확인해야 합니다.

## 명시적인 상태 모델의 가치

문자열 하나만 반환하는 방식으로는 정상 결과와 비교 불가, 분석 불가, 실제 실패를 안정적으로 구분하기 어렵습니다.

```text
“분석할 수 없습니다”
    → 호출자가 문자열을 다시 해석해야 함

ANALYSIS_UNAVAILABLE + DAILY_QUOTA_EXHAUSTED
    → Application과 CLI가 명시적으로 분기 가능
```

이 비교를 실제 타입으로 표현한 것이 `MovementUnavailable`, `WatchlistAnalysisStatus`, `WatchlistAnalysisUnavailableReason`입니다.

이 타입들은 모든 Package가 공유해야 하는 공통 Exception 체계가 아닙니다. Google Finance의 snapshot과 Watchlist 실행에 필요한 계약입니다. Namuwiki는 현재 `TrendInsight`와 Pipeline 예외 전파를 중심으로 다른 계약을 유지합니다.

명시적인 상태 모델이 있으면 Application은 “다음 종목을 계속할지”를 판단하고, CLI는 “stdout에 상태를 표시할지 exit code를 1로 만들지”를 별도로 결정할 수 있습니다. 데이터와 실행 결과의 의미를 문자열 비교에 맡기지 않는 것이 핵심입니다.

## 얻은 것과 감수한 것

현재 설계로 정상적인 unavailable과 실제 실패를 구분할 수 있게 되었습니다. Google Finance Watchlist에서는 종목별 실패를 격리하고, 일일 quota가 소진되면 후속 Gemini 호출을 막으며, 민감한 오류 원문을 숨깁니다. 운영 스크립트는 exit code로 전체 명령의 성공 여부를 판단할 수 있습니다.

대신 상태 모델과 CLI 분기가 늘어났고, 일부 종목의 결과가 존재해도 전체 명령은 실패할 수 있습니다. Provider 실패 단계를 항상 정밀하게 구분할 수 있는 것도 아닙니다. quota가 소진된 경우에는 가격과 뉴스 metadata가 남아도 최종 `StockInsight`는 생성되지 않습니다. 명확한 운영 상태를 얻기 위해 복잡성을 감수한 것입니다.

## 짧은 회고

실패를 다루면서 배운 점은 예외를 많이 만드는 것보다, 실패가 의미하는 상태를 먼저 정해야 한다는 사실입니다. 데이터가 부족한 경우와 외부 서비스가 고장 난 경우를 구분해야 사용자에게 필요한 다음 행동도 달라집니다.

## 마무리

Chapter 6에서 여러 외부 Provider를 하나의 흐름으로 연결했습니다. Chapter 7에서는 그 흐름이 실패했을 때 모든 오류를 성공 또는 Exception 하나로 뭉개지 않고, 데이터 부족·설정 오류·외부 실패·일일 quota 상태를 각 실행 목적에 맞게 표현했습니다.

이제 남은 질문은 이 실패 계약이 실제 외부 환경에서도 지켜지는지 어떻게 확인할 것인가입니다. Fake Exception, Integration Test, live smoke test를 어떤 경계에서 사용해야 하는지는 다음 Chapter에서 다룹니다.
