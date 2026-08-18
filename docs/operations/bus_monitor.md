# Bus Monitor 운영 절차

이 문서는 target ID 2의 퇴근길 Bus Monitor를 WSL cron에서 수집하는 현재 운영 계약을 다룬다.
현재 production 흐름은 `ODsay → 경기도 공식 버스 API → MySQL snapshot`이며, TAGO는 이
route enrichment 흐름에 사용하지 않는다.

## 대상과 수동 실행

```text
Target ID: 2
Name: 퇴근길
```

```bash
/home/kstec/projects/automation-hub/run_bus_monitor.sh
```

Wrapper는 `.venv/bin/python -m bus_monitor.main --target-id 2`를 실행한다. target 좌표와 노선은 script에 저장하지 않고 DB target과 Provider 결과에서 읽는다.

직접 CLI를 실행할 때는 repository root에서 다음 명령을 사용한다.

```bash
./.venv/bin/python -m bus_monitor.main --target-id 2
```

운영 수집에는 `.env`의 `DATABASE_URL`, `ODSAY_API_KEY`, `GYEONGGI_SERVICE_KEY`가 필요하다.
실제 값은 출력·로그·문서에 남기지 않는다. Dashboard 전용 DB URL을 분리할 경우
`DASHBOARD_DATABASE_URL`을 설정할 수 있으며, 없으면 Dashboard는 `DATABASE_URL`을 사용한다.

## Schedule

Host local timezone이 KST인 환경에서 평일 다음 시각에 실행한다.

```text
17:00 / 17:10 / 17:20 KST
```

```cron
0,10,20 17 * * 1-5 /home/kstec/projects/automation-hub/run_bus_monitor.sh
```

현재 host timezone은 `date '+%Z %z'`로 확인한다. `crontab -l`로 등록 entry를 확인하고, cron daemon은 `systemctl status cron` 또는 `service cron status`로 점검한다.

## Lock과 로그

```text
Lock: logs/bus_monitor_target_2.lock
Log:  logs/bus_monitor.log
```

`flock -n`이 lock을 얻지 못하면 실행은 API와 DB 호출 없이 exit `75`로 종료한다. 로그에는 target ID, 시작/종료 timestamp, process exit code와 CLI의 route/realtime 상태·snapshot ID가 남는다. API key, `.env` 원문, raw provider response는 기록하지 않는다.

## DB와 Dashboard 점검

Migration head와 target 2의 최신 snapshot은 repository root에서 확인한다.

```bash
./.venv/bin/alembic current
./.venv/bin/python -c 'from bus_monitor.storage import BusMonitorStorage; snapshot = BusMonitorStorage().get_latest_snapshot(2); print("no snapshot" if snapshot is None else f"snapshot_id={snapshot.id} collected_at={snapshot.collected_at} route={snapshot.route_status} realtime={snapshot.realtime_status}")'
```

첫 명령은 `0004_bus_monitor_snapshots`가 적용됐는지 확인하는 용도입니다. 두 번째 명령은
DB에 저장된 최신 parent snapshot의 식별자·수집시각·상태만 출력하며 API key나 raw payload를
출력하지 않습니다. realtime 차량과 lane의 상세는 Dashboard 또는 DB query layer에서 조회합니다.

Dashboard는 수집을 시작하지 않고 DB만 read-only로 조회합니다.

```bash
./run_dashboard.sh
```

`run_dashboard.sh`는 repository root와 `.venv/bin/streamlit`을 명시하고 root `PYTHONPATH`를
설정하므로 `bus_monitor` import가 shell의 현재 directory에 따라 달라지지 않습니다. Bus Monitor
page에서 target을 선택해 최신 snapshot과 KST 당일 이력을 확인합니다.

## API 호출량

현재 Pipeline은 실행당 다음을 호출한다.

| Provider | 호출 수 |
|---|---:|
| ODsay route planning | 1 |
| Gyeonggi station route validation | 1 |
| Gyeonggi arrival | 1 |
| Vehicle location | 0 |

따라서 평일 3회 기준 ODsay 3회, Gyeonggi 6회이며, 5일 주는 각각 15회·30회, 월 22영업일 추정은 각각 66회·132회다. 이 사용량은 매우 낮지만, 실제 ODsay·경기도 API 계약 한도는 각 API 콘솔에서 별도 확인한다.

## Snapshot 검증

수동 실행 전후에 target 2의 최신 snapshot ID를 비교한다. 성공·partial success·route failure가 저장되면 wrapper exit code는 `0`이며, DB/설정/target 오류는 non-zero다. 같은 target을 반복 실행하면 snapshot은 append-only로 추가된다.

route success 뒤 Gyeonggi realtime을 사용할 수 없으면 `UNAVAILABLE`, 검증된 노선에 현재
접근 중인 차량이 없으면 `NO_MATCHING_ARRIVAL`로 저장될 수 있다. 이 상태는 route 결과가
저장되지 않았다는 뜻이 아니다.
