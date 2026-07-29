# Software Engineering Handbook

`automation-hub`를 처음부터 다시 읽으며 Python 기반 자동화 프로젝트의 설계, 구현,
검증, 운영을 학습하기 위한 교재의 목차다.

이 문서는 Reference나 API Reference가 아니다. 각 Chapter의 본문은 다음 순서로 집필한다.

1. 왜 이 기술이 필요한가
2. 어떤 문제를 해결하는가
3. 핵심 개념
4. 실무에서는 어떻게 사용하는가
5. 이 프로젝트에서는 어디에 사용했는가
6. 장점
7. 단점
8. 언제 사용하면 안 되는가
9. 자주 하는 실수
10. 다음 Chapter와 어떻게 연결되는가

## 독자와 학습 방법

- 대상: Python을 조금 알고, Software Engineering을 체계적으로 배우려는 개발자
- 목표: 문법 암기보다 설계 이유, 책임 경계, 검증 방법과 운영 trade-off를 이해함
- 근거: 실제 코드, 테스트, 명령 결과, 공식 문서와 추론을 구분함
- 프로젝트 연결: 각 Chapter는 실제 파일과 공개 계약을 반드시 참조함
- 본문 집필 전: 관련 코드·테스트·문서를 다시 확인하고 현재 구현과 과거 결정을 구분함

## Handbook 전체 구성

| Part | 주제 | 역할 | 예상 분량 | 권장 난이도 |
|---|---|---|---:|---|
| 1 | Python Backend Foundations | Python 프로젝트를 읽고 작성하는 기반 | 35~45쪽 | 초급~중급 |
| 2 | Software Architecture | 책임과 의존성의 구조화 | 40~50쪽 | 중급 |
| 3 | Web Crawling and Browser Automation | 웹 데이터가 생성되는 위치를 검증하고 수집 | 45~55쪽 | 중급 |
| 4 | AI Integration | LLM을 별도 Provider로 연결하고 근거를 통제 | 40~50쪽 | 중급 |
| 5 | Testing and Quality Engineering | 실패를 재현하고 품질을 관찰 | 40~50쪽 | 중급 |
| 6 | DevOps and Operations | 검증, 배포, cron 운영과 장애 확인 | 35~45쪽 | 중급 |
| 7 | Case Study: namuwiki_trend | Sprint 순서로 전체 프로젝트 재구성 | 50~70쪽 | 종합 |

예상 본문 분량은 약 285~365쪽이며, 현재 Sprint에서는 목차만 설계한다.

---

# Part 1. Python Backend Foundations

Python 문법을 업무 자동화 프로젝트의 유지보수 가능한 코드로 연결하는 Part다.

## Chapter 1. Python 프로젝트를 읽는 법

- 난이도: 초급
- 선행 지식: Python 파일 실행과 기본 문법
- 학습 목표: 모듈, 패키지, import, 공개 API와 파일 구조를 구분함
- 예상 읽기 시간: 25분
- 연결 코드: `namuwiki_trend/__init__.py`, `config.py`, `models.py`

## Chapter 2. Virtual Environment와 의존성

- 난이도: 초급
- 선행 지식: 터미널 기본 명령
- 학습 목표: `.venv`, Python interpreter, 재현 가능한 설치의 필요성을 이해함
- 예상 읽기 시간: 30분
- 연결 코드: `.venv/`, `pyproject.toml`, `.gitignore`

## Chapter 3. `pyproject.toml`과 Package 설계

- 난이도: 초급~중급
- 선행 지식: Package와 Module
- 학습 목표: 프로젝트 metadata, dependencies, dev dependencies와 flat layout을 설계함
- 예상 읽기 시간: 35분
- 연결 코드: `pyproject.toml`, `namuwiki_trend/`, `google_finance/`

## Chapter 4. Type Hint와 데이터 계약

- 난이도: 중급
- 선행 지식: 함수와 class
- 학습 목표: Type Hint가 협업 계약과 오류 발견에 미치는 영향을 이해함
- 예상 읽기 시간: 35분
- 연결 코드: `models.py`, `pipeline.py`, `enricher.py`

