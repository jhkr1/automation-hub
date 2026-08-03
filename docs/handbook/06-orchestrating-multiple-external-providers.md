# Chapter 6. 여러 외부 서비스를 하나의 검증 가능한 자동화 파이프라인으로 연결하기

Google Finance에서는 저장된 두 가격을 비교하고, 그 결과를 Persistence와 연결하는 문제를 살펴보았습니다. 그때는 하나의 자동화 안에서 Business Rule과 데이터베이스의 경계를 어떻게 지킬지가 중심이었습니다.

이번에는 같은 원칙을 다른 종류의 문제에 적용합니다. `namuwiki_trend`는 브라우저에서 검색어를 가져온 뒤 뉴스 RSS를 조회하고, Gemini로 설명을 만든 다음 JSON 파일에 저장합니다. Google Finance와 Namuwiki는 같은 구조를 복사한 두 프로젝트가 아닙니다. 전자가 내부 규칙과 저장 경계를 보여준다면, 후자는 서로 다른 실패 방식과 데이터 형식을 가진 외부 Provider를 하나의 실행 흐름으로 조정하는 사례입니다.

이번 Chapter의 질문은 다음과 같습니다.

> 실패 방식과 데이터 형식이 서로 다른 Browser, News Provider, LLM, Storage를 어떻게 하나의 검증 가능한 실행 흐름으로 조정할 것인가?

## 화면을 읽는 일에서 결과를 저장하는 일까지

처음에는 나무위키에서 Top 10을 읽어 오면 자동화가 끝난다고 생각하기 쉽습니다. 그러나 운영 흐름에는 서로 다른 종류의 작업이 이어집니다. 브라우저는 JavaScript가 실행된 뒤의 DOM을 제공하고, 추출 단계는 목록의 순위와 항목 수를 확인합니다. 뉴스 Provider는 RSS XML을 반환하고, Gemini는 텍스트를 생성합니다. 마지막으로 Storage는 이 결과를 JSON 구조로 바꾸어 파일에 기록합니다.

이 단계들은 모두 “외부에서 값을 가져온다”는 한 문장으로 묶기 어렵습니다. 브라우저 연결 실패는 페이지를 읽지 못한 문제이고, RSS 파싱 실패는 응답 형식을 이해하지 못한 문제입니다. Gemini의 응답은 요청이 성공해도 비어 있거나 계약을 벗어날 수 있고, 파일 저장은 디렉터리나 파일 시스템의 실패를 가질 수 있습니다. 실패 이유가 다른 작업을 한 함수 안에 넣으면 어느 단계가 문제였는지 드러내기 어렵습니다.

`namuwiki_trend.main`의 production flow는 이 작업을 하나의 긴 함수로 구현하지 않습니다.

```text
Namuwiki rendered page
    ↓
collect_trends()
    ↓
list[TrendItem]
    ↓
TrendPipeline
    ↓
TrendEnricher
    ├─ NewsContextProvider → list[NewsArticle]
    └─ GeminiReasonGenerator → reason
    ↓
list[TrendInsight]
    ↓
JsonTrendInsightStorage
    ↓
output/trend_insights.json
```

이 흐름에서 `main.py`는 운영용 Collector, Provider, Enricher, Pipeline, Storage를 조립합니다. 여기서 Provider는 뉴스나 Gemini처럼 하나의 외부 서비스를 감싸는 구현을 뜻합니다. 실제 실행은 `python -m namuwiki_trend.main`에서 시작하고, 성공하면 기본 경로인 `output/trend_insights.json`에 결과를 저장합니다. Snapshot 수집이나 Daily Trend 조회를 위한 별도 실행 흐름도 Repository에 있지만, 이 Chapter의 중심은 `main.py`에서 시작하는 위 production flow입니다.

## 다음 단계로 넘길 내부 데이터

Provider의 원시 응답을 그대로 다음 Provider에 전달하지 않는 이유는 데이터의 의미와 검증 위치를 고정하기 위해서입니다. Collector는 브라우저의 DOM을 직접 반환하지 않고 `list[TrendItem]`을 반환합니다. `TrendItem`은 `rank`, `keyword`, `href`를 가지며, 순위 정보가 사라지지 않았다는 것을 다음 단계가 전제로 삼을 수 있습니다.

