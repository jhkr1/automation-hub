# Testing, Test Double과 Integration 경계

이 문서는 “실제 API나 DB를 매번 호출하지 않고도 왜 코드가 동작한다고 믿는가?”를
설명한다. 테스트는 버그가 없음을 증명하는 마법이 아니라, 특정 조건에서 코드가 약속한
동작을 하는지 검증하는 증거다.

## 1. 무엇을 검증하는가

테스트는 입력, 경계, 기대 결과를 명시한다. Fake HTTP test가 통과하면 parsing과 내부
계약을 검증하지만 실제 ODsay 서버의 가용성이나 API key가 유효하다는 뜻은 아니다.

```text
Code correctness        ≠ External system availability
```

테스트가 많다고 무조건 좋은 것은 아니다. 같은 경로만 반복하기보다 중요한 정상·오류·빈
결과·부분 성공 branch를 빠르고 재현 가능하게 검증하는 것이 중요하다.

## 2. Test Pyramid와 Boundary

일반적인 개념은 다음과 같다.

```text
많음 / 빠름       Unit Test
중간              Integration Test
적음 / 느림       E2E / Live Test
```

이는 절대 법칙이 아니라 비용과 신뢰 범위를 생각하는 모델이다. 핵심 질문은 “이 테스트가
어느 boundary까지 실제로 검증하는가?”다.

## 3. Unit Test와 Pure Function

Unit Test는 단순히 함수 하나가 아니라, 외부 의존성을 통제한 작은 동작 단위를 검증한다.

```python
def calculate_minutes(seconds: int) -> int:
    return seconds // 60


def test_calculate_minutes() -> None:
    assert calculate_minutes(322) == 5
```

순수 함수는 같은 입력에 같은 출력을 내고 외부 상태를 바꾸지 않아 테스트하기 쉽다.
현재 repository의 `arrival_matcher`, model validation, provider normalization과 query
helper도 외부 호출 없이 이런 경계를 검증한다. 순수 함수가 아니어도 dependency를 주입해
작은 경계를 만들 수 있다.

## 4. Test Double

Test Double은 테스트에서 실제 객체 대신 사용하는 대역의 총칭이다.

- Dummy: 호출을 채우기 위한 값
- Stub: 미리 정한 값을 반환
- Fake: 동작하는 간단한 구현
- Mock: 호출/상호작용을 관찰하고 검증

라이브러리와 팀마다 용어가 조금씩 다르므로 이름보다 테스트 목적을 먼저 본다.

### Stub

```python
class StubWeatherProvider:
    def get_weather(self) -> str:
        return "sunny"
```

결과에 집중할 때 유용하며 호출 횟수 자체를 검증하는 것이 주목적은 아니다.

### Fake

Fake는 실제 계약을 만족하는 작고 실행 가능한 구현이다. `tests/bus_monitor/test_pipeline.py`
의 실제 `FakeRouteProvider`, `FakeGyeonggiProvider`는 API를 호출하지 않고 route, station
route, arrival을 반환하며 호출 목록도 기록한다.

```text
Production: BusMonitorPipeline → OdsayRouteProvider → GyeonggiProvider
Test:       BusMonitorPipeline → FakeRouteProvider → FakeGyeonggiProvider
```

이것이 DI가 테스트 가능성과 직접 연결되는 사례다.

### Mock

Mock은 “`search_route()`가 정확히 한 번 호출되었는가?”처럼 상호작용을 검증할 때 적합하다.
현재 repository는 `unittest.mock`의 Mock/MagicMock보다 pytest `monkeypatch`와 자체 Fake를
주로 사용한다. Mock이 Fake보다 항상 좋은 것은 아니며 결과 검증과 interaction 검증 중
무엇이 목적이냐에 따라 선택한다.

## 5. monkeypatch와 Fixture

`monkeypatch`는 테스트 동안 속성·환경변수·함수를 임시 교체하고 테스트 종료 후 원래 상태로
복원하는 pytest 도구다.

```python
def fake_get(*args, **kwargs):
    return FakeResponse()

monkeypatch.setattr(module.requests, "get", fake_get)
```

현재 tests는 `watchlist_main.Settings`, storage, application 함수를 `monkeypatch`로
교체하고, `tmp_path`로 임시 파일을 사용한다. Fixture는 반복되는 sample model, Fake,
DB session, temporary path를 setup 함수로 재사용하는 방식이다. Fixture와 Mock은 다른
개념이다. Fixture는 준비/수명 관리이고 Mock은 대역의 한 종류다.

