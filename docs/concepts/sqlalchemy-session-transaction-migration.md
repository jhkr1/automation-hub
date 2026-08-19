# SQLAlchemy Session, Transaction and Migration

## 1. 먼저 한 문장으로

SQLAlchemy는 Python 코드와 DB 사이를 연결하는 library이고, Session은 ORM 작업 단위, Transaction은 변경을 확정하거나 되돌리는 경계, Alembic은 schema 변경 이력을 관리하는 도구입니다.

## 2. ORM, SQLAlchemy, MySQL

ORM은 Python class와 관계형 table의 mapping 방식입니다. SQLAlchemy는 ORM과 SQL expression, Engine, Session을 제공하는 Python library입니다. MySQL은 실제 데이터를 저장하고 SQL을 실행하는 DBMS입니다.

```text
Python Application
      ↓
SQLAlchemy ORM / Session
      ↓
MySQL connection
      ↓
MySQL tables
```

ORM을 쓴다고 SQL이 사라지는 것은 아닙니다. `select()`, `add()`, relationship과 mapping이 결국 DB가 실행할 SQL로 변환됩니다. 따라서 기본 SQL과 table 구조를 이해하면 ORM 코드를 더 정확히 읽을 수 있습니다.

## 3. 가장 간단한 ORM 예제

```python
from sqlalchemy import String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
```

`User`는 Python class이면서 `users` table의 구조를 설명하는 ORM Model입니다. `Base.metadata`에는 이 table의 metadata가 등록됩니다. 이 예제만으로 실제 DB에 table이 생성되는 것은 아닙니다.

## 4. Session과 Connection

둘은 같은 것이 아닙니다.

- **Database**: 데이터를 저장하고 SQL을 실행하는 시스템
- **Connection**: application과 DB 사이의 실제 통신 경로
- **Session**: ORM object 상태와 작업을 관리하는 SQLAlchemy 작업 공간
- **Transaction**: 변경을 하나의 논리적 단위로 확정·취소하는 DB 경계

학습용으로 다음처럼 그릴 수 있습니다.

```text
Python ORM Object
      ↓ session.add()
SQLAlchemy Session
      ↓ flush / execute
Transaction
      ↓ Connection checkout
DB Connection
      ↓ SQL
MySQL
```

실제 SQLAlchemy는 Session이 필요할 때 Engine의 connection pool에서 connection을 빌리고 반환합니다. Session이 connection 하나와 영원히 같은 객체라는 뜻은 아닙니다.

## 5. Session은 무엇을 하는가?

Session은 ORM 객체를 작업 목록에 올리고, flush·query·commit·rollback을 조정하며, 같은 작업 단위 안에서 객체 상태를 관리합니다.

현재 `database/session.py`는 다음 factory를 정의합니다.

```python
SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)
```

`SessionLocal`은 Session 자체가 아니라 Session을 만들어 주는 factory입니다. `BusMonitorStorage`는 이 factory를 주입받거나 기본 `SessionLocal`을 사용합니다.

## 6. add, flush, commit, rollback

### `add()`

```python
session.add(parent)
```

ORM object를 현재 Session의 작업 목록에 등록합니다. 이 순간 DB에 INSERT가 확정되었다고 볼 수 없습니다.

### `flush()`

현재 Transaction에서 필요한 SQL을 DB로 보냅니다. parent의 auto-generated primary key가 필요한 경우 flush 뒤에 `parent.id`가 채워질 수 있습니다.

```python
session.add(parent)
session.flush()
session.add(Child(parent_id=parent.id))
```

Flush는 SQL 실행과 오류 확인을 앞당기지만 commit은 아닙니다.

### `commit()`

현재 Transaction의 변경을 확정합니다. 이후 다른 DB 작업에서 영구적으로 관찰할 수 있는 상태가 됩니다.

### `rollback()`

현재 Transaction에서 아직 commit하지 않은 변경을 되돌립니다. 부모와 자식 저장 중 자식에서 실패하면 부분 상태를 남기지 않는 데 사용합니다.

```text
add(parent)
  ↓ flush → parent INSERT, id 확보
add(child)
  ↓ 실패
rollback()
  ↓ parent도 commit되지 않아 함께 취소
```

`flush == commit`이 아닙니다. `flush`는 SQL을 보내고, `commit`은 Transaction을 확정합니다.

## 7. automation-hub의 Session 사용

`BusMonitorStorage.save_snapshot()`은 다음 context를 사용합니다.

```python
with self._session_factory.begin() as session:
    session.add(snapshot)
    session.add(BusRouteSnapshotLane(...))
    session.add(BusRealtimeSnapshot(...))
```

`begin()` context는 정상 종료 시 commit하고 예외가 나면 rollback한 뒤 Session 자원을 정리합니다. 현재 production 코드가 모든 위치에서 직접 `session.commit()`과 `session.rollback()`을 반복하지 않는 이유입니다.

