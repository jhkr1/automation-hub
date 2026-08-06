# namuwiki_trend 운영 절차

이 문서는 현재 구현된 `namuwiki_trend`의 Docker MySQL, snapshot과 WSL cron 절차만 다룬다.

현재 Production 흐름은 Google News RSS와 Gemini를 사용한다. `NAVER_CLIENT_ID`와
`NAVER_CLIENT_SECRET`은 현재 실행 경로에서 참조되지 않는 legacy 설정이며, 운영을 위해
가짜 값을 입력하지 않는다.

## 검증

```bash
python scripts/verify.py
```

기본 테스트는 외부 MySQL을 요구하지 않는다. DB 통합 테스트는 MySQL과 마이그레이션이
준비된 환경에서 다음처럼 별도로 실행한다.

```bash
RUN_DB_INTEGRATION=1 pytest tests/database/test_integration.py -q
```

## MySQL 개발 환경

```bash
docker compose up -d mysql
docker compose ps
```

Python 프로세스에서 DB를 사용하려면 `.env.docker`의 값을 셸 환경변수로 export한다.
Python 설정은 `.env.docker` 파일을 직접 읽지 않는다.

```bash
set -a
source .env.docker
set +a
```

중지할 때는 일반적으로 named volume을 보존하는 `docker compose stop mysql` 또는
`docker compose down`을 사용한다. `docker compose down -v`는 개발 DB 데이터를 삭제할 수
있으므로 데이터 삭제가 필요한 경우에만 사용한다.

## Snapshot과 Daily Trend

```bash
python -m namuwiki_trend.snapshot_main
python -m namuwiki_trend.daily_trend_main --date 2026-07-30 --limit 10
```

snapshot은 `trend_snapshots`에 저장되고, Daily Trend 조회는 `collection_date`를 기준으로
집계한다. 저장 시각은 UTC 기준으로 관리하며 사용자 표시 날짜는 Asia/Seoul 기준이다.

## WSL cron

운영 Wrapper는 저장소 루트를 기준으로 `.venv/bin/python`을 사용하고, `.env`를 자식
프로세스에 전달하며 `flock`으로 중복 실행을 방지한다. 기본 전체 timeout은 10분이며,
`SIGINT`와 `SIGTERM`을 받으면 실행 중인 자식에게 같은 신호를 전달한다. timeout은
표준 종료 코드 `124`, 신호 중단은 각각 `130`과 `143`으로 기록된다.

```bash
./run_namuwiki_trend.sh --key-profile production
./run_namuwiki_trend.sh --key-profile test
```

Gemini를 호출하지 않는 Snapshot 수집은 별도 Wrapper로 실행한다.

Namuwiki enrichment는 `production` 또는 수동 smoke test용 `test` profile을 명시한다.
선택된 profile 이름만 Python entrypoint로 전달하며, credential 선택·quota reservation·retry는
`LlmRuntime`이 담당한다. 선택된 Namuwiki key만 사용하며 다른 job/profile key로 fallback하지
않는다.

```bash
python -m namuwiki_trend.main --key-profile test
```

```bash
./run_namuwiki_snapshot.sh
```

Gemini가 포함된 전체 enrichment는 뉴스가 있는 Top 10 항목을 하나의 JSON Batch로 처리한다.
정상 실행에서 `LlmRuntime` 호출은 최대 1회이며, 뉴스가 없는 항목은 기존 근거 부족
fallback을 사용한다. Batch 응답의 rank·keyword·reason 매핑이 완전하지 않으면 전체 분석을
실패시키고 기존 `output/trend_insights.json`은 유지한다. 일시적 Provider 오류의 retry와
quota reservation은 `LlmRuntime`이 담당한다. 무료 quota를 고려해 cron 등록 전에는 `test`
profile로 수동 smoke test를 수행한다. 현재 production artifact 경로는 기존과 동일하며,
test artifact 분리는 다음 Batch Sprint의 범위다. Snapshot만 수집하는 `snapshot_main`은
2시간 주기부터 시작할 수 있다.

예시:

```cron
# cron host local timezone 기준 예시
17 */2 * * * /home/kstec/projects/automation-hub/run_namuwiki_snapshot.sh
30 8 * * * /home/kstec/projects/automation-hub/run_namuwiki_trend.sh --key-profile production
```

현재 cron 간격과 운영 환경은 Wrapper 및 실제 crontab 설정을 확인해야 한다. 이 문서는
특정 호스트의 crontab이 등록되어 있다고 가정하지 않는다.
