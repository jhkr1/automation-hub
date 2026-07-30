# Flat Layout 채택

## Status

Accepted

## Context

현재 자동화 패키지는 작은 독립 모듈 집합이며, 저장소는 `src/`를 사용하지 않는
flat layout을 기준으로 개발한다.

## Decision

각 패키지의 Python 모듈을 패키지 디렉터리 바로 아래에 둔다. 현재 요구사항이 없는
`src/` 구조 전환과 깊은 하위 계층은 도입하지 않는다.

## Consequences

- import 경로와 초기 구조가 단순하다.
- 패키지가 커지면 모듈 경계를 다시 검토해야 한다.
- 외부 배포 요구가 생기면 layout 전환 비용을 별도로 평가해야 한다.