`database/snapshot_save_service.py`와 `google_finance/storage.py`도 `SessionLocal.begin()`을 사용합니다. Integration test에서는 중복 오류를 확인하기 위해 `flush()`와 명시적 `rollback()`을 직접 호출하는 사례가 있습니다.

## 8. Transaction과 Atomicity

Bus Monitor 한 실행은 다음 parent-child 구조를 저장합니다.

```text
BusRouteSnapshot
  ├─ BusRouteSnapshotLane 1
  ├─ BusRouteSnapshotLane 2
  ├─ BusRouteSnapshotLane 3
  ├─ BusRealtimeSnapshot vehicle 1
  └─ BusRealtimeSnapshot vehicle 2
```

Route row와 lane row가 저장된 뒤 vehicle 2에서 실패했다고 합시다. Transaction이 없다면 불완전한 실행이 DB에 남아 “성공한 route인데 일부 realtime만 있는지” 설명하기 어려워집니다. `BusMonitorStorage.save_snapshot()`은 하나의 `begin()` context 안에서 parent와 child를 등록하므로 예외가 발생하면 전체 작업이 rollback됩니다.

여기서 중요한 ACID 개념은 Atomicity입니다. 이 저장 묶음이 전부 확정되거나 전부 확정되지 않아야 한다는 의미입니다. Transaction은 실패를 숨기는 기능이 아니라 부분 상태를 방지하는 경계입니다.

## 9. Storage와 Repository

`BusMonitorStorage`는 persistence 관점에서 다음을 담당합니다.

- monitoring target 생성·조회
- enabled target 조회
- `BusRouteResult`를 ORM row로 변환
- snapshot 저장
- 최신·기간 snapshot 조회

Repository는 Domain object collection을 다루는 추상화라는 의미가 강하고, Storage는 저장 구현의 책임을 직접 드러내는 이름으로 쓰일 수 있습니다. 둘 중 하나가 항상 우월한 것은 아닙니다. 이 프로젝트는 실제 class 이름인 `BusMonitorStorage`, `StockQuoteStorage`, `SnapshotSaveService`를 기준으로 읽는 것이 정확합니다.

## 10. Alembic과 Migration

ORM Model을 수정하는 것과 실제 DB schema를 변경하는 것은 다른 작업입니다.

```text
ORM Model 변경
      ↓
Migration 파일 작성
      ↓
alembic upgrade
      ↓
실제 MySQL schema 변경
```

Alembic migration은 schema 변경을 순서와 코드로 기록합니다. 현재 revision chain은 다음과 같습니다.

```text
0001_initial_empty
  → 0002_create_trend_snapshots_table
  → 0003_create_stock_quote_snapshots_table
  → 0004_create_bus_monitor_snapshots_tables
```

`0004_create_bus_monitor_snapshots_tables.py`는 target, route snapshot, lane, realtime snapshot table을 foreign key 의존 순서로 만들고, `downgrade()`에서는 child부터 제거합니다.

- `upgrade`: 다음 schema revision 적용
- `downgrade`: 이전 revision 방향으로 되돌리는 migration 함수
- revision chain: `down_revision`으로 연결된 변경 이력

Migration 파일을 Git으로 관리하면 개발·검증·운영 환경이 어떤 순서로 schema를 바꿔야 하는지 재현할 수 있습니다. Migration은 DB backup과 다르며, 데이터를 복구하는 파일이 아닙니다.

## 11. Append-only Snapshot

현재 값만 UPDATE하는 모델은 과거를 잃습니다.

```text
17:00  ETA 20분
17:10  ETA 10분
17:20  ETA  2분
```

UPDATE만 하면 마지막 2분만 남지만, snapshot은 세 관찰을 모두 INSERT합니다. 그래서 시간대별 이동시간·대기시간·좌석 변화를 분석할 수 있습니다.

현재 구현 사례는 서로 다릅니다.

- Namuwiki: `TrendSnapshot`이 수집 시점의 Top 10 row를 append합니다.
- Google Finance: `StockQuoteSnapshot`이 종목별 시세 관찰을 append합니다.
- Bus Monitor: `BusRouteSnapshot`과 child lane/realtime row가 실행 결과를 append합니다.

세 package의 table 구조가 동일하다는 뜻은 아닙니다. 공통점은 과거 관찰을 현재 값으로 덮어쓰지 않는다는 persistence 목적입니다.

## 12. UTC와 KST

```python
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

collected_at = datetime.now(timezone.utc)  # aware UTC
kst = collected_at.astimezone(ZoneInfo("Asia/Seoul"))
```

- UTC: 전 세계 기준 시각
- KST: UTC+09:00인 한국 표준시
- aware datetime: timezone 정보와 offset을 가진 datetime
- naive datetime: timezone 정보가 없는 datetime

현재 저장 정책은 Python에서 aware UTC를 만들고, MySQL `DATETIME(timezone=False)`에 저장할 때 UTC 기준의 naive 값으로 변환하는 방식입니다. Dashboard는 저장된 naive UTC를 UTC로 해석한 뒤 `Asia/Seoul`로 바꿔 표시합니다.

