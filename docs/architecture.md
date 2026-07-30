# automation-hub 공통 아키텍처

이 문서는 모든 자동화 패키지에 적용되는 모노레포 공통 규칙만 다룬다.
패키지별 구현과 설계 결정은 [패키지 문서](packages/)와
[Decision Records](decisions/)를 참고한다.

## 모노레포와 패키지 독립성

`automation-hub`는 여러 독립 자동화 프로젝트를 하나의 저장소에서 관리한다.
공통 Python 의존성, 개발 도구와 검증 명령은 루트에서 관리하지만, 각 패키지는
자신의 모델·Provider·Application 흐름을 소유한다.

현재 패키지는 다음과 같다.

- `namuwiki_trend`: 나무위키 실시간 검색어 수집 및 활용
- `google_finance`: 설정과 시세 모델 뼈대만 구현된 패키지

## 레이아웃

Python 코드는 flat layout을 사용한다. 현재 요구사항이 없는 `src/` 레이아웃이나
공통 `shared` 패키지를 추가하지 않는다. 공통 코드는 실제 세 프로젝트에서 반복될
때 Rule of Three를 적용해 검토한다.

## 계층 경계

```text
Application
    ↓
Provider / Collector
    ↓
Model
    ↓
Storage 또는 외부 시스템
```

- Application Layer는 흐름과 의존성 조립을 담당한다.
- Provider와 Collector는 외부 시스템의 세부사항을 감싼다.
- Model은 계층 사이의 데이터 계약을 보존한다.
- Collector와 Provider는 Application이나 LLM을 직접 호출하지 않는다.
- 외부 시스템과 생성기는 생성자 주입을 우선한다.

## 테스트와 검증

- 기본 테스트는 외부 네트워크, 실제 API, 실제 브라우저에 의존하지 않는다.
- Provider와 SDK는 Fake 또는 Mock으로 대체한다.
- 파서와 변환 로직은 fixture로 검증한다.
- 공개 데이터 계약, 입력 순서, 빈 응답과 실패 정책을 테스트한다.
- 표준 검증 명령은 `python scripts/verify.py`다.

## 문서 규칙

- 루트 README는 GitHub 첫 화면용 빠른 안내로 유지한다.
- 공통 설계는 이 문서에만 기록한다.
- 패키지 전용 설계는 `docs/packages/<package>/`에 기록한다.
- 설계 선택의 근거는 개별 [Decision Record](decisions/)로 기록한다.
- 시간순 구현 기록은 [개발 로그](development/DEV_LOG.md)에 기록한다.
- 학습 자료와 PoC 결과는 프로젝트 운영 문서와 분리한다.

## 패키지 관계

패키지 사이에 직접적인 기능 의존성을 만들지 않는다. 루트의 `pyproject.toml`,
검증 Harness와 문서 정책만 공통으로 사용한다. 공통 기능이 세 패키지 이상에서
실제로 반복될 때만 별도 패키지 추출을 검토한다.
