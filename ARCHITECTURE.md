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
- **이유**: `src/` 구조는 PyPI 등 외부에 라이브러리를 배포할 때 유용합니다. 현재는 flat layout의 모듈과 `scripts/verify.py`를 기준으로 개발합니다. 단일 실행 Entry Point는 `namuwiki_trend.main`에 구현되어 있습니다.

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

비교 시 다음 기준을 함께 고려했습니다.

- 동적 DOM 처리
- 대기 전략과 Locator 사용 방식
- 브라우저 및 드라이버 관리
- 세션 격리
- 네트워크 관찰과 디버깅
- 실제 브라우저 호환성
- Selenium Grid 또는 기존 기업 자산 활용 가능성
- 테스트 작성 경험
- 현재 프로젝트에서의 전환 비용

Playwright는 Locator 중심 API, auto-wait, `BrowserContext` 기반 세션 격리,
Chromium·Firefox·WebKit 지원, trace 및 request/response 관찰 기능을 제공합니다.
대신 Playwright 버전과 브라우저 바이너리를 함께 관리해야 하며, Linux 시스템 의존성 설치가
필요할 수 있습니다.

Selenium은 W3C WebDriver 기반으로 Chrome, Edge, Firefox, Safari 등 브라우저 생태계와
Selenium Grid 및 기존 기업 자산을 활용할 수 있습니다. Selenium Manager로 드라이버 관리
부담은 과거보다 줄었지만, 대기 조건은 explicit wait 중심으로 설계해야 합니다.
이번 프로젝트에서는 Selenium을 실행하여 비교하지 않았으므로 Selenium의 실제 실행 시간이나
동일 Locator의 안정성은 `확인하지 못함`으로 기록합니다.

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
- CSV 저장 테스트 추가 후 전체 테스트 27개가 통과함
- 운영 Collector 기반 live PoC 실행이 성공함

위 Evidence는 현재 실행과 조사에서 확인한 범위에 한정됩니다. 향후 모든 실행에서도
동일하다고 일반화하지 않습니다.

### 5.6 최종 선택

현재 `namuwiki_trend`의 수집 방식으로 Python Playwright를 선택합니다.

- **Verified**: Headless/Headed 환경과 대상 DOM을 반복 검증함
- **Implemented**: `collect_trends() -> list[TrendItem]` 운영 Collector 구현 완료
- **Implemented**: `collector.py`는 Playwright 실행·페이지 접속·원시 DOM 수집을 담당함
- **Implemented**: `extraction.py`는 sentinel 검증·제거, keyword/href 검증, 정확히 10개 검증,
  rank 부여를 담당함
- **Implemented**: `models.py`는 `TrendItem`을 정의함
- **Implemented**: `playwright_poc.py`는 Collector 수동 실행과 결과 확인만 담당함
- **Implemented**: Collector 및 순수 추출 테스트 21개 통과
- **Implemented**: `csv_storage.py`의 `save_trends_to_csv()`가 `Sequence[TrendItem]`을 CSV로 저장함
- **Implemented**: CSV 테스트를 포함한 전체 테스트 27개 통과
- **Implemented**: `utf-8-sig`, `newline=""`, 부모 디렉터리 자동 생성, 기존 파일 덮어쓰기 정책 적용
- **Planned**: 수집 시각을 포함한 저장 스키마 검토
- **Historical initial decision**: 초기 Sprint에서는 XLSX 저장, Database 저장, Scheduler, CLI,
  Logging framework, retry, fallback locator를 현재 요구사항 밖으로 두었음
- **Current implementation**: 이후 `TrendSnapshot` DB 저장, snapshot CLI, Daily Trend 조회가
  추가됨. 집계 결과 저장과 전용 집계 CLI는 아직 구현하지 않음

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

현재 첫 저장 기능으로 CSV를 구현했습니다.

- **Implemented**: `save_trends_to_csv(items, output_path) -> Path`
- **선택 근거**: 현재 데이터가 `rank`, `keyword`, `href`로 구성된 단순 tabular data이고,
  저장 파이프라인 검증에 서식이나 여러 Sheet가 필요하지 않으며, 추가 외부 의존성 없이 구현할 수 있음
- **Implemented**: UTF-8 BOM을 포함한 `utf-8-sig`로 한국어와 Windows Excel 소비를 고려함
- **Implemented**: 부모 디렉터리를 자동 생성하고 같은 경로의 기존 파일을 덮어씀
- **Rejected for now**: append와 atomic write는 누적 저장·무결성 요구가 명시되지 않아 구현하지 않음
- **Historical initial decision**: 초기에는 XLSX와 Database가 현재 요구사항에 필요한지
  확인되지 않아 보류했음. 현재는 시간대별 원본 누적과 조회 요구로 `TrendSnapshot` DB를 구현함

### 5.9 저장 형식 재검토 조건

다음 조건이 확인되면 수집 방식을 다시 검토합니다.

- XLSX: 비개발자가 파일을 직접 소비하거나, 필터·정렬·여러 Sheet·차트·조건부 서식이 필요함
- Database: 데이터가 장기 누적되고, 중복 방지·무결성·기간별 조회·동시 쓰기가 필요함
- SQLite/PostgreSQL: 여러 Collector 결과를 통합하거나 조회 요구가 커짐

### 5.10 Automation Anywhere와 Python 재구현의 의미

Automation Anywhere와 Python은 우열을 비교하기 위한 대상이 아니라, 같은 업무를 서로 다른
실행 모델로 해결하며 차이를 분석하기 위한 대상입니다.

Automation Anywhere는 화면 기반 구성, 기업용 credential·scheduler·bot runner,
중앙 모니터링 환경이 이미 있는 경우에 적합할 수 있습니다. 라이선스와 플랫폼 종속성,
코드 단위 테스트와 세밀한 Git 버전 관리의 비용도 함께 고려해야 합니다.

