# Bus Monitor Code Flow

이 문서는 현재 Bus Monitor가 **한 번 수집하고 저장한 뒤 Dashboard에서 읽히는 흐름**을 코드
순서대로 설명합니다. Provider raw payload와 API key는 이 흐름을 통과하지 않고 Provider 내부에
머뭅니다.

## 한눈에 보는 운영 흐름

```text
cron (Mon–Fri 17:00, 17:10, 17:20 KST)
        ↓
run_bus_monitor.sh
        ↓
bus_monitor/main.py --target-id 2
        ↓
BusMonitorStorage.get_target()
        ↓
BusMonitorPipeline
        ├── ODsayRouteProvider
        ├── GyeonggiProvider.get_station_routes()
        └── GyeonggiProvider.get_arrivals()
        ↓
BusRouteResult
        ↓
BusMonitorStorage.save_snapshot()
        ↓
MySQL
        ↓
automation_dashboard/pages/4_bus_monitor.py
```

`run_dashboard.sh`는 별도 실행 경로입니다. repository root를 `PYTHONPATH`로 설정하고
`.venv/bin/streamlit`으로 Dashboard를 시작합니다. Dashboard는 자동화를 실행하지 않고 MySQL의
snapshot을 read-only로 조회합니다.

## 단계별 흐름

### 1. cron과 shell wrapper

`docs/operations/cron.md`의 cron expression은 평일 17:00, 17:10, 17:20에
`run_bus_monitor.sh`를 시작합니다. Wrapper는 다음 운영 경계를 책임집니다.

- 자신의 위치에서 repository root를 계산하고 `.venv/bin/python`을 사용합니다.
- `.env`를 읽고 `DATABASE_URL`, `ODSAY_API_KEY`, `GYEONGGI_SERVICE_KEY`가 비어 있지 않은지
  확인합니다.
- target ID 2를 고정해 `python -m bus_monitor.main --target-id 2`를 실행합니다.
- `flock -n`과 `logs/bus_monitor_target_2.lock`으로 겹치는 실행을 막습니다.
- 표준 출력과 오류를 `logs/bus_monitor.log`에 기록하고 기본 600초 timeout을 적용합니다.

### 2. target 조회와 composition root

`bus_monitor/main.py`의 `_run_target()`은 `BusMonitorStorage.get_target()`으로 enabled target을
읽습니다. target에는 출발지·목적지 이름과 WGS84 좌표가 있고, 특정 통근 경로는 Pipeline 코드에
하드코딩되지 않습니다.

같은 파일의 `build_pipeline()`은 `BusMonitorSettings`에서 key를 읽어
`OdsayRouteProvider`와 `GyeonggiProvider`를 만들고 `BusMonitorPipeline`에 주입합니다.

### 3. ODsay route planning

`bus_monitor/odsay.py`의 `OdsayRouteProvider.search_route()`는 입력 좌표로 ODsay 대중교통
길찾기 API를 호출합니다. Provider가 반환 순서를 바꾸지 않고 첫 번째 유효 route option의 첫
버스 구간을 정규화합니다.

정규화 결과는 `bus_monitor/models.py`의 `TransitRoute`, `BusLeg`, `RouteStation`, `BusLane`입니다.
여기에는 총 이동시간, 도보거리, 환승 수, 승·하차 정류장과 ODsay bus lane 후보가 포함됩니다.

### 4. 경기도 노선 검증과 도착정보

`bus_monitor/pipeline.py`는 `BusLeg.start_station.local_station_id`를 경기도 API의 `stationId`로
전달합니다.

1. `GyeonggiProvider.get_station_routes()`가 해당 정류장을 실제로 지나는 `routeId` 목록을 읽습니다.
2. `_matched_route_ids()`가 ODsay `BusLane.local_route_id`와 경기도 `routeId`를 **정확히** 비교합니다.
   표시용 버스 번호는 fallback key로 사용하지 않습니다.
3. 일치한 route ID가 있으면 `GyeonggiProvider.get_arrivals()`로 정류장의 도착정보를 읽고, 일치
   노선의 차량만 `RealtimeArrival`로 남깁니다.