## 6. Arrange / Act / Assert와 assert

테스트를 읽는 기본 순서는 다음이다.

```python
def test_empty_arrival_is_normal_state() -> None:
    # Arrange: Fake Provider가 route만 지원하고 arrival은 빈 tuple을 반환
    # Act: pipeline.run(...)
    # Assert: route SUCCESS, realtime NO_MATCHING_ARRIVAL
    assert result.route_status is RouteStatus.SUCCESS
    assert result.realtime_status is RealtimeStatus.NO_MATCHING_ARRIVAL
```

`assert`는 단순 boolean이 아니라 expected behavior를 코드로 남기는 계약이다.

`pytest.raises`는 예외가 올바른 동작인 경우를 검증한다.

```python
with pytest.raises(ValueError):
    RealtimeArrival(route_id="", route_number="5600", arrival_seconds=10, remaining_stops=1)
```

`pytest.mark.parametrize`는 같은 규칙에 여러 입력을 적용할 때 중복을 줄인다. 모든 테스트를
무리하게 parameterize할 필요는 없다.

## 7. HTTP Provider Test

현재 Gyeonggi/ODsay 테스트는 실제 네트워크 대신 Fake HTTP client와 prepared payload를
사용한다.

```text
Fake HTTP Client
      ↓
Prepared JSON
      ↓
Provider
      ↓
Domain Model
```

검증하는 것:

- endpoint와 parameter
- timeout 전달
- JSON envelope parsing
- result code/error handling
- normalization

검증하지 않는 것:

- 실제 인터넷
- 실제 API key
- 실제 provider availability

## 8. Browser Collector Test

`tests/google_finance/test_collector.py`는 실제 Chromium을 실행하지 않는다. FakePage,
FakeLocator, FakeBrowser, FakeContext, FakePlaywright를 제공해 `goto`, locator 추출,
cleanup 계약을 검증한다. 즉 selector와 Browser 경계의 코드 동작은 확인하지만 실제 Google
Finance DOM이 현재 살아 있다는 것은 확인하지 않는다.

## 9. Integration Test

Integration Test는 함수 여러 개를 묶는다는 뜻보다, 실제 구성요소 사이의 계약을 검증하는
테스트다.

`tests/database/test_bus_monitor_integration.py`는 `RUN_DB_INTEGRATION=1`일 때 실제 MySQL,
SQLAlchemy, migration schema, FK, transaction을 함께 확인한다. 기본 실행에서는 skip된다.
Integration이 잡을 수 있는 문제는 실제 SQL dialect, datatype, FK, rollback, migration
mismatch다. 대신 느리고 DB 환경과 data cleanup에 의존한다.

## 10. E2E, Smoke, Live Test

E2E는 사용자 입력부터 Application, External System, DB, 출력까지 전체 흐름을 검증한다.
현재 repository가 완전한 자동 E2E suite를 갖췄다고 추측하지 않는다.

Smoke Test는 깊은 정확성보다 핵심 기능이 최소한 살아 있는지 빠르게 확인한다. 현재 사례는
Dashboard `AppTest`, wrapper 실행, migration round-trip, 실제 Provider 수동 smoke test다.

Live Test는 실제 ODsay, Gyeonggi, Google Finance, Namuwiki 같은 external service를 호출한다.
실제 계약을 확인하지만 느리고 network, quota, API key, 시간 변화에 의존하며 flaky할 수 있다.

## 11. 왜 pytest가 Live API를 기본 호출하지 않는가

모든 pytest가 실제 API를 호출하면 다음 문제가 생긴다.

- quota와 비용 소모
- 느린 전체 suite
- network 장애로 인한 flaky test
- 실제 운영 데이터 오염
- 시간에 따라 달라지는 arrival/quote 결과

그래서 기본 suite는 Fake와 fixture를 사용하고, Live/Integration은 명시적인 환경 조건으로
분리한다.

## 12. Isolation, Determinism, Coverage

Test Isolation은 한 테스트의 DB, 파일, 환경변수, global state가 다른 테스트에 영향을 주지
않는다는 뜻이다. `tmp_path`, `monkeypatch`, 독립 Fake가 이를 돕는다.

