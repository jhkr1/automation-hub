# 관계형 데이터베이스 설계 읽기

이 문서는 용어를 외우는 대신, **한 번의 자동화 결과를 왜 여러 관계형 테이블로 나누고
어떻게 안전하게 조회하는가**를 배우는 교재다. SQLAlchemy 사용법의 상세 내용은
[SQLAlchemy·Session·Transaction·Migration](sqlalchemy-session-transaction-migration.md),
운영 스키마의 전체 표는 [Database Architecture](../database/database_architecture.md)를
참조한다.

## 1. 먼저 한 문장으로

관계형 설계는 데이터를 행과 열로 보존하면서 PK/FK/제약조건/index를 사용해 **잘못된
데이터는 막고, 자주 하는 조회는 예측 가능하게 만드는 작업**이다.

## 2. Table, Row, Column

작은 예제로 시작해 보자.

```text
users
id | name | email
1  | Mina | mina@example.com
```

Table은 같은 종류의 행을 담는 DB 구조이고, row는 한 사실, column은 그 사실의 한 속성이다.
Python class와 row, attribute와 column이 닮았지만 완전히 같지는 않다. Python 객체는
메모리의 동작과 메서드를 포함할 수 있고, DB table은 여러 프로세스가 공유하는 영속 데이터와
제약조건을 가진다. `BusRouteSnapshot` ORM class는 table을 표현하는 어댑터이지, DB의 한
row와 동일한 개념은 아니다.

## 3. Primary Key

PK는 한 table의 row를 다른 row와 확실히 구별하는 계약이다. PK가 없으면 같은 내용의
두 row를 특정하기 어렵고, child row가 어느 parent를 가리키는지도 불분명해진다.

현재 Bus Monitor의 네 table은 모두 자동 증가 `id`를 PK로 사용한다.

| table | PK |
|---|---|
| `bus_monitoring_targets` | `id` |
| `bus_route_snapshots` | `id` |
| `bus_route_snapshot_lanes` | `id` |
| `bus_realtime_snapshots` | `id` |

이런 인공 식별자를 **surrogate key**라고 한다. 정류장 이름이나 수집 시각 같은
natural key를 PK로 쓰면 이름 변경, 중복 시각, provider별 ID 충돌이 식별자 변경으로
번질 수 있다. 현재 schema가 자연키를 PK로 쓰지 않은 이유는 코드에 명시되어 있지는
않지만, append-only 이력의 row를 안정적으로 참조하려는 설계로 해석할 수 있다.

## 4. Foreign Key와 관계

FK는 child row가 존재하는 parent를 가리키도록 DB가 확인하는 장치다. FK가 없으면
`route_snapshot_id=999999`인 realtime row 같은 orphan row가 생길 수 있다.

```text
bus_monitoring_targets (1)
        └── bus_route_snapshots (N)
                ├── bus_route_snapshot_lanes (N)
                └── bus_realtime_snapshots (N)
```

실제 FK는 각각 `monitoring_target_id`, `route_snapshot_id`다. 이것은 1:N 관계다. 일반적으로
1:1은 한 parent에 child 하나, N:M은 중간 연결 table이 필요한 관계다. 현재 Bus Monitor는
N:M이 아니라 실행별 route, lane 후보, 차량 행을 부모와 자식으로 보존한다.

왜 `lane1`, `lane2`, `lane3` column을 만들지 않았을까? lane 수가 실행마다 다르고, 새 후보가
늘어날 때 schema를 바꿔야 하기 때문이다. `bus_route_snapshot_lanes`의 한 row가 한 후보를
표현하면 개별 query, FK, index를 사용할 수 있다.

## 5. JSON column과 child table

`lanes_json=[...]` 한 column은 구현과 원본 보존이 단순하다는 장점이 있다. 반면 특정 버스만
찾거나 순서를 검증하거나 lane별 집계를 하려면 JSON 파싱이 필요하고 관계형 제약을 적용하기
어렵다. 현재 요구사항은 lane 분석과 Dashboard 조회, `lane_order` 검증이 있으므로 child
table이 합리적이다. JSON이 항상 나쁜 것은 아니다. schema가 고정되지 않은 payload를 원본
그대로 보관하거나 거의 읽지 않는 경우라면 JSON이 더 적절할 수 있다.

## 6. NULL, NOT NULL, 0, 빈 값

`NULL`은 “값이 알려지지 않았거나 제공되지 않음”이고 `0`은 실제 숫자 0이다. `""`은
빈 문자열이며 빈 list/tuple은 “목록은 알지만 항목이 없음”이라는 별도 의미다.

