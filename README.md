# automation-hub

Python 기반 업무 자동화 프로젝트 모음입니다. 각 자동화 프로젝트는 독립 패키지로 관리하며,
현재 `namuwiki_trend`와 `google_finance`의 설정·모델 뼈대가 있습니다.

## 현재 구현된 기능

`namuwiki_trend`에서 실제로 구현된 기능은 다음과 같습니다.

- Playwright 기반 나무위키 실시간 검색어 Top 10 수집
- `TrendItem` 모델과 rank 보존
- `TrendItem` CSV 저장
- Google News RSS 기반 뉴스 문맥 검색
- `NewsArticle` 모델
- 뉴스 문맥을 사용하는 Gemini Prompt grounding
- Gemini `gemini-3.5-flash` 기반 reason 생성
- Gemini 호출 최소 간격 제한과 429 `RESOURCE_EXHAUSTED` bounded retry
- 단일 `TrendItem` enrichment와 `TrendInsight` 생성
- `TrendPipeline` 기반 Top10 목록 enrichment orchestration
- `DailyTrendNewsService` 기반 Daily Trend와 뉴스 문맥 결합
- `TrendInsight` JSON 저장
- `TrendInsight` 품질 진단 지표 계산
- 외부 명령을 통합 실행하는 verification Harness

`google_finance`는 현재 `config.py`와 `models.py`만 구현되어 있습니다.

## 현재 Pipeline

실제 구현된 데이터 흐름은 다음과 같습니다.

```text
Playwright Collector
        ↓
list[TrendItem]
        ├── save_trends_to_csv()
        └── TrendPipeline.run()
                ↓
        TrendEnricher.enrich(trend)
                ↓
        NewsContextProvider
                ↓
        list[NewsArticle]
                ↓
        GeminiReasonGenerator
                ↓
        TrendInsight
```

`TrendPipeline`은 Collector callable과 `TrendEnricher`를 주입받아 목록 순회와 결과 순서
보존을 담당합니다. `namuwiki_trend.main`은 운영 의존성을 조립하고 Pipeline 실행 결과를
`output/trend_insights.json`에 저장하는 Application Entry Point입니다.

## 개발 환경

Python 3.12 이상과 가상환경을 사용합니다.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

환경변수 템플릿을 복사한 뒤 필요한 값을 설정합니다.

```bash
cp .env.example .env
```

`.env.example`에는 `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET`, `GEMINI_API_KEY`,
`STOCK_SYMBOLS`, `LOG_LEVEL`이 정의되어 있습니다. API Key와 실제 secret은 저장소에
커밋하지 않습니다.

## Docker MySQL 개발 환경

애플리케이션 코드와 연결하지 않은 로컬 개발용 MySQL 8.4 LTS 컨테이너를 제공합니다.
데이터는 named Docker Volume `mysql_data`에 저장되며, 컨테이너가 재생성되어도 유지됩니다.
컨테이너 timezone은 `Asia/Seoul`로 설정합니다.

기본값으로 바로 시작:

```bash
docker compose up -d
```

개발용 환경변수를 지정하려면 템플릿을 복사하고 값을 변경합니다.

```bash
cp .env.docker.example .env.docker
docker compose --env-file .env.docker up -d
```

상태와 healthcheck 확인:

```bash
docker compose ps
docker compose logs mysql
```

MySQL이 healthy 상태가 되면 로컬 호스트의 `${MYSQL_PORT:-3306}` 포트로 접근할 수 있습니다.
현재 snapshot 저장 흐름은 `trend_snapshots` 테이블에 연결되어 있습니다.

중지:

```bash
docker compose down
```

`down`은 named Volume을 삭제하지 않습니다. 개발 데이터를 삭제해야 하는 경우에만 별도로
`docker compose down -v`를 사용합니다.

## SQLAlchemy와 Alembic 개발 환경

SQLAlchemy 2.x, Alembic, PyMySQL은 `TrendSnapshot` ORM과 원본 snapshot 저장 흐름에 사용됩니다.
Gemini enrichment 결과 JSON 저장 흐름과 원본 snapshot DB 저장 흐름은 별도의 실행 진입점입니다.

의존성을 설치합니다.

```bash
pip install -e ".[dev]"
```

Docker 환경변수 파일은 Compose가 사용하므로, Python 명령에서도 같은 값을 사용하려면 셸
환경변수로 내보냅니다. Python 설정은 `.env.docker` 파일을 직접 읽지 않습니다.

```bash
cp .env.docker.example .env.docker
set -a
source .env.docker
set +a
```

DB 연결과 Alembic 상태를 확인합니다.

```bash
python scripts/test_database_connection.py
alembic current
```

새로운 ORM 모델을 추가한 뒤 migration을 생성할 때는 다음 명령을 사용합니다.

```bash
alembic revision --autogenerate -m "describe schema change"
alembic upgrade head
```

