# Automation Dashboard

`automation_dashboard`는 저장된 Automation 데이터를 읽어 보여주는 로컬 전용 Streamlit
Dashboard입니다. Google Finance, Namuwiki Trends, Operations의 저장 상태를 조회하며, 수집·분석·저장·cron
제어는 수행하지 않습니다.

## Pages

| Page | Shows |
|---|---|
| Google Finance | 최신 가격, 선택 종목의 가격 이력, Snapshot 비교 |
| Namuwiki Trends | 최신 Top 10, 선택 검색어 순위 이력, 검색어 통계, 저장된 LLM Insight |
| Operations | Snapshot·로그 파일 메타데이터·Alembic·런타임·LLM quota 상태 |

모든 화면은 같은 KST 시간, 숫자 포맷, Empty State와 최대 60초 조회 캐시를 사용합니다.

## Install and run

```bash
pip install -e ".[dashboard,dev]"
streamlit run automation_dashboard/app.py
```

앱이 실행되면 Streamlit sidebar 또는 시작 화면에서 원하는 화면을 선택합니다. **조회 캐시 새로고침**은
최대 60초인 화면 조회 캐시만 비우며, 어떤 자동화 작업도 실행하지 않습니다.

## Database configuration

Dashboard는 `DASHBOARD_DATABASE_URL`을 우선 사용하고, 로컬 MVP에서는 기존
`DATABASE_URL`로 fallback합니다. 외부 공개 전에는 반드시 MySQL read-only 계정을 사용해야
합니다. URL, password, API key는 화면과 Dashboard 로그에 표시하지 않습니다.

## Current scope

- symbol별 최신 가격, 수집 시각, snapshot 수
- 선택 symbol의 가격 추이와 최신 두 snapshot delta
- Namuwiki 최신 Top 10, 검색어별 순위 이력, 저장 통계
- Operations의 Snapshot·로그 파일 메타데이터·Alembic·런타임 상태
- Namuwiki `output/trend_insights.json`의 read-only LLM Insight와 freshness 상태
- Local quota ledger의 profile별 요청 수와 retry count
- data 없음 및 database 연결 실패의 안전한 화면

Google Finance Insight artifact 저장은 아직 구현하지 않았으며, Google Finance 화면은 Planned
placeholder만 표시합니다. Dashboard는 Gemini를 직접 호출하지 않고, Namuwiki artifact가 오래되거나
손상된 경우 Healthy 결과로 표시하지 않습니다. 이 Dashboard는 로컬 Streamlit 화면이며, 외부 공개
전에는 MySQL read-only 계정을 사용해야 합니다.

Namuwiki artifact의 `Healthy` 또는 `Stale` 상태는 파일 freshness만 나타내며, 현재 Provider의
Live smoke test 성공을 보장하지 않습니다. Live 검증이 완료되기 전에는 생성 시각과 상태를 함께
확인해야 합니다.
