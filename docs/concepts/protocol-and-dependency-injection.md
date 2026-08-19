# Protocol and Dependency Injection

## 1. 먼저 한 문장으로

Protocol은 “어떤 동작을 제공해야 하는가”를 표현하고, Dependency Injection은 그 동작을 제공하는 객체를 사용하는 쪽의 밖에서 전달하는 방법입니다.

## 2. 왜 필요한가?

다음 service는 생성될 때 실제 API 구현을 직접 만듭니다.

```python
class ReportService:
    def __init__(self):
        self.provider = RealApiProvider()

    def run(self):
        return self.provider.get_report()
```

이 코드는 당장 실행되지만 다음 문제가 있습니다.

- 테스트마다 실제 API를 호출하게 됩니다.
- 다른 Provider로 바꾸려면 service 내부를 수정해야 합니다.
- API key와 생성 방식이 업무 객체 안에 숨어 있습니다.

## 3. Interface란 무엇인가?

Interface는 구현 방법이 아니라 사용할 수 있는 동작의 계약입니다. Pipeline 입장에서는 “ODsay라는 회사의 객체인가?”보다 “경로를 조회할 수 있는가?”가 중요합니다.

일반적인 Python class로도 개념을 표현할 수 있습니다.

```python
class WeatherProvider:
    def get_weather(self, city: str) -> str:
        raise NotImplementedError
```

이 예제의 핵심은 구현 코드가 아니라 호출자가 기대하는 method와 반환 의미입니다.

## 4. Python Protocol

Python의 `Protocol`은 필요한 method와 type을 선언하는 방법입니다.

```python
from typing import Protocol


class WeatherProvider(Protocol):
    def get_weather(self, city: str) -> str:
        ...
```

Protocol을 명시적으로 상속하지 않은 class라도 같은 method를 제공하면 structural typing 관점에서 이 계약을 만족할 수 있습니다.

```python
class SimpleWeather:
    def get_weather(self, city: str) -> str:
        return f"{city}: sunny"


def show(provider: WeatherProvider) -> str:
    return provider.get_weather("Seoul")
```

Java interface와 완전히 같은 runtime mechanism이라고 단순화하면 안 됩니다. Python Protocol은 주로 type checker와 코드 독자에게 필요한 구조적 계약을 보여주며, 실제 runtime 검증은 별도 validation이나 테스트의 책임입니다.

## 5. Dependency란 무엇인가?

Dependency는 한 객체가 일을 수행하기 위해 알고 있거나 사용하는 다른 객체입니다.

```python
class ReportService:
    def __init__(self, provider: WeatherProvider):
        self.provider = provider
```

여기서 `ReportService`는 `WeatherProvider`가 제공하는 동작에 의존합니다. 중요한 점은 `RealApiProvider`라는 구체 class를 직접 생성하지 않고, 필요한 계약만 받는다는 것입니다.

## 6. Dependency Injection

Before:

```python
class ReportService:
    def __init__(self):
        self.provider = RealApiProvider()
```

After:

```python
class ReportService:
    def __init__(self, provider: WeatherProvider):
        self.provider = provider


provider = RealApiProvider()
service = ReportService(provider)
```

구체 구현을 만드는 쪽과 사용하는 쪽을 분리하고, 생성한 객체를 생성자 인자로 전달하는 것이 Constructor Injection입니다.

DI는 framework 이름이 아닙니다. 거대한 DI Container 없이도 생성자 호출만으로 구현할 수 있습니다.

## 7. Dependency Inversion

Dependency Inversion은 상위 정책이 하위 기술의 구체 구현에 직접 묶이지 않도록 의존 방향을 바꾸는 관점입니다.

Pipeline이 원하는 것은 “경로를 조회할 수 있는 객체”입니다. 따라서 Pipeline이 ODsay의 URL·SDK·응답 field를 직접 알아야 할 필요는 없습니다. `RouteProvider`라는 계약에 의존하고, ODsay는 그 계약을 구현하는 쪽에 둡니다.

DIP는 원칙이고 DI는 그 원칙을 실현하는 방법 중 하나입니다. 둘을 같은 말로 사용하지 않습니다.

## 8. Composition Root

그렇다면 실제 구현체는 누가 만들고 연결할까요? 실행을 시작하는 경계, 즉 Composition Root가 담당합니다.

현재 Bus Monitor에서는 `bus_monitor/main.py`의 실제 함수가 이 역할을 합니다.

```python
def build_pipeline(settings: BusMonitorSettings | None = None) -> BusMonitorPipeline:
    configured_settings = settings or BusMonitorSettings()
    return BusMonitorPipeline(
        route_provider=OdsayRouteProvider(api_key=configured_settings.odsay_api_key),
        realtime_provider=GyeonggiProvider(
            service_key=configured_settings.gyeonggi_service_key
        ),
    )
```