Python은 Git diff와 코드 리뷰, 함수 단위 테스트, Playwright 및 데이터 처리 생태계,
세밀한 오류 처리를 활용할 수 있습니다. 반면 실행 환경·의존성·배포를 직접 관리해야 하며,
비개발자에게는 흐름이 덜 시각적일 수 있습니다.

현재 Python 재구현의 목적은 Automation Anywhere보다 우월함을 증명하는 것이 아닙니다.
다음 내용을 학습하고 검증하기 위한 재구현입니다.

- 브라우저 자동화 내부 동작
- DOM 분석
- 데이터 모델링
- 책임 분리
- 자동화 테스트
- Git 기반 개발 흐름

### 5.11 브라우저 자동화 재검토 조건

- **Reconsider when**: 정적 HTML 또는 검증된 API가 동일한 Top10을 안정적으로 제공함
- **Reconsider when**: 조직 표준이 Selenium이고 Selenium Grid 또는 기존 테스트 자산 재사용이 필요함
- **Reconsider when**: Safari 실브라우저 검증이 핵심 요구가 됨
- **Reconsider when**: 팀 운영 경험이 Selenium에 집중되어 전환 비용이 낮아짐
- **Reconsider when**: Playwright의 브라우저 실행 시간·메모리·Linux 시스템 의존성이 운영 제약을 초과함

위 조건이 발생하면 Selenium 또는 requests 기반 방식을 새 Evidence로 검증한 후 재결정합니다.

## 6. LLM Enrichment Layer (Implemented; Gemini Provider and TrendEnricher)

### 6.1 목표와 현재 상태

현재 구현된 수집·enrichment 경계는 다음과 같습니다.

    Playwright Collector
    ↓
    list[TrendItem]
    ├── CSV 저장
    └── TrendEnricher.enrich(trend)
            ↓
    NewsContextProvider → list[NewsArticle]
            ↓
    GeminiReasonGenerator → reason
            ↓
    TrendInsight

Collector와 TrendEnricher를 연결하는 Top10 전체 Application Pipeline과 이를 조립하는
`namuwiki_trend.main` Entry Point를 구현했습니다.

- **Implemented**: Collector는 `list[TrendItem]`만 반환함
- **Implemented**: CSV 저장은 `TrendItem`만 입력으로 받음
- **Implemented**: `gemini_reason_generator.py`의 `GeminiReasonGenerator` 구현
- **Implemented**: Provider 공개 API `generate_reason(trend: TrendItem, articles: list[NewsArticle]) -> str`
- **Implemented**: Gemini API 호출, 응답 text 검증, 최대 300자 검증
- **Implemented**: `build_reason_prompt()`의 뉴스 문맥 grounding과 URL 제외
- **Verified**: `손흥민` 1건으로 Google News RSS 5건과 Gemini 응답을 연속 호출함
- **Evidence**: Prompt에는 title/source/published_at만 포함되고 URL은 포함되지 않았으며, 응답 94자·전체 호출 시간 약 5.857초를 확인함
- **Implemented**: `TrendEnricher`가 `TrendItem`과 뉴스 문맥·reason을 `TrendInsight`로 결합함
- **Implemented**: `TrendPipeline`이 Collector의 목록을 순서대로 `TrendEnricher`에 전달함
- **Implemented**: `main.py`가 운영용 Provider, Enricher, Pipeline, JSON Storage를 조립함
- **Implemented**: `python -m namuwiki_trend.main`으로 전체 흐름을 실행함
- **Implemented**: 기본 출력 경로는 `output/trend_insights.json`임
- **Rejected for now**: Prompt 기반 최신성 보강, CSV 스키마 변경

### 6.5 Application Entry Point

`main.py`는 Composition Root로서 운영 의존성을 생성하고 다음 흐름을 조립합니다.

    collect_trends
    ↓
    TrendPipeline.run()
    ↓
    JsonTrendInsightStorage.save()

- `build_pipeline()`이 `NewsContextProvider`, `GeminiReasonGenerator`, `TrendEnricher`와
  `TrendPipeline`을 생성합니다.
- `run_application()`이 Pipeline 결과를 Storage에 전달합니다.
- `main()`은 성공 시 `0`, 실행 예외 발생 시 `1`을 반환합니다.
- CLI 옵션, Scheduler, Retry, Cache, 병렬 처리와 저장 이후 후속 작업은 담당하지 않습니다.
- 테스트에서는 `run_application()`에 Fake Pipeline과 Fake Storage를 주입합니다.

단위 테스트는 fake client로 검증합니다. 실제 Gemini 응답의 사실성·생성 품질은 뉴스 문맥의
품질과 모델 응답에 의존하므로 Unit Test만으로 확정하지 않습니다.

### 6.2 모델 경계 검토

두 가지 모델 방식을 검토합니다.

#### 대안 A: TrendItem에 reason 필드 추가

```text
TrendItem
- rank
- keyword
- href
- reason
```

장점은 결과가 단일 객체에 모이고 직렬화가 단순하다는 점입니다. 단점은 Collector가
LLM 결과가 있는 객체를 알게 되고, `TrendItem`의 원시 수집 계약과 CSV 저장 계약이 변경됩니다.
LLM 실패나 재생성 상태를 원시 수집 결과와 함께 다루기도 어려워집니다.

#### 대안 B: TrendInsight wrapper

```text
TrendInsight
- trend: TrendItem
- reason: str
```

장점은 Collector와 기존 CSV가 `TrendItem` 계약을 그대로 유지하고, LLM 결과가 선택적
Enrichment 결과임을 명확히 표현할 수 있다는 점입니다. 단점은 저장·출력 시 wrapper를
변환하는 단계가 추가됩니다.

현재는 대안 B를 선택합니다.

- **현재 선택**: `TrendItem`은 수집 원본으로 유지하고, `TrendInsight`를 별도 결과로 둠
- **근거**: Collector와 CSV 저장의 책임을 변경하지 않고 LLM 계층을 추가할 수 있음
- **Reconsider when**: 모든 소비자가 항상 설명을 요구하고 원시 TrendItem 계약을 변경해도
  호환성 문제가 없다는 Evidence가 확인되면 단일 모델 통합을 재검토함

