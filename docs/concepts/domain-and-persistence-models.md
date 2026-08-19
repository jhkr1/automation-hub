# Domain Model, DTO and ORM Model

## 1. 먼저 한 문장으로

Domain Model은 업무 의미를 표현하고, DTO는 경계 사이의 전달 모양을 표현하며, ORM Model은 데이터베이스의 행과 제약을 표현합니다.

## 2. 왜 필요한가?

외부 API에서 받은 값과 DB에 저장할 값이 항상 같은 모양이라고 가정하면 한 변경이 모든 계층으로 번집니다. 예를 들어 버스 API가 `routeName`을 보내더라도 내부 application은 `route_number`라는 의미를 사용할 수 있고, DB는 다시 `route_number` column에 저장할 수 있습니다.

세 표현을 구분하면 다음 질문에 답하기 쉬워집니다.

```text
업무에서 이 값은 무엇인가?      → Domain Model
경계를 통과할 때 무엇을 보낼까? → DTO 또는 전달 객체
DB에는 어떤 열로 보존할까?      → ORM / Persistence Model
```

## 3. 가장 간단한 예제

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class Order:
    product: str
    quantity: int


@dataclass
class OrderRow:
    product_name: str
    quantity_value: int


def to_row(order: Order) -> OrderRow:
    return OrderRow(order.product, order.quantity)
```

`Order`는 업무에서 주문을 의미하고, `OrderRow`는 저장할 행의 이름을 의미합니다. 필드가 우연히 같아도 두 객체의 변경 이유는 다를 수 있습니다.

## 4. Domain Model

Domain Model은 업무적으로 의미 있는 상태와 유효 조건을 Python 객체로 표현합니다. 단순히 값을 담는 모든 dataclass가 자동으로 Domain Model이 되는 것은 아닙니다. 그 값이 시스템의 업무 언어로 사용되고, 잘못된 상태를 거부하거나 의미 있는 연산을 제공할 때 Domain Model이라고 설명할 근거가 생깁니다.

`bus_monitor/models.py`의 실제 예는 다음과 같습니다.

- `TransitRoute`: 선택된 경로의 이동시간·도보거리·환승 수와 버스 구간
- `RealtimeArrival`: 특정 정류장의 한 차량 도착 정보
- `BusRouteResult`: route 성공과 realtime 상태를 함께 표현하는 최종 결과

이들은 `BusRouteSnapshot` table과 1:1로 같은 객체가 아닙니다. Domain은 `RealtimeStatus`와 `RouteStatus`의 의미를 보존하고, DB row는 foreign key·column type·index를 보존합니다.

## 5. DTO

DTO(Data Transfer Object)는 계층이나 시스템 사이에 값을 전달하기 위한 객체입니다. DTO는 전달에 필요한 field와 serialization 모양을 강조하며, 업무 규칙을 반드시 소유하지는 않습니다.

현재 repository에서 `DTO`라는 이름의 공통 class 계층은 확인되지 않았습니다. Dashboard query의 `RouteSnapshotRow`, `LatestQuoteRow` 같은 read model과 각 Provider가 반환하는 정규화된 model은 DTO와 비슷한 역할을 할 수 있지만, 프로젝트가 모두를 DTO라고 부르는 것은 아닙니다.

따라서 “automation-hub에는 DTO 계층이 있다”고 단정하지 않습니다. 개념은 이해하되 실제 코드의 class 이름과 책임을 기준으로 읽습니다.

## 6. ORM Model

ORM(Object-Relational Mapping) Model은 Python class와 관계형 DB table 사이를 연결하는 persistence 표현입니다. column, nullable, foreign key, index, constraint와 relationship처럼 저장 구조에 필요한 정보를 가집니다.

`bus_monitor/db_models.py`에는 실제 ORM Model이 있습니다.

```python
class BusRouteSnapshot(Base):
    __tablename__ = "bus_route_snapshots"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    monitoring_target_id: Mapped[int] = mapped_column(
        ForeignKey("bus_monitoring_targets.id"),
        nullable=False,
    )
```

`BusRouteSnapshot`은 route 상태와 저장 column을 표현합니다. `BusRouteResult`의 업무 의미를 그대로 대신하는 객체가 아니며, `BusRouteResult`를 row로 변환하는 일은 `BusMonitorStorage._route_snapshot()` 경계에서 일어납니다.

## 7. Domain → Persistence 경계

Bus Monitor 저장 흐름은 다음과 같습니다.

```text
BusRouteResult
        ↓
BusMonitorStorage._route_snapshot()
        ↓
BusRouteSnapshot
BusRouteSnapshotLane
BusRealtimeSnapshot
        ↓
SQLAlchemy Session
        ↓