`main.py`는 설정을 읽고 `OdsayRouteProvider`, `GyeonggiProvider`를 생성해 `BusMonitorPipeline`의 생성자에 전달합니다. Pipeline은 어떤 API key를 읽거나 Provider를 새로 만들지 않습니다.

## 9. automation-hub에서는?

Bus Monitor의 계약과 구현은 다음처럼 대응합니다.

```text
RouteProvider Protocol      ← OdsayRouteProvider
RealtimeProvider Protocol   ← GyeonggiProvider
BusMonitorPipeline          ← 두 Provider를 생성자로 주입받음
main.build_pipeline()       ← production 구현체를 조립
```

`bus_monitor/pipeline.py`의 `RouteProvider`는 `search_route()`를, `RealtimeProvider`는 `get_station_routes()`와 `get_arrivals()`를 요구합니다. 테스트는 이 method를 제공하는 작은 Fake를 주입할 수 있습니다.

다른 package에도 Protocol이 실제로 있습니다. `namuwiki_trend/pipeline.py`의 `TrendEnricherProtocol`, `namuwiki_trend/enricher.py`의 `NewsProvider`와 `ReasonGenerator`, `google_finance/analysis_application.py`의 `StockNewsProvider`와 Generator 계약이 예입니다. 모든 협력자에 Protocol을 만든 것이 아니라 교체·테스트 경계가 필요한 곳에 사용했습니다.

## 10. 장점과 단점

| 선택 | 장점 | 단점 |
|---|---|---|
| 직접 생성 | 작은 코드에서 단순함 | 교체·테스트가 어려움 |
| Constructor Injection | 의존성이 명시되고 Fake 주입이 쉬움 | 생성자 인자가 늘 수 있음 |
| Protocol | 필요한 동작과 type을 문서화함 | 계약과 실제 구현을 함께 관리해야 함 |
| DI Container | 복잡한 조립을 자동화할 수 있음 | 생성 위치 추적이 어려워질 수 있음 |

## 11. 언제 쓰지 않아도 되는가?

한 함수에서만 사용하는 순수 formatter나 단순 값 객체까지 Protocol로 만들 필요는 없습니다. 외부 API, DB, 시계처럼 교체·격리할 이유가 있는 dependency부터 경계를 검토합니다.

## 12. 자주 헷갈리는 개념

- **Interface vs Protocol**: Interface는 일반 설계 개념이고, Protocol은 Python에서 그 구조적 계약을 표현하는 도구입니다.
- **DIP vs DI**: DIP는 의존 방향의 원칙, DI는 구현체를 외부에서 전달하는 방법입니다.
- **DI vs DI framework**: DI는 생성자 인자만으로도 가능하며 framework는 선택 사항입니다.
- **Composition Root vs Application Service**: Composition Root는 객체를 만들고 연결하며, Application은 이미 연결된 객체로 업무 흐름을 실행합니다.

## 13. 내가 설명해본다면

“Pipeline은 ODsay라는 이름이 아니라 경로 조회 계약에 의존합니다. `RouteProvider` Protocol은 필요한 method를 표현하고, `main.build_pipeline()`이 실제 ODsay와 Gyeonggi 구현체를 만들어 생성자로 주입합니다. 그래서 테스트에서는 같은 method를 가진 Fake를 넣을 수 있고, API 구현이 바뀌어도 Pipeline의 업무 흐름은 그대로 둘 수 있습니다.”

## 14. 이해도 체크

1. `ReportService`가 `RealApiProvider()`를 내부에서 생성하면 테스트가 어려워지는 이유는 무엇인가요?
2. Protocol이 없어도 Python이 실행되는데 Protocol을 작성하는 이유는 무엇인가요?
3. `BusMonitorPipeline`이 API key를 직접 읽지 않아야 하는 이유는 무엇인가요?
4. `main.build_pipeline()`과 `BusMonitorPipeline.__init__()`의 책임은 어떻게 다른가요?
5. 모든 class에 Protocol을 추가하면 왜 오히려 복잡해질 수 있나요?

## 다음 읽기

[Pipeline, Provider and Storage](pipeline-provider-storage.md)에서 주입된 구성요소가 실제 Use Case 흐름에서 어떤 역할을 하는지 읽습니다.

Protocol 자체의 세부 설명은 [Dependency Injection](dependency-injection.md)과
[Composition Root](composition-root.md)를 기준 문서로 사용합니다. 이 문서는 두 개념을
Bus Monitor의 실제 `main.py` wiring과 연결하는 보충 안내서입니다.
