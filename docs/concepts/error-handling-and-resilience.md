# Error Handling, Timeout, Retry와 Resilience

이 문서는 외부 시스템이 실패했을 때 **어느 계층이 실패를 감지하고, 어떤 상태로 바꾸며,
프로세스가 무엇을 반환하는가**를 학습한다. 현재 구현과 일반적인 설계를 구분한다.

## 1. 먼저 한 문장으로

Exception은 기술적 사건을 전달하고, Domain Status는 업무 결과를 표현하며, Exit Code는
운영체제와 cron에 프로세스 결과를 전달한다.

```text
External API / Browser
        ↓
Provider / Collector exception
        ↓
Pipeline domain result
        ↓
Storage
        ↓
CLI exit code
        ↓
Wrapper / cron
```

## 2. Error, Exception, Failure, Status

“API 요청이 timeout됐다”는 기술적 failure다. 반면 “도착 예정 차량이 0대”는 요청이
성공했지만 데이터가 없는 valid empty result일 수 있다. `NO_MATCHING_ARRIVAL`은 예외가
아니라 application/domain status다.

| 상황 | 분류 | 처리 예 |
|---|---|---|
| HTTP timeout | technical failure | Provider exception |
| malformed JSON | technical/provider failure | response exception |
| API rows가 빈 list | valid empty result | 빈 tuple 또는 정상 상태 |
| `NO_MATCHING_ARRIVAL` | domain state | `BusRouteResult` status |
| route 자체 없음 | application failure | `RouteStatus.FAILED` |

## 3. try / except

다음 코드는 실패를 숨긴다.

```python
try:
    collect()
except Exception:
    pass
```

원인을 잃고 잘못된 정상 처리를 만들며 debugging과 운영 관찰을 막는다. 경계에서 이해할
수 있는 구체 예외를 잡는다.

```python
try:
    response = client.get(url, timeout=10)
except requests.Timeout as exc:
    raise ProviderError("upstream timed out") from exc
```

모든 `Exception`을 무조건 잡는 것이 정답은 아니다. 현재 repository의 process boundary나
watchlist per-item 격리처럼 의도적인 범위에서만 broad catch가 사용된다.

## 4. Custom Exception과 Boundary

현재 실제 Provider 예외는 다음처럼 boundary 의미를 가진다.

- `OdsayProviderError`: ODsay 요청/응답/정규화 실패
- `OdsayConfigurationError`, `OdsayApiError`, `OdsayRouteNotFoundError`
- `GyeonggiProviderError`: Gyeonggi 요청/응답 실패
- `GyeonggiConfigurationError`, `GyeonggiApiError`, `GyeonggiResponseError`
- `StationResolverError` 계열: station 후보/매칭 실패
- `TagoProviderError` 계열: 별도 PoC Provider 경계

Provider는 `requests.Timeout`, HTTP status와 JSON envelope를 Provider-specific exception으로
변환한다. Pipeline은 그 예외를 보고 route/realtime 상태를 정한다. CLI는 최종 process
exit code를 결정한다. 따라서 `requests.Timeout`을 Dashboard까지 그대로 던지거나 Pipeline이
HTTP 503을 직접 알아야 할 필요가 없다.

## 5. Timeout

Timeout은 외부 시스템이 영원히 응답하지 않는 상황을 작업의 실패로 제한하는 안전장치다.
연결 timeout, read timeout, 전체 작업 timeout은 서로 다른 경계다.

- ODsay/Gyeonggi Provider: `timeout=10.0` seconds 기본값
- Google News Provider: timeout을 생성자 주입
- Playwright collector: `PAGE_TIMEOUT_MS=30_000`, `goto`와 locator wait에 사용
- `run_bus_monitor.sh`: `BUS_MONITOR_TIMEOUT_SECONDS` 기본 600초, `timeout` 명령으로 child 제한

timeout이 없으면 cron process와 flock이 장시간 점유되고 다음 실행과 겹칠 수 있다. timeout은
재시도와 같지 않다. 응답을 중단할 뿐, 다시 요청할지는 별도 정책이다.

## 6. Retry와 Backoff

retry는 일시적인 network timeout이나 일시적 5xx에는 유효할 수 있지만, 잘못된 API key,
400 invalid parameter, schema 오류, DB migration 오류에는 보통 소용이 없다. 무조건 retry하면
실패를 늦추고 외부 부하와 quota를 키운다.

즉시 retry보다 다음과 같은 backoff가 외부 회복 시간을 준다.

```text
즉시: 1초, 1초, 1초
backoff: 1초, 2초, 4초, 8초
```

