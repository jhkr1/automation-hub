# Bus Monitor 기술 선택과 의사결정

이 문서는 현재 production MVP에서 실제로 사용되는 Bus Monitor의 선택 근거를 기록합니다.
일반적인 ADR 형식 대신 각 결정의 Context, Decision, Reason, Trade-off만 간단히 남깁니다.

## 1. 지도 UI가 아닌 공식 API 사용

### Context

기존 RPA는 지도 화면에 출발지·목적지를 입력하고 Recorder로 표시값을 읽었습니다. 화면 UI와
DOM selector는 변경될 수 있고 headless browser 운영에는 로그인·동적 렌더링·대기시간 문제가
따릅니다.

### Decision

현재 MVP는 Naver 지도 UI, Playwright, Selenium을 사용하지 않고 Route Planning과 realtime을
공식 API로 분리합니다.

### Reason

API 응답은 Python Provider에서 정규화하고 Fake HTTP client로 테스트할 수 있습니다. cron에서
browser runtime과 selector 유지보수를 피할 수 있습니다.

### Trade-off

지도 화면이 보여주는 모든 추천·표시 정보를 동일하게 재현하지 않습니다. Provider가 제공하는
필드와 지역 coverage 안에서만 기능을 구성합니다.

## 2. Route Planning은 ODsay

### Context

출발·도착 WGS84 좌표에서 버스 후보, 승·하차 정류장, 이동시간을 얻어야 했습니다.

### Decision

`bus_monitor/odsay.py`가 ODsay 대중교통 길찾기 API의 첫 유효 route option과 첫 bus leg를
정규화합니다.

### Reason

live PoC에서 대상 통근 경로의 버스 후보, `startLocalStationID`, `endLocalStationID`,
`busLocalBlID`와 시간 정보를 실제로 확보했습니다. 이 값은 realtime Provider에 전달할
정류장·노선 후보를 제공합니다.

### Trade-off

현재 Pipeline은 여러 route option이나 이후 bus leg를 비교하지 않습니다. ODsay가 반환한 첫
option의 첫 버스 구간만 MVP 범위입니다.

## 3. TAGO를 먼저 조사했지만 production route enrichment에는 사용하지 않음

### Context

TAGO 버스정류소·도착정보 API는 좌표 기반 정류소 검색 후 `cityCode`와 `nodeId`로 실시간
도착정보를 조회할 수 있어, 전국 공공 realtime source 후보로 검토했습니다.

### Decision

TAGO PoC는 보존하되, 현재 production Pipeline의 route enrichment Provider로 사용하지
않습니다.

### Reason

TAGO Station → Arrival PoC에서는 ID 호환과 도착정보 조회가 성공했습니다. 그러나 ODsay가
선택한 경기도 노선과 TAGO의 도시별 경유노선 catalog를 연결하는 live 검증에서 신뢰할 수 있는
cross-provider route association을 확보하지 못했습니다.

### Trade-off

TAGO는 독립적인 정류장 monitoring 조사 결과로는 남아 있지만, 현재 통근 route의 실시간
enrichment 범위는 경기도 API coverage에 한정됩니다.

## 4. ODsay와 경기도 공식 API를 직접 결합

### Context

ODsay route의 승차 정류장과 노선 후보에 대해, 같은 지역 BIS가 제공하는 실시간 정보를
안정적으로 결합해야 했습니다.

### Decision

ODsay `startLocalStationID`를 경기도 API `stationId`로 그대로 전달하고, 경기도
정류소별 경유노선의 `routeId`가 ODsay `busLocalBlID`와 정확히 일치하는 lane만 arrival과
결합합니다.

### Reason

조사 과정에서 ODsay의 경기도 실시간 버스정보 연동 안내가 `localStationID`를 경기도
`stationId`로 사용하는 방식을 제시하는 것을 확인했습니다. 이어 live 검증에서 ODsay
`localStationID=206000542`가 경기도 API `stationId=206000542`로 직접 조회됐고, ODsay
`busLocalBlID`와 해당 경기도 `routeId`의 direct match도 확인했습니다. 따라서 문자열 prefix,
노선번호만의 matching, 하드코딩 mapping table을 만들 필요가 없습니다.

### Trade-off

이 관계는 경기도 provider context에서 검증된 것입니다. 다른 지역에 같은 규칙을 일반화하지
않으며, 경기도 경유노선 API 호출이 실행당 한 번 추가됩니다.

## 5. Vehicle Location API는 MVP runtime에서 제외

### Context

경기도 Provider에는 노선별 차량 위치를 정규화하는 client가 있습니다. 하지만 현재 Dashboard가
필요로 하는 정보는 승차 정류장 기준 ETA, 남은 정거장, 좌석이며 현재 Pipeline에는 위치 기반
판단이나 지도 표시가 없습니다.

### Decision

MVP runtime은 station-route validation과 arrival API만 호출합니다. Vehicle Location API는
호출하지 않습니다.

### Reason

필요하지 않은 API 호출과 결과 해석을 추가하지 않고, 현재 사용자 화면과 저장 모델에 맞는
최소 데이터를 수집합니다.

### Trade-off

차량의 지도상 위치나 구간별 이동 추정은 현재 제공하지 않습니다.

## 6. normalized snapshot만 저장

### Context

Provider의 HTTP payload는 크고 형식이 바뀔 수 있으며, API key와 함께 보관하면 보안과
보존 범위가 불필요하게 커집니다.

### Decision

`BusRouteResult`의 normalized route, lane, realtime field만 MySQL에 저장합니다. raw JSON,
HTTP response, API key는 저장하지 않습니다.

### Reason

Dashboard와 운영 판단에는 이동시간, 정류장, candidate lane, ETA, 남은 정거장, 좌석 같은
정규화된 필드면 충분합니다. Provider adapter 책임과 persistence contract도 분리됩니다.

### Trade-off

새 provider field가 필요하면 Provider와 model을 명시적으로 확장해야 하며, 과거 raw payload를
나중에 재파싱할 수는 없습니다.

## 7. append-only snapshot

### Context

버스 ETA와 좌석은 수집 시점마다 변합니다. 최신 값만 update하면 통근 시간대의 변화와 부분
실패 이력을 잃습니다.

### Decision

target별 실행마다 `bus_route_snapshots` parent row를 추가하고 lane과 realtime child row를 같은
transaction으로 append합니다.

### Reason

한 realtime 차량은 한 `bus_realtime_snapshots` row이므로 여러 차량의 ETA/좌석을 보존합니다.
Dashboard는 이력에서 가장 빠른 차량을 표시용 대표값으로 선택할 수 있고, 원본 snapshot은 남습니다.

### Trade-off

저장량은 시간이 지날수록 증가합니다. retention·aggregation은 아직 MVP 범위가 아니므로
운영자가 보존 정책을 별도로 정해야 합니다.