Collector는 Playwright로 원시 항목을 읽고, Extraction은 이를 검증된 `TrendItem`으로 바꿉니다. 따라서 Pipeline이나 Enricher는 DOM selector와 목록 끝 표시 값을 알 필요가 없습니다. 외부 화면의 표현 방식이 뉴스 검색이나 JSON 저장 코드까지 퍼지지 않는 것이 이 경계의 목적입니다.

뉴스 단계의 출력도 내부 모델로 바뀝니다. `NewsContextProvider`는 Google News RSS의 XML을 파싱하여 `NewsArticle` 목록을 반환합니다. 제목, URL, 출처, 게시 시각을 가진 이 모델을 사용하면 Gemini Generator는 RSS XML의 태그 구조나 HTTP 응답을 알지 않아도 됩니다. Provider는 하나의 검색 결과 안에서 원본 URL이 중복된 기사를 제거하지만, 서로 다른 keyword 사이의 전역 URL deduplication은 적용하지 않습니다.

이런 변환은 파일 수를 늘리기 위한 장식이 아닙니다. 외부 응답이 내부 계약으로 바뀌어야 다음 단계가 무엇을 신뢰할 수 있는지 결정할 수 있습니다. 두 모델을 바로 문자열이나 딕셔너리로 바꾸면 필드가 누락되거나 순서가 바뀌어도 호출자가 알아채기 어려워집니다.

## Pipeline보다 중요한 조정 책임

`TrendPipeline`은 Collector가 반환한 목록을 입력 순서대로 순회하고, 각 항목을 `TrendEnricher`에 전달합니다. Pipeline은 DOM selector를 해석하지 않고, RSS를 파싱하지 않으며, Gemini Prompt나 JSON serialization을 구현하지 않습니다. Pipeline의 역할은 실행 순서와 단계 사이의 데이터 전달을 한곳에서 설명 가능하게 만드는 것입니다.

이 구조에서 더 중요한 판단은 `TrendEnricher`에 있습니다. Enricher는 단순히 뉴스와 LLM을 차례로 호출하는 클래스가 아닙니다. 하나의 `TrendItem`에 대해 뉴스가 있는지 확인하고, 뉴스가 있을 때만 Generator를 호출하며, 그 결과를 `TrendInsight`로 결합하는 Application 경계입니다.

```text
TrendItem
    ↓ keyword
NewsContextProvider.search()
    ↓ list[NewsArticle]
뉴스 있음 ────────→ GeminiReasonGenerator.generate_reason() ─→ reason ─┐
뉴스 없음 ────────→ 근거 부족 reason ────────────────────────────────┘
                                                               ↓
                                                          TrendInsight
```

`TrendInsight`는 `TrendItem`, reason, 뉴스 기사 tuple을 묶은 최종 내부 결과입니다. Enricher는 Generator가 반환한 값이 문자열인지, 비어 있지 않은지, 최대 길이를 넘지 않는지도 확인합니다. 이 검증이 끝난 뒤에야 Pipeline의 다음 결과 목록에 들어갑니다. Generator가 자유롭게 만든 텍스트를 바로 파일에 저장하지 않는 이유도 여기에 있습니다.

## 뉴스가 없을 때도 하나의 정책이 필요합니다

뉴스 검색 결과가 0건인 경우는 Provider 오류와 다릅니다. HTTP 요청이 실패했거나 RSS XML을 파싱하지 못한 것이 아니라, 해당 검색어에 대해 현재 사용 가능한 뉴스 문맥이 없다는 정상적인 결과입니다.

현재 `TrendEnricher`는 이 상태에서 Gemini를 호출하지 않고 근거 부족 문장을 사용합니다. 이 결정에는 두 가지 이유가 있습니다. 첫째, Generator에 전달할 근거가 없으므로 호출해도 검증 가능한 설명을 만들 수 없습니다. 둘째, 근거 없이 모델에 생성을 맡기면 검색어의 인기 이유를 추측할 가능성이 커집니다. 따라서 “뉴스가 없다”는 내부 상태와 “뉴스 Provider가 실패했다”는 예외를 같은 결과로 만들지 않습니다.