## Chapter 5. `dataclass`, 불변성, `Pathlib`

- 난이도: 중급
- 선행 지식: class, 타입, 파일 경로
- 학습 목표: 모델 불변성, 명시적 데이터 구조와 플랫폼 독립 경로 처리를 사용함
- 예상 읽기 시간: 40분
- 연결 코드: `models.py`, `insight_storage.py`, `main.py`

## Chapter 6. Exception과 Logging

- 난이도: 중급
- 선행 지식: 함수 호출과 파일·네트워크 오류
- 학습 목표: 예외를 숨기지 않고 경계별로 전달·기록하는 방법을 설계함
- 예상 읽기 시간: 40분
- 연결 코드: `collector.py`, `news_context_provider.py`, `main.py`, `config.py`

---

# Part 2. Software Architecture

작은 Python 스크립트를 교체 가능하고 테스트 가능한 Application으로 만드는 Part다.

## Chapter 7. 책임 분리와 계층 구조

- 난이도: 중급
- 선행 지식: Part 1
- 학습 목표: Model, Provider, Application, Storage의 변경 이유를 분리함
- 예상 읽기 시간: 40분
- 연결 코드: `collector.py`, `enricher.py`, `pipeline.py`, `insight_storage.py`

## Chapter 8. Interface와 Protocol

- 난이도: 중급
- 선행 지식: Type Hint, 객체의 행동 계약
- 학습 목표: 구체 클래스가 아닌 필요한 동작에 의존하는 구조를 이해함
- 예상 읽기 시간: 35분
- 연결 코드: `pipeline.py`, `enricher.py`, `main.py`

## Chapter 9. Dependency Injection과 Composition Root

- 난이도: 중급
- 선행 지식: Interface와 생성자
- 학습 목표: 의존성 생성 위치와 주입 위치를 분리하고 Fake를 연결함
- 예상 읽기 시간: 40분
- 연결 코드: `main.py`, `pipeline.py`, `tests/namuwiki_trend/test_main.py`

## Chapter 10. Pipeline과 Application Orchestration

- 난이도: 중급
- 선행 지식: 계층 분리, DI
- 학습 목표: 순서 보존, fail-fast, 빈 결과 정책을 Application Layer에 표현함
- 예상 읽기 시간: 40분
- 연결 코드: `pipeline.py`, `enricher.py`, `main.py`

## Chapter 11. Repository·Storage Pattern과 Output Contract

- 난이도: 중급
- 선행 지식: dataclass, 파일 I/O
- 학습 목표: 원본 CSV와 Enriched JSON의 소비 목적을 분리하고 schema를 관리함
- 예상 읽기 시간: 40분
- 연결 코드: `csv_storage.py`, `insight_storage.py`, `ARCHITECTURE.md`

## Chapter 12. Clean Architecture와 과도한 추상화

- 난이도: 중급~고급
- 선행 지식: Part 2 앞 Chapter
- 학습 목표: KISS, YAGNI, SOLID, Rule of Three를 현재 규모에 적용함
- 예상 읽기 시간: 35분
- 연결 코드: 전체 `namuwiki_trend/`, `AGENTS.md`

---

# Part 3. Web Crawling and Browser Automation

웹 페이지의 초기 응답과 최종 DOM을 구분하고 검증된 근거로 수집 방식을 선택하는 Part다.

## Chapter 13. HTTP Request와 Response

- 난이도: 초급~중급
- 선행 지식: URL, 네트워크 기본
- 학습 목표: HTTP status, header, payload, GET과 POST의 역할을 구분함
- 예상 읽기 시간: 35분
- 연결 코드: `news_context_provider.py`, `collector.py`

## Chapter 14. HTML, DOM, View Source

- 난이도: 초급~중급
- 선행 지식: HTML 기본 구조
- 학습 목표: 초기 HTML과 JavaScript 이후 DOM이 달라지는 이유를 이해함
- 예상 읽기 시간: 35분
- 연결 코드: `namu.html`, `collector.py`, `PoC Preparation Report.md`

