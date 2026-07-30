# google_finance

Google Finance 관련 자동화를 위한 독립 패키지다.

## 현재 구현 상태

- **Implemented**: `config.py`의 `Settings`와 프로젝트 로거
- **Implemented**: `models.py`의 `StockPrice`, `StockReport`
- **Not verified**: 실제 Google Finance endpoint, HTTP 방식, 응답 형식 또는 DOM 구조
- **Not implemented**: Collector, Parser, Pipeline, Storage, CLI, 운영 실행 흐름

## 다음 범위

향후 Sprint에서 실제 데이터 접근 방식을 확인한 뒤 수집 Provider, Model 변환 경계,
Fake 기반 테스트와 최소 Application 흐름을 설계한다.

상세 상태와 제안 구조는 [architecture.md](architecture.md)를 참고한다.
