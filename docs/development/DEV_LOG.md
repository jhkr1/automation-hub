# Development Log

프로젝트를 진행하며 발생한 이슈, 해결 과정, 배운 점 등을 날짜별로 기록합니다.

---

## 2026-07-29

### 1. 오늘 구현한 기능
- `automation-hub` 모노레포 프로젝트 뼈대 구축 완료 (Sprint 1)
- `pyproject.toml`, `.gitignore`, `.env.example`, `README.md` 작성
- `namuwiki_trend`와 `google_finance` 두 개의 패키지에 대해 기본 환경 설정 모듈(`config.py`) 및 데이터 구조(`models.py`) 정의
- `namuwiki_trend`의 `TrendKeyword` 모델은 실시간 검색어 순위의 `rank`, 검색어의 `keyword`, 수집시각의 `collected_at`을 보존하도록 정의
- 가상환경 설정 및 의존성 라이브러리 정상 설치 검증 완료

### 2. 발생한 문제
- **setuptools 패키지 탐지 이슈**: `pip install -e ".[dev]"` 명령어로 의존성을 설치할 때, `setuptools`가 저장소 루트에 있는 `logs`, `output` 폴더까지 파이썬 패키지로 잘못 인식하여 `Multiple top-level packages discovered in a flat-layout` 오류가 발생하며 설치가 실패했습니다.

### 3. 해결 과정
- **pyproject.toml 설정 명시**: Flat layout 구조에서는 `setuptools`의 자동 탐지 기능이 의도치 않은 디렉토리를 포함시킬 수 있습니다. 이를 해결하기 위해 `pyproject.toml`에 `packages.find` 옵션을 명시적으로 추가했습니다.
  ```toml
  [tool.setuptools.packages.find]
  include = ["namuwiki_trend*", "google_finance*"]
  ```
- 위 옵션을 추가한 후 다시 설치를 시도하여 정상적으로 패키지가 인식되고 설치되는 것을 확인했습니다.

### 4. 배운 점
- `src/` 디렉토리를 쓰지 않는 Flat Layout 구조에서는 최상위 디렉토리에 있는 모든 폴더를 잠재적인 패키지로 간주하기 때문에, 빌드 시스템(`setuptools`)에게 우리가 코드로 만든 폴더만 패키지라는 것을 정확히 알려주어야 한다는 점을 배웠습니다.
- 자동화된 도구의 `Auto-discovery` 기능이 항상 내 의도대로 동작하지는 않는다는 것을 실감했습니다.

### 5. 나무위키 실시간 검색어 수집 방식 조사

#### 조사 과정

1. **초기 가설**
   - `requests`와 `BeautifulSoup`로 실시간 검색어를 수집할 수 있을 것으로 예상했습니다.

2. **View Source 확인**
   - 브라우저에서 Ctrl+U로 초기 HTML을 확인했습니다.
   - 초기 HTML에는 실시간 검색어가 존재하지 않았습니다.
   - 결론적으로 실시간 검색어는 초기 HTML이 아닌 방식으로 렌더링됩니다.

3. **Network 분석**
   - DevTools의 Fetch/XHR 요청을 조사했습니다.
   - `sidebar.json`은 최근 변경 문서 API였습니다.
   - `/i/xxxxx` 요청은 검색어 클릭 시 발생했고 `application/octet-stream` 형식이었지만, 실시간 검색어 API는 아니었습니다.

4. **DOM 조사**
   - Elements에서 실시간 검색어가 `<ul>` → `<li>` → `<a>` → `<span>` 구조로 렌더링되는 것을 확인했습니다.
   - DOM 순서가 실시간 검색어 순위임을 확인했습니다.

#### 기술 선택

AA(RPA), Python `requests`와 `BeautifulSoup`, Python `Playwright`를 비교한 후
Python `Playwright`를 채택했습니다.

- **AA(RPA)**
  - 장점: 단기간 구현 속도가 매우 빠르고, 화면 기반 자동화에 적합하며, 비개발자도 유지보수할 수 있습니다.
  - 단점: 복잡한 로직 구현이 어렵고, 재사용성과 확장성이 낮으며, 버전 변경에 취약합니다.
