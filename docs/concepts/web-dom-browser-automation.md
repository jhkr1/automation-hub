# Web, HTML, DOM과 Browser Automation

이 문서는 “왜 어떤 데이터는 `requests`로 읽고 어떤 데이터는 Playwright로 Browser를
실행하는가?”를 배우는 교재다. HTTP와 JSON의 기본은 [HTTP/API Concept](http-rest-json-external-api.md)을
참조하고, 여기서는 브라우저가 화면을 만드는 과정과 수집 도구 선택을 다룬다.

## 1. 먼저 한 문장으로

수집 도구는 서버가 처음 보낸 표현을 읽을지, JavaScript 실행 후 브라우저에 만들어진
최종 DOM을 읽을지 선택하는 도구다.

## 2. Web의 기본 구조

Internet은 연결 기반이고, Web은 HTTP와 URL로 문서를 교환하는 시스템이다. Website는 여러
Web Page의 집합이며, Browser는 HTML/CSS/JavaScript를 처리하는 client다. Web Server는
요청에 HTML, JSON, CSS, JavaScript 등을 응답한다.

```text
URL 입력 → Browser → HTTP Request → Web Server
         ← HTML / CSS / JavaScript ←
         → parsing / JS 실행 / rendering → 화면
```

## 3. HTML

HTML은 문서 구조와 의미를 표현한다. Tag가 element를 만들고 attribute가 추가 정보를 준다.

```html
<html>
  <body>
    <div class="stock" data-symbol="NVDA">
      <span class="price">123.45</span>
    </div>
  </body>
</html>
```

`div`와 `span`은 element이고 `class`, `data-symbol`은 attribute다. `div`는 parent,
`span`은 child이며 같은 parent 아래의 element는 sibling이다. 정적 HTML parser나 Browser
locator로 `.price`를 찾으면 `123.45`를 읽을 수 있다.

## 4. DOM

DOM(Document Object Model)은 Browser가 HTML을 parsing해 만든 tree다.

```text
HTML source → Browser parsing → DOM tree → JavaScript 변경 → 최종 화면
```

DOM에는 document, node, element, parent, child, sibling, attribute, text content가 있다.
중요한 점은 **HTML source != 현재 DOM**일 수 있다는 것이다. JavaScript가 element를
추가하거나 API 응답을 화면에 삽입하면 `requests.get(url).text`에는 없는 값이 최종 DOM에
나타날 수 있다.

## 5. CSS Selector

```css
price                  /* tag */
.price                 /* class */
#main                  /* id */
.stock .price          /* descendant */
[data-symbol="NVDA"]  /* attribute */
```

Selector는 Browser Automation이 의미 있는 element를 찾는 계약이다. 위치만 의존하는
`div > div:nth-child(3) > span:nth-child(2)`는 중간 구조가 조금만 바뀌어도 깨질 수 있다.
그렇다고 CSS가 항상 XPath보다 낫거나 나쁜 것은 아니다. 의미, 안정성, 가독성과 실제 DOM을
함께 평가한다.

## 6. JavaScript, 동적 페이지, SSR/CSR

HTML에 모든 데이터가 있는 것은 아니다.

```text
HTML 다운로드 → JavaScript 실행 → 추가 API 호출 → DOM 변경 → 가격 표시
```

SSR(Server-Side Rendering)은 서버가 완성된 HTML을 만든다.

```text
Browser → Server → 완성된 HTML → 표시
```

CSR(Client-Side Rendering)은 기본 HTML과 JavaScript를 받은 뒤 Browser가 데이터를 요청하고
DOM을 만든다.

```text
Browser → 기본 HTML + JS → JS 실행/데이터 요청 → DOM 생성
```

실제 서비스는 SSR과 CSR을 섞을 수 있으므로 초기 HTML, 최종 DOM, Network 요청을 확인해야
한다. 그래서 `requests.get(url).text`에 데이터가 없는데 Browser에는 보일 수 있다.

## 7. Static Scraping

```text
requests GET → HTML → BeautifulSoup → element 탐색 → text 추출
```

초기 HTML에 값이 있으면 빠르고 resource가 적다. JavaScript를 실행하지 않으므로 CSR 데이터,
로그인 후 DOM, Browser 상태에는 한계가 있다. 현재 repository에서 BeautifulSoup production
collector는 확인하지 못했으며, 이 조합은 선택 가능한 일반 방식으로 설명한다.

## 8. Browser Automation과 Playwright

Browser Automation은 Python이 HTTP만 직접 호출하는 대신 Browser를 제어하는 방식이다.

```text
Python → Browser/Context/Page → navigation/JS/DOM → Locator → text/attribute
```

독립 예제:

```python
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto("https://example.com")
    print(page.title())
    browser.close()
```

`pyproject.toml`에는 `playwright`가 있다. `namuwiki_trend/collector.py`는
`sync_playwright()` → Chromium headless → `page.goto()` → visible locator wait → raw
항목 추출 순서다. `google_finance/collector.py`는 Playwright factory를 주입하고
BrowserContext를 만든 뒤 symbol-scoped locator로 quote를 읽는다. 두 collector 모두
context와 browser를 `finally`로 닫는다.

