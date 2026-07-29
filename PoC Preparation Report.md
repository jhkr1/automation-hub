# Playwright PoC Preparation Report

## 1. 목적과 범위

이번 Sprint 2-3의 목표는 Playwright 운영 코드를 구현하는 것이 아니다.
Playwright PoC를 실행할 수 있는 개발 환경과 기술 검증 기준을 준비하는 것이다.

이번 작업에서 수행한 범위:

- 필요한 Playwright 의존성 조사
- 브라우저 설치 절차 조사
- PoC 대상 URL 확정 시도
- 저장된 HTML과 기존 브라우저 조사 결과 대조
- Locator 후보와 우선순위 정의
- Headless 실행 위험 요소 정리
- PoC 성공 기준 정의
- Commit #2에서 개발용 Playwright 의존성 반영
- 의존성 설치 절차 문서화

이번 작업에서 수행하지 않은 범위:

- Python 코드 작성
- Playwright 패키지 설치
- 브라우저 바이너리 설치
- 실제 페이지 접속
- 실제 Top 10 추출
- 운영 코드 작성

## 2. 현재 상태와 근거

### 2.1 저장소 상태

현재 pyproject.toml의 런타임 의존성에는 requests, beautifulsoup4,
google-genai, openpyxl과 pydantic-settings가 있다.
Playwright는 운영 의존성이 아니라 dev optional dependency로 추가했다.

현재 가상환경에서 다음을 확인했다.

    importlib.util.find_spec("playwright") -> None

현재 가상환경에는 아직 Playwright 패키지를 설치하지 않았으므로 PoC는 실행할 수 없다.

### 2.2 기존 조사 결과

기존 브라우저 조사에서 다음을 확인했다.

- Ctrl+U의 초기 HTML에는 실시간 검색어가 없었다.
- Fetch/XHR의 sidebar.json은 최근 변경 문서 API였다.
- /i/xxxxx 요청은 검색어 클릭 시 발생하는 application/octet-stream 관련 요청이지만 실시간 검색어 API가 아니었다.
- Elements에서 실시간 검색어는 ul → li → a → span 구조로 렌더링되었다.
- DOM 순서가 실시간 검색어 순위임을 확인했다.

이 결과는 실시간 브라우저 렌더링을 검증해야 한다는 근거가 된다.
다만 구체적인 CSS selector와 locator 문자열은 아직 확정되지 않았다.

### 2.3 저장된 fixture 확인

namu.html의 canonical link에서 다음 URL을 확인했다.

    https://namu.wiki/w/%EB%82%98%EB%AC%B4%EC%9C%84:%EB%8C%80%EB%AC%B8

저장된 fixture의 title은 나무위키:대문 - 나무위키이다.
fixture 자체에는 실시간, 검색어 또는 인기 검색어 텍스트가 포함되어 있지 않았다.

따라서 위 URL은 fixture에서 확인한 PoC 대상 URL 후보이며,
현재 환경에서 live 접속이 성공한다는 의미는 아니다.

## 3. 필요한 Playwright 의존성

### 3.1 기본 패키지

PoC에 필요한 핵심 Python 패키지는 playwright이다.

Playwright Pytest plugin은 pytest 기반 end-to-end 테스트로 PoC를 작성할 때 선택적으로 사용할 수 있다.
단순한 독립 실행 PoC에는 playwright 패키지만으로도 충분하다.

권장 준비안:

- PoC 독립 실행: playwright
- pytest fixture와 브라우저 테스트 통합: playwright + pytest-playwright

### 3.2 pyproject.toml 반영 결과

Commit #2에서 기존 프로젝트 정책에 맞춰 개발용 optional dependency에 추가했다.

    [project.optional-dependencies]
    dev = [
        "pytest>=8.0",
        "ruff>=0.5",
        "playwright>=1.61",
    ]

프로젝트의 기존 의존성 표기 방식이 최소 버전 기준이므로 playwright>=1.61 형식을 사용했다.
현재 확인된 PyPI 최신 버전은 1.61.0이다.
pytest-playwright는 PoC를 pytest fixture 기반으로 실행할지 결정한 후 별도로 판단한다.

### 3.3 의존성 추가 판단

