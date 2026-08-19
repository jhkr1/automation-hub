# Software Design Foundations

## 1. 먼저 한 문장으로

소프트웨어 설계는 파일을 많이 만드는 일이 아니라, 서로 다른 이유로 바뀌는 책임과 경계를 코드에 드러내는 일입니다.

## 2. 왜 필요한가?

처음에는 다음과 같은 함수도 충분해 보입니다.

```python
def run():
    response = requests.get("https://example.test/data")
    data = response.json()
    if data["value"] > 10:
        result = "high"
    connection = make_connection()
    connection.execute("INSERT ...", result)
    print(result)
```

이 코드가 20줄일 때는 한 번에 읽을 수 있습니다. 하지만 200줄, 2,000줄이 되면 API 응답 형식 변경, 업무 판단 변경, DB 변경, 출력 변경이 하나의 함수에 얽힙니다. 테스트도 실제 네트워크와 DB 없이는 실행하기 어려워집니다.

설계는 이 문제를 “현재 코드를 몇 개의 파일로 나눌까?”가 아니라 “무엇이 어떤 이유로 바뀌는가?”라는 질문으로 다시 보는 데서 시작합니다.

## 3. 책임(Responsibility)

책임은 객체나 module이 담당해야 하는 의미 있는 변경 이유입니다. “class 하나에는 책임 하나”라는 문장을 기계적으로 적용하기보다, 한 class를 수정하는 이유가 서로 독립적인지 살펴보는 편이 정확합니다.

예를 들어 외부 API의 URL 변경과 버스 도착 결과의 상태 판단 변경은 서로 다른 이유입니다. 같은 class가 둘 다 직접 담당하면 한 변경이 다른 변경의 테스트와 배포까지 흔듭니다.

## 4. Separation of Concerns

관심사 분리는 서로 다른 문제를 서로 다른 경계에서 다루는 것입니다.

```text
외부 API 호출       → Provider
응답 해석·정규화    → Provider / Model 변환
업무 흐름 조정      → Pipeline
업무 상태·값        → Domain Model
저장                → Storage
화면 출력           → CLI / Dashboard
```

관심사를 나눈다고 모든 함수가 작아지는 것은 아닙니다. 중요한 것은 각 경계가 무엇을 알고 무엇을 모르는지 설명할 수 있는가입니다.

## 5. Coupling과 Cohesion

Coupling(결합도)은 한 부분의 변경이 다른 부분에 얼마나 강하게 전파되는지를 보는 관점입니다. A를 고쳤는데 B, C, D의 내부 코드까지 함께 고쳐야 한다면 결합도가 높은 구조일 가능성이 있습니다.

Cohesion(응집도)은 한 module 안의 작업들이 같은 목적에 얼마나 모여 있는지를 보는 관점입니다. API 요청과 DB 저장을 `utils.py` 하나에 넣으면 파일은 하나지만 응집도는 낮을 수 있습니다. 반대로 route 조회에 필요한 Provider 코드를 가까이 두면 응집도가 높습니다.

### 파일 분리와 책임 분리는 다릅니다

```text
api.py
database.py
utils.py
```

라는 이름만으로 좋은 구조가 되지 않습니다. `database.py`가 `api.py`의 전역 상태와 내부 함수 이름을 모두 알아야 한다면 실제 결합은 여전히 높습니다. 경계는 파일명보다 입력·출력 계약과 의존 방향으로 판단해야 합니다.

## 6. abstraction과 boundary

Abstraction은 불필요한 세부사항을 숨기고 현재 사용자가 필요한 의미만 드러내는 것입니다. Boundary는 서로 다른 책임·기술·변경 이유가 만나는 지점입니다.

`BusMonitorPipeline`은 “ODsay HTTP 요청의 URL이 무엇인가”가 아니라 “경로를 조회할 수 있다”는 의미가 필요합니다. `RouteProvider` Protocol이 그 boundary를 표현합니다.

추상화는 많을수록 좋은 것이 아닙니다. 실제로 교체·검증·변경 분리가 필요할 때만 경계를 추가해야 합니다. 작은 script의 단일 계산 함수에 여러 interface를 만드는 것은 비용만 늘릴 수 있습니다.

## 7. automation-hub에서는?

