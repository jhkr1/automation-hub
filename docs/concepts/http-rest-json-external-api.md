# HTTP, REST API, JSON과 외부 API 경계

이 문서는 HTTP 용어 사전이 아니라, 외부 서버의 응답을 안전한 내부 Domain Model로
바꾸는 과정을 공부하는 교재다. 현재 구현은 `requests` 기반 API Provider를 사용하며,
브라우저 DOM 자동화나 범용 REST client를 구현하지 않는다.

## 1. 먼저 한 문장으로

Python 애플리케이션은 HTTP Request를 보내고 Response를 받은 뒤, 외부 JSON을 검증·정규화해
내부 계약으로 바꾼다.

## 2. Client, Server, Request, Response

Client는 요청을 시작하는 쪽이고 Server는 요청을 처리해 응답하는 쪽이다. 다음 한 줄은
“ODsay 서버에 경로를 요청한다”는 뜻이다.

```python
response = requests.get(
    "https://api.example.test/routes",
    params={"origin": "A", "destination": "B"},
    timeout=10,
)
```

Request에는 method, URL, headers, body가 들어갈 수 있고 Response에는 status code,
headers, body가 들어온다. HTTP는 평문 전송 규약이고 HTTPS는 TLS로 전송 구간을 보호한다.
HTTPS라고 해서 API key가 자동으로 안전해지는 것은 아니다. 로그·소스·문서에 key를 남기지
않는 별도 관리가 필요하다.

## 3. URL과 Endpoint

URL은 보통 다음처럼 구성된다.

```text
https://api.example.test/v1/routes?origin=A&limit=10
└scheme┘ └──── host ────┘└path┘└ query parameter ┘
```

Endpoint는 특정 작업을 제공하는 서버 주소다. 같은 host라도 path가 다르면 다른 API
계약일 수 있다. 현재 실제 endpoint는 `bus_monitor/odsay.py`의
`ODSAY_ROUTE_ENDPOINT`, `bus_monitor/gyeonggi.py`의 station/route/arrival/location
상수에서 확인한다. 문자열을 임의로 조합하지 않고 공식 문서와 코드의 endpoint를 함께 읽는다.

### Query parameter, path parameter, header, body

```python
requests.get(
    "https://api.example.test/stations/123",  # path parameter: 123
    params={"format": "json"},                # query parameter
    headers={"Accept": "application/json"},  # header
    timeout=10,
)
```

POST의 JSON body 예시는 다음과 같다.

```python
requests.post(
    "https://api.example.test/routes",
    json={"origin": "A", "destination": "B"},
    headers={"Content-Type": "application/json"},
    timeout=10,
)
```

`Content-Type`은 body의 형식이고 `Accept`는 받고 싶은 응답 형식이다. GET은 보통 조회,
POST는 생성/명령, PUT은 전체 교체, PATCH는 부분 변경, DELETE는 삭제에 사용된다. 하지만
method 이름만으로 외부 API의 실제 계약을 추측해서는 안 된다. 현재 Bus Monitor는 조회용
GET만 사용하며 PUT/PATCH/DELETE는 구현하지 않는다.

## 4. Status code

- 2xx: 서버가 요청을 성공적으로 처리함
- 4xx: 요청 형식, 인증, 권한, rate limit 등 client 측 수정이 필요한 경우가 많음
- 5xx: 서버 내부 또는 upstream 문제일 가능성이 큼

HTTP 성공과 업무 성공은 다르다. 200 응답이어도 JSON 안에 API `resultCode` 오류가 있을 수
있다. 반대로 404는 정상적인 빈 결과가 아니라 endpoint 또는 resource 문제일 수 있다.

## 5. JSON과 Python 자료형

JSON은 네트워크에서 객체와 배열을 표현하는 문자열 기반 교환 형식이다.

```json
{"routeId": "R1", "arrivals": [120, null]}
```

Python `dict`/`list`는 메모리 객체이고 JSON은 직렬화된 텍스트 또는 bytes다.

```python
import json

payload = {"routeId": "R1", "arrivals": [120, None]}
text = json.dumps(payload)       # serialization: Python → JSON text
again = json.loads(text)         # deserialization: JSON text → Python object
```

`response.json()`은 Response body를 JSON으로 역직렬화한다. 이것은 schema validation이
아니다. 외부 JSON을 내부에서 그대로 사용하면 필드 누락, `""`/`null`, 숫자 문자열,
list 대신 object 같은 변형이 Domain 코드까지 퍼진다.

## 6. Python requests의 실제 읽기

현재 Provider의 공통 흐름은 다음과 같다.