기존 requests와 BeautifulSoup로는 JavaScript 실행 후 DOM을 생성할 수 없다.
이번 프로젝트의 조사 결과 초기 HTML에 실시간 검색어가 없었으므로,
브라우저 렌더링 검증을 위해 Playwright를 추가할 기술적 이유가 있다.

이는 운영 의존성 추가의 최종 승인과는 다르다.
PoC 결과가 실패하면 Playwright를 프로젝트 의존성으로 채택하지 않을 수 있다.

## 4. Playwright 브라우저 설치 절차

Playwright 공식 Python 문서 기준의 일반적인 절차는 다음과 같다.

### 4.1 Python 패키지 설치

가상환경을 활성화한 뒤 개발 의존성을 설치한다.

    source .venv/bin/activate
    pip install -e ".[dev]"

pytest plugin을 사용하는 경우에는 다음을 추가한다.

    pip install pytest-playwright

이번 Sprint에서는 위 명령을 실행하지 않았다.

### 4.2 브라우저 바이너리 설치

기본 브라우저를 설치하는 명령:

    playwright install

PoC에서 Chromium만 사용할 경우:

    playwright install chromium

Linux 환경에서 시스템 의존성까지 설치해야 하는 경우:

    playwright install --with-deps chromium

시스템 패키지 설치는 권한과 운영 환경에 영향을 줄 수 있으므로 별도 승인이 필요하다.
Commit #2에서는 위 브라우저 설치 명령을 실행하지 않았다.
브라우저 바이너리 설치는 사용자 승인 후 별도 작업에서 수행한다.

### 4.3 설치 확인

설치된 브라우저 목록을 확인한다.

    playwright install --list

Playwright 버전이 변경되면 해당 버전에 맞는 브라우저 바이너리를 다시 설치해야 할 수 있다.
브라우저 바이너리는 Playwright 버전과 결합되어 관리된다.

공식 참고 문서:

- Playwright Python 설치: https://playwright.dev/python/docs/intro
- 브라우저 설치와 시스템 의존성: https://playwright.dev/python/docs/browsers

## 5. PoC 대상 URL

### 5.1 준비 단계의 대상 URL

PoC의 대상 URL은 fixture의 canonical 값으로 다음을 사용한다.

    https://namu.wiki/w/%EB%82%98%EB%AC%B4%EC%9C%84:%EB%8C%80%EB%AC%B8

이 URL은 저장소의 namu.html에서 확인한 값이다.

### 5.2 아직 확인하지 못한 사항

다음은 아직 live 브라우저에서 확인하지 못했다.

- page.goto 성공 여부
- HTTP 상태 코드와 실제 응답
- Headless Chromium에서의 접근 성공 여부
- Cloudflare 또는 CAPTCHA 개입 여부
- 현재 페이지의 실시간 검색어 DOM
- 현재 페이지에서 동일한 DOM 구조가 유지되는지 여부

따라서 이 URL은 준비 문서상의 PoC 대상이며,
실제 접속 성공 URL로 확정되었다고 기록하지 않는다.

## 6. DOM 구조 재조사 계획

### 6.1 현재까지 확인된 구조

기존 Elements 조사에서 확인한 구조는 다음과 같다.

    ul
      └── li
          └── a
              └── span

DOM 순서가 순위라는 점도 확인했다.

### 6.2 PoC 직전 재확인 항목

실제 Playwright 환경에서 다음을 다시 확인해야 한다.

1. 실시간 검색어 영역을 포함하는 가장 가까운 root 요소
2. root가 list 또는 다른 semantic role을 가지는지
3. 목록 항목의 실제 개수
4. 각 항목에 순위 숫자가 별도 노드로 존재하는지
5. 검색어 텍스트가 어느 요소에 있는지
6. 항목이 숨겨진 복제 DOM에도 존재하는지
7. 동일한 구조가 새로고침과 Headless 실행에서도 유지되는지
8. 요소의 data attribute, id, aria attribute 존재 여부
9. class 이름이 고정인지 빌드마다 바뀌는지

### 6.3 현재 fixture의 한계

namu.html은 저장된 초기 HTML이다.
fixture에서 실시간 검색어 텍스트가 발견되지 않았으므로,
fixture만으로 최종 동적 DOM의 locator를 확정할 수 없다.

## 7. Locator 후보와 우선순위