반대로 뉴스 Provider가 네트워크 오류를 내거나 RSS 응답을 파싱하지 못하면 현재 production flow는 그 예외를 Enricher 밖으로 전달합니다. Gemini 인증·응답 검증 실패도 마찬가지입니다. 이 Chapter에서는 이 실패들을 어떻게 운영 상태와 종료 코드로 세분화할지는 결정하지 않습니다. 중요한 점은 정상적인 근거 부족과 외부 시스템 오류가 이미 서로 다른 경계를 가진다는 사실입니다.

## LLM을 판단 주체가 아닌 제한된 Provider로 다루기

Gemini가 하는 일은 제공된 뉴스 문맥을 짧은 reason으로 요약하는 것입니다. 시스템이 코드로 판단해야 하는 것은 뉴스 목록의 존재, 입력 모델의 유효성, 순위와 데이터 형식, 그리고 Generator를 호출할지 여부입니다. 모델에게 검색어의 진실을 판정하거나 뉴스에 없는 사실을 보완하도록 맡기지 않습니다.

Prompt는 Generator가 제공된 뉴스만 사용하도록 범위를 제한합니다. 상충하는 보도를 한쪽의 사실로 확정하지 않고, 근거가 부족하면 보수적으로 응답하게 하는 정도의 규칙만 전달합니다. 호출 여부와 입력 데이터의 유효성, 결과 길이와 형식은 LLM이 아니라 Application이 판단합니다.

이것은 Prompt 문구를 잘 쓰면 모든 오류가 해결된다는 뜻이 아닙니다. Generator는 여전히 외부 Provider이고, 응답 형식과 길이를 애플리케이션이 검증해야 합니다. OpenAI Generator도 Repository에 있지만, `namuwiki_trend.main`의 production 조립에는 Gemini Generator가 사용됩니다. Provider Protocol을 통해 이 경계를 주입할 수 있다는 점과 실제 운영 Provider가 무엇인지 구분해야 합니다.

## 실패를 어디까지 허용할 것인가

현재 `TrendPipeline.run()`은 Collector가 반환한 항목을 순차적으로 Enricher에 전달합니다. 리스트 생성 과정에서 한 항목의 Enricher 오류가 발생하면 전체 실행이 중단되고, `main.py`의 process boundary가 오류를 stderr로 출력하며 non-zero exit code를 반환합니다. 그 실행에서 일부 `TrendInsight`만 모아 정상 결과처럼 JSON에 저장하는 부분 성공 정책은 현재 production flow에 없습니다.

이 선택은 저장된 JSON이 Top 10 전체 결과라는 단순한 계약을 제공합니다. 그러나 한 검색어의 뉴스나 Gemini 문제가 전체 결과 저장을 막는 비용도 있습니다. 외부 Provider 장애의 영향 범위가 Top 10 전체로 커지는 것입니다. 부분 성공과 항목별 오류 보존은 가능한 후속 선택이지만, 현재 구현의 정책으로 설명하면 안 됩니다.

## 순차 실행과 외부 호출 비용

Top 10 항목은 Pipeline에서 입력 순서대로 처리됩니다. 각 항목은 뉴스 검색을 거친 뒤, 뉴스가 있으면 Gemini 호출까지 이어질 수 있습니다. 따라서 하나의 전체 실행은 최대 10개의 LLM 요청을 만들 수 있습니다. 순차 실행은 호출 순서와 실패한 항목을 추적하기 쉽지만, 외부 요청 시간이 누적되어 전체 실행은 길어집니다.

현재 구현은 병렬 실행을 사용하지 않습니다. Provider 호출 순서와 실패 경계를 단순하게 유지하기 위한 현재의 선택입니다. API quota와 순간적인 요청 제한의 세부 정책은 다음 운영 Chapter에서 다룰 문제입니다.

## JSON Storage까지 도달하는 계약

