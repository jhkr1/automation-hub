# automation-hub

Python 3.12 기반 업무 자동화 프로젝트를 독립 패키지로 관리하는 모노레포입니다.
Automation Anywhere에서 다뤘던 자동화를 Python의 명시적인 모델, 테스트와 실행 경계로
재구현하며, 기능 수보다 유지보수 가능한 구조와 검증 가능성을 우선합니다.

## 패키지

| 패키지 | 상태 |
|---|---|
| `namuwiki_trend` | Top 10 수집, enrichment, JSON·DB snapshot과 Daily Trend 조회 구현 |
| `google_finance` | 단일 종목 시세 수집·정규화·MySQL snapshot 저장·CLI 구현 |

패키지별 실행 방법과 제한사항은 [`docs/packages/`](docs/packages/)에서 확인합니다.

## 빠른 시작

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

현재 구현된 `namuwiki_trend` 실행 예시는 다음과 같습니다.

```bash
python -m namuwiki_trend.main
python -m namuwiki_trend.snapshot_main
python -m namuwiki_trend.daily_trend_main --date 2026-07-30
```

Google Finance는 exchange-qualified symbol 하나를 받아 실행할 수 있습니다.

```bash
python -m google_finance.main AAPL:NASDAQ
python -m google_finance.main AAPL:NASDAQ --save-db
```

실행에는 대상 외부 서비스, 환경변수와 경우에 따라 MySQL이 필요합니다. 자세한 운영 절차는
[`docs/operations/`](docs/operations/)와 [`namuwiki_trend 문서`](docs/packages/namuwiki_trend/README.md)를
참고합니다.

## 검증

```bash
python scripts/verify.py
```

표준 Harness는 Ruff, pytest, compileall과 `git diff --check`를 실행합니다.

## 문서

- [공통 아키텍처](docs/architecture.md)
- [프로젝트 철학](docs/project-philosophy.md)
- [자동화 패턴 비교](docs/automation-patterns.md)
- [RPA에서 Python으로 전환하는 절차](docs/rpa-to-python.md)
- [설계 결정](docs/decisions/README.md)
- [개발 로그](docs/development/DEV_LOG.md)
- [학습 자료](docs/learning/STUDY_NOTE.md)
- [PoC 기록](docs/poc/playwright-preparation.md)
- [코드베이스 탐색 가이드](CODEBASE_GUIDE.md)

## 현재 범위와 미구현 범위

`namuwiki_trend`의 현재 구현 범위는 패키지 문서와 코드에 근거합니다. `google_finance`는
현재 단일 종목의 Playwright 수집·정규화·MySQL snapshot 저장·CLI까지 구현되어 있으며,
Movement Detection, News, LLM, Scheduler, DB 외 저장 형식은 구현하지 않았습니다. Google
Finance의 내부 RPC는 사용하지 않으며, selector 안정성과 테스트하지 않은 시장은 확인되지 않은
상태입니다.

공통 원칙은 [docs/architecture.md](docs/architecture.md)에, 패키지별 세부사항은
[`docs/packages/`](docs/packages/)에 기록합니다.
