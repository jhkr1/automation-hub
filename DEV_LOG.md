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
