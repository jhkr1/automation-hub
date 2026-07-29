# Architecture Review & Design

이 문서는 `automation-hub` 프로젝트의 설계 의도와 아키텍처 결정 사항을 기록합니다.

## 1. 설계 의도 (모노레포 구조)

이 프로젝트는 하나의 거대한 웹 서버가 아닌, 주기적으로 실행되는 **독립적인 자동화 스크립트 모음**입니다.
현재 `namuwiki_trend`와 `google_finance` 두 가지 프로젝트를 포함하며, 향후 지속적으로 기능이 추가될 수 있습니다.

`namuwiki_trend`는 나무위키 실시간 검색어 순위(1~10위)를 주기적으로 수집하고 활용하는 패키지입니다.
검색어 데이터에서는 `rank` 순위 정보가 핵심이며, 수집 결과에서 반드시 보존해야 합니다.

- **모노레포(Monorepo)**를 채택하여 공통 환경 설정(`.env`), 의존성(`pyproject.toml`), 가상환경(`.venv`), 스케줄링 관리(`cron`)를 한 곳으로 중앙화했습니다.
- 프로젝트가 분산되어 발생하는 관리 비용을 줄이고, 나중에 공통 모듈(로거, Gemini API 래퍼 등)을 쉽게 분리하기 위함입니다.

## 2. 왜 이런 구조를 선택했는지

### Flat 파일 구조 채택
패키지 내부에 `crawler/`, `llm/`, `storage/` 같은 서브 디렉토리를 만들지 않고 프로젝트 디렉토리 바로 아래에 파일들을 두었습니다 (예: `namuwiki_trend/crawler.py`).
- **이유**: 각 모듈의 코드가 100줄 이내로 매우 짧습니다. 서브 디렉토리를 깊게 파는 것은 오히려 불필요한 `__init__.py`를 양산하고 임포트 경로만 복잡하게 만듭니다.

### `src/` 레이아웃 배제
- **이유**: `src/` 구조는 PyPI 등 외부에 라이브러리를 배포할 때 유용합니다. 우리는 파이프라인을 실행(`python -m namuwiki_trend.main`)하는 것이 목적이므로, 실행 스크립트 중심의 구조가 더 직관적입니다.

## 3. 다른 방법과의 비교

### Playwright vs Requests + BeautifulSoup
- **초기 계획**: JS 렌더링을 처리하기 위해 Playwright를 사용하려 했습니다.
- **현재 결정**: `namuwiki_trend`의 검증된 수집 흐름에는 Playwright를 사용합니다.
- **근거**: 초기 HTML에 실시간 검색어가 없었고, 확인한 Network 요청만으로 실시간 검색어 API를 확정하지 못했습니다. 반면 Headless Chromium에서 최종 DOM과 `ul:has(> li > a[href^="/Go?q="])` root를 확인하고 Top10 추출에 성공했습니다.
- `requests`와 `BeautifulSoup`는 정적 HTML 또는 확인된 API가 제공될 때 더 적합할 수 있으므로 대안으로 남겨둡니다.

### 멀티레포 vs 모노레포
- 2개의 자동화 스크립트를 위해 2개의 Git 저장소를 만들면, 환경 세팅과 의존성 설치, 서버 내 디렉토리 관리가 2배로 증가합니다. 모노레포는 이를 효율화합니다.

## 4. 적용된 설계 원칙