Deterministic Test는 같은 입력에서 예측 가능한 결과를 내야 한다. 실시간 arrival을 Unit
Test에서 직접 조회하면 이 조건을 잃는다.

Coverage는 실행된 코드 비율을 보여주는 지표일 뿐 100%가 bug 없음이라는 뜻은 아니다.
현재 repository는 별도 coverage tool을 verification에 포함하지 않으며, branch와 오류
계약을 우선 확인한다.

## 13. scripts/verify.py

현재 `scripts/verify.py`는 다음을 순서대로 실행한다.

```text
ruff check .
pytest -q
python -m compileall bus_monitor google_finance namuwiki_trend tests
git diff --check
```

- Ruff: style/static quality
- pytest: behavior
- compileall: syntax/import compile
- git diff --check: whitespace 오류

각 도구는 서로 대체되지 않는다. pytest가 통과해도 syntax compile이나 diff whitespace
검증을 생략할 수 없고, Ruff가 통과해도 behavior를 증명하지 않는다.

## 14. Skip의 의미

현재 기본 verification은 DB 환경 flag가 없어 integration test가 skip되어
`569 passed, 8 skipped` 형태가 될 수 있다. `tests/database/test_integration.py`는
`RUN_DB_INTEGRATION=1`일 때 MySQL을 대상으로 실행된다.

Skip은 환경 의존 테스트를 기본 suite에서 분리하는 정상적인 선택일 수 있지만, 핵심 검증이
영원히 skip되는지와 skip 이유를 주기적으로 확인해야 한다.

## 15. DI·Error Handling·Database와 Testing

- DI: Pipeline에 Real Provider 대신 Fake를 주입한다.
- Error Handling: timeout, malformed response, empty result, partial success, config error를
  각각 검증한다.
- Database: Unit은 mapping logic, Integration은 실제 MySQL의 FK/transaction/rollback을
  검증한다.

따라서 테스트는 별도 활동이 아니라 Architecture, Error Boundary, Persistence 설계를
확인하는 방법이다.

## 16. 코드 읽기 순서

1. `bus_monitor/pipeline.py`
2. `tests/bus_monitor/test_pipeline.py`
3. `bus_monitor/gyeonggi.py`
4. `tests/bus_monitor/test_gyeonggi.py`
5. `bus_monitor/storage.py`
6. `tests/bus_monitor/test_storage.py`
7. `tests/database/test_bus_monitor_integration.py`

각 테스트에서 Arrange/Act/Assert, Real dependency 여부, Fake 구성, 검증 범위와 미검증
범위를 표시한다.

## 17. 자주 헷갈리는 것과 30초 설명

- Unit vs Integration: 작은 통제 경계 vs 실제 구성요소 계약
- Integration vs E2E: 일부 시스템 연결 vs 사용자 전체 흐름
- Smoke vs E2E: 핵심 생존 확인 vs 깊은 전체 검증
- Fake vs Mock: 간단한 구현/결과 vs interaction 검증
- Fixture vs Mock: setup 수명 관리 vs 대역 객체
- pytest pass vs Live availability: 코드 계약 통과 vs 외부 서비스 현재 상태

“기본 테스트는 Fake와 fixture로 빠르고 결정적으로 동작을 검증하고, Integration은 실제
DB 계약을, Live Smoke는 실제 외부 서비스와 실행 환경을 확인합니다. DI가 있어 Real
Provider를 Fake로 바꿀 수 있고, `verify.py`는 style·behavior·compile·diff를 각각 확인합니다.”

## 18. 이해도 체크

1. FakeGyeonggiProvider 테스트가 PASS해도 실제 Gyeonggi API가 정상이라고 확신할 수 없는 이유는?
2. Unit Test에서 매번 MySQL을 사용하면 어떤 문제가 생기는가?
3. `pytest.raises`로 예외를 검증해야 하는 이유는?
4. Integration PASS 후 ODsay Live 호출이 실패해도 모순이 아닌 이유는?
5. `569 passed`가 의미하는 것과 의미하지 않는 것은?

## 다음 읽기

- [Unit Test](unit-test.md)
- [Integration Test](integration-test.md)
- [Fake](fake.md)
- [Mock and Stub](mock-and-stub.md)
- [Test Fixture](test-fixture.md)
- [Error Handling and Resilience](error-handling-and-resilience.md)
