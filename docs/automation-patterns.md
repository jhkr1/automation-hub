# Automation Anywhere와 Python 자동화 패턴

아래 대응은 개념적 유사성을 설명할 뿐, 두 기술이 동일하다는 뜻은 아니다.
실제 저장소에서 확인된 사례와 일반적인 대응을 구분한다.

| Automation Anywhere | Python 프로젝트의 대응 | 차이와 주의점 |
|---|---|---|
| Recorder | Playwright 또는 명시적 Provider 코드 | 기록 결과를 그대로 운영 코드로 간주하지 않는다. |
| Object Cloning / XPath | Locator와 DOM 경계 검증 | selector는 실제 DOM 확인 후 확정한다. |
| Click Action | `locator.click()` 또는 HTTP 호출 | UI 조작이 정말 필요한지 먼저 판단한다. |
| Get Property / Capture | `text_content()`, `get_attribute()` 또는 parser | 반환값을 Model 계약으로 변환한다. |
| Variable | Python 변수 | 타입과 생명주기를 코드로 확인한다. |
| List / Loop | `list` / `for` | 순서 보존과 빈 입력 정책을 테스트한다. |
| If | `if`와 명시적 검증 함수 | 실패를 조용히 무시하지 않는다. |
| Error Handler | 예외 타입과 Application 경계 | 모든 예외를 일괄 retry하지 않는다. |
| Subtask / TaskBot | 함수·모듈·패키지 | 책임과 의존성 방향을 명확히 한다. |
| Credential Vault | 환경변수 또는 Secret 관리 | 키와 개인정보를 로그에 남기지 않는다. |
| Log to File | Python logging 또는 실행 Wrapper | 구조와 운영 경계를 문서화한다. |
| Scheduler | cron 또는 외부 Scheduler | 패키지 Application과 스케줄러를 분리한다. |

`namuwiki_trend`와 `google_finance`에는 Playwright Collector, 분리된 변환 단계와 내부 Model을
두는 사례가 확인되어 있다. 반면 Bus Monitor production은 지도 UI를 읽지 않고 ODsay와 경기도
공식 API Provider를 사용한다. 따라서 이 표의 UI 자동화 대응은 모든 Package의 구현 방식을
의미하지 않으며, 실제 Provider 선택은 Package별 문서를 기준으로 확인한다.