```python
response = client.get(endpoint, params=params, timeout=timeout)
response.raise_for_status()
payload = response.json()
```

- `params=`: query string을 library가 조립하고 encoding한다.
- `headers=`: 인증/협상 metadata를 전달한다. 현재 Gyeonggi 구현은 key를 query parameter로 전달한다.
- `timeout=`: 응답을 무한정 기다리지 않게 한다.
- `response`: status, headers, body를 가진 HTTP 결과다.
- `raise_for_status()`: 4xx/5xx를 `requests` 예외로 바꾼다.

네트워크 오류(timeout, DNS, connection reset)와 HTTP 오류(403, 500)는 요청이 서버에
도달했는지와 원인이 다르다. HTTP 200 뒤의 API-level `resultCode` 오류도 별도다. 현재
`OdsayRouteProvider`와 `GyeonggiProvider`는 이 세 층을 provider 전용 예외로 구분한다.

## 7. REST API의 의미

REST는 resource를 URI로 식별하고 HTTP method, representation, stateless 요청 등의 제약을
활용하는 설계 스타일이다. JSON을 반환한다고 REST가 되는 것은 아니다. JSON을 쓰는 RPC형
HTTP API도 있고, REST API가 JSON 이외의 representation을 반환할 수도 있다.

현재 프로젝트에서는 “REST 준수 여부”보다 공식 endpoint 계약과 Provider 경계가 중요하다.
ODsay route resource와 Gyeonggi station/arrival resource를 GET으로 조회하지만, 모든 REST
제약을 별도로 검증하거나 HATEOAS를 구현하지 않는다.

## 8. Authentication과 API Key

API key는 호출자를 식별하거나 quota를 적용하는 credential이다. 환경변수에서 읽고 request
parameter/header에 전달하되, 소스·fixture·로그·문서에는 원문을 기록하지 않는다.

현재 실제 설정은 `bus_monitor/config.py`의 `ODSAY_API_KEY`와 `GYEONGGI_SERVICE_KEY`다.
`BusMonitorSettings`가 값을 읽고 Provider 생성자가 주입받는다. key가 비어 있으면 Provider
전용 configuration error를 낸다. API key가 있다고 해서 권한, endpoint, quota가 자동으로
보장되는 것은 아니다.

## 9. URL Encoding과 Double Encoding

URL에는 공백이나 `+`, `%`처럼 특별한 의미를 가진 문자가 있다. `requests.get(...,
params=params)`는 query parameter를 URL에 맞게 percent-encoding한다. 따라서 이미 encoded된
key를 다시 encoded 상태로 넣으면 `%`가 `%25`가 되는 **double encoding**이 발생할 수 있다.

```text
원문 값        → library가 한 번 encoding → 서버가 기대하는 값
이미 % 포함 값 → %25로 재-encoding       → 다른 key로 해석될 수 있음
```

공공 API의 decoding/encoding key 선택은 해당 포털 계약을 확인해야 한다. 인증키를 직접
문자열 replace, `quote`, `unquote`로 “고쳐서” 전달하면 어떤 형태를 서버가 기대하는지
잃어버릴 수 있다. 현재 구현은 key 원문을 직접 출력하거나 수동 조작하지 않고 `params=`에
값을 전달한다. 403 진단 시에는 최종 URL에서 key를 마스킹한 뒤 `%25` 재인코딩 여부만
확인해야 한다.

## 10. External API Boundary

외부 response와 Domain Model은 서로 다른 계약이다.

```text
ODsay / Gyeonggi Server
        ↓ HTTP GET
JSON response
        ↓ parsing / validation / normalization
OdsayRouteProvider / GyeonggiProvider
        ↓
TransitRoute / RealtimeArrival
        ↓
BusMonitorPipeline
```

- Parsing: JSON의 envelope와 field 위치를 읽는다.
- Validation: 필수 field, 타입, 음수 ETA, 허용 result code를 확인한다.
- Normalization: provider별 이름과 숫자 표현을 하나의 내부 타입으로 통일한다.

Provider가 필요한 이유는 endpoint, key, timeout, response envelope, provider 예외를 한 곳에
가두기 위해서다. Pipeline이 HTTP `Response`나 `predictTimeSec1` 같은 provider field를 직접
알면 외부 API 변경이 application 전체 변경으로 번진다.

## 11. automation-hub 실제 사례

### ODsay