**Implemented**: `TrendInsight`는 원본 TrendItem, 뉴스 근거 tuple, 생성된 reason을 묶습니다.

### 6.3 LLM 계층 책임과 데이터 흐름

현재 책임 분리는 다음과 같습니다.

    Collector
    ↓ list[TrendItem]
    Reason Generator
    ↓
    LLM Provider
    ↓ reason
    TrendInsight 생성

- `collector.py`: 브라우저 수집과 순위 검증만 담당함
- `extraction.py`: sentinel, 개수, keyword/href, rank 규칙만 담당함
- `csv_storage.py`: 현재 `TrendItem` 원본을 CSV로 직렬화함
- `enricher.py`: TrendItem 하나에 대해 Provider와 Generator를 호출하고 TrendInsight를 생성함
- Gemini Provider: Gemini API 호출과 응답 처리를 담당함
- `TrendInsight`: 원본 TrendItem과 생성된 reason을 함께 표현함

Collector가 Gemini Provider를 직접 호출하지 않도록 합니다.

### 6.4 Provider Interface 검토

다음 인터페이스를 비교합니다.

#### 키워드만 전달

```python
generate_reason(keyword: str) -> str
```

단순하고 Provider 구현이 쉽지만 `rank`, `href`와 같은 검증된 TrendItem 문맥을 잃습니다.
향후 뉴스 제목 등 추가 입력을 연결할 때 별도 확장이 필요합니다.

#### TrendItem과 뉴스 문맥 전달

```python
generate_reason(trend: TrendItem, articles: list[NewsArticle]) -> str
```

Collector의 원본 계약을 보존하면서 Provider가 keyword와 뉴스 문맥을 함께 사용합니다.
뉴스 URL은 Prompt에 전달하지 않아 모델 입력을 필요한 근거 필드로 제한합니다.

#### 목록을 한 번에 전달

```python
generate_reasons(trends: list[TrendItem]) -> list[str]
```

API 호출 수나 batch 처리 효율을 검토하기 쉽지만, 한 항목 실패가 전체 결과에 영향을 줄 수
있고 항목별 재시도·검증·오류 추적이 복잡해질 수 있습니다.

#### 현재 계획

현재 MVP Provider 경계는 다음 동기 메서드로 구현했습니다.

```python
generate_reason(trend: TrendItem, articles: list[NewsArticle]) -> str
```

Reason Generator가 항목별로 호출하고 결과를 `TrendInsight`에 결합합니다. batch API가
필요하다는 실제 비용 Evidence가 생기면 목록 단위 메서드를 별도로 검토합니다.

### 6.5 Provider 교체 가능성

현재 첫 Provider는 Gemini Flash입니다. 향후 OpenAI, Claude, 로컬 LLM으로 교체할 수
있도록 상위 계층은 `generate_reason(trend, articles)`라는 동작 계약만 사용하도록 합니다.

- **Implemented**: `google-genai` SDK의 `from google import genai`와
  `client.models.generate_content()` 사용
- **Implemented**: 공식 model identifier `gemini-3.5-flash`를 `DEFAULT_MODEL` 한 곳에서 관리함
- **Implemented**: `GEMINI_API_KEY` 환경 변수를 사용하며 코드에 key를 저장하지 않음
- **Implemented**: `GeminiReasonGenerator`가 요청 간 최소 간격을 적용함
- **Implemented**: `429 RESOURCE_EXHAUSTED`에만 최대 재시도 횟수 내에서 retry함
- **Implemented**: SDK `ClientError.details`의 Google RPC `RetryInfo.retryDelay`를 우선 사용하고,
  값이 없거나 파싱되지 않으면 bounded exponential backoff를 사용함
- **Implemented**: 테스트에서 실제 대기를 하지 않도록 clock과 sleeper를 주입할 수 있음
- **Reconsider when**: 두 번째 Provider가 실제로 추가될 때 공통 Protocol 또는 최소 인터페이스를
  코드로 도입함
- **Rejected for now**: Provider가 하나뿐인 단계에서 abstract base class, DI container,
  factory registry를 미리 만들지 않음

이 판단은 추상화를 거부하는 것이 아니라 현재 구현 규모와 실제 교체 요구가 확인되지 않은
상태에서 복잡도를 제한하는 선택입니다.

### 6.6 Prompt 설계 방향

현재 Prompt는 실행 코드의 `build_reason_prompt(trend, articles)` 순수 함수로 분리되어
있습니다. Gemini에는 검색어와 각 뉴스의 title, source, published_at만 전달하며 URL은
전달하지 않습니다.

```text
검색어: {keyword}
뉴스 문맥: title, source, published_at

검색어가 기사의 핵심 주제인 경우에만 근거로 사용하라.
여러 기사에서 반복되는 공통 사건을 우선하라.
제공된 기사 밖의 사실을 추측하지 마라.
공통 사건이 없으면 "제공된 기사만으로는 정확한 이유를 확인하기 어렵다."라고 답하라.
```

현재 뉴스 Provider가 반환한 title, source, published_at을 Prompt에 전달합니다. 향후
summary나 본문을 추가할 필요가 생기면 입력 필드별 근거와 길이 제한을 별도 검증합니다.

- **Implemented**: 현재 Provider는 `TrendItem.keyword`와 뉴스 title/source/published_at을 Prompt에 포함함
- **Implemented**: Prompt에 URL을 포함하지 않음
- **Implemented**: 기사 핵심 주제·반복 공통 사건·불충분한 근거에 대한 grounding 규칙 추가
- **Verified**: `손흥민` Live 실행에서 MLS 올스타전·올스타 스킬 챌린지 관련 공통 문맥을 사용한 94자 응답 생성
- **Planned**: 더 많은 검색어와 반복 실행을 통한 뉴스 문맥 기반 생성 결과의 사실성·품질 평가
- **Rejected for now**: 확인되지 않은 뉴스나 API 응답을 Prompt에 자동으로 추가함