## Chapter 15. CSR, SSR, Dynamic Rendering

- 난이도: 중급
- 선행 지식: HTTP, DOM
- 학습 목표: 데이터 생성 위치가 수집 도구 선택에 미치는 영향을 분석함
- 예상 읽기 시간: 30분
- 연결 코드: `collector.py`, `playwright_poc.py`

## Chapter 16. DevTools Network와 Evidence 기반 조사

- 난이도: 중급
- 선행 지식: HTTP와 브라우저 DevTools
- 학습 목표: Fetch/XHR, Response, Initiator를 확인하고 API를 추측하지 않음
- 예상 읽기 시간: 40분
- 연결 코드: `STUDY_NOTE.md`의 과거 조사 기록, `PoC Preparation Report.md`

## Chapter 17. CSS Selector, Locator, XPath

- 난이도: 중급
- 선행 지식: DOM tree
- 학습 목표: 실제 구조에 기반한 안정적 Locator를 선택하고 fallback을 남용하지 않음
- 예상 읽기 시간: 40분
- 연결 코드: `collector.py`, `extraction.py`, `playwright_poc.py`

## Chapter 18. requests와 BeautifulSoup

- 난이도: 초급~중급
- 선행 지식: HTTP, HTML
- 학습 목표: 정적 HTML 파싱의 장점과 동적 사이트의 한계를 판단함
- 예상 읽기 시간: 30분
- 연결 코드: `news_context_provider.py`, `pyproject.toml`

## Chapter 19. Playwright와 Chromium

- 난이도: 중급
- 선행 지식: DOM, Locator, Python context manager
- 학습 목표: Headless browser, BrowserContext, 대기와 종료를 안전하게 관리함
- 예상 읽기 시간: 45분
- 연결 코드: `collector.py`, `playwright_poc.py`, `namu.html`

---

# Part 4. AI Integration

외부 LLM을 애플리케이션의 책임과 분리하고 근거·비용·실패를 통제하는 Part다.

## Chapter 20. RSS와 News Context

- 난이도: 중급
- 선행 지식: HTTP, XML, datetime
- 학습 목표: RSS field, parsing, URL 검증과 뉴스 문맥의 한계를 이해함
- 예상 읽기 시간: 40분
- 연결 코드: `news_context_provider.py`, `news_context_poc.py`

## Chapter 21. LLM Provider와 Prompt Builder

- 난이도: 중급
- 선행 지식: Provider interface, 문자열 처리
- 학습 목표: Prompt 생성과 SDK 호출을 분리하고 교체 가능한 경계를 설계함
- 예상 읽기 시간: 40분
- 연결 코드: `gemini_reason_generator.py`, `enricher.py`

## Chapter 22. Prompt Engineering과 Grounding

- 난이도: 중급
- 선행 지식: 뉴스 문맥, LLM 기본 개념
- 학습 목표: 근거 밖 추측을 제한하고 fallback 응답을 정의함
- 예상 읽기 시간: 40분
- 연결 코드: `build_reason_prompt()`, `tests/namuwiki_trend/test_gemini_reason_generator.py`

## Chapter 23. Rate Limit, Quota, Retry

- 난이도: 중급~고급
- 선행 지식: 예외 처리, 시간과 함수 주입
- 학습 목표: 최소 요청 간격, 429 제한 재시도, RetryInfo와 exponential backoff를 설계함
- 예상 읽기 시간: 45분
- 연결 코드: `gemini_reason_generator.py`, `main.py`

## Chapter 24. Clock Injection과 시간 의존성

- 난이도: 중급
- 선행 지식: DI, 함수 객체
- 학습 목표: 실제 sleep 없이 시간 기반 정책을 테스트함
- 예상 읽기 시간: 30분
- 연결 코드: `gemini_reason_generator.py`, 관련 Gemini 테스트

---

# Part 5. Testing and Quality Engineering

테스트를 기능 확인을 넘어 계약 검증과 데이터 품질 관찰 도구로 사용하는 Part다.

## Chapter 25. pytest의 기본 구조

