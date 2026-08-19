# Python Data Contracts

## 1. 먼저 한 문장으로

데이터 계약은 한 단계가 어떤 값과 상태를 받아 어떤 형태로 다음 단계에 전달할지 명시하는 약속입니다.

## 2. 왜 필요한가?

외부 API의 JSON은 편리하지만 모든 계층이 같은 `dict`를 직접 읽으면 다음 문제가 생깁니다.

- 필드 이름과 누락 처리 방식이 여러 곳에 반복됩니다.
- 문자열 숫자와 실제 정수의 차이를 호출자가 매번 판단합니다.
- API 응답에 없는 값과 실제 오류를 구분하기 어렵습니다.
- Provider가 바뀌면 Pipeline, Storage, Dashboard까지 JSON field name에 묶입니다.

그래서 Provider 경계에서 응답을 검증하고, 내부 계층은 의미가 명확한 Python model을 사용합니다.

## 3. 가장 간단한 예제

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class Arrival:
    route_number: str
    arrival_seconds: int


arrival = Arrival(route_number="5600", arrival_seconds=322)
assert arrival.arrival_seconds == 322
```

이 model은 `route_number`와 `arrival_seconds`가 내부에서 필요한 값이라는 계약을 보여줍니다. JSON에 어떤 다른 field가 더 들어왔는지는 이 객체를 사용하는 계층의 관심사가 아닙니다.

## 4. 핵심 개념

### Type Hint

```python
def get_station(station_id: int) -> GyeonggiStation:
    ...
```

`station_id: int`는 인자에 기대하는 타입을 설명하고, `-> GyeonggiStation`은 반환 계약을 설명합니다. IDE, 정적 분석기, 코드를 읽는 개발자에게 유용한 정보입니다.

Type Hint는 runtime validation과 동일하지 않습니다. Python은 일반적으로 annotation만으로 잘못된 값을 자동 거부하지 않습니다. 실제 검증이 필요하면 `GyeonggiStation.__post_init__`, Pydantic 설정, 명시적인 조건문처럼 실행되는 검증이 필요합니다.

### `Optional`과 `None`

경기도 도착 응답에서 모든 차량이 모든 부가 정보를 제공한다고 보장할 수 없습니다. 예를 들어 차량 번호, `remaining_seats`, `operating_status`가 없을 수 있습니다.

```python
plate_number: str | None
remaining_seats: int | None
operating_status: str | None
```

`None`은 “값이 0이다” 또는 “호출이 실패했다”와 다릅니다. 값이 제공되지 않았거나 해당 차량에 적용되지 않는 정상 상태를 표현할 수 있습니다. 반대로 필수인 `route_id`나 `arrival_seconds`는 nullable로 만들지 않아야 누락을 조기에 발견할 수 있습니다.

### `list`, `tuple`, `dict`

```python
routes: list[str] = ["5600", "9241"]
lanes: tuple[str, ...] = ("5600", "9241")
payload: dict[str, object] = {"routeId": "228000184"}
```

- `list`: 순서가 있고 변경 가능한 여러 값
- `tuple`: 순서가 있고 일반적으로 변경하지 않는 여러 값
- `dict`: key와 value를 연결하는 자료 구조

API 응답은 보통 `dict`로 시작하지만, 모든 계층에 raw `dict`를 전달하지 않습니다. Provider가 key와 타입을 확인해 `GyeonggiStationRoute`나 `RealtimeArrival` 같은 domain object로 바꾸면 이후 코드는 `route_id`가 무엇을 의미하는지 명시적으로 알 수 있습니다.

### dataclass

일반 class도 데이터를 표현할 수 있지만, 생성자·비교·표현 문자열 같은 반복 코드를 직접 작성해야 할 수 있습니다. `dataclass`는 필드 선언을 기준으로 이런 기본 동작을 생성해 줍니다.

```python
from dataclasses import dataclass


@dataclass
class Point:
    x: int
    y: int


assert Point(1, 2) == Point(1, 2)
```

`dataclass`는 ORM model이나 API response 그 자체가 아닙니다. Python 안에서 전달할 값의 구조를 선언하는 도구이며, 필요한 경우 `__post_init__`에서 domain invariant를 검사할 수 있습니다.

### frozen dataclass와 불변성

불변성은 객체를 만든 뒤 필드를 바꾸지 못하게 하는 성질입니다.

```python
@dataclass(frozen=True)
class Coordinate:
    latitude: float
    longitude: float