### 7.1 프로젝트 우선순위

Locator는 다음 우선순위로 조사하고 채택한다.

    data-* 또는 명시적 test id
        >
    id
        >
    aria-label 또는 접근성 이름
        >
    role
        >
    semantic structure
        >
    class

이 순서는 프로젝트의 안정성 평가 기준이다.
실제 DOM에 해당 속성이 존재하지 않으면 다음 후보로 내려간다.

### 7.2 후보 A: data-* 또는 test id

가장 우선하는 후보이다.
자동화 대상 영역에 의미 있는 data attribute가 있고 반복 실행에서 값이 유지된다면 가장 안정적인 후보로 평가한다.

확인할 내용:

- data-testid 또는 프로젝트 고유 data attribute 존재 여부
- 값이 새로고침과 배포 후에도 유지되는지
- 목록 전체를 정확히 한 번만 선택하는지

현재 실시간 검색어 영역에 이런 attribute가 존재한다는 사실은 확인하지 못했다.

### 7.3 후보 B: id

root 요소에 고유 id가 있고 의미가 분명하다면 후보로 사용한다.
id가 페이지에서 유일하고 동적으로 생성되지 않는지 확인한다.

현재 대상 영역의 id는 확인하지 못했다.

### 7.4 후보 C: aria-label 또는 접근성 이름

접근성 이름이나 aria-label이 실시간 검색어 영역을 의미 있게 설명한다면 후보로 평가한다.
Playwright 공식 문서도 사용자가 인식하는 방식에 가까운 role과 접근성 기반 locator를 권장한다.

현재 대상 영역의 aria-label은 확인하지 못했다.

### 7.5 후보 D: role

role=list와 role=listitem이 실제 접근성 트리에 노출되고,
다른 목록과 구분할 수 있는 accessible name이 있다면 후보가 된다.

role만으로 페이지의 모든 목록을 선택하지 않도록 root 범위를 먼저 좁혀야 한다.
현재 대상 영역의 실제 role은 확인하지 못했다.

### 7.6 후보 E: semantic structure

기존 조사에서 확인된 ul → li → a → span 구조를 후보로 둔다.
이 구조는 class보다 의미가 명확하지만 페이지에 여러 목록이 있으면 오선택할 수 있다.

따라서 구조만으로 확정하지 않고 다음 조건을 함께 확인한다.

- root 목록이 정확히 하나인가
- li 개수가 10개 이상인가
- 각 항목의 텍스트가 비어 있지 않은가
- 순서가 1위부터 10위와 일치하는가
- 다른 메뉴, footer와 구분되는가

### 7.7 후보 F: class

class는 마지막 후보로 둔다.
페이지 fixture에는 빌드 생성형으로 보이는 class와 data-v 속성이 다수 존재한다.
이런 class는 스타일 빌드 또는 배포 과정에서 변경될 가능성이 있으므로 안정성을 먼저 입증해야 한다.

class를 사용하려면 다음을 확인한다.

- class가 의미 기반 이름인가
- 반복 실행에서 동일한가
- 다른 영역과 중복되지 않는가
- 긴 generated class 조합에 의존하지 않는가

### 7.8 Locator 채택 기준

Locator 하나를 채택하려면 다음 조건을 모두 만족해야 한다.

- 후보가 실제 live DOM에 존재한다.
- 목표 root를 정확히 하나 선택한다.
- Top 10 항목을 정확히 10개 선택한다.
- 숨겨진 복제 요소를 포함하지 않는다.
- 10회 반복 실행에서 결과가 동일하다.
- 페이지 구조 변화에 대한 실패 원인을 확인할 수 있다.

Playwright 공식 locator 문서:

https://playwright.dev/python/docs/locators

공식 문서는 role, text, label, placeholder, alt text, title과 test id 같은 locator를 제공하며,
CSS와 XPath는 필요한 경우에 사용하도록 설명한다.

## 8. Headless 실행 위험 요소

### 8.1 접근 제한과 CAPTCHA

namu.html에는 reCAPTCHA와 hCaptcha 관련 문구 및 challenge script가 포함되어 있다.
이는 실제 Headless 실행에서 challenge가 발생할 가능성을 보여주는 증거이지만,
실제 challenge가 반드시 발생한다고 확정하는 근거는 아니다.