지터(jitter)는 여러 worker가 동시에 retry하지 않도록 지연에 무작위 변동을 더하는 일반
기법이다. 현재 ODsay/Gyeonggi production Provider에는 자동 retry/backoff/jitter가 구현되어
있지 않다. LLM runtime에는 quota와 제한된 retry 관련 구현이 있지만 이를 모든 Provider의
공통 정책으로 확대해 설명하지 않는다.

## 7. Retry Budget

retry 횟수와 총 시간을 제한해야 한다. cron job이 API timeout을 무한 retry하면 다음 실행과
겹치고, quota·lock·로그를 소모한다. 현재 wrapper의 전체 timeout과 `flock -n`은 이런 운영
위험을 제한하지만, Provider-level retry budget 자체를 구현한 것은 아니다.

## 8. Rate Limit과 Quota

- Rate limit: 짧은 시간 동안 허용되는 요청 빈도
- Quota: 일/월 또는 기간별 총 사용량

HTTP 429는 흔히 rate limit을 뜻하지만 서비스마다 quota 오류가 다른 status나 JSON code로
표현될 수 있다. 현재 repository에서 확인한 사실은 LLM runtime의 local quota ledger와
Provider별 오류 분류이며, ODsay/Gyeonggi의 수치나 계약은 이 문서에서 추측하지 않는다.

`LlmDailyQuotaExceededError`, `LlmRateLimitError`는 LLM 경계의 실제 예외다. quota 초과를
일반 네트워크 timeout처럼 retry한다고 가정하지 않는다.

## 9. Partial Success

Bus Monitor는 전체 성공/전체 실패 두 상태만 사용하지 않는다.

```text
route_status = SUCCESS
realtime_status = SUCCESS | UNAVAILABLE | NO_MATCHING_ARRIVAL
```

ODsay route는 성공했지만 Gyeonggi station/arrival 조회가 실패하면 route와 bus leg를 유지한
`UNAVAILABLE` 결과를 만든다. 사용자는 경로 정보라도 활용할 수 있고, 저장된 snapshot은
실시간 실패를 숨기지 않는다.

ODsay 자체가 실패하면 `route_status=FAILED`, `realtime_status=NOT_REQUESTED`이며 route
데이터는 없다. 이것이 partial result가 필요한 이유다.

## 10. Valid Empty Result와 Failure

Gyeonggi API가 정상 응답했지만 arrival rows가 비어 있거나 matching 차량이 없으면 예외가
아니다. 현재 Pipeline은 `NO_MATCHING_ARRIVAL`을 반환한다. 반대로 다음은 technical/config
failure다.

- HTTP 500
- malformed JSON
- timeout
- missing API key
- invalid response envelope

빈 결과를 예외로 바꾸면 “현재 차량 없음”을 장애로 오인하고 cron/알림/통계가 왜곡된다.

## 11. Fail-fast와 Fallback

API key나 `DATABASE_URL` 같은 필수 설정이 없으면 외부 호출 전에 빠르게 실패하는 것이
fail-fast다. 현재 `run_bus_monitor.sh`는 `DATABASE_URL`, `ODSAY_API_KEY`,
`GYEONGGI_SERVICE_KEY`를 확인하고 missing이면 exit 78을 반환한다.

Fallback은 primary Provider 실패 시 secondary Provider를 선택하는 별도 설계다. 현재
Bus Monitor에 ODsay→다른 route Provider 또는 Gyeonggi→TAGO 자동 fallback은 구현되어 있지
않다. TAGO PoC가 남아 있다고 production fallback으로 해석하지 않는다.

## 12. Circuit Breaker

Circuit breaker는 반복 실패 시 호출을 잠시 차단하는 일반 resilience 패턴이다.

```text
Closed → 실패 누적 → Open → 대기 → Half-open → 성공이면 Closed
```

현재 automation-hub에는 circuit breaker가 구현되어 있지 않다. 이번 문서에서는 개념과
향후 검토 지점만 설명한다.

## 13. Exit Code와 cron

Exit code `0`은 process가 성공적으로 종료되었고, non-zero는 process-level 실패를
운영체제에 알린다. Domain failure와 process failure는 항상 같지 않다.

- coordinate CLI에서 route failure는 exit 1
- persisted target 실행은 route failure snapshot을 저장해도 storage 작업이 성공하면 exit 0
- 설정/DB 오류는 main에서 exit 1
- wrapper의 missing env/invalid timeout/python 없음은 exit 78
- `flock -n`으로 이미 실행 중이면 exit 75
- timeout child 상태는 child exit status를 전달