- 난이도: 초급
- 선행 지식: Python 함수
- 학습 목표: test discovery, assertion, parametrization과 실패 읽기를 익힘
- 예상 읽기 시간: 35분
- 연결 코드: `tests/`, `pyproject.toml`

## Chapter 26. Fake, Mock, Fixture, MonkeyPatch

- 난이도: 중급
- 선행 지식: DI, 객체 계약
- 학습 목표: 외부 API 없이 Provider, Gemini, Pipeline을 검증함
- 예상 읽기 시간: 45분
- 연결 코드: `tests/namuwiki_trend/test_enricher.py`, `test_main.py`

## Chapter 27. Unit Verification과 Live Verification

- 난이도: 중급
- 선행 지식: pytest, 외부 시스템
- 학습 목표: 재현 가능한 단위 테스트와 quota를 소비하는 Live 검증을 분리함
- 예상 읽기 시간: 35분
- 연결 코드: `scripts/verify.py`, `README.md`, `ARCHITECTURE.md`

## Chapter 28. Quality Diagnostics와 Heuristic

- 난이도: 중급
- 선행 지식: dataclass, sequence, 문자열 정규화
- 학습 목표: 구조적 성공과 의미적 품질을 구분하고 관찰 지표를 설계함
- 예상 읽기 시간: 40분
- 연결 코드: `quality_diagnostics.py`, `test_quality_diagnostics.py`

## Chapter 29. 데이터 계약과 회귀 방지

- 난이도: 중급
- 선행 지식: JSON, CSV, pytest
- 학습 목표: rank, order, schema와 불변성을 테스트로 보존함
- 예상 읽기 시간: 35분
- 연결 코드: `extraction.py`, `csv_storage.py`, `insight_storage.py`

---

# Part 6. DevOps and Operations

코드가 실제 환경에서 반복 실행되고 실패를 진단할 수 있도록 만드는 Part다.

## Chapter 30. Ruff, compileall, verify.py

- 난이도: 초급~중급
- 선행 지식: shell command, pytest
- 학습 목표: 정적 검사·테스트·컴파일·diff 검사를 하나의 Harness로 실행함
- 예상 읽기 시간: 30분
- 연결 코드: `scripts/verify.py`, `tests/test_verify.py`

## Chapter 31. Shell Script와 실행 경계

- 난이도: 중급
- 선행 지식: Bash 기본 명령
- 학습 목표: root 계산, 환경변수, exit code, stdout/stderr를 운영 경계에 배치함
- 예상 읽기 시간: 35분
- 연결 코드: `run_namuwiki_trend.sh`

## Chapter 32. Linux, WSL, cron

- 난이도: 중급
- 선행 지식: shell, 프로세스와 파일 경로
- 학습 목표: cron 표현식, WSL 지속성, daemon과 사용자 crontab을 이해함
- 예상 읽기 시간: 40분
- 연결 코드: `README.md`, `ARCHITECTURE.md`, `run_namuwiki_trend.sh`

## Chapter 33. Logging, Monitoring, Debugging

- 난이도: 중급
- 선행 지식: exception, shell exit code
- 학습 목표: 로그에서 실행 상태·실패 원인·소요 시간을 관찰함
- 예상 읽기 시간: 40분
- 연결 코드: `config.py`, `run_namuwiki_trend.sh`, `logs/`

## Chapter 34. Git, GitHub, Conventional Commit

- 난이도: 초급~중급
- 선행 지식: Git 기본 명령
- 학습 목표: 작은 Commit, Working Tree, branch와 원격 협업 규칙을 적용함
- 예상 읽기 시간: 35분
- 연결 코드: Git history, `AGENTS.md`

## Chapter 35. CI/CD와 Release

- 난이도: 중급~고급
- 선행 지식: verify Harness, Git
- 학습 목표: 로컬 검증을 CI와 릴리스 기준으로 확장할 때의 조건을 설계함
- 예상 읽기 시간: 40분
- 연결 코드: 현재 `scripts/verify.py`; CI workflow와 Release는 향후 설계 대상