확인할 항목:

- Headless와 headed에서 응답이 다른가
- challenge 페이지로 이동하는가
- 검색어 영역이 challenge 뒤에 가려지는가
- 접근 제한으로 반복 실행이 실패하는가

### 8.2 렌더링 완료 시점

DOMContentLoaded 또는 load 이벤트만으로 실시간 검색어 DOM이 준비되었다고 단정하면 안 된다.
JavaScript 실행과 추가 요청이 끝난 뒤 목록이 나타나는지 확인해야 한다.

PoC에서는 고정 sleep만을 성공 기준으로 사용하지 않는다.
목표 root와 항목 개수에 대한 명시적 대기를 검토한다.

### 8.3 networkidle의 한계

분석·광고·추적 요청이 계속 발생하면 networkidle 상태가 늦어지거나 도달하지 않을 수 있다.
따라서 networkidle만 기다리는 방식은 단독 기준으로 사용하지 않는다.

### 8.4 viewport와 responsive layout

Headless의 기본 viewport가 실제 사용 환경과 다르면 모바일 또는 다른 responsive layout이 나타날 수 있다.
PoC에서는 viewport를 고정하고, 해당 viewport에서 목표 목록이 보이는지 기록한다.

### 8.5 언어, 시간대와 브라우저 상태

언어, 시간대, 쿠키, localStorage와 기존 browser context가 화면과 목록에 영향을 줄 수 있다.
반복 실행은 독립적인 context에서 수행하고 필요한 상태를 명시적으로 기록한다.

### 8.6 브라우저와 시스템 의존성

Chromium 실행에는 Playwright가 관리하는 브라우저 바이너리와 Linux 시스템 의존성이 필요할 수 있다.
브라우저 설치 성공과 실제 Headless 실행 성공은 별도로 검증한다.

### 8.7 반복 실행과 차단

10회 반복 실행은 단순 성능 측정이 아니라 접근 제한, 일시적 네트워크 오류,
DOM 변화와 locator 불안정성을 확인하는 실험이다.
실패 횟수와 실패 원인을 각각 기록한다.

## 9. Playwright PoC 성공 기준

### 9.1 환경 준비 기준

- Python 3.12 가상환경에서 playwright import 성공
- Chromium 브라우저 설치 성공
- playwright install --list에서 설치 상태 확인
- Headless browser launch 성공

### 9.2 페이지 접속 기준

- 준비된 대상 URL로 page.goto 성공
- timeout 없이 제한 시간 안에 페이지 응답 수신
- 접근 제한 또는 challenge 페이지가 아닌지 확인
- page title과 URL을 기록

### 9.3 DOM 렌더링 기준

- 초기 HTML 파싱 결과가 아니라 브라우저 DOM에서 목표 root 발견
- 목표 root가 visible 상태
- 실시간 검색어 항목이 렌더링 완료
- 목록의 DOM 순서가 순위 순서와 일치

### 9.4 Top 10 추출 기준

- 항목을 정확히 10개 추출
- 1위부터 10위까지 순서 보존
- 각 항목의 keyword가 비어 있지 않음
- 동일한 keyword 중복 여부 기록
- 수집 시각과 rank를 함께 기록할 수 있음

### 9.5 Headless 기준

- headed UI 없이 실행
- 브라우저 console error와 page error를 기록
- challenge 또는 접근 제한 없이 Top 10 추출
- 실행 종료 후 브라우저와 context가 정상 종료

### 9.6 10회 반복 기준

- 동일 조건에서 10회 연속 실행
- 10회 모두 페이지 접속 성공
- 10회 모두 DOM 렌더링 성공
- 10회 모두 정확히 10개 추출
- 실패가 있으면 성공률과 원인을 기록

PoC의 1차 통과 조건은 10회 중 10회 성공이다.
실패가 발생하면 Playwright 채택 여부를 즉시 결론 내리지 않고 실패 원인을 분류한다.

### 9.7 실행 시간 기준

각 실행에서 다음 시간을 측정한다.

- browser launch 시간
- page.goto 시작부터 페이지 접근 완료까지
- 목표 DOM 발견까지
- Top 10 추출 완료까지
- 전체 실행 시간

