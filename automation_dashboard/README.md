# Automation Dashboard

`automation_dashboard`는 저장된 Automation 데이터를 읽어 보여주는 로컬 전용 Streamlit
Dashboard입니다. 현재 화면은 Google Finance snapshot만 지원하며, 수집·분석·저장·cron 제어는
수행하지 않습니다.

## Install and run

```bash
pip install -e ".[dashboard,dev]"
streamlit run automation_dashboard/app.py
```

## Database configuration

Dashboard는 `DASHBOARD_DATABASE_URL`을 우선 사용하고, 로컬 MVP에서는 기존
`DATABASE_URL`로 fallback합니다. 외부 공개 전에는 반드시 MySQL read-only 계정을 사용해야
합니다. URL, password, API key는 화면과 Dashboard 로그에 표시하지 않습니다.

## Current scope

- symbol별 최신 가격, 수집 시각, snapshot 수
- 선택 symbol의 가격 추이와 최신 두 snapshot delta
- data 없음 및 database 연결 실패의 안전한 화면

Google Finance Insight·뉴스, Namuwiki, Operations 실행 이력, 인증과 외부 공개는 아직
구현하지 않았습니다.