`bus_monitor/storage.py`의 `_as_utc_naive()`와 `google_finance/db_models.py`의 `_as_utc_naive()`·`_as_utc_aware()`가 이 경계를 보여줍니다. `automation_dashboard/ui/formatting.py`의 `format_kst_datetime()`은 화면 표시를 담당합니다.

저장된 `2026-08-18 08:00:00`을 근거 없이 KST로 읽으면 실제 UTC 08:00을 KST 08:00으로 표시하는 9시간 오류가 생길 수 있습니다.

## 13. 실제 코드를 읽는 방법

1. [`bus_monitor/models.py`](../../bus_monitor/models.py)에서 Domain 결과와 상태를 읽습니다.
2. [`bus_monitor/db_models.py`](../../bus_monitor/db_models.py)에서 ORM table·FK·nullable·index를 읽습니다.
3. [`bus_monitor/storage.py`](../../bus_monitor/storage.py)의 `save_snapshot()`에서 domain → ORM mapping을 찾습니다.
4. `database/base.py`에서 `Base.metadata` 등록 지점을 확인합니다.
5. `database/session.py`에서 `SessionLocal` factory 설정을 읽습니다.
6. `alembic/env.py`에서 모든 ORM model을 import해 metadata를 등록하는 이유를 확인합니다.
7. `alembic/versions/0004_create_bus_monitor_snapshots_tables.py`의 `upgrade()`와 `downgrade()`를 비교합니다.
8. `tests/database/test_bus_monitor_integration.py`와 storage tests에서 실제 계약과 Fake transaction 경계를 확인합니다.

## 14. 언제 쓰지 않아도 되는가?

- 한 번 실행하고 버리는 script에는 ORM이 과할 수 있습니다.
- 작은 SQLite 실험에는 직접 table을 만드는 방식이 더 단순할 수 있습니다.
- 단일 INSERT에 복잡한 Repository abstraction을 추가할 필요는 없습니다.
- 현재 값만 중요하고 이력 분석이 필요 없다면 append-only snapshot이 과할 수 있습니다.
- ORM Model과 Domain Model이 분리될 변경 이유가 없다면 작은 프로젝트에서는 단순한 매핑으로 시작할 수 있습니다.

## 15. 자주 헷갈리는 개념

| 비교 | 한 문장 차이 |
|---|---|
| Domain vs ORM Model | 업무 의미 vs 저장 구조 |
| DTO vs Domain | 전달 모양 vs 업무 상태 |
| ORM vs Database | mapping library/기술 vs 실제 저장 시스템 |
| SQLAlchemy vs MySQL | Python DB library vs DBMS |
| Session vs Connection | ORM 작업 단위 vs DB 통신 경로 |
| flush vs commit | SQL 전송·오류 확인 vs 변경 확정 |
| rollback vs delete | 미확정 Transaction 취소 vs 이미 저장된 row 삭제 |
| Migration vs ORM Model | schema 변경 이력 vs 현재 Python mapping |
| Migration vs Backup | schema 재현 절차 vs 데이터 복구 사본 |
| Repository vs Storage | collection 추상화 강조 vs 저장 책임 강조 |
| Snapshot vs Current State | 관찰 이력 보존 vs 최신 값 유지 |
| aware vs naive datetime | timezone 포함 vs timezone 미포함 |

## 16. 내가 설명해본다면

“SQLAlchemy Session은 DB connection 그 자체가 아니라 ORM 객체와 작업을 관리하는 단위입니다. `add()`는 객체를 등록하고, `flush()`는 SQL을 보내 필요한 PK나 오류를 확인하며, `commit()`이 변경을 확정합니다. Bus Monitor는 parent route와 child lane·vehicle을 하나의 Transaction에 넣어 중간 실패 시 rollback하고, Alembic은 ORM 변경을 실제 MySQL schema에 적용할 migration 이력으로 관리합니다.”

## 17. 이해도 체크 해설

1. **`add()` 직후 프로세스가 종료되면?** `commit()` 전이라면 변경이 반드시 확정됐다고 볼 수 없습니다.
2. **Realtime child 저장 중 실패하면?** 하나의 저장 묶음이라면 route와 이미 등록한 child도 함께 rollback하는 것이 일관된 snapshot을 보존합니다.
3. **ORM column 추가는 자동 schema 변경인가?** 아닙니다. migration을 작성하고 `alembic upgrade`를 실행해야 합니다.
4. **17:00 row를 17:10 값으로 UPDATE하면?** 17:00의 과거 ETA와 변화량을 분석할 수 없게 됩니다.
5. **naive UTC를 KST로 읽으면?** 실제 시각보다 9시간 어긋난 표시가 발생할 수 있습니다.

## 다음 읽기

[Relational Database Design](relational-database-design.md)을 먼저 읽었다면, [Database Learning](../database/database_learning.md)에서 Engine·Session·SQL·Alembic의 세부 동작을, [Database Architecture](../database/database_architecture.md)에서 실제 table 관계와 운영 migration 구조를 읽습니다.
