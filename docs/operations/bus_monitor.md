# Bus Monitor 운영 절차

이 문서는 target ID 2의 퇴근길 Bus Monitor를 WSL cron에서 수집하는 현재 운영 계약을 다룬다.

## 대상과 수동 실행

```text
Target ID: 2
Name: 퇴근길
```

```bash
/home/kstec/projects/automation-hub/run_bus_monitor.sh
```

Wrapper는 `.venv/bin/python -m bus_monitor.main --target-id 2`를 실행한다. target 좌표와 노선은 script에 저장하지 않고 DB target과 Provider 결과에서 읽는다.

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