현재 초기 migration은 의도적으로 비어 있으며 테이블을 생성하지 않습니다.

## 원본 Snapshot 실행 및 확인

MySQL을 시작하고 상태를 확인합니다.

```bash
docker compose up -d mysql
docker compose ps
```

`.env.docker`의 `DATABASE_URL`을 Python 프로세스 환경변수로 로드한 뒤 snapshot을 실행합니다.

```bash
set -a
source .env.docker
set +a
python -m namuwiki_trend.snapshot_main
```

성공하면 저장된 row 수가 출력됩니다.

```text
Snapshot collection completed: 10 rows saved.
Collected at: 2026-07-30 03:45:31 UTC
Collected at: 2026-07-30 12:45:31 KST
```

`collected_at`은 DB에 naive UTC `DATETIME`으로 저장되며, CLI는 사용자가 이해하기 쉽도록
UTC와 KST 표시를 함께 출력합니다. CLI의 KST 표시는 저장값이나 DB timezone을 변경하지
않습니다.

수집 결과가 없으면 다음 메시지가 출력되며 정상 종료합니다.

```text
Snapshot collection completed: no trends collected.
```

Compose service를 통해 MySQL CLI에 접속합니다. 비밀번호는 명령에 직접 입력하지 말고
프롬프트에서 입력합니다.

```bash
docker compose exec mysql mysql --default-character-set=utf8mb4 -u automation_hub -p automation_hub
```

PowerShell에서도 같은 한 줄 명령을 사용할 수 있습니다.

```powershell
docker compose exec mysql mysql --default-character-set=utf8mb4 -u automation_hub -p automation_hub
```

이미 접속한 세션에서는 다음 명령으로 문자셋을 설정할 수 있습니다.

```sql
SET NAMES utf8mb4;
```

사용자명과 데이터베이스명은 `.env.docker`의 `MYSQL_USER`, `MYSQL_DATABASE` 값을 확인합니다.
접속 후 최근 snapshot과 순위를 조회합니다.

```sql
SELECT id, collected_at, collection_date, rank_position, keyword, created_at
FROM trend_snapshots
ORDER BY id DESC
LIMIT 10;
```

한 번의 수집 실행에서 동일한 `collected_at`을 공유했는지 확인합니다.

```sql
SELECT collected_at, COUNT(*) AS row_count,
       MIN(rank_position) AS first_rank,
       MAX(rank_position) AS last_rank
FROM trend_snapshots
GROUP BY collected_at
ORDER BY collected_at DESC
LIMIT 10;
```

MySQL만 중지하려면 다음 명령을 사용합니다.

```bash
docker compose stop mysql
```

`stop`은 컨테이너와 named volume의 데이터를 유지합니다. `docker compose down -v`는
`mysql_data` volume과 DB 데이터를 삭제할 수 있으므로 일반 종료 절차로 사용하지 않습니다.

## Daily Trend 집계

`DailyTrendQueryService`는 저장된 원본 snapshot을 `collection_date` 기준으로 조회하고,
DB에 집계 결과를 저장하지 않고 `DailyTrendRank` 목록으로 반환합니다. `collection_date`는
Asia/Seoul 기준이므로 KST 날짜를 직접 전달합니다.

집계 지표:

- `appearance_count`: 해당 날짜에 keyword가 등장한 횟수
- `best_rank`: 가장 높은 순위(`MIN(rank_position)`)
- `average_rank`: 평균 순위
- `rank_score`: `SUM(11 - rank_position)`; 1위 10점부터 10위 1점

정렬은 `rank_score` 내림차순, `appearance_count` 내림차순, `best_rank` 오름차순,
`average_rank` 오름차순, `keyword` 오름차순 순서입니다. 결과는 기본 10개로 제한합니다.

`DailyTrendNewsService`는 Daily Trend 결과와 keyword별 Google News RSS 문맥을 결합합니다.
현재는 Application Layer 단위 서비스로만 제공되며, CLI·저장·LLM 분석에는 연결하지 않습니다.

저장된 snapshot이 있는 날짜의 Daily Trend를 터미널에서 조회할 수 있습니다. `--date`를
생략하면 Asia/Seoul 기준 오늘 날짜를 사용하고, `--limit`으로 표시할 결과 수를 지정합니다.

```bash
python -m namuwiki_trend.daily_trend_main --date 2026-07-30 --limit 10
```

결과가 없으면 성공 종료와 함께 `No daily trends found ...` 메시지를 표시합니다. 먼저
`snapshot_main`으로 해당 날짜의 snapshot을 저장해야 집계 결과가 생성됩니다.

MySQL이 실행 중이고 `DATABASE_URL`이 설정된 환경에서만 통합 테스트를 실행합니다. 기본
테스트는 외부 MySQL을 요구하지 않습니다.

```bash
RUN_DB_INTEGRATION=1 pytest tests/database/test_integration.py -q
```