예를 들어 `remaining_seats=NULL`은 좌석 정보 미제공이고 `0`은 좌석이 실제로 0석일 수
있다. Dashboard가 두 상태를 같은 “매진”으로 표시하면 운영 판단과 분석이 틀어진다.
현재 `bus_realtime_snapshots`에서 `vehicle_type`, `plate_number`, `remaining_seats`,
`crowded`, `state_code`, `operating_status`는 nullable이고, ETA와 남은 정거장 수는
필수다. nullable은 편의를 위한 Optional 남발이 아니라 provider가 항상 주지 않는 사실을
정직하게 표현하는 선택이다.

## 7. Constraint

제약조건은 애플리케이션을 거치지 않는 SQL도 보호하는 마지막 경계다.

| constraint | 현재 예 | 막는 문제 |
|---|---|---|
| PK | 모든 Bus Monitor `id` | row 식별 불가/중복 참조 |
| FK | snapshot의 parent id | orphan child |
| NOT NULL | `route_status`, `arrival_seconds` | 필수 사실 누락 |
| UNIQUE | `(route_snapshot_id, lane_order)` | 한 실행에서 같은 순서 중복 |
| CHECK | `arrival_seconds >= 0` | 음수 ETA |

`lane_order`만 UNIQUE가 아닌 이유는 snapshot마다 0번 lane이 다시 나와야 하기 때문이다.
복합 UNIQUE는 “같은 route snapshot 안에서만 순서가 유일하다”는 뜻이다. 또한 migration에는
`route_status IN ('SUCCESS','FAILED')`, realtime 상태 허용값, `FAILED`이면
`NOT_REQUESTED`여야 한다는 cross-state CHECK가 실제로 있다. Python Enum 검증은 사용자
입력의 빠른 피드백을 주고, DB CHECK는 다른 쓰기 경로와 동시성에도 같은 불변식을 보장한다.

## 8. Index와 Composite Index

Index는 조건과 정렬에 맞는 row를 찾는 보조 구조다. 하지만 index도 저장 공간과 INSERT/UPDATE
유지 비용이 있다. append-only snapshot table에 모든 column을 index로 만들면 쓰기 비용과
optimizer 선택지가 늘어날 뿐, 모든 query가 빨라지지 않는다.

현재 route snapshot에는
`(monitoring_target_id, collected_at)` composite index가 있고, realtime table에는
`route_snapshot_id` index가 있다. 실제 핵심 query는 다음과 같다.

```sql
WHERE monitoring_target_id = 2
ORDER BY collected_at DESC, id DESC
```

target으로 범위를 좁힌 뒤 수집 시각을 정렬하는 패턴이므로 두 column을 함께 둔 index가
자연스럽다. 같은 `collected_at`이 두 번 기록될 수 있어 `id DESC`를 tie-break로 사용한다.
`collected_at`만으로는 어느 row가 최신인지 결정되지 않는다.

## 9. Query Pattern과 JOIN

schema는 query와 함께 설계한다. 현재 storage/query 코드는 다음 패턴을 실제로 사용한다.

- target의 최신 route snapshot: `collected_at DESC, id DESC`
- snapshot별 lane: `route_snapshot_id` 조건 후 `lane_order ASC, id ASC`
- snapshot별 realtime: `route_snapshot_id` 조건 후 `arrival_seconds ASC, id ASC`
- Dashboard 운영 요약: package별 count와 최신 수집 시각

서로 다른 table의 정보를 한 화면에 함께 보려면 FK를 따라 결합해야 한다. 예를 들어
`route_snapshots`와 `realtime_snapshots`를 `route_snapshot_id`로 JOIN하면 최신 실행과
그 실행의 차량 rows를 함께 읽을 수 있다. INNER JOIN은 양쪽에 matching row가 있는 경우만,
LEFT JOIN은 route는 있지만 realtime이 없는 경우도 남긴다. `NO_MATCHING_ARRIVAL`을 보여줘야
하는 현재 모델에는 후자의 사고방식이 중요하다.

## 10. Read Model

저장하기 좋은 형태와 화면에서 읽기 좋은 형태는 다를 수 있다. DB에는
`arrival_seconds=322`, UTC `collected_at`을 저장하지만 Dashboard는 “약 5분”, “17:25 KST”로
표시한다. `automation_dashboard/queries/bus_monitor.py`가 ORM row를 화면용 값으로
정리하고, `ui/formatting.py`가 UTC를 Asia/Seoul로 변환한다. ORM 객체를 Streamlit에
그대로 넘기면 DB 세부사항과 표시 규칙이 섞인다. 별도 read model은 변환 위치가 분명해지는
대신 query DTO를 추가로 유지해야 한다.

## 11. Normalization과 Denormalization

다음처럼 lane과 차량을 고정 column으로 펼치면 차량 수나 lane 수가 변할 때 column이 계속
늘어난다.

