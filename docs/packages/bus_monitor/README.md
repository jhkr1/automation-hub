# bus_monitor

`bus_monitor`는 좌표로 정의한 통근 경로를 조회하고, 승차 정류장에서 실제로 도착하는
버스 정보를 snapshot으로 저장하는 Package입니다. 현재 운영 target은 DB의 ID 2, `퇴근길`이며
경로 이름·좌표·활성 상태는 코드가 아니라 DB에 저장합니다.

## 문제 정의

통근 시에는 추천 버스, 승차 정류장, 예상 이동시간뿐 아니라 지금 도착하는 차량의 대기시간,
남은 정거장과 좌석 정보가 함께 필요합니다. 이 Package는 한 번의 수집 결과를 덮어쓰지 않고
시간별 snapshot으로 저장해 Dashboard에서 현재 상태와 당일 변화를 읽을 수 있게 합니다.

## 기존 RPA 방식과 Python 전환

기존 RPA는 지도 화면에 출발지와 목적지를 입력하고 Recorder로 화면의 대중교통 정보를 읽었습니다.
현재 구현은 지도 UI, DOM selector, Playwright에 의존하지 않습니다. ODsay와 경기도 공식 API의
문서화된 응답을 정규화해 실행·재시도 경계와 저장 결과를 코드와 테스트로 확인합니다.

## 현재 기능

- 좌표 4개로 ODsay의 첫 번째 유효 경로 option에서 첫 버스 구간을 조회합니다.
- ODsay 승차 정류장 ID로 경기도 정류소별 경유노선을 조회해 후보 `busLocalBlID`를 검증합니다.
- 검증된 노선의 경기도 도착정보를 정규화합니다.
- route 성공 후 realtime이 없거나 사용할 수 없는 상태도 결과 상태로 보존합니다.
- enabled target 실행 결과를 MySQL에 append-only snapshot으로 한 transaction에 저장합니다.
- Streamlit Dashboard가 target별 최신 결과와 KST 기준 당일 이력을 read-only로 조회합니다.

아직 장소명 geocoding, 목적지까지의 모든 버스 구간 처리, 다중 target scheduler, 알림과 추천
알고리즘은 구현하지 않았습니다.

## Architecture

```text
Origin / Destination coordinates
        ↓
ODsay Route Planning
        ↓
TransitRoute / BusLeg / BusLane
        ↓
Gyeonggi station-route validation
        ↓
Gyeonggi arrival lookup
        ↓
BusRouteResult
        ↓
BusMonitorStorage
        ↓
MySQL snapshots
        ↓
Streamlit Dashboard
```

`BusMonitorPipeline`은 Provider를 생성자 주입으로 받아 이 흐름을 조정합니다. ODsay route가
실패하면 realtime은 요청하지 않으며, ODsay가 성공한 뒤 경기도 조회가 실패하거나 검증된 노선이
없으면 route 결과는 유지하고 realtime 상태를 `UNAVAILABLE`로 반환합니다. 검증된 노선에는
현재 도착 차량이 없을 수 있으며, 이는 `NO_MATCHING_ARRIVAL`로 구분합니다.

상세 실행 순서는 [CODE_FLOW.md](CODE_FLOW.md), Provider 선택 근거는
[Bus Monitor Decisions](../../architecture/bus_monitor_decisions.md)를 참고합니다.

## API Provider

| Provider | 현재 역할 | Production runtime 사용 |
|---|---|---:|
| ODsay | 출발·도착 좌표의 대중교통 route와 첫 버스 구간, lane 후보 | 예 |
| 경기도 공식 버스 API | 승차 정류장 경유노선 검증과 도착정보 | 예 |
| TAGO | 정류소·도착정보와 cross-provider mapping 조사 PoC | 아니오 |

Pipeline은 표시용 노선번호만으로 두 Provider를 연결하지 않습니다. ODsay
`startLocalStationID`를 경기도 `stationId`로 사용하고, ODsay `busLocalBlID`가 경기도
정류소별 경유노선의 `routeId`와 정확히 같은 경우만 realtime arrival을 결합합니다.

## 실행 방법

개발 환경에서 의존성을 설치합니다.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dashboard,dev]"
```

좌표 직접 실행은 저장하지 않는 smoke test 용도입니다.

```bash
python -m bus_monitor.main \
  --origin-longitude 127.102446246531 \
  --origin-latitude 37.4043389599242 \
  --destination-longitude 127.10856729001851 \
  --destination-latitude 37.27220279535416