## 검증

프로젝트 표준 검증 명령은 다음 하나입니다.

```bash
python scripts/verify.py
```

Harness는 Ruff, Pytest, Python compileall, `git diff --check`를 순서대로 실행합니다.

## 문서

- [Architecture](ARCHITECTURE.md): 현재 구현 구조와 설계 정책
- [Development Log](DEV_LOG.md): 날짜별 실제 개발 과정과 검증 결과
- [Software Engineering Handbook](STUDY_NOTE.md): 프로젝트를 통해 학습하는 개념 중심 교재

## Live Verification 상태

- `NewsContextProvider`: Live Verified
- `GeminiReasonGenerator`: Live Verified
- `TrendEnricher`: Unit Verified
- `TrendPipeline`: Unit Verified
- `JsonTrendInsightStorage`: Unit Verified
- Application Entry Point: Unit Verified
- `InsightQualityAnalyzer`: Unit Verified
- 전체 Application Pipeline: Live Verified (2026-07-29)

단일 Provider PoC는 다음 명령으로 직접 실행할 수 있습니다.

```bash
python -m namuwiki_trend.news_context_poc
python -m namuwiki_trend.playwright_poc
python -m namuwiki_trend.main
python -m namuwiki_trend.snapshot_main
python -m namuwiki_trend.daily_trend_main --date 2026-07-30
```

앞의 두 명령은 개별 기술 검증용이며, `namuwiki_trend.main`은 Collector부터 JSON 저장까지
실행합니다.
`namuwiki_trend.snapshot_main`은 별도로 Collector 결과를 MySQL `trend_snapshots`에 한 번의
transaction으로 저장합니다. 실행 전 `DATABASE_URL`을 셸 환경변수로 설정해야 합니다.
전체 실행은 Gemini 요청 간격 제한의 영향으로 실행 시간이 늘어날 수 있으며,
Free Tier quota는 프로젝트와 모델 조건에 따라 달라질 수 있습니다.

## Planned / Not Implemented

현재 다음 기능은 구현되지 않았습니다.

- `google_finance.main`
- Cache
- Batch 병렬화

따라서 위 기능을 실행하는 명령이나 운영 절차는 제공하지 않습니다.

## 운영 방법 (WSL Ubuntu)

운영 실행 구조는 다음과 같습니다.

```text
cron (3시간마다)
    ↓
run_namuwiki_trend.sh
    ↓
python -m namuwiki_trend.main
    ↓
output/trend_insights.json
    ↓
logs/namuwiki_trend.log
```

Wrapper는 저장소 루트를 기준으로 `.venv/bin/python`을 사용하고, 실행 전용 환경변수
`.env`를 자식 프로세스에만 전달합니다. API key와 credential은 로그에 기록하지 않습니다.

수동 실행:

```bash
./run_namuwiki_trend.sh
```

cron 등록:

```bash
(crontab -l 2>/dev/null; echo "0 */3 * * * /home/kstec/projects/automation-hub/run_namuwiki_trend.sh") | crontab -
crontab -l
```

`0 */3 * * *`는 매일 0분에 3시간 간격(00:00, 03:00, 06:00 …)으로 실행한다는 뜻입니다.
실제 3시간을 기다리지 않고 `crontab -l`로 등록 상태를 확인합니다.

cron 제거:

```bash
crontab -l | grep -v '/home/kstec/projects/automation-hub/run_namuwiki_trend.sh' | crontab -
```

출력은 `output/trend_insights.json`, 로그는 `logs/namuwiki_trend.log`에 저장됩니다.
Wrapper는 `flock`으로 중복 실행을 방지합니다. Gemini 요청 간 최소 간격과 뉴스·브라우저·
Gemini 호출 때문에 전체 실행은 약 2분이 걸릴 수 있으며, Free Tier quota와 WSL이 실행 중이어야
합니다. WSL이 종료되면 Linux cron도 실행되지 않습니다.

## MVP 완료 기준

현재 프로젝트는 MVP 완료 전입니다. MVP는 다음 조건을 모두 만족해야 합니다.

- 나무위키 실시간 검색어 Top 10 수집
- 각 `TrendItem`의 뉴스 문맥 검색
- Gemini reason 생성
- `TrendInsight` 생성
- Enriched 결과 파일 저장
- 단일 명령 실행
- 외부 네트워크 없는 Unit Test
- 실제 전체 Pipeline Live Verification 1회 완료
- `python scripts/verify.py` 통과

## Roadmap

권장 구현 순서는 다음과 같습니다.

1. 완료: Top10 Batch Orchestrator
2. 완료: Enriched Output Contract
3. 완료: `TrendInsight` Storage
4. 완료: 단일 실행 Application Entry Point
5. 완료: 전체 Pipeline Live Verification

계층 책임과 상세 설계 결정은 [ARCHITECTURE.md](ARCHITECTURE.md)에 기록합니다.