### 6.7 CSV 영향 범위

현재 CSV 스키마는 다음과 같습니다.

```text
rank,keyword,href
```

`reason`을 기존 CSV에 바로 추가하면 기존 파일 소비자와 헤더 계약이 변경됩니다. 따라서
다음 두 방식을 비교합니다.

- 기존 CSV에 `reason` 컬럼 추가: 한 파일에서 완성 결과를 소비하기 쉽지만 원본 저장 계약과
  LLM 생성 결과가 결합되고, 생성 실패·재생성 상태를 다루기 어려움
- Enrichment 결과를 별도 CSV로 저장: 기존 원본 CSV 호환성을 유지하지만 두 결과를 연결할
  키와 파일 관리 규칙이 필요함

현재는 기존 CSV를 변경하지 않습니다.

- **Implemented**: 원본 CSV는 `rank,keyword,href` 유지
- **Planned**: 후속 저장 Sprint에서 `reason` 저장 위치와 스키마를 별도 결정
- **Reconsider when**: 실제 소비자가 원본과 설명을 항상 함께 요구하는지, LLM 실패를 어떻게
  표현할지 확인된 후 컬럼 추가 또는 별도 파일을 결정함

### 6.8 후속 검증 조건

후속 운영 확장과 실제 Gemini 호출을 반복 검증할 때 다음을 별도로 확인해야 합니다.

- API Key를 코드나 로그에 노출하지 않는지
- Gemini Provider가 Collector와 분리되어 있는지
- 빈 응답, API 오류, 과도한 응답, 근거 없는 설명을 어떻게 처리하는지
- `TrendItem` 원본 결과가 LLM 실패로 손상되지 않는지
- 생성된 reason이 1~2줄 요구를 만족하는지
- 실제 API 호출 테스트와 네트워크 비의존 테스트의 경계를 어떻게 나누는지

Gemini 호출 계층의 rate limiting과 retry는 `GeminiReasonGenerator` 내부 책임입니다.
`TrendPipeline`에는 sleep이나 Gemini-specific 예외 처리를 넣지 않습니다. 429가 아닌 SDK
예외는 즉시 호출자에게 전달하며, retry 횟수는 생성자 설정으로 제한합니다.

### 6.9 Trend Enrichment Application Layer

현재 단일 항목 enrichment 흐름은 다음과 같습니다.

```text
TrendItem
    ↓ keyword
NewsContextProvider.search()
    ↓ list[NewsArticle]
GeminiReasonGenerator.generate_reason()
    ↓ reason
TrendInsight
```

- **Application Layer**: `TrendEnricher`가 뉴스 검색, reason 생성, 결과 조합 순서를 조정함
- **Provider Layer**: `NewsContextProvider`는 뉴스 문맥을, `GeminiReasonGenerator`는 Gemini 응답을 담당함
- **Model Layer**: `TrendItem`은 원본 순위 데이터, `NewsArticle`은 뉴스 근거, `TrendInsight`는 결합 결과를 표현함
- **Dependency Injection**: `TrendEnricher`는 Provider와 Generator를 생성자로 받아 테스트 대체 구현을 허용함
- **Implemented**: `TrendEnricher.enrich(trend) -> TrendInsight`
- **Implemented**: 뉴스 호출 limit 전달, 빈 기사 전달, reason trim·타입·빈 값·최대 300자 검증
- **Implemented**: `JsonTrendInsightStorage`가 `TrendInsight` 목록을 JSON으로 저장함
- **Not implemented**: Scheduler, cache, 전용 Daily Trend CLI 및 집계 결과 저장

Known Limitation:

- 현재 `TrendEnricher`는 한 번에 `TrendItem` 하나를 처리하고, `TrendPipeline`이 목록 순회를 담당함
- `TrendPipeline`은 Top10 개수나 rank를 재검증하지 않으며 Collector 계약을 신뢰함
- 빈 뉴스 목록도 오류로 보정하지 않고 Gemini에 전달함
- 뉴스 기사의 핵심 주제 여부는 Prompt 지침에 의존하며 별도 분류기는 없음
- JSON 저장은 현재 파일을 overwrite하며 장기 누적 정책은 아직 결정하지 않음

## 7. Executable Project Harness

현재 프로젝트 Harness는 문서 규칙과 실행 도구를 다음처럼 분리합니다.

- `AGENTS.md`: AI가 항상 따르는 프로젝트 불변 규칙과 실행 진입점 안내
- `scripts/verify.py`: 검증 명령의 순서, 실패 중단, non-zero 반환, 성공 메시지 담당
- Ruff: 정적 품질 검사 담당
- Pytest: 단위·통합 경계 테스트 담당
- Compileall: Python 파일 컴파일 가능 여부 담당
- Git Rule: diff 검토, 명시적 stage, 커밋, push 금지 정책 담당

표준 검증 진입점은 다음 하나입니다.

```bash
python scripts/verify.py
```

`verify.py`는 Ruff, Pytest, Compileall, `git diff --check`를 순서대로 실행하며 하나라도
실패하면 즉시 중단합니다. Harness 자체 테스트는 Fake runner를 사용해 성공·실패 흐름을
검증하고 실제 외부 API나 검증 명령에 의존하지 않습니다.

공식 참고 문서:

