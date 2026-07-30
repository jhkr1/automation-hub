# google_finance

Google Finance 관련 자동화를 위한 독립 패키지다.

## 현재 구현 상태

- **Implemented**: `config.py`의 `Settings`와 프로젝트 로거
- **Implemented**: `models.py`의 `StockPrice`, `StockReport`
- **Implemented**: Playwright 기반 단일 종목 Collector, 순수 추출·정규화 함수, Pipeline, CLI
- **Implemented**: 가격과 변동률은 `Decimal`, 수집 시각은 UTC-aware datetime으로 유지
- **Implemented**: Fake 기반 단위 테스트와 `AAPL:NASDAQ` 실제 CLI 검증
- **Not verified**: `en-US` 외 locale, 테스트하지 않은 거래소·종목의 DOM 차이, 장기적인 Google Finance selector 안정성
- **Not implemented**: 다중 종목 실행, Storage, Scheduler, DB·Excel 연동, LLM 분석

## 다음 범위

현재 CLI는 다음처럼 exchange-qualified symbol 하나를 받아 화면에 표시한다.

```bash
python -m google_finance.main AAPL:NASDAQ
```

현재 Collector와 parser는 검증된 영어 화면 계약에 따라 `en-US` locale만 허용한다.
Google Finance의 렌더링 DOM에서 수집한 문자열은 `extraction.py`에서 검증·정규화한 뒤
`StockPrice`로 변환한다. 내부 batchexecute/RPC 호출은 사용하지 않는다.

Google Finance 데이터의 지연·정확성·사용 제한과 selector 변경 위험은 별도로 검토해야 한다.

상세 상태와 제안 구조는 [architecture.md](architecture.md)를 참고한다.