10회 실행 후 평균, 최소, 최대 시간을 기록한다.
가능하면 중앙값과 95 percentile도 기록한다.
운영 주기와 허용 시간은 PoC 결과를 본 뒤 별도로 결정한다.

### 9.8 Locator 안정성 기준

- 선택한 locator가 10회 모두 동일한 root를 선택
- 항목 수가 10회 모두 10개
- hidden 또는 duplicate 요소를 선택하지 않음
- fallback locator 없이 성공
- class 변경에 의존하지 않음
- locator 실패 시 원인을 확인할 수 있음

## 10. PoC 실행 후 작성할 기술 판정

PoC를 실제로 실행한 뒤 다음 형식으로 판정한다.

### 성공 여부

- 환경 준비:
- 페이지 접속:
- DOM 렌더링:
- Top 10 추출:
- Headless:
- 10회 반복:
- 평균 실행 시간:
- Locator 안정성:

### 발견한 문제점

- 접근 제한 또는 challenge:
- 렌더링 지연:
- DOM 변화:
- locator 중복 또는 누락:
- 브라우저 자원 사용:
- 실행 환경 문제:

### Playwright 채택 가능 여부

다음 조건을 모두 충족할 때 PoC 관점에서 채택 가능으로 판정한다.

- Top 10 추출 성공률 100%
- Headless 실행 성공
- 10회 반복 모두 성공
- locator가 안정적임
- 평균 실행 시간이 주기 실행 요구와 양립 가능함
- 실패 원인과 재현 방법을 설명할 수 있음

### 다른 대안 검토 여부

다음 경우에는 requests, 검증된 내부 데이터 소스 또는 다른 브라우저 자동화 방식을 다시 검토한다.

- Playwright가 반복 실행에서 불안정함
- challenge와 접근 제한을 해결할 수 없음
- locator가 지속적으로 변경됨
- 브라우저 실행 비용이 요구사항을 초과함
- 목표 데이터를 더 안정적인 공식 또는 확인된 데이터 경로에서 얻을 수 있음

## 11. 이번 Sprint의 결론

현재는 Playwright PoC 준비 문서와 개발 의존성 반영까지 완료된 상태이다.

확정된 준비 내용:

- 필요한 핵심 패키지 이름은 playwright이다.
- pyproject.toml의 dev optional dependency에 playwright>=1.61을 추가했다.
- 공식 설치 절차와 Chromium 설치 절차를 확인했다.
- fixture에서 PoC 대상 canonical URL을 확인했다.
- 기존 조사에서 DOM 계층과 순위 관계를 확인했다.
- locator 우선순위와 안정성 평가 기준을 정의했다.
- Headless 위험 요소와 PoC 성공 기준을 정의했다.

아직 확인하지 못한 내용:

- 실제 live URL 접속 성공
- Playwright 패키지와 브라우저 설치 성공
- 현재 live DOM의 실제 locator
- Headless에서의 Top 10 추출
- 10회 반복 성공률과 실행 시간

따라서 다음 Commit의 승인 조건은 개발 의존성 설치, 브라우저 바이너리 설치와 live DOM 재확인이다.
그 전에는 PoC 코드와 운영 코드를 작성하지 않는다.

## 12. 첫 번째 Playwright 환경 실험 결과

### 12.1 패키지 설치

사용자 승인 후 다음 설치를 수행했다.

    ./.venv/bin/pip install 'playwright>=1.61'

결과:

- Playwright Python 패키지 설치 성공
- 설치된 Python 패키지 버전: 1.61.0
- import 확인 성공

### 12.2 Chromium 설치

다음 명령으로 Chromium과 관련 브라우저 파일을 설치했다.

    ./.venv/bin/playwright install chromium

결과:

- Chromium 설치 성공
- Chromium headless shell 설치 성공
- FFmpeg 설치 성공
- 설치 목록 확인 성공

### 12.3 Headless 실행

Headless Chromium을 실행하여 대상 URL에 접속하는 실험을 수행했다.

Playwright import는 성공했지만 browser launch 단계에서 실패했다.

실제 오류:

    error while loading shared libraries: libnspr4.so: cannot open shared object file

즉, 브라우저 바이너리는 존재하지만 Linux 시스템 라이브러리 libnspr4.so가 없어 Headless Chromium을 시작할 수 없었다.