Bus Monitor의 실제 구조는 다음처럼 책임이 나뉩니다.

```text
bus_monitor/main.py
  → 설정과 구체 구현체 조립
bus_monitor/odsay.py, gyeonggi.py
  → 외부 Provider 통신과 응답 정규화
bus_monitor/pipeline.py
  → route → station route → arrival 순서 조정
bus_monitor/models.py
  → TransitRoute, RealtimeArrival, 상태 Enum
bus_monitor/storage.py
  → target과 BusRouteResult snapshot 저장
```

Google Finance도 `main.py`, `pipeline.py`, `storage.py`, `models.py`로 경계를 나누지만, 수집·분석·Watchlist 흐름은 Bus Monitor와 다릅니다. Namuwiki는 `collector.py`, `extraction.py`, `enricher.py`, `pipeline.py`를 중심으로 구성됩니다. 세 package가 같은 pattern 이름을 복사해야 한다는 뜻이 아니라, 각 package의 변경 이유에 맞는 경계를 선택했다는 뜻입니다.

## 8. 장점과 단점

| 선택 | 장점 | 단점 |
|---|---|---|
| 책임을 분리함 | 변경 영향과 실패 위치가 선명함 | 계약·변환 코드가 늘어남 |
| 결합을 낮춤 | 구현 교체와 테스트가 쉬움 | 호출 경계를 설계해야 함 |
| 응집도 높은 module | 한 목적을 읽기 쉬움 | 너무 작게 나누면 탐색 비용이 생김 |
| 추상화·boundary 추가 | 세부사항을 숨기고 교체 가능 | 실제 필요가 없으면 복잡성만 증가 |

## 9. 언제 쓰지 않아도 되는가?

일회성 script, 한 번만 실행하는 변환, 외부 경계가 없는 짧은 계산은 한 module이나 함수로 충분할 수 있습니다. 기능이 늘어나고 외부 시스템·저장·여러 실행 방식이 생길 때 분리를 검토합니다.

## 10. 자주 헷갈리는 개념

- 파일을 나눈 것과 책임을 나눈 것은 다릅니다.
- 추상화와 무조건적인 interface 생성은 다릅니다.
- 낮은 결합도만으로 좋은 구조가 되는 것은 아니며, 각 module의 응집도도 봐야 합니다.
- Domain Model은 모든 흐름을 조정하는 객체가 아닙니다.
- SOLID 원칙의 이름을 적용하는 것보다 실제 변경 이유와 테스트 경계가 먼저입니다.

## 11. 내가 설명해본다면

“automation-hub는 기능을 파일 수에 맞춰 나눈 것이 아니라 변경 이유에 맞춰 나눴습니다. API가 바뀌면 Provider를, 실행 순서가 바뀌면 Pipeline을, 저장 schema가 바뀌면 Storage를 주로 수정합니다. 각 경계가 내부 세부사항 대신 작은 계약을 사용하므로 실제 API 없이도 상위 흐름을 테스트할 수 있습니다. 다만 작은 script에 이런 구조를 강제로 적용하지는 않습니다.”

## 12. 이해도 체크

1. API 호출과 DB 저장을 한 함수에 넣었을 때 각각 어떤 이유로 변경될 수 있나요?
2. `api.py`, `database.py`, `utils.py`로 나누었는데도 책임 분리가 아닐 수 있는 이유는 무엇인가요?
3. 결합도와 응집도는 각각 어떤 질문에 답하나요?
4. 작은 script에 interface와 여러 계층을 추가하지 않아도 되는 기준은 무엇인가요?
5. `BusMonitorPipeline`이 외부 Provider의 URL을 직접 알면 어떤 변경이 전파될까요?

## 다음 읽기

[Protocol and Dependency Injection](protocol-and-dependency-injection.md)에서 책임 경계에 필요한 계약과 의존성 주입을 읽습니다.

개별 개념을 더 자세히 읽으려면 [Application Service](application-service.md),
[Domain Model](domain-model.md), [Pipeline and Orchestration](pipeline-and-orchestration.md)을
함께 참고합니다. 이 문서는 세 문서의 내용을 복사하지 않고 변경 이유와 전체 연결을 보여주는
입문 경로입니다.