```text
route_snapshot(id, lane1, lane2, lane3, arrival1_eta, arrival2_eta, ...)
```

현재 `Route Snapshot`, `Lane`, `Realtime` 분리는 반복 그룹을 별도 row로 옮겨 query와
제약을 가능하게 한다. 이것이 이 사례에서 정규화가 주는 이점이다. 1NF/2NF/3NF는 이
원칙을 더 엄밀히 설명하는 용어이지, 번호를 암기하는 것이 목적은 아니다.

반대로 JOIN 비용과 query 복잡성이 커지는 경우 일부 중복을 허용하는 denormalization을
검토할 수 있다. 현재 repository에서 명확히 선언된 별도 denormalized table은 확인하지
못했다. 그러므로 “정규화할수록 항상 좋다”라고 결론내리지 않는다.

## 12. Delete 정책과 Snapshot

migration은 target→route에 `RESTRICT`, route→lane/realtime에 `CASCADE`를 지정한다.
parent target을 실수로 삭제하면 과거 운영 이력이 사라질 수 있으므로 target은 보통
`enabled=False`로 비활성화하는 편이 안전하다. 반면 route snapshot을 의도적으로 제거할
때 그 실행에만 속한 child rows를 함께 지우는 CASCADE는 일관성을 유지한다.

각 실행은 기존 row를 수정하지 않고 새 snapshot으로 append한다. 그래서 시간대 비교,
장애 시점 회고, Dashboard의 “오늘 수집 수”가 가능하다. Namuwiki의 `TrendSnapshot`과
Google Finance의 `StockQuoteSnapshot`도 같은 snapshot 관점을 쓰지만 한 수집 결과가
단일 row에 가까워 더 단순하다. Bus Monitor는 한 실행에 lane과 여러 차량이 있어 child
table이 필요하다.

## 13. Schema trade-off

가능한 설계는 (A) 결과 JSON 한 row, (B) 현재처럼 route/lane/realtime 분리, (C) realtime만
별도 time-series table 등 여러 가지다. Dashboard, lane 분석, 차량별 이력, append-only
저장, MySQL이라는 현재 요구에서는 B가 query와 무결성 사이의 균형을 제공한다. 이것이
유일한 정답이라는 뜻은 아니며, 데이터량과 query가 바뀌면 재평가해야 한다.

## 14. 실제 코드 읽는 순서

1. `bus_monitor/db_models.py`: table, PK, FK, nullable, relationship, index, constraint
2. `alembic/versions/0004_create_bus_monitor_snapshots_tables.py`: 실제 생성 계약과 ondelete
3. `bus_monitor/storage.py`: transaction 경계와 저장 순서
4. `automation_dashboard/queries/bus_monitor.py`: read query와 화면용 변환
5. `tests/database/test_bus_monitor_integration.py`: 실제 DB 계약과 실패 사례

읽을 때 “이 column은 어떤 query를 위해 존재하는가?”, “이 제약이 막는 잘못은 무엇인가?”를
각각 적어 본다.

## 15. 자주 헷갈리는 질문

**PK와 FK의 차이는?** PK는 자기 table의 row 식별자, FK는 다른 table parent를 참조하는 값이다.

**왜 child table인가?** lane/차량 개수가 가변이고 개별 query·FK·index가 필요하기 때문이다.

**왜 NULL과 0을 구분하는가?** 미제공과 실제 0은 운영 의미가 다르기 때문이다.

**왜 모든 column에 index를 두지 않는가?** index는 읽기 이득 대신 쓰기·저장 비용을 낸다.

**왜 append-only인가?** 과거 수집 결과를 비교하고 장애를 재구성하기 위해서다.

**FK가 없으면?** 존재하지 않는 parent를 가리키는 orphan row가 저장된다.

**Target을 CASCADE 삭제하면?** 과거 snapshot까지 사라질 수 있어 운영 이력 보존에 위험하다.

## 16. 이해도 체크

1. `(route_snapshot_id, lane_order)`에 복합 UNIQUE가 필요한 이유를 설명해 보라.
2. `monitoring_target_id`만 index인 경우 최신 시각 정렬 비용이 어떻게 달라질지 말해 보라.
3. `remaining_seats`의 NULL과 0을 Dashboard에서 어떻게 다르게 표시할지 정해 보라.
4. realtime child가 없는 route를 보존하려면 어떤 JOIN이 필요한가?
5. JSON 한 column이 더 적합할 수 있는 상황을 하나 제시해 보라.

## 다음 읽기

- [SQLAlchemy·Session·Transaction·Migration](sqlalchemy-session-transaction-migration.md)
- [Database Learning](../database/database_learning.md)
- [Database Architecture](../database/database_architecture.md)
- [Python Data Contracts](python-data-contracts.md)
