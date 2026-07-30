# Monorepo 구조 채택

## Status

Accepted

## Context

저장소는 `namuwiki_trend`와 `google_finance`를 포함하고 있으며, 루트에서 Python
의존성, 개발 도구와 검증 명령을 관리한다.

## Decision

독립 자동화 프로젝트를 하나의 `automation-hub` 모노레포에서 관리한다. 패키지별
기능과 모델은 독립적으로 유지하고, 공통 정책만 루트에서 관리한다.

## Consequences

- 환경 설정과 검증 절차를 공유할 수 있다.
- 패키지 간 기능 결합을 피해야 한다.
- 패키지가 늘어나면 패키지별 문서와 테스트 경계를 유지해야 한다.
