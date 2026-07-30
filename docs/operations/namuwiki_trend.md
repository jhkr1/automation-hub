# namuwiki_trend 운영 절차

이 문서는 현재 구현된 `namuwiki_trend`의 Docker MySQL, snapshot과 WSL cron 절차만 다룬다.

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
프로세스에 전달하며 `flock`으로 중복 실행을 방지한다.

```bash
./run_namuwiki_trend.sh
```

현재 cron 간격과 운영 환경은 Wrapper 및 실제 crontab 설정을 확인해야 한다. 이 문서는
특정 호스트의 crontab이 등록되어 있다고 가정하지 않는다.