```

수집 결과가 여러 단계로 전달될 때 중간 단계가 원본을 몰래 바꾸면 원인을 추적하기 어렵습니다. `frozen=True`는 이런 변경을 막고 값 객체처럼 사용할 수 있게 합니다.

하지만 모든 객체를 frozen으로 만들 필요는 없습니다. 수집 중 상태를 누적하거나, framework가 변경 가능한 객체를 요구하거나, 큰 객체를 단계적으로 구성해야 한다면 일반 dataclass가 더 적절할 수 있습니다.

### Enum

상태 문자열을 곳곳에 직접 쓰면 오타가 실행 시점까지 드러나지 않을 수 있습니다.

```python
from enum import Enum


class RouteStatus(str, Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
```

Enum은 허용되는 상태 집합을 한 곳에 모으고 비교 기준을 명확히 합니다. 다만 Enum이 외부 API의 모든 문자열을 자동으로 검증하는 것은 아니며, Provider parsing 단계에서 mapping이 필요합니다.

### `pathlib.Path`

```python
"/home/kstec/projects/automation-hub/logs/test.log"
```

절대 문자열 경로는 특정 컴퓨터에 묶입니다. `Path`는 경로 조합과 파일 작업을 Python 객체로 표현합니다.

```python
from pathlib import Path


log_path = Path("logs") / "test.log"
```

현재 `run_dashboard.sh`는 shell 경로를 사용하지만, Python 코드의 `automation_dashboard/config.py`, `automation_dashboard/readers/llm_usage.py`, `bus_monitor/config.py`와 `bus_monitor/tago_poc.py`는 `Path(__file__).resolve()`로 repository 기준 경로를 계산합니다.

## 5. Data Contract의 흐름

예를 들어 Provider가 다음 JSON을 받았다고 하겠습니다.

```json
{
  "routeId": "228000184",
  "routeName": "5600"
}
```

내부 흐름은 다음처럼 분리합니다.

```text
External JSON dict
        ↓
Provider parsing and validation
        ↓
GyeonggiStationRoute / RealtimeArrival
        ↓
BusMonitorPipeline
        ↓
Storage or presentation
```

여기서 `routeName`을 내부에서 항상 `route_number`라고 부르기로 했다면, 그 mapping은 Provider boundary에서 끝나야 합니다. Pipeline은 원본 key를 다시 해석하지 않습니다.

## 6. automation-hub에서는?

`bus_monitor/models.py`는 production domain contract의 실제 예입니다.

```python
@dataclass(frozen=True)
class RealtimeArrival:
    route_id: str
    route_number: str
    arrival_seconds: int
    remaining_stops: int
    vehicle_type: str | None
    plate_number: str | None = None
    remaining_seats: int | None = None
    operating_status: str | None = None
```

필수 route 식별자와 도착 시간은 non-null 계약이고, 차량 번호·좌석·운행 상태는 API가 제공하지 않을 수 있으므로 nullable입니다. `arrival_minutes`는 별도 저장 field가 아니라 `arrival_seconds // 60`으로 계산되는 presentation property입니다.

같은 module의 `RouteStatus`, `RealtimeStatus`는 `SUCCESS`, `FAILED`, `UNAVAILABLE`, `NO_MATCHING_ARRIVAL`, `NOT_REQUESTED`처럼 상태 집합을 Enum으로 제한합니다. `BusLane`, `TransitRoute`, `ResolvedStation`, `GyeonggiStationRoute`도 각각 Provider raw payload 전체가 아니라 다음 단계에 필요한 정규화된 값만 보존합니다.

`google_finance/models.py`의 `StockPrice`와 `StockInsight`, `namuwiki_trend/models.py`의 frozen `TrendItem`과 `TrendInsight`도 같은 원칙을 보여줍니다. 다만 `StockPrice`는 수집 중 기본값과 변경 가능한 상태가 필요해 frozen이 아니며, 모든 dataclass를 무조건 불변으로 만들지 않는 실제 사례입니다.

## 7. 실제 코드를 읽는 방법

1. `bus_monitor/odsay.py`와 `bus_monitor/gyeonggi.py`에서 외부 응답을 읽는 Provider를 찾습니다.
2. 반환 타입 또는 생성되는 model이 `bus_monitor/models.py`의 어떤 class인지 확인합니다.
3. `RealtimeArrival.__post_init__()`에서 필수 값과 non-negative 검증을 읽습니다.
4. `bus_monitor/pipeline.py`에서 `TransitRoute`, `BusLeg`, `RealtimeArrival`이 어떻게 조합되는지 확인합니다.
5. `bus_monitor/storage.py`와 `bus_monitor/db_models.py`에서 domain model이 저장 model로 변환되는 경계를 확인합니다.
6. `automation_dashboard/queries/bus_monitor.py`에서 저장된 값이 화면용 DTO로 바뀌는 흐름을 확인합니다.

## 8. 장점과 단점

| 선택 | 장점 | 단점 |
|---|---|---|
| raw dict 전달 | 처음 구현이 짧음 | key·타입·누락 정책이 계층마다 반복됨 |
| 명시적 dataclass | 계약과 의미가 읽기 쉬움 | 변환 코드와 model 정의가 필요함 |
| frozen dataclass | 변경 추적과 안전한 전달에 유리함 | 단계적 수정이 필요한 흐름에는 불편함 |
| Enum | 허용 상태와 오타 방지가 명확함 | 외부 문자열 mapping이 필요함 |
| Optional field | 정상적인 정보 부재를 표현함 | 호출자가 `None` 처리를 해야 함 |

## 9. 언제 쓰지 않아도 되는가?

한 함수 안에서만 쓰이고 외부 경계를 통과하지 않는 임시 값에는 작은 `dict`나 tuple이 더 읽기 쉬울 수 있습니다. 그러나 Provider, Pipeline, Storage, Dashboard 사이를 이동하는 값은 의미와 누락 정책을 명시하는 model이 장기적으로 유리합니다.

## 10. 자주 헷갈리는 개념

- **Type Hint vs runtime validation**: annotation은 설명·정적 분석 정보이고, `__post_init__`나 검증 함수는 실제 실행 제약입니다.
- **dataclass vs ORM model**: dataclass는 Python 내부 계약이고, ORM model은 테이블과 Session에 연결된 persistence 표현입니다.
- **Enum vs 문자열 상수**: Enum은 허용 상태를 타입으로 묶지만, 외부 문자열을 자동 변환하지는 않습니다.
- **`None` vs 0**: `None`은 값이 없음·미제공이고, 0은 실제 측정값일 수 있습니다.
- **list vs tuple**: list는 변경 가능한 수집 목록, tuple은 변경하지 않을 결과 묶음에 적합합니다.

## 11. 내가 설명해본다면

“Provider가 받은 JSON은 외부 계약이라 내부 전체에 그대로 흘려보내지 않습니다. 경계에서 key와 타입을 검증해 `RealtimeArrival`로 바꾸고, 필수 값은 non-null로 두며 좌석처럼 API가 생략할 수 있는 값은 `None`을 허용합니다. 상태는 Enum으로 제한하고, 수집 결과는 frozen dataclass로 전달해 중간 단계가 값을 바꾸지 못하게 합니다. 저장과 Dashboard는 이 내부 계약을 각자의 표현으로 변환합니다.”

## 12. 이해도 체크

1. `route_id`를 `str`로 둔 이유와 `arrival_seconds`를 `int`로 둔 이유는 무엇인가요?
2. `remaining_seats=0`과 `remaining_seats=None`은 어떤 의미 차이가 있나요?
3. API JSON의 `routeName`을 모든 계층이 직접 읽지 않고 `route_number`로 변환하는 위치는 어디여야 하나요?
4. `RealtimeArrival`을 frozen으로 만들면 어떤 실수를 막을 수 있고, 어떤 상황에서는 불편할까요?
5. Type Hint만 추가하면 잘못된 `arrival_seconds=-1`을 자동으로 막을 수 없는 이유는 무엇인가요?

## 다음 읽기

[STUDY_NOTE](../learning/STUDY_NOTE.md)의 Chapter 6에서 데이터 계약을 지키지 못했을 때 Exception과 Logging 경계를 읽습니다.