- **YAGNI (You Aren't Gonna Need It)**:
  - 현재 시점에서는 두 프로젝트의 공통 코드를 추출하는 `shared/` 패키지를 만들지 않았습니다. 3개 이상의 프로젝트에서 확실한 중복 패턴이 발견될 때 추출합니다 (Rule of Three).
  - 추상 클래스(ABC)나 의존성 주입(DI) 컨테이너 등은 현재의 단순한 순차 파이프라인 구조에서는 오버엔지니어링이므로 배제했습니다.
- **SOLID**:
  - 단일 책임 원칙(SRP)에 따라 크롤링, 뉴스 검색, LLM 요약, 엑셀 저장을 각각 독립적인 모듈로 분리했습니다.
- **KISS (Keep It Simple, Stupid)**:
  - 비동기(`asyncio`, `httpx`) 처리를 제외하고 동기 방식으로 단순하게 작성했습니다. 현재 나무위키 Collector는 Playwright Sync API를 사용하며, 처리해야 할 데이터 건수가 적으므로 비동기의 복잡도 오버헤드를 피하는 것이 우선입니다.

## 5. 기술 의사결정 기록: 나무위키 Top10 수집

### 5.1 해결하려는 문제

나무위키 홈페이지에서 JavaScript 렌더링 후 표시되는 실시간 검색어 순위 1~10위를
주기적으로 수집하고, 각 항목의 `rank`, `keyword`, `href`를 보존해야 합니다.

초기 HTML만 파싱하거나 확인되지 않은 내부 API를 호출하면 실제 화면의 순위 데이터와
달라질 수 있으므로, 검증된 DOM 수집 흐름과 순수 검증 로직을 분리하는 것이 문제의 범위입니다.

### 5.2 검토한 대안

- Automation Anywhere(RPA)
- Python `requests` + `BeautifulSoup`
- Python `Playwright`
- Selenium

### 5.3 대안별 장점과 단점

| 대안 | 장점 | 단점 |
|---|---|---|
| Automation Anywhere | 화면 기반 업무를 빠르게 구성할 수 있고 비개발자 유지보수에 적합함 | 복잡한 검증 로직, 재사용, Git 기반 테스트 협업에 비용이 커질 수 있음 |
| requests + BeautifulSoup | 가볍고 빠르며 순수 Python 테스트가 쉬움 | 초기 HTML에 데이터가 없거나 JavaScript 렌더링이 필요하면 사용할 수 없음 |
| Playwright | 실제 브라우저의 JavaScript 렌더링 결과와 DOM을 확인할 수 있고 Chromium Headless 실행을 지원함 | 브라우저 설치·실행 비용, 메모리 사용량, requests보다 긴 실행 시간이 발생함 |
| Selenium | 브라우저 자동화와 WebDriver 기반 DOM 조작이 가능하며 동일한 요구사항을 구현할 수 있음 | 이번 프로젝트에서는 Selenium을 별도로 실험하지 않았고, WebDriver 관리 구성이 추가로 필요할 수 있음 |

어떤 대안도 모든 상황에서 우월하다고 판단하지 않습니다. 선택은 데이터가 생성되는 위치,
운영 환경, 유지보수 방식, 테스트 요구사항에 따라 달라집니다.

### 5.4 현재 프로젝트 제약

- Python 3.12 기반 flat layout을 유지함
- 자동화 패키지는 독립성을 유지함
- 운영 Collector는 작은 동기 API로 시작함
- 새 외부 의존성은 추가하지 않음
- 확인되지 않은 API URL, HTML 구조, CSS selector를 추측하지 않음
- Top10 순위와 sentinel 검증을 숨기지 않음
- 단위 테스트는 외부 네트워크에 의존하지 않음

### 5.5 실험으로 확인한 Evidence

다음은 코드와 명령 실행 결과로 확인한 내용입니다.

- Ctrl+U의 초기 HTML에 실시간 검색어가 없었음
- `sidebar.json`은 최근 변경 문서 요청으로 확인되었고, `/i/xxxxx` 요청은 검색어 API로 확정하지 못했음
- Headless Chromium에서 `https://namu.wiki/` 접속과 HTTP 200을 확인함
- 실제 DOM 구조는 `ul > li > a > span`이었음
- `ul:has(> li > a[href^="/Go?q="])` root를 1개 선택함
- visible `li` 11개 중 마지막 항목이 첫 항목의 keyword와 href를 복제하는 sentinel이었음
- sentinel 제거 후 `TrendItem` 10개와 rank 1~10을 반환함
- Headless/Headed 각각 5회 반복에서 동일한 DOM 규칙을 관찰함
- 순수 추출 및 Collector 경계 테스트 21개가 통과함
- 운영 Collector 기반 live PoC 실행이 성공함

위 Evidence는 현재 실행과 조사에서 확인한 범위에 한정됩니다. 향후 모든 실행에서도
동일하다고 일반화하지 않습니다.

### 5.6 최종 선택

현재 `namuwiki_trend`의 수집 방식으로 Python Playwright를 선택합니다.

선택 이유는 일반적인 선호가 아니라 다음 현재 조건 때문입니다.

1. 데이터가 초기 HTML이 아닌 렌더링된 DOM에서 확인됨
2. 확인된 API를 기반으로 수집할 근거가 부족함
3. Playwright Headless Chromium에서 실제 접속과 DOM 추출을 검증함
4. sentinel과 Top10 경계를 코드와 단위 테스트로 검증함
5. 브라우저 실행 비용을 감수하더라도 현재 요구사항에서는 화면 결과와 동일한 데이터 확보가 중요함

Playwright는 DOM에서 원시 항목을 읽고, sentinel·개수·rank 검증은 Playwright와 분리된
순수 Python 함수가 담당합니다.

### 5.7 선택하지 않은 대안이 더 적합해지는 조건

- `requests` + `BeautifulSoup`: 초기 HTML에 Top10이 포함되거나, 안정성이 검증된 공식 또는 내부 API가 제공되는 경우
- Selenium: 조직의 표준 브라우저 자동화 환경이 Selenium/WebDriver이고, 해당 환경에서 동일한 DOM 안정성과 운영 비용을 확인한 경우
- Automation Anywhere: 화면 기반 업무를 빠르게 연결하고 비개발자 중심의 운영·유지보수가 중요한 경우
- Playwright: 브라우저 실행 비용이 운영 환경의 메모리·실행 시간 제약을 초과하는 경우 다른 방식과 재비교함

### 5.8 CSV, XLSX, Database의 역할 구분

저장 형식은 우열이 아니라 소비 목적에 따라 선택합니다.

- CSV: 원본 Top10 데이터 저장과 시스템 간 교환에 적합함
- XLSX: 사람이 읽고 필터링하는 보고서에 적합함
- Database: 장기 누적, 조회, 무결성, 동시성 요구가 있을 때 적합함

현재 Sprint에서는 저장 기능을 구현하거나 형식을 선택하지 않았습니다.

### 5.9 향후 재검토 조건

다음 조건이 확인되면 수집 방식을 다시 검토합니다.

- 초기 HTML 또는 공식 API에서 동일한 Top10과 순위를 안정적으로 제공함
- 현재 locator 또는 DOM 구조가 반복 실행에서 더 이상 유지되지 않음
- Headless 실행 시간·메모리 사용량이 운영 주기를 충족하지 못함
- Chromium 설치와 시스템 의존성이 배포 환경의 제약과 충돌함
- Selenium 또는 다른 도구가 동일한 Evidence를 더 낮은 유지보수 비용으로 제공함
- 장기 저장 요구가 생겨 CSV, XLSX, Database 중 하나의 목적별 선택이 필요해짐