- **Python `requests`**
  - 장점: 가장 빠르고 가벼우며 테스트하기 쉽습니다.
  - 단점: JavaScript 렌더링에 대응할 수 없고 동적 사이트에서 사용하기 어렵습니다.
- **Python `BeautifulSoup`**
  - 장점: 정적 HTML 파싱이 쉽습니다.
  - 단점: 초기 HTML에 데이터가 없으면 사용할 수 없습니다.
- **Python `Playwright`**
  - 장점: JavaScript 렌더링과 동적 사이트를 지원하고, 브라우저와 동일한 결과를 확보할 수 있으며, 자동화 범위가 넓습니다.
  - 단점: 브라우저 실행 비용과 메모리 사용량이 증가하고 `requests`보다 느립니다.

#### Trade-off

이번 프로젝트에서는 속도보다 안정성과 유지보수성을 우선했습니다.
HTTP API를 역공학하는 대신 브라우저 렌더링 결과를 수집하는 것이 장기 유지보수 측면에서 더 적합하다고 판단했습니다.

#### Lessons Learned

- View Source와 DOM은 다를 수 있습니다.
- Network만으로 데이터 출처를 단정하면 안 됩니다.
- `application/octet-stream`은 반드시 실제 응답을 확인해야 합니다.
- 기술 선택은 성능뿐 아니라 유지보수성과 구현 비용까지 고려해야 합니다.

### 6. 다음 작업 (Sprint 2)
- 나무위키 실시간 검색어 순위(Top 10) 수집기(`crawler.py`) 로직 구현
- DevTools를 활용해 나무위키 내부 API 엔드포인트 파악 시도
- 네이버 뉴스 API(`news.py`) 연동

---

## 2026-07-30

### 목표
- Docker MySQL 기반 원본 snapshot 저장 흐름을 문서화하고 검증함
- `TrendSnapshot`을 날짜별로 집계하는 조회 기능을 구현함

### 구현
- SQLAlchemy 2.x와 Alembic으로 `trend_snapshots` 스키마를 관리함
- `TrendSnapshot`에 UTC naive `collected_at`, `Asia/Seoul` 기준 `collection_date`를 적용함
- `SnapshotSaveService`가 한 수집 실행의 `TrendItem` 목록을 하나의 transaction으로 저장함
- `SnapshotCollectionPipeline`과 `snapshot_main`을 통해 Collector 결과를 MySQL에 저장함
- `DailyTrendQueryService`가 `collection_date`와 keyword 기준 SQL 집계를 수행함

### 주요 결정
- DB에는 UTC naive `DATETIME`을 저장하고, KST는 표시·업무 날짜 기준으로 사용함
- snapshot은 append-only로 취급하며 집계 결과는 아직 별도 테이블에 저장하지 않음
- 집계는 Python 전체 row 처리 대신 MySQL의 `GROUP BY`, `COUNT`, `MIN`, `AVG`, `SUM`을 사용함

### 발생한 문제와 해결
- MySQL CLI에서 한국어가 올바르게 표시되지 않는 문제가 있었음
- 원인은 저장 데이터가 아니라 client/connection/results 문자셋이 latin1로 설정된 것이었음
- `--default-character-set=utf8mb4`와 `SET NAMES utf8mb4` 사용 방법을 README에 기록함

### 검증
- `python scripts/verify.py`: 118 passed, 3 skipped
- `RUN_DB_INTEGRATION=1 pytest tests/database -q`: 15 passed
- 실제 snapshot 실행: 10개 row 저장 성공
- 최신 10개 row가 하나의 동일한 `collected_at`을 공유함을 DB에서 확인함
- `2026-07-30` 대상 Daily Trend SQL 집계 결과를 실제 DB에서 확인함

### 배운 점
- 저장 표준과 사용자 표시 형식은 분리할 수 있음
- `collection_date`를 저장해두면 집계 시 DB timezone 변환에 의존하지 않음
- ORM 모델과 read model은 저장 계약과 조회 결과라는 서로 다른 목적을 가짐

