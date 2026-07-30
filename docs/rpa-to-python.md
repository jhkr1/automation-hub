# RPA에서 Python 자동화로 전환하는 절차

이 문서는 기존 RPA 업무를 Python 프로젝트로 옮길 때 사용하는 분석 순서다.

1. 기존 TaskBot의 입력, 출력, 외부 시스템과 예외 흐름을 기록한다.
2. 자동화의 성공 조건과 데이터 계약을 정의한다.
3. UI 조작이 필요한지, 확인된 API나 정적 HTTP로 대체할 수 있는지 검토한다.
4. 브라우저·HTTP·DOM·파일·DB 중 실제 Evidence가 있는 방식을 선택한다.
5. 외부 시스템에서 읽은 원시 데이터를 순수 Parser와 Model 경계로 넘긴다.
6. Collector/Provider, Application Pipeline, Storage의 책임을 분리한다.
7. 빈 응답, 잘못된 응답, timeout과 부분 실패 정책을 결정한다.
8. Fake Provider와 fixture를 사용해 외부 시스템 없는 테스트를 작성한다.
9. CLI 또는 Scheduler는 Composition Root에서 연결한다.
10. Live 검증은 단위 테스트와 별도로 수행하고, 확인한 사실과 미확인 범위를 기록한다.

구체적인 selector, endpoint, payload는 실제 시스템을 확인하기 전까지 확정하지 않는다.
