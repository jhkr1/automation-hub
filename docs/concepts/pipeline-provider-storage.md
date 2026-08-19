# Pipeline, Provider and Storage

## 1. 먼저 한 문장으로

Provider는 외부 시스템과 통신하고, Pipeline은 여러 작업의 순서를 조정하며, Storage는 완성된 결과를 실행 이후에도 보존합니다.

## 2. 왜 필요한가?

한 application이 커지면 다음 질문이 서로 섞이기 쉽습니다.

- 외부 API를 어떻게 호출하는가?
- 어떤 순서로 route와 arrival을 조회하는가?
- 결과를 어디에 저장하는가?

이 세 질문은 변경 이유가 다릅니다. API endpoint가 바뀌는 일, 실행 순서가 바뀌는 일, DB schema가 바뀌는 일은 각각 다른 경계에서 처리하는 편이 안전합니다.

## 3. 가장 간단한 예제

```python
class Provider:
    def get_value(self) -> int:
        return 10


class Storage:
    def save(self, value: int) -> None:
        print(f"saved={value}")


def run(provider: Provider, storage: Storage) -> None:
    value = provider.get_value()
    storage.save(value)
```

`run()`은 Provider의 내부 통신과 Storage의 저장 방법을 직접 구현하지 않고 호출 순서만 드러냅니다.

## 4. 조금씩 개선해보기

### 한 함수에 모두 넣기

```text
main
  → requests.get
  → JSON field 해석
  → 업무 판단
  → SQL 실행
  → print
```

작을 때는 빠르지만, API와 DB가 모두 필요한 통합 테스트가 되고, 한 변경이 전체 함수를 흔듭니다.

### Provider

Provider는 외부 시스템의 URL, 인증, response 해석을 감쌉니다.

```text
ODsay API → OdsayRouteProvider → TransitRoute
Gyeonggi API → GyeonggiProvider → GyeonggiStationRoute / RealtimeArrival
```

Provider는 외부 response를 내부 model로 변환하지만 Dashboard를 렌더링하거나 전체 application 순서를 조정하지 않습니다.

### Pipeline

Pipeline은 이미 계약을 가진 구성요소를 어떤 순서로 호출할지 조정합니다.

```text
Route 조회
  ↓
Bus Leg 선택
  ↓
정류장 경유 노선 검증
  ↓
도착정보 조회
  ↓
BusRouteResult
```

Pipeline은 Provider의 HTTP 세부사항 대신 Protocol이 제공하는 method에 의존합니다.

### Storage

Storage는 결과를 저장하거나 다시 조회하는 경계를 담당합니다. `BusMonitorStorage`는 target 조회, target 생성, snapshot 저장·조회 method를 제공하며 Provider API를 호출하지 않습니다.

## 5. 핵심 개념

### Orchestration

Orchestration은 거대한 별도 Pattern이라기보다 여러 객체에게 일을 시키고 실행 순서를 조율하는 책임입니다. `main.py`는 객체를 조립하고, `BusMonitorPipeline`은 Provider를 순서대로 호출하고, `BusMonitorStorage`는 결과를 저장합니다.

### Repository와 Storage

Repository는 Domain object collection을 다루는 추상화라는 의미가 강합니다. Storage는 저장 책임과 영속화 구현을 직접 표현하는 이름으로 사용될 수 있습니다.

두 이름 사이에 모든 프로젝트에 적용되는 절대적 규칙은 없습니다. `automation-hub`는 `BusMonitorStorage`, `StockQuoteStorage`, `SnapshotSaveService`처럼 Storage 중심 이름을 사용합니다. 이 문서에서 Repository 개념은 저장 기술의 이름이 아니라 “저장·조회 경계를 application 밖으로 분리하는 역할”로 이해하면 됩니다.

SQLAlchemy Session, Transaction, Migration은 이 문서의 범위가 아닙니다. 해당 내용은 Database 문서를 읽습니다.

## 6. automation-hub에서는?

Bus Monitor의 실제 production 흐름은 다음과 같습니다.

```text
bus_monitor.main.build_pipeline()
        ↓
BusMonitorPipeline.run()
        ↓
RouteProvider.search_route()
        ↓
RealtimeProvider.get_station_routes()
        ↓
RealtimeProvider.get_arrivals()
        ↓
BusRouteResult
        ↓
BusMonitorStorage.save_snapshot()
```

`BusMonitorPipeline.run()`은 ODsay route 실패 시 `RouteStatus.FAILED`와 `RealtimeStatus.NOT_REQUESTED`를 반환합니다. route가 성공했지만 Gyeonggi 조회가 불가능하면 route를 보존한 채 `RealtimeStatus.UNAVAILABLE`을 반환합니다. 검증된 route가 있어도 현재 도착 차량이 없으면 `NO_MATCHING_ARRIVAL`로 구분합니다.

Google Finance는 `StockPricePipeline.run()`이 Collector 결과를 `StockPrice`로 바꾸고, `StockQuoteStorage.save()`가 저장합니다. `watchlist_main.py`는 여러 symbol을 순차 조정하고 Batch 분석 artifact를 저장합니다.

