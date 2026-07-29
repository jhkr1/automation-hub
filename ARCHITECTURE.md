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
- **이유**: `src/` 구조는 PyPI 등 외부에 라이브러리를 배포할 때 유용합니다. 현재는 flat layout의 모듈과 `scripts/verify.py`를 기준으로 개발합니다. 단일 실행 Entry Point는 Planned입니다.

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
- **Rejected for now**: XLSX 저장, Database 저장, Scheduler, CLI,
  Logging framework, retry, fallback locator

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
- **Rejected for now**: XLSX와 Database는 현재 요구사항에 필요한 조건이 확인되지 않음

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

Collector와 TrendEnricher를 연결하는 Top10 전체 Application Pipeline은 아직 구현되지
않았습니다.

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
- **Rejected for now**: Prompt 기반 최신성 보강, CSV 스키마 변경,
  전체 실행 Entry Point

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
- **Not implemented**: Scheduler, retry, cache, CLI

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

현재 MVP는 단일 항목 enrichment와 Top10 Batch Orchestrator까지 구현되었으며, 실행 Entry
Point와 결과 저장이 남아 있습니다. 권장 순서는 책임을 섞지 않는 다음 단계입니다.

1. **완료: Top10 Batch Orchestrator**: `TrendPipeline`이 Collector의 `list[TrendItem]`을
   순회하여 `list[TrendInsight]`를 반환함. 저장은 포함하지 않음.
2. **완료: Enriched Output Contract**: JSON 최상위 구조, schema version, 시간·encoding,
   overwrite 정책을 확정함.
3. **완료: TrendInsight Storage**: 확정된 JSON 계약에 따라 Enriched 결과를 저장함.
4. **Application Entry Point**: Collector, Batch Orchestrator, Storage를 단일 실행 명령으로
   연결함. Scheduler는 포함하지 않음.
5. **전체 Pipeline Live Verification**: 실제 Top10 1회 실행으로 수집·뉴스·Gemini·저장을
   검증함.

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
- JSON을 `TrendPipeline`에 연결하는 Application Entry Point는 아직 없음
- JSON schema migration과 backward compatibility는 `schema_version`만 정의된 상태임