### 다음 작업
- 현재 집계 결과를 사용한 뉴스 문맥 수집 연계를 검토함

### Daily Trend CLI
- `daily_trend_main`에서 KST 날짜와 limit을 받아 `DailyTrendQueryService` 결과를 표시함
- 명시 날짜, KST 기본 날짜, 빈 결과, 입력 오류와 서비스 예외 전파를 테스트함
- 실제 DB CLI 실행 결과는 별도 Live 검증 후 기록함

### Daily Trend News Application Service
- `DailyTrendNewsService`가 Daily Trend 결과와 keyword별 NewsArticle 목록을 결합함
- Query Service와 News Provider를 생성자 주입하고, 순서 보존·fail-fast 정책을 적용함
- Fake 기반 단위 테스트로 빈 결과, limit 전달, 예외 전파를 검증함

### Trend Reason Generator
- `DailyTrendNews` 기반 Prompt Builder와 구조화된 `TrendReason` 모델을 추가함
- 뉴스 메타데이터만 Prompt에 포함하고, JSON 응답 필드와 confidence를 검증함
- 뉴스가 없을 때는 Gemini 호출 없이 근거 부족 결과를 반환함
- Fake client 단위 테스트로 정상 응답, malformed 응답, 필드 누락과 예외 전파를 검증함
- 단일 Live 호출은 Free Tier 일일 quota 20회 초과로 `429 RESOURCE_EXHAUSTED`가 발생해
  성공하지 못함. API key와 quota 값은 로그에 기록하지 않음

### Daily Trend Reason Application Service
- `DailyTrendReasonService`가 `DailyTrendNews` 목록을 입력 순서대로 처리함
- 항목별 Generator 1회 호출, fail-fast 예외 전파, 빈 입력 정책을 적용함
- Fake Generator로 순서, 중복 keyword, fallback 결과 보존과 예외 전파를 검증함

### OpenAI Trend Reason Generator
- OpenAI Responses API 기반 Generator와 동일한 `TrendReason` 결과 contract를 추가함
- JSON Schema 응답 형식과 supporting URL subset 검증을 적용함
- Gemini 구현과 DailyTrendReasonService는 변경하지 않음
- OpenAI SDK가 현재 가상환경에 없어 Unit Test는 Fake client로 검증함
- OpenAI API key 미확인 상태이므로 Live 검증은 수행하지 않음

---

## 2026-07-30 — Google Finance Sprint 1

### 구현

- exchange-qualified symbol을 검증하는 Playwright Collector를 추가함
- rendered DOM에서 현재가, 전일 종가, 시가, 변동률, 통화를 읽고 `StockPrice`로 정규화함
- Collector와 extraction 사이에 `StockPricePipeline`을 두고 생성자 주입을 적용함
- `python -m google_finance.main AAPL:NASDAQ` 단일 종목 CLI를 추가함
- Fake Playwright graph와 순수 extraction fixture 기반 테스트를 추가함
- `StockPrice.currency`와 UTC-aware `collected_at` 계약을 보강함
- 가격과 변동률을 `Decimal`로 유지해 float 변환에 따른 정밀도 손실을 제거함
- 현재 영어 parsing contract와 일치하지 않는 locale은 명시적으로 거부함
- locator wait에도 Collector timeout을 전달하고 CLI 오류는 stderr로 출력함

### 검증

- Google Finance 실제 페이지 CLI 실행 성공: `AAPL:NASDAQ`
- `python scripts/verify.py`: 190 passed, 3 skipped
- Google Finance 전용 테스트: 27 passed
- Ruff와 compileall 통과

### 범위와 미검증 사항

- 다중 종목, DB·Excel Storage, Scheduler, LLM 분석은 구현하지 않음
- 내부 batchexecute/RPC 호출은 사용하지 않음
- 테스트하지 않은 시장의 DOM 차이와 selector 장기 안정성은 확인하지 못함
- Google Finance 데이터의 지연·정확성·사용 제한은 운영 도입 전에 별도 검토해야 함