Pipeline이 반환하는 것은 `TrendInsight` 목록입니다. `JsonTrendInsightStorage`는 이 목록을 외부 파일 형식으로 명시적으로 변환합니다. 각 결과에는 `trend` 안에 rank, keyword, href가 들어가고, reason과 기사 목록도 별도 필드로 기록됩니다. 최상위 payload에는 실제 구현된 `schema_version`, 생성 시각, insights 목록이 포함됩니다.

저장기는 UTF-8 JSON을 만들고 부모 디렉터리를 생성합니다. 임시 파일에 기록한 뒤 대상 경로로 교체하는 방식으로 저장 중간 상태가 최종 파일로 남는 위험을 줄입니다. 입력 결과의 순서는 Pipeline의 순서대로 직렬화되므로 rank와 목록 순서를 외부 출력에서도 확인할 수 있습니다. 저장 과정에서 오류가 발생하면 `run_application()`을 통해 process boundary까지 전달되고, 정상적인 저장 완료 메시지는 출력되지 않습니다.

이 마지막 경계가 있기 때문에 “Gemini가 응답했다”와 “자동화 결과가 보관되었다”를 같은 사건으로 취급하지 않습니다. 내부 모델을 만들고 전체 Pipeline을 통과한 뒤 Storage 계약으로 변환해야 production 실행이 성공합니다. Repository 문서와 특정 시점의 실행 기록에는 `python -m namuwiki_trend.main`을 통해 Top 10 수집, 뉴스·Gemini enrichment, JSON 저장을 확인한 흐름이 기록되어 있습니다.

## 테스트 가능한 Provider 경계

현재 테스트는 Pipeline과 Enricher에 Fake Provider를 주입합니다. 이 구조는 Application 정책을 외부 네트워크와 분리해 확인할 수 있다는 의미를 가집니다. 구체적인 Fake·Integration·Live 검증 기준은 Chapter 8에서 다룹니다.

## 얻은 것과 감수한 것

여러 외부 서비스를 분리된 경계로 연결하면서 단계별 실패 위치를 설명할 수 있게 되었습니다. 브라우저의 원시 DOM은 `TrendItem`으로, RSS는 `NewsArticle`로, 뉴스와 reason은 `TrendInsight`로 변환됩니다. Provider를 Fake로 대체할 수 있고, 뉴스가 없을 때 불필요한 LLM 호출과 근거 없는 생성을 줄일 수 있습니다. 전체 실행 흐름도 `main.py`의 조립과 Pipeline의 순서로 설명할 수 있습니다.

대신 파일과 모델이 늘었고, 단계 사이의 변환 코드가 필요해졌습니다. Provider를 순차 호출하므로 전체 실행 시간이 길어질 수 있으며, 현재 fail-fast 정책에서는 한 항목의 오류가 전체 JSON 저장을 막습니다. 뉴스와 Gemini의 외부 quota에도 영향을 받습니다. 이 비용들은 분리된 책임과 검증 가능한 계약을 얻기 위해 현재 프로젝트가 받아들인 Trade-off입니다.

## 짧은 회고

다시 설계한다면 외부 서비스를 연결하기 전에 각 단계가 다음 단계에 어떤 값을 넘겨야 하는지부터 기록할 것입니다. Provider의 응답을 그대로 전달하는 것보다, 그 응답이 내부에서 어떤 의미를 가지는지 먼저 정하는 일이 전체 흐름을 단순하게 만들었습니다.

## 마무리

`namuwiki_trend`의 핵심은 Browser, News, LLM, Storage를 한 함수로 묶는 데 있지 않습니다. 각 외부 시스템의 결과를 내부 모델로 바꾸고, Enricher가 호출 여부와 근거 부족 상태를 판단하며, Pipeline이 순서를 조정하고, Storage가 최종 출력 계약을 지키도록 연결하는 데 있습니다.

여러 외부 서비스를 하나의 실행 흐름으로 만들었다면 다음 문제가 남습니다. 각 Provider의 인증 오류, 네트워크 실패, 응답 오류, API 제한이 발생했을 때 이를 전체 시스템에서 어떻게 표현하고 운영할 것인가? 이 질문은 다음 Chapter에서 다룹니다.