ODsay 경로가 실패하면 결과는 `RouteStatus.FAILED`와 `RealtimeStatus.NOT_REQUESTED`입니다.
경로는 성공했지만 경기도 호출이나 노선 검증을 사용할 수 없으면 `UNAVAILABLE`, 검증된 노선에
현재 접근 중인 차량이 없으면 `NO_MATCHING_ARRIVAL`입니다. 이 구분 때문에 partial success가
실패처럼 사라지지 않습니다.

### 5. normalized result와 저장

`BusMonitorPipeline.run()`의 반환값은 `BusRouteResult`입니다. 이 계약은 route 상태, realtime
상태, 선택된 route/bus leg와 현재 도착 차량만 담습니다.

`BusMonitorStorage.save_snapshot()`은 한 SQLAlchemy transaction 안에서 다음을 append합니다.

```text
BusRouteResult
  ├── bus_route_snapshots              (실행당 1 row)
  ├── bus_route_snapshot_lanes         (ODsay 후보 lane별 1 row)
  └── bus_realtime_snapshots           (접근 차량별 1 row)
```

수집 시각은 timezone-aware UTC에서 MySQL의 UTC-naive `DATETIME`으로 저장됩니다. 결과 실패나
partial success도 route snapshot은 남길 수 있으며, raw provider JSON은 저장하지 않습니다.

### 6. Dashboard 조회와 KST 표시

`automation_dashboard/queries/bus_monitor.py`는 ORM row를 화면 전용 DTO로 바꾸고 UTC-naive
수집 시각을 KST로 변환합니다. `automation_dashboard/pages/4_bus_monitor.py`는 다음을 표시합니다.

- target header의 출발지 → 목적지와 최신 조회시간
- 예상 이동시간, 남은 시간, 남은 정거장, 남은 좌석
- `collected_at + arrival_seconds`로 계산한 예상 도착시간
- KST 당일의 예상 이동시간·버스 대기시간·잔여좌석 chart

Dashboard의 기본 realtime 표는 내부 ID와 차량번호를 보여주지 않습니다. 저장은 유지하되 화면은
통근 판단에 필요한 ETA·정거장·좌석 중심으로 단순하게 유지합니다.

## 주요 파일 책임

| 파일 | 책임 |
|---|---|
| `bus_monitor/config.py` | ODsay·경기도 key 설정을 안전하게 읽음 |
| `bus_monitor/main.py` | CLI 인자 처리, Provider/Storage 조립, target 실행과 결과 출력 |
| `bus_monitor/odsay.py` | ODsay route 응답을 domain model로 정규화 |
| `bus_monitor/gyeonggi.py` | 경기도 정류장·경유노선·도착정보 API 응답을 정규화 |
| `bus_monitor/pipeline.py` | route → 정류장 경유노선 검증 → arrival의 순서를 조정 |
| `bus_monitor/models.py` | Provider와 저장 계층 사이의 normalized 결과 계약 |
| `bus_monitor/db_models.py` | target과 append-only snapshot ORM table 정의 |
| `bus_monitor/storage.py` | target 조회와 snapshot transaction 저장/조회 |
| `alembic/versions/0004_create_bus_monitor_snapshots_tables.py` | Bus Monitor table schema migration |
| `run_bus_monitor.sh` | cron-safe target 2 수집 wrapper, lock/log/timeout 경계 |
| `run_dashboard.sh` | root import path를 보장하는 Streamlit wrapper |
| `automation_dashboard/queries/bus_monitor.py` | Dashboard read model과 KST-day 범위 조회 |
| `automation_dashboard/pages/4_bus_monitor.py` | 최신 상태·이력·chart를 렌더링하는 read-only 화면 |

## 관련 문서

- [Package README](README.md): 기능, 설정, DB, cron과 제한사항
- [Bus Monitor Decisions](../../architecture/bus_monitor_decisions.md): Provider와 persistence 선택 근거
- [Bus Monitor Operations](../../operations/bus_monitor.md): 수동 실행, DB 점검, cron 운영 절차