## 9. Wait와 동적 로딩

`page.goto()` 완료는 원하는 데이터가 준비됐다는 뜻이 아니다.

```text
navigation 완료 ≠ 원하는 locator visible/ready
```

`sleep(5)`는 빠른 환경에서는 낭비이고 느린 환경에서는 부족하다. 현재 구현은 조건 기반
대기를 사용한다.

- Namuwiki: `domcontentloaded` 후 `ROOT_LOCATOR.first.wait_for(state="visible")`
- Google Finance: `domcontentloaded` 후 `_wait_for_one()`이 locator visible 대기

현재 코드가 network idle 대기를 사용한다고 기록하지 않는다. 필요한 DOM 조건을 기준으로
기다리는 것이 핵심이다.

## 10. Selector 안정성과 비교

Google Finance는 symbol title로 범위를 좁힌 뒤 quote container와 price/name/metadata를
각각 찾고 `_require_one()`으로 정확히 하나인지 확인한다. Namuwiki는 `ROOT_LOCATOR`와
직접 child 관계, visible 항목을 사용한다. selector는 절대적으로 좋고 나쁜 것이 아니라
실제 DOM 의미와 변경 가능성의 trade-off다.

| 도구 | JavaScript | 적합한 경우 | 주의 |
|---|---:|---|---|
| `requests` | 아니오 | 공식 API, 초기 HTML | 최종 DOM을 모름 |
| BeautifulSoup | 아니오 | 받은 HTML parsing | 동적 데이터 한계 |
| Playwright | 예 | 최종 DOM, click, JS 필요 | browser 비용·selector 유지보수 |

판단 흐름은 `공식 API 우선 → 초기 HTML이면 requests+parser → JS/최종 DOM이면 Browser`다.
절대 규칙이 아니라 contract, 약관, 인증, 호출량과 안정성을 함께 본다.

## 11. API와 Web Scraping

API는 `Application → 정해진 contract → structured data`, scraping은
`Application → 사용자용 page → HTML/DOM → 값 추출`이다. API는 field 계약이 상대적으로
명확하지만 key/quota에 의존하고, scraping은 API가 없어도 가능하지만 UI/selector 변경과
Browser resource 비용을 감수한다.

현재 사례는 다음과 같다.

| Package | 방식 | 이유 |
|---|---|---|
| `google_finance` | Playwright | 렌더된 quote DOM에서 값 추출 |
| `namuwiki_trend` | Playwright | 렌더링된 Top 10 visible DOM 추출 |
| `bus_monitor` | ODsay/Gyeonggi 공식 HTTP API | 구조화된 route/arrival JSON 제공 |

Namuwiki의 News/RSS와 LLM은 Browser collection과 별도 Provider/Application 단계다.
Bus Monitor에는 공식 API가 있으므로 Playwright가 필요하지 않다.

## 12. 코드 읽기 훈련

Google Finance는 `main.py`/`watchlist_main.py` → `collector.py` → locator/raw quote →
`extraction.py`/`pipeline.py` → `StockPrice` → `storage.py` 순으로 읽는다.

Namuwiki는 `snapshot_main.py`/`main.py` → `collector.py` → `extraction.py` → `TrendItem`
→ `pipeline.py`/`enricher.py` → News/LLM → output 또는 snapshot storage 순으로 읽는다.

Bus Monitor는 `odsay.py`/`gyeonggi.py`의 endpoint·JSON·normalization을 읽은 뒤
`pipeline.py`에서 HTTP 세부사항 없이 Provider 결과만 조합하는지 확인한다.

## 13. 자주 헷갈리는 것과 30초 설명

- HTML source와 최종 DOM은 다를 수 있다.
- `goto` 완료와 데이터 준비는 다르다.
- Playwright는 API client의 대체재가 아니라 Browser가 필요한 경계의 도구다.
- REST/JSON/API와 scraping은 서로 같은 말이 아니다.

“공식 API나 초기 HTML에 값이 있으면 requests가 단순합니다. JavaScript 실행 후에만 값이
나타나면 Playwright로 최종 DOM을 읽습니다. Google Finance와 Namuwiki는 Browser가 필요하고,
Bus Monitor는 공식 JSON API가 있으므로 Browser를 사용하지 않습니다. locator와 조건 기반
wait로 DOM을 검증한 뒤 내부 Domain Model로 변환합니다.”

## 14. 이해도 체크

1. `requests.get(url).text`에 값이 없는데 Browser에 보이는 이유는 무엇인가?
2. 왜 `goto()` 뒤 locator wait가 필요한가?
3. `nth-child` selector가 취약할 수 있는 이유는?
4. Bus Monitor에 Playwright를 추가하지 않는 이유는?
5. API와 scraping 중 API를 먼저 검토하는 이유는 무엇인가?

## 다음 읽기

- [HTTP, REST API, JSON과 외부 API](http-rest-json-external-api.md)
- [namuwiki_trend Architecture](../packages/namuwiki_trend/architecture.md)
- [google_finance Architecture](../packages/google_finance/architecture.md)
- [Playwright PoC](../poc/playwright-preparation.md)