Namuwiki는 `TrendPipeline.run()`이 `collect_trends`와 `TrendEnricher`를 연결하고, `snapshot_main.py`는 `SnapshotCollectionPipeline`과 `SnapshotSaveService`를 조립합니다. 세 package는 같은 이름의 class를 공유하지 않으며, 각 업무 흐름에 맞는 Provider·Pipeline·Storage 경계를 갖습니다.

## 7. 실제 코드를 읽는 방법

### Bus Monitor

1. `bus_monitor/main.py`의 `build_pipeline()`을 엽니다.
2. 생성자 인자인 `OdsayRouteProvider`, `GyeonggiProvider`를 확인합니다.
3. `bus_monitor/pipeline.py`에서 `RouteProvider`, `RealtimeProvider` Protocol을 찾습니다.
4. `BusMonitorPipeline.run()`의 호출 순서와 상태 분기를 읽습니다.
5. `bus_monitor/models.py`에서 `TransitRoute`, `RealtimeArrival`, `BusRouteResult`를 확인합니다.
6. `bus_monitor/storage.py`의 `save_snapshot()`으로 결과가 전달되는 지점을 찾습니다.

### Google Finance

1. `google_finance/main.py`의 `build_pipeline()`을 읽습니다.
2. `google_finance/pipeline.py`의 `StockPricePipeline.run()`을 확인합니다.
3. `google_finance/models.py`의 `StockPrice`를 찾습니다.
4. `google_finance/storage.py`의 `StockQuoteStorage.save()`와 `db_models.py`의 mapping을 읽습니다.

### Namuwiki

1. `namuwiki_trend/main.py`의 `build_pipeline()`을 읽습니다.
2. `TrendPipeline`과 `TrendEnricher`의 Protocol을 확인합니다.
3. `namuwiki_trend/models.py`의 `TrendItem`, `TrendInsight`를 찾습니다.
4. `snapshot_main.py`, `snapshot_pipeline.py`, `database/snapshot_save_service.py`의 저장 흐름을 비교합니다.

## 8. 장점과 단점

| 경계 | 장점 | 단점 |
|---|---|---|
| Provider 분리 | 외부 API 변경과 내부 흐름을 분리함 | 응답 mapping 코드가 필요함 |
| Pipeline 분리 | 순서·실패·부분 결과를 한 곳에서 읽음 | 중간 계약을 설계해야 함 |
| Storage 분리 | 저장 방식이 application 흐름에 섞이지 않음 | domain-to-row 변환이 추가됨 |
| 하나의 함수로 통합 | 초기 구현이 짧음 | 외부·업무·저장 변경이 결합됨 |

## 9. 언제 쓰지 않아도 되는가?

외부 API도 저장도 없는 짧은 변환은 Provider·Pipeline·Storage 세 계층으로 나누지 않아도 됩니다. 한 번의 독립 함수가 더 명확하다면 그대로 두는 것이 KISS에 맞습니다. 경계를 추가하는 기준은 pattern 이름이 아니라 변경 이유와 테스트 필요성입니다.

## 10. 자주 헷갈리는 개념

- Provider는 외부 시스템 통신, Pipeline은 실행 순서 조정, Storage는 저장·조회입니다.
- Pipeline은 Workflow Engine이 아닙니다. 현재는 단일 실행 흐름을 조정하며 장기 재개·분산 실행을 제공하지 않습니다.
- Storage와 Repository는 조직·프로젝트마다 이름이 다를 수 있습니다.
- Model은 모든 raw payload를 담는 창고가 아니라 다음 계층에 필요한 내부 계약입니다.
- `main.py`는 entry point와 composition을 담당하지만 모든 business rule을 담는 파일이 아닙니다.

## 11. 내가 설명해본다면

“Bus Monitor에서 ODsay와 Gyeonggi API를 직접 다루는 것은 Provider입니다. Pipeline은 두 Provider를 route 검증과 arrival 조회 순서로 조정하고, 결과는 `BusRouteResult`라는 domain 계약으로 합칩니다. 마지막으로 Storage가 이 결과를 snapshot으로 저장합니다. 그래서 API 변경, 실행 순서 변경, 저장 schema 변경의 영향 범위를 분리할 수 있습니다.”

## 12. 이해도 체크

1. `BusMonitorPipeline` 안에서 직접 `requests.get()`을 호출하면 어떤 변경과 테스트 문제가 생길까요?
2. `OdsayRouteProvider`와 `GyeonggiProvider`를 하나의 class로 합치면 어떤 책임이 섞일까요?
3. `BusMonitorStorage`가 API 호출까지 담당하면 어떤 경계가 사라질까요?
4. Provider와 Pipeline을 하나의 함수로 두어도 되는 작은 프로그램은 어떤 경우일까요?
5. route 성공과 realtime unavailable을 하나의 실패로 저장하지 않는 이유는 무엇일까요?

## 다음 읽기

[Database Architecture](../database/database_architecture.md)에서 Storage 이후 ORM·Session·Transaction 경계를 읽습니다.

개별 개념의 기준 문서는 [Pipeline and Orchestration](pipeline-and-orchestration.md),
[Provider](provider.md), [Persistence](persistence.md), [Repository Pattern](repository-pattern.md)입니다.
이 문서는 해당 문서를 반복하지 않고 세 역할이 하나의 Bus Monitor 실행에서 어떻게 이어지는지
보여줍니다.