`OdsayRouteProvider.search_route()`는 좌표와 `apiKey`, `OPT`, `SearchType`을 query
parameter로 보내고, `response.raise_for_status()` 후 `result.path[0]`을 읽는다.
`totalTime`, `totalWalk`, `busTransitCount`, `startLocalStationID`, `busNo` 등을 검증해
`TransitRoute`, `BusLeg`, `BusLane`으로 바꾼다.

### Gyeonggi

`GyeonggiProvider._fetch_body()`는 `serviceKey`, `format=json`, `stationId` 또는
`routeId`를 query로 보낸다. `response.msgHeader.resultCode == "0"`을 확인한 뒤
`busStationInfo`, `busRouteList`, `busArrivalList`, `busLocationList`를 각각
`GyeonggiStation`, `GyeonggiStationRoute`, `RealtimeArrival`,
`GyeonggiVehicleLocation`으로 정규화한다.

### Pipeline

`bus_monitor/pipeline.py`의 `BusMonitorPipeline`은 Provider를 호출하지만 HTTP URL이나
JSON envelope를 알지 못한다. 이것이 외부 데이터 경계와 Application orchestration을 분리하는
핵심이다.

Google Finance도 같은 원칙으로 HTTP 수집과 Domain 변환을 분리하지만, 이번 문서는 Bus
Monitor를 주 사례로 삼는다.

## 12. 실제 코드를 읽는 순서

1. [`bus_monitor/config.py`](../../bus_monitor/config.py): 어떤 credential과 설정이 필요한가?
2. [`bus_monitor/odsay.py`](../../bus_monitor/odsay.py): endpoint, params, timeout, JSON path, 예외
3. [`bus_monitor/gyeonggi.py`](../../bus_monitor/gyeonggi.py): 공통 envelope, result code, list/object/empty 처리
4. [`bus_monitor/models.py`](../../bus_monitor/models.py): 외부 field가 어떤 내부 타입이 되는가?
5. [`bus_monitor/pipeline.py`](../../bus_monitor/pipeline.py): Provider 결과를 어떤 순서로 조합하는가?
6. [`tests/bus_monitor/`](../../tests/bus_monitor/): fake response로 성공·빈 결과·잘못된 JSON을 어떻게 검증하는가?

각 파일에서 “HTTP 세부사항이 어디에서 끝나는가?”와 “Domain invariant가 어디에서 시작하는가?”를
표시해 본다. 실제 API key나 전체 response를 테스트 fixture에 넣지 않는다.

## 13. 자주 헷갈리는 개념

- 200 OK ≠ 업무 성공: JSON 내부 result code와 필드 검증이 필요하다.
- JSON object ≠ Python dict: 직렬화/역직렬화 단계가 있다.
- REST ≠ JSON: REST는 설계 제약이고 JSON은 representation 형식이다.
- timeout ≠ API error: 응답 자체가 없었던 네트워크 실패와 서버 응답 오류는 다르다.
- API key 전달 ≠ 인증 성공: 권한·endpoint·encoding·quota도 맞아야 한다.
- Provider ≠ Pipeline: Provider는 외부 시스템을 감싸고 Pipeline은 업무 흐름을 조정한다.

## 14. 내가 30초 안에 설명한다면

“Provider가 `requests`로 공식 API에 GET을 보내 JSON을 받고, status와 provider result code,
필수 field를 검증한 뒤 `TransitRoute`나 `RealtimeArrival`로 바꿉니다. Pipeline은 HTTP나
JSON 구조를 몰라도 이 Domain Model만 조합합니다. API key는 환경변수에서 주입하고
`params=` encoding은 library에 맡겨 double encoding을 피합니다.”

## 15. 이해도 체크

1. `raise_for_status()`가 성공해도 왜 `resultCode`를 확인해야 하는가?
2. `params=`와 URL 문자열 직접 연결의 차이는 무엇인가?
3. JSON의 `null`, 빈 문자열, 누락 field를 같은 값으로 취급하면 어떤 문제가 생기는가?
4. `busArrivalList`가 list가 아니라 object 하나로 올 때 Provider가 정규화해야 하는 이유는?
5. Pipeline이 `response.json()`을 직접 호출하지 않도록 한 이유는?
6. 이미 `%`가 포함된 API key를 다시 encoding하면 왜 `%25`가 될 수 있는가?

## 다음 읽기

- [Provider와 외부 의존성](provider.md)
- [Pipeline, Provider and Storage](pipeline-provider-storage.md)
- [Python Data Contracts](python-data-contracts.md)
- [Web Crawling과 DOM](../learning/STUDY_NOTE.md#chapter-14-html-dom-view-source)
- [Web, DOM and Browser Automation](web-dom-browser-automation.md)
