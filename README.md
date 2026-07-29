# automation-hub

데이터 수집 자동화 허브 — 여러 소스에서 데이터를 수집하고 분석하여 Excel로 저장합니다.
현재 나무위키 실시간 검색어 순위(Top 10)를 주기적으로 수집하고 활용하는 기능과 Google Finance 종목 시세 수집 기능을 하나의 저장소(모노레포)에서 관리하고 있습니다.

## 프로젝트 구조

```
automation-hub/
├── namuwiki_trend/    # 나무위키 실시간 검색어 순위(Top 10) 수집 및 요약
├── google_finance/    # Google Finance 종목 시세 수집 및 요약
├── tests/             # 테스트 코드
├── output/            # 생성된 Excel 파일 저장 위치 (Git 미추적)
├── logs/              # 애플리케이션 및 cron 실행 로그 (Git 미추적)
└── scripts/           # 스케줄러 등록 등 운영 스크립트
```

## 기술 스택

- **언어**: Python 3.12
- **크롤링**: `requests`, `BeautifulSoup4`
- **LLM 연동**: `google-genai` (Gemini 2.5 Flash 모델)
- **데이터 저장**: `openpyxl` (Excel 파일 생성 및 쓰기)
- **설정 관리**: `pydantic-settings` (.env 파일 타입 검증)
- **개발 환경**: `pytest`, `ruff`

## 실행 방법

### 1. 가상환경 생성

```bash
python3.12 -m venv .venv
source .venv/bin/activate
```

### 2. 의존성 설치

```bash
pip install -e ".[dev]"
```

### 3. 환경변수 설정

저장소 루트에 `.env` 파일을 생성하고 아래 양식에 맞게 API 키를 입력합니다. (템플릿은 `.env.example`을 참고하세요)

```bash
cp .env.example .env
```

| 변수 | 설명 | 사용 프로젝트 |
|:---|:---|:---|
| `NAVER_CLIENT_ID` | 네이버 검색 API Client ID | namuwiki_trend |
| `NAVER_CLIENT_SECRET` | 네이버 검색 API Client Secret | namuwiki_trend |
| `GEMINI_API_KEY` | Google Gemini API Key | 공통 |
| `STOCK_SYMBOLS` | 수집할 종목 코드 (쉼표 구분) | google_finance |
| `LOG_LEVEL` | 로그 출력 레벨 (기본: INFO) | 공통 |

### 4. 수동 실행

```bash
# 나무위키 실시간 검색어 순위(Top 10) 수집 파이프라인 1회 실행
python -m namuwiki_trend.main

# Google Finance 종목 시세 수집 파이프라인 1회 실행
python -m google_finance.main
```

## 결과 예시 (예상 데이터)

실행이 완료되면 `output/` 디렉토리에 일자별 엑셀 파일이 생성됩니다.
(예: `output/namuwiki_trend/2026-07-29.xlsx`)

| 수집시각 | 순위 | 키워드 | 관련 뉴스 | 인기 이유 (Gemini 요약) |
|:---|:---|:---|:---|:---|
| 10:00 | 1 | 파리 올림픽 | 대표팀 금메달 획득... | 최근 올림픽 경기에서 대표팀이 우수한 성적을 거두어 네티즌들의 관심이 집중되고 있습니다. |

## cron 등록 방법 (자동화)

`scripts/setup_cron.sh` 스크립트를 사용하여 시스템 crontab에 스케줄러를 등록할 수 있습니다.
이 스크립트는 `flock`을 활용하여 중복 실행을 방지합니다.

```bash
# 크론탭 일괄 등록
bash scripts/setup_cron.sh
```

**등록되는 스케줄:**
- `namuwiki_trend`: 매 2시간마다 (0시, 2시, 4시...)
- `google_finance`: 매일 오전 9시 30분, 오후 3시 30분 (한국 증시 기준)
