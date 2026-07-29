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

## 검증

프로젝트 표준 검증 명령은 다음 하나입니다.

```bash
python scripts/verify.py
```

Harness는 Ruff, Pytest, Python compileall, `git diff --check`를 순서대로 실행합니다.

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
```

앞의 두 명령은 개별 기술 검증용이며, 마지막 명령은 Collector부터 JSON 저장까지 실행합니다.
전체 실행은 Gemini 요청 간격 제한의 영향으로 실행 시간이 늘어날 수 있으며,
Free Tier quota는 프로젝트와 모델 조건에 따라 달라질 수 있습니다.

## Planned / Not Implemented

현재 다음 기능은 구현되지 않았습니다.

- `google_finance.main`
- Scheduler와 Cron 설정
- Cache
- Database 저장
- Batch 병렬화

따라서 위 기능을 실행하는 명령이나 운영 절차는 제공하지 않습니다.

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
