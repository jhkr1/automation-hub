# bus_monitor

> ODsay 경로 계획과 경기도 공식 실시간 버스 정보를 결합해 하나의 monitoring target을 조회·저장하는 Package입니다.

## Environment

| 환경 변수 | 용도 |
|---|---|
| `ODSAY_API_KEY` | 대중교통 경로 계획 |
| `GYEONGGI_SERVICE_KEY` | 경기도 정류장 경유노선·도착정보 |
| `DATABASE_URL` | Monitoring Target 및 snapshot MySQL 저장 |

## Commands

좌표 직접 실행은 smoke test 용도로 유지합니다.

```bash
python -m bus_monitor.main \
  --origin-longitude 127.102446246531 \
  --origin-latitude 37.4043389599242 \
  --destination-longitude 127.10856729001851 \
  --destination-latitude 37.27220279535416
```

운영 전 수동 수집은 DB에 생성된 enabled target을 사용합니다.

```bash
python -m bus_monitor.main --target-id 1
```

`--target-id` 실행은 target 좌표로 Pipeline을 실행하고 route, lane, realtime snapshot을 하나의 transaction으로 저장합니다. route failure와 partial success도 저장이 성공하면 process exit code `0`입니다. target 없음·비활성, 설정 오류, DB 저장 오류는 `1`입니다. target 2의 평일 cron 운영은 [운영 문서](../../operations/bus_monitor.md)를 따른다.

첫 target은 `BusMonitorStorage.create_target()`으로 명시적으로 생성합니다. Package 코드에는 특정 통근 경로를 하드코딩하지 않습니다.

## Current scope

- ODsay Route Planning
- 경기도 공식 Realtime enrichment
- MySQL append-only target/route/lane/realtime snapshot
- 단일 target 수동 CLI 실행
- target 2의 평일 17:00 / 17:10 / 17:20 KST cron 수집
- Streamlit Dashboard의 target별 최신 상태와 KST 당일 snapshot 조회

알림, 장소명 geocoding과 다중 target scheduler는 아직 구현하지 않았습니다.