따라서 target snapshot의 `RouteStatus.FAILED`와 cron이 관찰하는 process exit code를 같은
개념으로 섞지 않는다. cron은 Python exception을 이해하지 않고 process 종료, exit code,
stdout/stderr를 관찰한다.

## 14. flock과 운영 상태

`run_bus_monitor.sh`는 target별 lock file을 열고 `flock -n`을 시도한다. lock 획득 실패는
API 장애가 아니라 “이미 다른 process가 실행 중”인 정상적인 운영 상태이며 exit 75다.
모든 non-zero를 API 오류로 처리하면 원인 분류가 틀어진다.

## 15. DB Transaction Failure

Transaction의 일반 설명은 [SQLAlchemy 학습 문서](sqlalchemy-session-transaction-migration.md)에
있다. 오류 처리 관점에서는 Bus Monitor의 route/lane/realtime 저장 중 child row 하나가
실패하면 rollback되어 부분 DB state를 남기지 않는다는 점이 핵심이다. 이것은 Provider retry가
아니라 persistence boundary의 일관성 보장이다.

## 16. Package별 실제 차이

### Bus Monitor

ODsay/Gyeonggi Provider exception을 Pipeline status로 변환하고, route partial success를
저장한다. Provider 자동 retry/fallback은 없다.

### Google Finance

Playwright collection과 News/LLM Provider가 각각 존재한다. Watchlist application은 symbol별
실패를 격리할 수 있고, daily quota 초과는 unavailable 상태로 표현한다. 모든 symbol을
동일한 예외 전략으로 처리한다고 가정하지 않는다.

### Namuwiki

Browser collection, News Provider, LLM enrichment가 분리되어 있다. 뉴스 없음은 LLM 호출을
생략하는 정상 경로이고, generator 응답 오류는 해당 boundary에서 검증 실패로 처리한다.

## 17. 코드 읽기 훈련

Bus Monitor 오류 흐름은 다음 순서로 읽는다.

1. `bus_monitor/odsay.py`: request, timeout, response/API 예외
2. `bus_monitor/gyeonggi.py`: result code, JSON shape, normalization 예외
3. `bus_monitor/pipeline.py`: Provider exception → partial/status 변환
4. `bus_monitor/models.py`: 상태 조합과 invariant
5. `bus_monitor/main.py`: storage/config 오류와 exit code
6. `run_bus_monitor.sh`: env, timeout, flock, child status
7. 관련 tests: 실패와 정상 empty 결과 계약

각 파일에서 예외 발생·변환·처리·상태 변환·exit code 결정을 표시해 본다.

## 18. 자주 헷갈리는 것과 30초 설명

- Error와 Exception: Error는 문제의 의미, Exception은 전달되는 Python 객체다.
- HTTP Error와 API Error: HTTP status와 JSON 내부 업무 code는 별도다.
- Empty와 Failure: 빈 결과는 정상 데이터 부재일 수 있다.
- Timeout과 Retry: 시간 제한과 재시도 정책은 다르다.
- Retry와 Fallback: 같은 Provider 재호출과 다른 Provider 선택은 다르다.
- Domain Status와 Exit Code: 업무 결과와 process 결과는 다르다.

“Provider가 외부 오류를 자기 예외로 바꾸고, Pipeline이 route와 realtime의 partial 상태를
결정합니다. 정상적인 빈 arrival은 예외가 아니며, CLI와 wrapper는 별도로 exit code를
반환합니다. timeout은 무한 대기를 막고, retry는 일시 오류에만 제한적으로 사용해야 합니다.”

## 19. 이해도 체크

1. Gyeonggi timeout인데 ODsay route가 성공하면 전체 결과를 FAILED로 해야 하는가?
2. 잘못된 API key에 5회 retry가 왜 좋은 해결이 아닐 수 있는가?
3. 도착 차량 0대를 exception으로 만들면 어떤 운영 문제가 생기는가?
4. `flock` exit 75를 API 장애로 해석하면 왜 틀리는가?
5. `RouteStatus.FAILED` snapshot이 저장된 target 실행이 exit 0일 수 있는 이유는?
6. Pipeline이 `requests.Timeout`을 직접 처리하지 않는 이유는?

## 다음 읽기

- [Pipeline, Provider and Storage](pipeline-provider-storage.md)
- [SQLAlchemy Session, Transaction and Migration](sqlalchemy-session-transaction-migration.md)
- [Bus Monitor CODE_FLOW](../packages/bus_monitor/CODE_FLOW.md)
- [Cron 운영](../operations/cron.md)