### 12.4 시스템 의존성 설치 시도

Playwright 공식 절차에 따라 다음 명령을 시도했다.

    ./.venv/bin/playwright install --with-deps chromium

결과:

- 시스템 의존성 설치가 sudo 단계에서 중단됨
- 현재 실행 환경은 sudo 비밀번호 입력을 요구함
- 사용자 비밀번호를 제공하지 않았으므로 설치를 완료하지 않음

### 12.5 URL과 Locator 검증 결과

Headless browser launch가 실패했으므로 다음 단계는 실행하지 못했다.

- 나무위키 대상 URL 접속
- 페이지 제목 출력
- 최종 URL 출력
- 실시간 검색어 영역의 live DOM 재확인
- 실제 Locator 확정

따라서 이번 실험에서는 URL과 Locator에 대한 새로운 live 증거를 얻지 못했다.
기존 fixture의 canonical URL과 기존 DevTools 조사 결과만 유효한 근거로 유지한다.

### 12.6 첫 번째 실험 판정

- Python 패키지 설치: 성공
- Chromium 바이너리 설치: 성공
- Headless Chromium 실행: 실패
- 대상 URL 접속: 미실행
- 페이지 제목과 URL 출력: 미실행
- Locator 재확인: 미실행

이번 실패의 직접 원인은 브라우저 바이너리 자체가 아니라 Linux 시스템 라이브러리 부족이다.
시스템 의존성을 설치한 뒤 Headless 실행을 다시 검증해야 한다.

## 13. 두 번째 환경 실험 결과

사용자가 Linux 시스템 의존성 설치를 완료한 후 Headless 실험을 다시 수행했다.

### 13.1 환경 확인

- libnspr4.so 확인 성공
- libnss3.so 확인 성공
- Playwright Python import 성공
- Chromium과 Headless Shell 설치 목록 확인 성공

### 13.2 대상 URL 재검증

기존 fixture의 canonical 문서 URL:

    https://namu.wiki/w/%EB%82%98%EB%AC%B4%EC%9C%84:%EB%8C%80%EB%AC%B8

이 URL은 Headless에서 HTTP 404를 반환했다.
따라서 PoC의 live 접속 대상은 저장된 canonical 문서 URL이 아니라 홈페이지 root URL로 변경한다.

홈페이지 URL:

    https://namu.wiki/

홈페이지 URL의 Headless 결과:

- HTTP status: 200
- title: 나무위키:대문 - 나무위키
- 최종 URL: https://namu.wiki/w/%EB%82%98%EB%AC%B4%EC%9C%84%ED%82%A4:%EB%8C%80%EB%AC%B8
- console error: 0건
- page error: 0건

실험 출력에서 최종 URL은 다음과 같이 확인되었다.

    https://namu.wiki/w/%EB%82%98%EB%AC%B4%EC%9C%84%ED%82%A4:%EB%8C%80%EB%AC%B8

### 13.3 실시간 검색어 DOM 재확인

Headless 홈페이지에서 다음 후보를 확인했다.

    ul.yKuNIpkC

결과:

- locator count: 1
- visible: true
- 직접 자식 li 수: 실행 시점에 10 또는 11
- li 내부는 a와 span으로 구성
- a href는 /Go?q= 형태
- a title과 span 텍스트에 검색어가 존재
- root에는 id가 없음
- root와 li에는 data-v 속성이 있으나 값은 빌드 생성형으로 보임

관찰된 DOM 구조:

    ul.yKuNIpkC
      └── li.aabxWUc+
          └── a.ntqH4deF[href^="/Go?q="]
              └── span.HiABlndl

첫 번째 목록의 마지막 항목이 첫 번째 항목과 중복되는 실행이 반복되었다.
이는 10개 검색어와 carousel 반복 sentinel이 함께 렌더링되는 구조일 가능성이 있지만,
현재 실험만으로 내부 의도를 확정하지 않는다.

### 13.4 Locator 후보 비교

홈페이지에서 다음 후보를 비교했다.