- [Gemini API 시작하기](https://ai.google.dev/gemini-api/docs/generate-content/get-started)
- [Gemini 3.5 Flash 모델 ID](https://ai.google.dev/gemini-api/docs/generate-content/whats-new-gemini-3.5)
- [Gemini API Key 사용](https://ai.google.dev/gemini-api/docs/generate-content/api-key)

## 8. 최신 뉴스 문맥 Provider PoC

### 8.1 해결하려는 문제

`TrendItem.keyword`만으로는 검색어가 실시간 검색어 순위에 오른 최신 사건을 확인하기
어렵습니다. 이번 단계의 범위는 검색어 하나에 대한 최신 뉴스 제목·URL·출처·게시 시각을
가져올 수 있는지 검증하는 것이며, Gemini enrichment와의 연결은 포함하지 않습니다.

### 8.2 검토한 후보

| 후보 | 장점 | 단점 및 확인 상태 |
|---|---|---|
| Google News RSS 검색 | API Key 없이 검색어별 XML을 받을 수 있고, 한국어 locale 파라미터와 title/link/source/pubDate 필드를 다루기 쉬움 | Google이 안정적인 소비자 검색 API로 명시한 공식 RSS 사양은 확인하지 못함. feed URL과 결과 범위의 장기 안정성·호출 제한은 `확인하지 못함` |
| 네이버 뉴스 검색 API | 한국어 검색에 맞는 공식 검색 API 후보이며 구조화된 JSON 응답을 사용할 수 있음 | 개발자 애플리케이션 등록과 Client ID/Secret 관리가 필요함. 현재 프로젝트에서 실제 발급 키·한도·Live 응답은 `확인하지 못함` |
| 개별 언론사 RSS | API Key 없이 접근할 수 있고 특정 출처의 원문 feed를 사용할 수 있음 | 검색어 통합 검색이 아니며 출처마다 필드·갱신 주기·약관이 달라 공통 Provider로 사용하기 어려움 |
| 뉴스 HTML 브라우저 수집 | 화면에서 보이는 검색 결과를 직접 확인할 수 있음 | DOM 변경·접근 제한·약관 검토 비용이 커서 API/RSS가 불가능할 때만 검토함 |

네이버 검색 API는 [공식 뉴스 검색 문서](https://developers.naver.com/docs/serviceapi/search/news)에서
제공되는 후보로 확인했습니다. Google News는 [Publisher Center 안내](https://support.google.com/news/publisher-center/answer/15898024)
에서 Publisher Center 제출 RSS/web location 흐름이 변경되었다고 안내하므로, 이번 구현의
Google News RSS 주소를 공식적인 안정 API 계약으로 해석하지 않습니다.

### 8.3 최종 선택과 이유

이번 PoC에서는 Google News RSS 검색을 선택했습니다.

- **선택 이유**: API Key 없이 검색어 하나의 최신 문맥을 요청할 수 있어 현재 PoC의 인증·비밀정보 범위를 늘리지 않음
- **한국어 처리**: `hl=ko`, `gl=KR`, `ceid=KR:ko`를 요청 URL에 포함함
- **테스트성**: XML parser를 순수 함수로 분리하고 HTTP client를 주입할 수 있음
- **비용**: 이미 설치된 `requests`와 Python 표준 XML parser만 사용하며 새 의존성을 추가하지 않음
- **Verified**: RSS XML 파싱, trim, 필수 필드, URL, 출처, 게시 시각, 중복 제거, limit을 Unit Test로 검증함
- **Live Verified**: 초기 Provider PoC에서는 자동 Live 호출을 실행하지 않았으며, 이후 별도 Live 검증에서 확인함

이는 Google News RSS가 장기 운영에 절대적으로 적합하다는 의미가 아닙니다. 현재 목표인
키워드 하나의 뉴스 문맥 확보 PoC에 대한 선택이며, 공개 feed의 계약·호출 제한·결과 품질은
운영 전 추가 검증이 필요합니다.

### 8.4 데이터 흐름

```text
keyword: str
    ↓ trim 및 입력 검증
NewsContextProvider.search(keyword, limit)
    ↓ Google News RSS 검색 URL
주입된 HTTP client
    ↓ bytes XML
parse_google_news_rss()
    ↓ URL 중복 제거 및 limit 적용
list[NewsArticle]
```

`NewsArticle`은 다음 필드를 보존합니다.

```text
title: str
url: str
source: str | None
published_at: datetime | None
```

title과 HTTP(S) 절대 URL은 필수입니다. source와 pubDate가 없거나 pubDate를 해석할 수
없으면 선택 필드를 `None`으로 둡니다. 같은 URL은 최초 항목만 보존하고, 중복 제거 후
앞에서부터 `limit`개를 반환합니다. HTTP 예외는 원인 보존을 위해 그대로 전달합니다.

### 8.5 구현 범위와 실행 방법

- **Implemented**: `models.py`에 뉴스 문맥용 `NewsArticle` 모델 추가
- **Implemented**: `news_context_provider.py`의 `NewsContextProvider.search()`와 순수 RSS parser
- **Implemented**: `news_context_poc.py`에 검색어 `손흥민` 하나를 조회하는 수동 실행 경로 추가
- **Not changed in the initial PoC**: Collector, 기존 CSV, CLI, Scheduler
- **Not implemented**: retry, cache, batch 처리, 브라우저 HTML 수집

Live 확인은 자동 테스트에 포함하지 않습니다. 사용자가 직접 다음 명령을 실행합니다.

```bash
python -m namuwiki_trend.news_context_poc
```

스크립트는 결과 개수, 제목, 출처, 게시 시각, URL, 호출 시간을 출력합니다. 이 명령을
실행하지 않은 상태에서는 Live Verified로 기록하지 않습니다.

### 8.6 알려진 한계와 재검토 조건

- Google News RSS의 공개 feed URL은 공식 소비자 검색 API 계약으로 확인되지 않았습니다.
- 검색 결과가 나무위키 실시간 검색어의 실제 등재 원인을 증명하지는 않습니다.
- 결과의 순위·완전성·최신성은 Google News의 수집·정렬 정책에 의존합니다.
- source와 게시 시각은 feed 항목에 없거나 형식이 달라질 수 있습니다.
- 호출 제한, 장애율, 장기 URL 안정성은 Live 반복 실험 전까지 `확인하지 못함`입니다.
- 네이버 API 키를 확보하고 공식 한도·한국어 결과 품질을 실제로 비교할 수 있게 되면 재검토합니다.
- Google RSS 계약 변경, 빈 결과 증가, HTTP 차단 또는 운영 SLA 요구가 확인되면 네이버 API,
  출처별 RSS, 승인된 다른 뉴스 API를 새 Evidence로 비교합니다.

### 8.7 후속 Gemini 연결 참고

현재 `list[NewsArticle]`는 `TrendEnricher`를 통해 Reason Generator에 전달됩니다. 뉴스
Provider는 Collector를 호출하지 않으며, Gemini Provider도 뉴스 검색을 직접 수행하지
않습니다. 기사 제목을 사실의 증거로 사용하는 범위, 출처·시각 표시, 뉴스가 없을 때의
응답, LLM 생성 품질은 별도 테스트와 Live 검증 대상입니다.

검증 명령:

```bash
ruff check .
pytest -q
python -m compileall namuwiki_trend tests
git diff --check
```

## 9. MVP Roadmap

현재 MVP는 단일 실행 Entry Point를 포함한 수집·enrichment·JSON 저장 흐름까지 구현되었으며,
전체 Pipeline Live Verification도 완료되었습니다. 권장 순서는 책임을 섞지 않는 다음 단계입니다.

1. **완료: Top10 Batch Orchestrator**: `TrendPipeline`이 Collector의 `list[TrendItem]`을
   순회하여 `list[TrendInsight]`를 반환함. 저장은 포함하지 않음.
2. **완료: Enriched Output Contract**: JSON 최상위 구조, schema version, 시간·encoding,
   overwrite 정책을 확정함.
3. **완료: TrendInsight Storage**: 확정된 JSON 계약에 따라 Enriched 결과를 저장함.
4. **완료: Application Entry Point**: Collector, Batch Orchestrator, Storage를 단일 실행 명령으로
   연결함. Scheduler는 포함하지 않음.
5. **완료: 전체 Pipeline Live Verification**: 2026-07-29 실제 실행으로 수집·뉴스·Gemini·저장을
   검증함. 실행 명령은 `python -m namuwiki_trend.main`, 기본 출력 경로는
   `output/trend_insights.json`임.

각 단계의 구현 전에는 실제 소비 요구와 실패 정책을 확인하며, 확인되지 않은 저장 형식이나
운영 방식을 추측하여 선행 구현하지 않습니다.

## 10. Enriched Output Contract and Storage

`TrendItem` 원본 CSV와 Enriched 결과 파일의 소비 목적이 다르므로 저장 계층을 분리합니다.
기존 CSV 계약은 `rank,keyword,href`로 유지하고, `TrendInsight` 목록은 JSON으로 저장합니다.

### 10.1 JSON 계약

```json
{
  "schema_version": 1,
  "generated_at": "2026-07-29T12:30:00+00:00",
  "insights": [
    {
      "trend": {
        "rank": 1,
        "keyword": "...",
        "href": "..."
      },
      "reason": "...",
      "articles": [
        {
          "title": "...",
          "url": "...",
          "source": "...",
          "published_at": "..."
        }
      ]
    }
  ]
}
```

- `schema_version`: 정수 `1`. 필드 계약 변경 시 호환성 판단 기준으로 사용함
- `generated_at`: Storage clock이 반환한 timezone-aware datetime의 ISO 8601 문자열
- datetime 필드: `published_at`은 ISO 8601 문자열이며 `None`은 JSON `null`로 저장함
- encoding: UTF-8, `ensure_ascii=False`
- formatting: 사람이 확인할 수 있도록 JSON indentation 2칸 사용
- 순서: 입력 Insight와 각 Insight의 articles 순서를 그대로 보존함
- 빈 목록: `insights: []`인 유효한 JSON으로 저장함

### 10.2 Storage 책임과 파일 정책

`JsonTrendInsightStorage.save(insights, path) -> Path`는 모델을 명시적으로 JSON 객체로
매핑하고 파일 I/O만 담당합니다. Collector, Pipeline, Enricher, 환경변수, 파일명 자동
생성 정책을 직접 다루지 않습니다.

- 부모 디렉터리를 자동 생성함
- 지정한 경로의 기존 파일은 overwrite함
- 동일 디렉터리의 임시 파일에 JSON을 작성하고 `replace`하여 부분 파일 노출을 줄임
- 입력 모델과 순서를 변경하지 않음
- `TrendItem`, `NewsArticle`, `TrendInsight` 외 입력은 `TypeError`로 거부함
- timezone-naive `generated_at`은 `ValueError`로 거부함

### 10.3 Known Limitation

- 파일은 overwrite되며 append·날짜별 보관·장기 누적은 구현하지 않음
- Gemini 요청 간 최소 간격으로 전체 실행 시간이 늘어날 수 있음
- Free Tier quota는 프로젝트·모델 조건에 따라 달라지며, quota 초과 시 bounded retry 후 실패할 수 있음
- 2026-07-29 Live 실행 stdout에서는 429 retry 발생을 확인하지 못함
- JSON schema migration과 backward compatibility는 `schema_version`만 정의된 상태임

## 11. Quality Diagnostics

`InsightQualityAnalyzer`는 `Sequence[TrendInsight]`를 입력받아 현재 Enrichment 결과의
구조적·관찰 가능한 품질 지표를 계산합니다. 분석 계층은 Collector, News Provider,
Gemini, TrendPipeline, JSON schema를 수정하지 않으며 외부 API를 호출하지 않습니다.

### 11.1 Report 지표

`InsightQualityReport`는 다음 값을 immutable dataclass로 반환합니다.

- 전체 Insight 개수
- fallback reason 개수
- article이 0개인 Insight 개수
- Insight별 article 개수
- keyword가 article title에 포함된 기사 개수
- keyword가 어떤 title에도 포함되지 않은 Insight의 rank
- 실행 전체에서 두 번 이상 등장한 서로 다른 article URL 개수
- rank 순서 이상 여부
- 비어 있는 keyword와 reason 개수

### 11.2 Heuristic 한계

keyword-title match는 trim 후 `casefold()`한 문자열 포함 여부만 확인합니다. 이는 의미적
관련성, 동명이인 구분, 다의어 해석, 기사의 실제 원인 여부를 판정하지 않습니다.
따라서 `InsightQualityReport`는 품질 문제를 관찰하기 위한 진단 자료이며, 뉴스 검색
알고리즘이나 Gemini Prompt의 품질을 자동으로 보증하는 평가 결과가 아닙니다.

## 12. Database Layer: TrendSnapshot

SQLAlchemy 2.x와 Alembic은 원본 실시간 검색어 스냅샷을 저장하기 위한 기반으로 추가되어
있습니다. 현재 DB 레이어는 `database/base.py`의 `Base`, `database/engine.py`의 Engine,
`database/session.py`의 `SessionLocal`, `database/models.py`의 `TrendSnapshot`으로
분리되어 있습니다. Collector와 저장 서비스는 아직 연결하지 않았습니다.

`TrendSnapshot`은 한 수집 시점의 순위 항목을 보존합니다.

- `collected_at`, `created_at`: 애플리케이션에서 timezone-aware 입력만 받고 UTC로 변환한
  뒤 timezone 정보를 제거한 naive UTC 값으로 ORM 객체와 MySQL `DATETIME`에 저장합니다.
  이 naive 값은 local time이 아니라 UTC임을 전제로 하며, MySQL `DATETIME` 자체의 timezone
  자동 변환에는 의존하지 않습니다.
- `collection_date`: `collected_at`을 `Asia/Seoul`로 변환해 애플리케이션에서 계산합니다.
- `rank_position`: 1~10 범위는 애플리케이션 검증과 DB `CHECK` 제약조건으로 이중 보호합니다.
- `keyword`: 앞뒤 공백만 제거하고 내부 공백과 원래 대소문자는 유지합니다. lowercase나
  Unicode normalization은 적용하지 않습니다. 빈 문자열은 애플리케이션과 DB에서 검증하며,
  동일성 비교는 현재 MySQL collation 정책을 따릅니다. 길이는 `VARCHAR(255)`로 제한합니다.
- `created_at`: 저장 시점의 UTC를 애플리케이션 기본값으로 사용합니다. DB 서버 timezone에
  의존하지 않고 입력 정책을 한 곳에서 유지하기 위한 선택입니다.

일일 집계의 날짜 필터와 keyword 그룹화를 고려해
`(collection_date, keyword)` 복합 인덱스를 사용합니다. `collection_date` 단독 인덱스는
복합 인덱스의 선행 컬럼과 중복되므로 추가하지 않았습니다. `(collected_at,
rank_position)` unique 제약조건은 한 수집 시각의 동일 순위 중복을 방지합니다.

`TrendSnapshot`은 원본 수집 이력을 보존하는 append-only 모델입니다. 생성 후
`collected_at`, `collection_date`, `rank_position`, `keyword`를 변경하는 update API를
제공하지 않습니다. 현재 ORM 객체를 완전한 immutable 객체로 강제하지는 않으며, 저장 계층은
기존 snapshot을 수정하지 않고 새 snapshot을 추가하는 방식으로 설계합니다.

Alembic `0002_create_trend_snapshots`가 이 테이블을 생성하며, `0001_initial_empty`는
수정하지 않았습니다.

## 13. Collector-to-Snapshot Application Flow

원본 스냅샷 저장 흐름은 `snapshot_main.py`에서 의존성을 조립하고
`SnapshotCollectionPipeline`이 실행을 조정합니다.

```text
collect_trends()
    ↓ list[TrendItem]
SnapshotCollectionPipeline
    ↓
SnapshotSaveService
    ↓ one transaction
trend_snapshots
```

- Collector: 나무위키에서 `TrendItem` 목록만 수집합니다.
- `SnapshotCollectionPipeline`: Collector를 호출하고 결과를 저장 서비스에 전달합니다.
- `SnapshotSaveService`: 동일한 `collected_at`을 생성하고 `TrendSnapshot`으로 변환한 뒤
  하나의 transaction으로 저장합니다.
- MySQL: 원본 snapshot을 영속화하며, 일부 항목만 저장되는 상태를 rollback으로 방지합니다.

Collector는 DB를 알지 않고, 저장 서비스는 Collector를 호출하지 않도록 분리했습니다.
따라서 실제 네트워크 수집과 DB 저장을 각각 fake로 교체해 Application Pipeline을 테스트할
수 있습니다. 빈 수집 결과는 정상 결과로 보고 저장 서비스를 호출하지 않습니다.

`snapshot_main.py`는 이 흐름의 Composition Root이자 CLI entry point입니다. Pipeline 실행
결과의 row 개수만 stdout에 표시해 사용자가 수집·저장 성공 여부를 확인할 수 있게 하며,
transaction과 DB 저장 책임은 `SnapshotSaveService`에 유지합니다. 실제 저장 여부와
`collected_at` 일관성은 MySQL CLI 조회로 검증합니다.

UTC는 DB 저장 표준이고, KST(`Asia/Seoul`)는 사용자 표시와 일일 집계 기준입니다. 저장
형식과 표시 형식을 분리하면 DB의 UTC 일관성을 유지하면서 운영자가 CLI에서 직관적인
한국 시각을 확인할 수 있습니다.

## 14. Daily Trend Query

`DailyTrendQueryService`는 `collection_date`를 기준으로 `TrendSnapshot`을 SQL에서
`GROUP BY keyword` 집계합니다. 결과는 영속화하지 않고 immutable read model인
`DailyTrendRank` 목록으로 반환합니다.

- `appearance_count`: keyword 등장 횟수
- `best_rank`: `MIN(rank_position)`
- `average_rank`: 평균 rank
- `rank_score`: `SUM(11 - rank_position)`

정렬은 rank score, 등장 횟수, best rank, average rank, keyword 순서이며, 마지막 keyword
정렬로 동률 결과도 deterministic하게 유지합니다. `target_date`는 이미 저장된
Asia/Seoul 기준 `collection_date`이므로 MySQL timezone 변환 함수에 의존하지 않습니다.
현재 결과는 별도 테이블에 저장하지 않습니다. `namuwiki_trend.daily_trend_main`은 이 read
model을 터미널 표로 표시하는 얇은 Application/Presentation 경계이며, 집계 SQL이나 저장
책임을 갖지 않습니다. 날짜는 Asia/Seoul 기준으로 결정하고 Query Service의 반환 순서를
그대로 출력합니다.

`DailyTrendNewsService`는 Query Service와 News Context Provider를 조정하는 Application
Service입니다.

```text
DailyTrendQueryService
    ↓ list[DailyTrendRank]
DailyTrendNewsService
    ↓ keyword별 NewsContextProvider.search()
list[DailyTrendNews]
```

Query Service는 뉴스 Provider를 모르고, 뉴스 Provider는 Daily Trend를 모릅니다. Application
Service가 두 흐름을 결합하며 DailyTrendRank와 기사 순서를 유지합니다. SQL, RSS 파싱, 저장,
LLM 호출은 담당하지 않고 하위 예외를 숨기지 않습니다. 현재는 CLI·저장·LLM 연결 없이 단위
테스트로 검증된 Application Layer입니다.

### 16. Trend Reason Generator

`TrendReasonGenerator`는 `DailyTrendNews` 한 건을 입력받아 `TrendReason`을 반환합니다.

```text
DailyTrendNews
    ↓ prompt builder
Gemini client
    ↓ JSON response validation
TrendReason
```

Prompt Builder는 집계 정보와 기사 제목·출처·게시 시각·URL만 전달하며 기사 전문을
가져오지 않습니다. 출력은 `keyword`, `reason`, `confidence`, `supporting_articles`를
검증한 immutable read model입니다. 뉴스가 없으면 Gemini를 호출하지 않고 근거 부족·low
confidence 결과를 반환합니다. SDK client는 생성자 주입하여 단위 테스트에서 외부 호출을
차단합니다. malformed JSON, 필수 필드 누락, 허용되지 않은 confidence와 빈 reason은
성공으로 처리하지 않습니다.

현재는 단일 항목 Generator만 구현되었고 Top N orchestration, CLI, 저장, retry는 범위 밖입니다.
Unit Test는 완료했지만, 2026-07-30 단일 Live 호출은 Gemini Free Tier 일일 요청 quota
초과(`429 RESOURCE_EXHAUSTED`, quota value 20)로 성공하지 못했습니다. 따라서 현재
Generator는 Live Verified로 표시하지 않습니다.

### 16.1 OpenAI Trend Reason Generator

Reason Generator contract는 Provider 교체 지점으로 사용합니다.

```text
DailyTrendNews
        ↓
Reason Generator Contract
       ↙          ↘
Gemini              OpenAI Responses API
       ↘          ↙
          TrendReason
```

`OpenAITrendReasonGenerator`는 OpenAI Responses API의 JSON Schema 출력을 사용하고,
기존 `TrendReason` contract로 변환·검증합니다. `DailyTrendReasonService`는 구체 Provider를
알지 않으며 생성자 주입으로 교체할 수 있습니다. 자동 Gemini/OpenAI fallback은 없습니다.
OpenAI SDK는 `pyproject.toml`에 추가했지만 현재 환경에서는 설치 여부를 확인하지 못했으며,
OpenAI Live 호출도 수행하지 않았습니다.

### 17. Daily Trend Reason Application Service

```text
list[DailyTrendNews]
    ↓
DailyTrendReasonService
    ↓ 항목별 1회, 입력 순서 유지
TrendReasonGenerator
    ↓
list[TrendReason]
```

`DailyTrendReasonService`는 순회와 orchestration만 담당합니다. Prompt 생성, Gemini 호출,
응답 검증은 `TrendReasonGenerator`의 책임입니다. Generator 예외는 그대로 전파하며,
부분 결과·재시도·중복 제거·병렬 처리는 수행하지 않습니다. 빈 입력은 빈 목록을 반환합니다.

## 15. WSL 운영 구조

namuwiki_trend의 WSL 운영 실행 경계는 저장소 루트의
`run_namuwiki_trend.sh` Wrapper입니다.

```text
cron: 0 */3 * * *
    ↓
run_namuwiki_trend.sh
    ↓
.venv/bin/python -m namuwiki_trend.main
    ↓
output/trend_insights.json
logs/namuwiki_trend.log
```

- cron은 Python 모듈을 직접 호출하지 않고 Wrapper만 호출함
- Wrapper는 자신의 위치에서 저장소 루트를 계산하고 해당 위치로 이동함
- 프로젝트의 `.venv/bin/python`을 사용함
- `.env`를 자식 프로세스 환경에만 전달하며 secret을 출력하지 않음
- 시작·종료 시각, 경과 시간, exit code를 로그에 기록함
- `flock` 비배타 잠금으로 이전 실행이 끝나지 않았으면 중복 실행을 건너뜀
- 로그와 JSON은 저장소의 `logs/`, `output/`에 두며 Git에서 무시함

`0 */3 * * *`는 매일 3시간 간격으로 실행하는 cron 표현식입니다. cron 등록은 사용자의
WSL crontab에 별도로 존재하며, WSL이 종료되면 cron도 실행되지 않습니다. Gemini 요청
간격 제한으로 실행 시간이 약 2분까지 늘어날 수 있으므로 다음 예약 실행과 겹치지 않도록
Wrapper의 `flock`을 유지합니다.

운영 제한:

- 이번 Sprint에서는 실제 3시간 대기를 하지 않음
- WSL과 cron daemon의 부팅·상시 실행 여부는 운영 환경 책임임
- quota 초과, 외부 사이트 장애와 Gemini 실패는 Wrapper exit code와 로그로 확인함
