# google_finance 아키텍처

## 현재 상태

- **Implemented**: `config.py`는 `GEMINI_API_KEY`, `STOCK_SYMBOLS`, `LOG_LEVEL` 설정과
  로거를 정의한다.
- **Implemented**: `StockPrice`는 종목 시세 데이터 계약을, `StockReport`는 시세와 reason을
  묶는 결과 계약을 정의한다.
- **Not implemented**: 외부 수집, 파싱, Pipeline, Storage와 CLI는 존재하지 않는다.
- **Not verified**: Google Finance의 URL, endpoint, payload, headers, DOM selector와 응답 형식.

## 제안 상태

- **Proposed**: 외부 접근을 Provider 또는 Collector 경계에 둔다.
- **Proposed**: 원시 응답 파싱과 Model 변환을 Application 흐름에서 분리한다.
- **Proposed**: 종목 순회와 결과 순서 보존은 Application Pipeline이 담당한다.
- **Proposed**: 테스트에서는 Fake Provider를 주입하고 외부 네트워크를 호출하지 않는다.

위 제안은 공통 아키텍처 원칙에 따른 방향이며, 실제 수집 방식이 확인되기 전의 구현 확정이 아니다.