MySQL rows
```

`BusRouteSnapshot` 하나가 route 실행을 나타내고, lane 후보와 realtime 차량은 child row로 저장됩니다. `BusRouteResult`에는 raw HTTP response나 API key가 없고, ORM row에는 Provider의 전체 JSON이 없습니다.

Google Finance도 같은 원칙을 사용합니다. `StockPrice`는 domain model이고 `StockQuoteSnapshot`은 `google_finance/db_models.py`의 persistence model입니다. `StockQuoteSnapshot.from_domain()`과 `to_domain()`이 두 표현 사이를 변환합니다.

Namuwiki의 `TrendItem`과 `database.models.TrendSnapshot`도 내부 순위 값과 DB snapshot row를 구분합니다. 다만 각 package의 model과 저장 흐름은 동일한 class를 공유하지 않습니다.

## 8. ORM은 무엇을 해결하고 무엇을 해결하지 않는가

ORM은 Python attribute와 table column을 연결하고, 객체를 Session에서 추적하며, SQL 표현을 구성하는 데 도움을 줍니다. 그러나 ORM이 다음 일을 자동으로 결정하지는 않습니다.

- 어떤 값이 업무적으로 유효한가
- 어떤 API field를 내부 model로 선택할 것인가
- 어느 시점에 snapshot을 만들 것인가
- schema 변경을 production DB에 적용할 것인가

그래서 ORM을 Domain Model이나 Migration과 같은 것으로 부르면 안 됩니다.

## 9. 실제 코드를 읽는 방법

1. [`bus_monitor/models.py`](../../bus_monitor/models.py)에서 `BusRouteResult`, `TransitRoute`, `RealtimeArrival`의 업무 의미를 읽습니다.
2. [`bus_monitor/db_models.py`](../../bus_monitor/db_models.py)에서 `BusMonitoringTarget`, `BusRouteSnapshot`, `BusRouteSnapshotLane`, `BusRealtimeSnapshot`의 table·column·FK를 읽습니다.
3. [`bus_monitor/storage.py`](../../bus_monitor/storage.py)의 `save_snapshot()`에서 domain 결과가 ORM 객체로 바뀌는 위치를 찾습니다.
4. `google_finance/db_models.py`의 `from_domain()`·`to_domain()`을 비교합니다.
5. `database/base.py`의 `Base`가 모든 ORM model의 metadata를 모으는 위치임을 확인합니다.

## 10. 장점과 단점

| 선택 | 장점 | 단점 |
|---|---|---|
| Domain·ORM 분리 | 저장 구조 변경이 업무 규칙에 덜 전파됨 | 변환 코드가 필요함 |
| ORM Model만 사용 | 초기 코드가 짧음 | DB 제약과 업무 의미가 결합됨 |
| DTO 사용 | 경계 전달 형식이 명확함 | 전달 객체가 늘어날 수 있음 |
| raw dict 전달 | 빠른 PoC에 편리함 | key·타입·누락 정책이 퍼짐 |

## 11. 언제 쓰지 않아도 되는가?

한 번만 읽고 버리는 짧은 script에는 Domain·DTO·ORM을 모두 만들 필요가 없습니다. DB 저장, 여러 계층 전달, 재실행 비교가 생길 때 분리를 검토합니다. 모든 dataclass를 Domain Model이라고 부르거나 모든 table에 별도 DTO를 만드는 것도 필요하지 않습니다.

## 12. 자주 헷갈리는 개념

- Domain Model과 ORM Model은 같은 필드를 가질 수 있지만 변경 이유가 다릅니다.
- DTO라는 이름이 코드에 없다고 전달 객체의 역할이 존재하지 않는 것은 아닙니다.
- ORM은 Database가 아닙니다.
- SQLAlchemy는 DBMS가 아니며 MySQL에 연결하는 Python library입니다.
- ORM Model 변경은 Python metadata 변경이지, production table 변경 자체가 아닙니다.

## 13. 내가 설명해본다면

“`BusRouteResult`는 버스 업무 결과를 표현하는 Domain 계약이고, `BusRouteSnapshot`은 그 결과를 MySQL 행으로 보존하기 위한 ORM Model입니다. 둘은 비슷한 field를 가질 수 있지만 하나는 업무 의미를, 다른 하나는 column·foreign key·constraint를 책임집니다. `BusMonitorStorage`가 두 표현을 변환하므로 Provider와 Domain은 SQLAlchemy를 직접 알 필요가 없습니다.”

## 14. 이해도 체크

1. `BusRouteResult`와 `BusRouteSnapshot`을 하나의 class로 합치면 어떤 변경이 결합될까요?
2. 현재 코드에서 DTO라는 이름의 class가 없다는 사실은 무엇을 의미하나요?
3. ORM Model에 column을 추가하면 production MySQL에도 자동으로 column이 생기나요?
4. raw API dict를 Storage까지 전달하지 않는 이유는 무엇인가요?

## 다음 읽기

[Relational Database Design](relational-database-design.md)에서 PK/FK·index·JOIN을 먼저 읽고, [SQLAlchemy Session, Transaction and Migration](sqlalchemy-session-transaction-migration.md)에서 Python 객체가 Session과 Transaction을 거쳐 DB에 저장되는 과정을 읽습니다.