---

# Part 7. Case Study: namuwiki_trend

앞의 개념을 실제 프로젝트의 시간 순서로 다시 학습하는 종합 Part다.

## Chapter 36. Sprint 1 — Flat Layout과 프로젝트 뼈대

- 난이도: 초급~중급
- 핵심 질문: 왜 독립 패키지와 flat layout으로 시작했는가
- 연결 코드: `pyproject.toml`, `namuwiki_trend/config.py`, `models.py`

## Chapter 37. Sprint 2 — Playwright 선택과 DOM 검증

- 난이도: 중급
- 핵심 질문: 왜 requests·BeautifulSoup 대신 브라우저 렌더링을 검증했는가
- 연결 코드: `collector.py`, `extraction.py`, `playwright_poc.py`

## Chapter 38. Sprint 3 — RSS와 Gemini Enrichment

- 난이도: 중급
- 핵심 질문: Collector가 LLM을 직접 알지 않아야 하는 이유는 무엇인가
- 연결 코드: `news_context_provider.py`, `gemini_reason_generator.py`, `enricher.py`

## Chapter 39. Sprint 4 — Pipeline과 JSON Output Contract

- 난이도: 중급
- 핵심 질문: 단일 Item을 Top10 Application으로 연결하고 결과를 어떻게 보존했는가
- 연결 코드: `pipeline.py`, `insight_storage.py`, `main.py`

## Chapter 40. Sprint 5 — Rate Limiting과 Retry

- 난이도: 중급~고급
- 핵심 질문: Free Tier quota 실패를 어느 계층에서 해결했는가
- 연결 코드: `gemini_reason_generator.py`, Live 실행 기록

## Chapter 41. Sprint 6 — Quality Diagnostics

- 난이도: 중급
- 핵심 질문: 구조적 성공과 의미적 뉴스 품질을 어떻게 구분해 관찰하는가
- 연결 코드: `quality_diagnostics.py`, `test_quality_diagnostics.py`

## Chapter 42. Sprint 7 — WSL cron 운영

- 난이도: 중급
- 핵심 질문: 개발 명령을 반복 가능한 운영 실행으로 어떻게 감싸는가
- 연결 코드: `run_namuwiki_trend.sh`, `README.md`, `ARCHITECTURE.md`

## Chapter 43. 전체 회고 — 설계·검증·운영의 연결

- 난이도: 종합
- 핵심 질문: 각 Sprint의 Evidence가 다음 설계 결정을 어떻게 제한하고 개선했는가
- 연결 코드: 전체 패키지, Git history, 문서와 로그

---

# 학습 순서와 집필 로드맵

## 권장 읽기 순서

1. Part 1에서 Python 프로젝트와 데이터 계약을 이해한다.
2. Part 2에서 책임·의존성·Pipeline 구조를 이해한다.
3. Part 3에서 실제 웹 데이터의 생성 위치와 수집 방식을 이해한다.
4. Part 4에서 뉴스 문맥과 Gemini 경계를 이해한다.
5. Part 5에서 테스트와 품질 측정 방법을 이해한다.
6. Part 6에서 로컬 검증을 운영 자동화로 연결한다.
7. Part 7에서 Sprint 순서로 전체 의사결정을 재구성한다.

## 추후 집필 순서

1. Chapter 1~6: Python과 프로젝트 읽기
2. Chapter 7~12: Architecture와 책임 경계
3. Chapter 13~19: Web Crawling 조사와 Playwright
4. Chapter 20~24: RSS, Gemini, Rate Limit
5. Chapter 25~29: Testing과 Quality Diagnostics
6. Chapter 30~35: Harness, WSL, cron, Git, CI/CD
7. Chapter 36~43: Sprint Case Study와 전체 회고

각 Chapter 집필 시 실제 코드·테스트·명령 결과를 먼저 확인하고, 일반 지식과 프로젝트
Evidence를 구분한다. 구현되지 않은 기능은 사례처럼 서술하지 않으며, 확인하지 못한 내용은
`확인하지 못함`으로 표시한다.