| 후보 | 선택 결과 | 평가 |
|---|---:|---|
| ul.yKuNIpkC | 1개 | 현재 실행에서 정확히 한 root를 선택하지만 generated class에 의존함 |
| ul[data-v-ca9e9b6d] | 1개 | 현재 실행에서 선택되지만 data-v 값이 빌드 생성형임 |
| ul:has(> li > a[href^="/Go?q="]) | 1개 | 검색어 링크의 실제 href 구조를 반영하며 class보다 의미가 명확함 |
| ul:has(> li > a > span) | 2개 | 다른 목록도 선택하여 범위가 넓음 |

현재 PoC 후보 우선순위:

1. ul:has(> li > a[href^="/Go?q="])
2. ul.yKuNIpkC
3. ul[data-v-ca9e9b6d]
4. ul:has(> li > a > span)

첫 번째 후보도 10회 반복 실행과 DOM 시점별 항목 수 차이를 추가 검증해야 한다.
아직 운영용 locator로 확정하지 않는다.

### 13.5 10회 반복 결과

홈페이지 URL과 ul.yKuNIpkC 후보로 Headless 실행을 10회 반복했다.

- 10회 모두 HTTP 200
- 10회 모두 후보 locator count 1
- 10회 모두 직접 li count 10으로 관찰됨
- 10회 모두 마지막 항목과 첫 항목이 중복됨
- 평균 실행 시간: 1490.4ms
- 최소 실행 시간: 1341.2ms
- 최대 실행 시간: 1689.8ms

10회 접속 자체는 성공했지만, 중복 sentinel 때문에 10개 li를 곧바로 1~10위 데이터로 간주할 수 없다.
따라서 Top10 추출 성공 기준은 아직 통과하지 못했다.

### 13.6 실험 판정

- 시스템 의존성 준비: 성공
- Headless Chromium launch: 성공
- 홈페이지 접속: 성공
- 페이지 제목과 최종 URL 출력: 성공
- live DOM 후보 재확인: 성공
- 단일 root locator 선택: 10회 성공
- Top10 추출: 미구현 및 미판정
- Locator 운영 채택: 보류

이번 실험으로 홈페이지 root URL과 브라우저 실행 환경은 검증했다.
그러나 첫 번째 DOM 후보는 실행 시점에 따라 항목 수가 달라지고 중복 sentinel이 관찰되므로,
다음 단계에서 렌더링 안정화 시점과 실제 순위 데이터 경계를 추가로 확인해야 한다.

## 14. Sprint 2-4 Top10 추출 규칙 검증

Sprint 2-4에서는 운영 Collector를 작성하지 않고, 홈페이지의 실시간 검색어 영역을
Headless와 Headed Chromium에서 반복 관찰했다.

### 14.1 검증 조건

- URL: `https://namu.wiki/`
- root 후보: `ul.yKuNIpkC`
- 렌더링 대기: root visible 확인 후 2초 대기
- 반복 검증: Headless 새로고침 5회, Headed 새로고침 5회

### 14.2 실제 DOM 캡처

실제 실행에서 확인한 `root.outerHTML`의 구조적 발췌는 다음과 같다.
`검색어`와 `...`는 중간 항목을 생략한 표기가 아니라 구조적 위치를 설명하기 위한 표기다.
실제 텍스트와 href는 아래 표에 모두 기록한다.

```html
<ul data-v-ca9e9b6d="" class="yKuNIpkC">
  <li data-v-ca9e9b6d="" class="aabxWUc+">
    <a data-v-ca9e9b6d="" href="/Go?q=..." class="ntqH4deF" title="..." tabindex="-1">
      <span data-v-ca9e9b6d="" class="HiABlndl">검색어</span>
    </a>
  </li>
  <!-- 동일한 구조의 li가 반복됨 -->
  <li data-v-ca9e9b6d="" class="aabxWUc+ NQ90pHJj">
    <a data-v-ca9e9b6d="" href="/Go?q=첫 번째 검색어" class="ntqH4deF" title="첫 번째 검색어" tabindex="-1">
      <span data-v-ca9e9b6d="" class="HiABlndl">첫 번째 검색어</span>
    </a>
  </li>
</ul>
```

위 캡처에서 `검색어`는 DOM 구조를 설명하기 위한 표기이고, 실제 실행에서 확인한 항목은
다음과 같다.