```

운영 target의 수동 수집은 wrapper를 사용합니다.

```bash
./run_bus_monitor.sh
```

이 wrapper는 repository root 기준 `.venv/bin/python -m bus_monitor.main --target-id 2`를
실행하고 결과를 DB에 저장합니다. `--target-id`를 직접 사용하려면 enabled target이 먼저 DB에
있어야 합니다.

```bash
python -m bus_monitor.main --target-id 2
```

target 실행은 route failure와 partial success도 snapshot 저장에 성공하면 exit code `0`으로
끝납니다. target 없음·비활성, 설정 오류, DB 저장 오류는 exit code `1`입니다.

## 환경변수

실제 값은 `.env`에만 두고 source control, 로그, 문서에 기록하지 않습니다.

| 환경 변수 | 분류 | 필요 시점 | 용도 |
|---|---|---|---|
| `ODSAY_API_KEY` | Production | route 조회 | ODsay route planning 인증 |
| `GYEONGGI_SERVICE_KEY` | Production | realtime 조회 | 경기도 정류장 경유노선·도착정보 인증 |
| `DATABASE_URL` | Production | target 실행·Dashboard | MySQL target 및 snapshot 저장/조회 |
| `DASHBOARD_DATABASE_URL` | Optional | Dashboard 선택 | Dashboard 전용 DB URL. 없으면 `DATABASE_URL`을 사용 |
| `TAGO_SERVICE_KEY` | POC/Legacy | `bus_monitor.tago` 직접 사용 | 현재 Pipeline이 사용하지 않는 TAGO provider client |
| `TAGO_ARRIVAL_SERVICE_KEY`, `TAGO_STATION_SERVICE_KEY`, `TAGO_LATITUDE`, `TAGO_LONGITUDE`, `TAGO_CITY_CODE`, `TAGO_NODE_ID` | POC/Legacy | `bus_monitor.tago_poc` 실행 | TAGO Station → Arrival 조사용 값 |

TAGO 관련 값은 현재 production Pipeline의 필수 설정이 아닙니다.

## DB

Alembic revision `0004_bus_monitor_snapshots`가 다음 네 table을 만듭니다.

```text
bus_monitoring_targets
        ↓ 1:N
bus_route_snapshots
        ├── ↓ 1:N bus_route_snapshot_lanes
        └── ↓ 1:N bus_realtime_snapshots
```

- `bus_monitoring_targets`: 이름, 출발·도착 좌표와 enabled 상태를 소유합니다.
- `bus_route_snapshots`: 한 수집 실행의 route/realtime 상태와 경로 요약을 저장합니다.
- `bus_route_snapshot_lanes`: ODsay가 반환한 lane 후보와 원래 순서를 저장합니다.
- `bus_realtime_snapshots`: 실제로 접근 중인 차량 하나당 한 row를 저장합니다. 한 노선에 두
  차량이 응답되면 두 row가 생기므로 ETA와 좌석의 시점별 변화를 잃지 않습니다.

저장은 append-only입니다. 과거 수집 결과를 갱신하지 않아 Dashboard의 당일 추이를 계산할 수
있습니다. raw JSON, HTTP response, API key는 저장하지 않습니다. 저장 구현은
`bus_monitor/storage.py`, ORM model은 `bus_monitor/db_models.py`, schema 이력은
`alembic/versions/0004_create_bus_monitor_snapshots_tables.py`에 있습니다.

## cron

KST local timezone의 현재 운영 host에서는 target 2를 평일 다음 시각에 수집합니다.

```text
17:00 / 17:10 / 17:20 KST
```

```cron
0,10,20 17 * * 1-5 /home/kstec/projects/automation-hub/run_bus_monitor.sh
```

`run_bus_monitor.sh`은 `flock -n`으로 `logs/bus_monitor_target_2.lock`을 획득하지 못한
중복 실행을 exit code `75`로 건너뜁니다. 운영 명령, 로그와 점검 절차는
[Bus Monitor 운영 문서](../../operations/bus_monitor.md)를 기준으로 합니다.

## Dashboard

Dashboard는 수집을 실행하지 않고 저장된 snapshot만 조회합니다.

```bash
./run_dashboard.sh
```

Bus Monitor page는 header에 출발지 → 목적지를 한 번 표시하고, 최신 수집의 조회시간,
예상 이동시간, 남은 시간, 남은 정거장, 남은 좌석, 예상 도착시간을 보여줍니다. 예상 도착시간은
DB column이 아니라 KST로 변환한 `collected_at + arrival_seconds`로 presentation layer에서
계산합니다. 내부 ID와 차량번호는 기본 realtime 표에서 숨겨 사용자 판단에 필요한 정보에 집중합니다.

## 테스트

기본 검증은 외부 API와 실제 MySQL에 의존하지 않는 unit test를 실행합니다.

```bash
python scripts/verify.py
```

이 명령은 Ruff, pytest, compileall, `git diff --check`를 순서대로 실행합니다. 실제 Provider와
MySQL 검증은 API key·DB가 준비된 운영 환경에서 별도로 수행해야 합니다.

## 현재 제한사항

- ODsay가 반환한 첫 route option의 첫 bus leg만 현재 Pipeline이 사용합니다.
- 경기도 공식 API 범위 밖 노선은 realtime enrichment 대상이 아닙니다.
- Vehicle Location API client는 존재하지만 MVP runtime은 station route와 arrival API만 호출합니다.
- TAGO는 현재 route enrichment 경로에 사용하지 않습니다.
- 좌석/혼잡 필드는 Provider가 값을 주지 않거나 좌석이 unavailable sentinel일 때 비어 있을 수 있습니다.