| DOM 순서 | 실제 텍스트 |
|---:|---|
| 1 | 이동형 |
| 2 | 황정민 |
| 3 | 서킷브레이커 |
| 4 | 유시은 |
| 5 | 스파이더맨 브랜드 뉴 데이 |
| 6 | 문근영 |
| 7 | 고지용 |
| 8 | 김용범 |
| 9 | lck |
| 10 | 최준용 |
| 11 | 이동형 |

### 14.3 항목과 sentinel 검증 결과

상세 DOM 조사 결과:

- root의 직접 자식은 모두 `LI`였다.
- 직접 자식 `li` 개수는 11개였다.
- 1~10번째 `li`와 11번째 `li` 모두 visible이었다.
- 11번째 텍스트와 `href`는 1번째 항목과 같았다.
- 11번째 `li`에는 `NQ90pHJj` 클래스가 추가되어 있었다.
- 11번째 이후의 추가 노드는 없었다.
- 확인한 반복 실행에서 sentinel은 항상 마지막 위치였다.
- 확인한 반복 실행에서 sentinel은 항상 첫 번째 항목의 복제였다.

반복 결과:

| 실행 모드 | 반복 횟수 | 매 실행 `li` 수 | 숨김 `li` | 마지막 항목 복제 | sentinel 위치 |
|---|---:|---:|---:|---|---|
| Headless | 5회 | 모두 11개 | 모두 0개 | 모두 확인 | 모두 마지막 |
| Headed | 5회 | 모두 11개 | 모두 0개 | 모두 확인 | 모두 마지막 |

이 결과는 이번에 확인한 10회 실행에 대한 사실이다. 모든 실행과 모든 향후 페이지 상태에서
동일하다고 일반화하지 않는다.

### 14.4 Headed / Headless 차이

이번 관찰 범위에서 Headed와 Headless의 다음 결과는 동일했다.

- HTTP status: 200
- root locator 선택
- `li` 개수: 11개
- hidden `li` 개수: 0개
- 마지막 항목의 첫 항목 복제 여부
- sentinel 위치

따라서 현재 검증 결과만으로는 Headed와 Headless 사이의 DOM 차이를 확인하지 못했다.

### 14.5 확정한 Top10 추출 규칙

운영 Collector 구현 시 적용할 검증 규칙은 다음과 같다.

1. `ul:has(> li > a[href^="/Go?q="])` 후보로 검색어 root를 선택한다.
2. root의 직접 자식 `li`만 조회한다.
3. 각 `li`가 visible인지 확인하고 hidden 항목은 제외한다.
4. 항목이 11개이고 마지막 항목의 텍스트와 `href`가 첫 항목과 같으면 마지막 항목을 sentinel로 제외한다.
5. sentinel을 제외한 항목이 정확히 10개인지 검증한다.
6. DOM 순서대로 1~10의 `rank`를 부여한다.
7. 위 조건을 만족하지 않으면 임의로 앞 10개를 사용하지 않고 추출 실패로 처리한다.

요약하면 다음 순서다.

    root 선택
    ↓
    직접 자식 li 조회
    ↓
    hidden 제외
    ↓
    마지막 항목이 첫 항목의 텍스트·href 복제인지 검증
    ↓
    복제 노드만 sentinel로 제외
    ↓
    정확히 10개인지 검증
    ↓
    DOM 순서로 rank 1~10 부여

이 규칙은 `NQ90pHJj` 클래스만으로 sentinel을 판별하지 않는다.
클래스는 보조 증거로 기록하되, 첫 항목과 마지막 항목의 텍스트·href 동일성과
마지막 위치를 함께 검증한다.

### 14.6 Sprint 2-4 판정

- 실제 DOM 구조 확인: 성공
- `li` 개수 확인: 성공
- sentinel 존재 여부 확인: 성공
- sentinel 위치 확인: 성공
- sentinel의 첫 항목 복제 여부 확인: 성공
- hidden 요소 확인: hidden `li` 없음
- Top10 이후 추가 노드 확인: 없음
- Headed / Headless 비교: 관찰 범위에서 차이 없음
- 새로고침 후 규칙 유지: Headless 5회, Headed 5회에서 유지
- 운영 Collector 구현: 수행하지 않음

따라서 다음 Sprint부터는 위 규칙을 검증 실패를 숨기지 않는 방식으로 구현할 수 있다.
