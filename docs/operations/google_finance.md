# google_finance 운영 절차

이 문서는 Watchlist를 서버에서 반복 실행할 때 필요한 Wrapper, cron, 로그와 quota
정책만 다룬다. 단일 종목 CLI의 사용법과 기능 설명은
[`google_finance README`](../packages/google_finance/README.md)를 참고한다.

## Production Wrapper

`run_google_finance.sh`는 다음 책임을 가진다.

- 저장소 루트에서 `.venv/bin/python` 실행
- `.env`를 자식 프로세스에만 전달
- `flock`으로 collect와 analyze의 중복 실행 방지
- 기본 10분 전체 timeout
- `SIGINT`와 `SIGTERM` 전달
- 실행 시작, 종료 코드와 경과 시간 기록

```bash
./run_google_finance.sh --collect
./run_google_finance.sh --analyze --key-profile production
./run_google_finance.sh --analyze --key-profile test
```

timeout은 필요하면 실행 환경에서 `GOOGLE_FINANCE_TIMEOUT_SECONDS`로 조정할 수 있다.
기본값은 600초이며, 이 값은 `.env`에 기록하지 않고 Wrapper 실행 환경에서만 설정한다.

분석은 `production` 또는 `test` profile을 명시해야 한다. 선택한 profile 이름만 Python
entrypoint로 전달하며, credential 선택·quota reservation·retry는 `LlmRuntime`이 담당한다.
해당 Google Finance key만 검사하며 다른 job/profile key로 fallback하지 않는다. `--collect`는
Gemini를 사용하지 않으며 cron은 production profile만 사용한다.

## Cron 권장 예시

Google Finance는 수집과 분석을 분리한다. 수집은 Snapshot을 쌓고, 분석은 저장된 최신
두 Snapshot과 News를 사용한다. Watchlist 분석은 분석 가능한 모든 Symbol을 하나의
Structured Output Batch 요청으로 보내므로 실행당 Gemini 호출은 최대 1회다.

```cron
# 매시간 현재 가격을 수집하고 Snapshot을 저장한다.
0 * * * * /home/kstec/projects/automation-hub/run_google_finance.sh --collect

# quota reset 이후 여유를 두고 하루 한 번 저장된 Snapshot을 분석한다.
10 8 * * * /home/kstec/projects/automation-hub/run_google_finance.sh --analyze --key-profile production
```

첫 분석 시점에 동일 종목의 Snapshot이 두 개 미만이면 `MOVEMENT_UNAVAILABLE`이
정상적으로 반환된다. Gemini 무료 quota가 20 requests/day인 환경에서는 다른 Gemini
사용량과 Namuwiki 실행을 합산해야 하며, quota가 확정되기 전에는 분석 주기를 늘리지
않는다. 정상 운영 기준으로 Namuwiki Batch 1회와 Google Finance Batch 1회가 하루
기본 호출량이 된다. 뉴스가 없는 Symbol은 Batch에서 제외하고 기존 근거 부족 결과를
사용한다. Batch Provider 또는 Parser가 실패하면 전체 Batch 대상이 실패하며 자동 개별
fallback 호출은 하지 않는다. 분석 결과는 CLI 출력과 profile별 JSON artifact로 보존한다.
Dashboard Reader는 production artifact를 읽고 Google Finance 페이지의 선택된 현재
Watchlist Symbol에 대한 Insight를 표시한다. 과거 DB Snapshot에만 남아 있는 AAPL 같은
Symbol은 selector에서 제외하며, artifact의 Symbol과 선택값은 exact canonical match만
사용한다. cron 등록 전에는 `test` profile로 수동 smoke test를 수행한다.

## Watchlist Batch 계약

분석 대상은 저장된 Snapshot이 두 개 이상이고 Movement를 계산할 수 있으며 회사명·가격·
통화와 뉴스가 모두 있는 Symbol이다. Snapshot이 없거나 두 개 미만이면
`MOVEMENT_UNAVAILABLE`, 뉴스가 없으면 Gemini 호출 없이 근거 부족 Summary를 반환한다.

Prompt에는 두 종류의 변동률을 구분해 전달한다.

| 값 | 의미 |
|---|---|
| Snapshot change | 최근 두 저장 Snapshot 사이의 가격 변화 |
| Google Finance change | Google Finance 페이지가 제공한 자체 기준 변동률 |

Summary에서도 두 기준을 섞지 않는다. Google Finance change를 오늘 또는 전일 대비로
단정하지 않으며, Snapshot movement가 변하지 않은 경우에는
`최근 두 차례 자동 수집 시점 사이에는 추가 가격 변동이 없었습니다`처럼 저장된 두
수집 시점을 명시한다. 가격이 변한 경우에도 최근 두 차례 자동 수집 사이의 가격 변화와
방향으로 설명한다. 이는 Google Finance 페이지의 표시 변동률과 다른 기준일 수 있다.

Batch JSON은 입력 Symbol과 정확히 일치해야 한다. Unknown, duplicate, missing Symbol,
빈 Summary, 300자 초과 Summary와 잘린 JSON은 전체 Batch 오류로 처리한다. 기존 Watchlist
순서는 복원하며, Batch 오류 뒤 개별 Gemini 요청은 추가하지 않는다.

## JSON Artifact

분석이 모든 Symbol에 대해 정상적으로 결과를 구성하면 다음 경로에 artifact를 원자적으로
저장한다.

| Profile | 경로 |
|---|---|
| Production | `output/google_finance_insights.json` |
| Test | `output/test/google_finance_insights.json` |

두 profile은 CLI에서 선택한 `KeyProfile`로 직접 구분하며 환경변수로 다시 추론하지 않는다.
artifact에는 `schema_version=1`, UTC timezone-aware `generated_at`, profile, model과
Watchlist 입력 순서를 보존한 `items`가 포함된다. Decimal 가격과 변동값은 정밀도 손실을
피하기 위해 문자열로 저장한다. 상태가 `SUCCESS`가 아닌 항목도 Symbol과 상태를 보존하며,
사용할 수 없는 필드는 `null`이다.

저장은 동일 디렉터리의 임시 파일에 기록하고 flush, fsync, atomic replace 순서로 수행하며
파일 권한은 `0600`이다. 저장 실패 시 임시 파일을 정리하고 기존 정상 artifact를 보존한다.
Batch Parser/Provider 실패, local budget, daily quota처럼 최종 결과에 실패 상태가 있으면
기존 artifact를 덮어쓰지 않는다. API key, Prompt, raw Gemini response, 뉴스 본문과 전체
기사 객체는 저장하지 않고 필요한 `news_count`만 저장한다.

Dashboard는 이 artifact를 read-only로 읽는다. CLI는 분석 실행과 종료 코드를 담당하고,
artifact는 profile별 결과 보존을 담당하며, Dashboard는 artifact를 표시하는 역할만
담당한다. artifact에 선택된 Symbol이 없으면 다른 Symbol의 Summary로 대체하지 않고
`No Insight for Selected Symbol` 상태를 표시한다.

## 로그

```text
logs/google_finance_wrapper.log
logs/google_finance.log
logs/google_finance.lock
```

Wrapper는 stdout과 stderr를 `google_finance_wrapper.log`로 모으고 `.env` 값을 출력하지
않는다. Python Collector의 구조화된 logger는 `google_finance.log`를 사용하므로 두 로그를
분리한다. 로그 파일은 저장소의 `logs/` 아래에 생성되므로 서버에서 보존 기간과 디스크
사용량을 별도로 관리해야 한다.

## 종료 코드

| 코드 | 의미 |
|---:|---|
| `0` | 전체 Watchlist 작업 성공. `MOVEMENT_UNAVAILABLE`만 있는 분석도 포함 |
| `1` | 종목 실패 또는 `ANALYSIS_UNAVAILABLE`을 포함한 분석 실패 |
| `2` | Wrapper 사용법 오류 |
| `75` | 다른 Google Finance Wrapper 실행 중이라 건너뜀 |
| `78` | Python 또는 `.env` 등 실행 환경 오류 |
| `124` | 10분 전체 timeout 초과 |
| `130` | SIGINT로 중단 |
| `143` | SIGTERM으로 중단 |

`75`는 중복 실행 방지를 위한 상태이므로 일반 실패와 분리해 모니터링한다. 나머지
비정상 코드는 운영 확인 대상이다.

## 운영 체크리스트

- [ ] `STOCK_SYMBOLS`가 실제 서버 환경에 설정되어 있다.
- [ ] 선택한 profile의 Google Finance key가 `--analyze` 실행 환경에 존재한다.
- [ ] `--collect`를 수동 실행해 DB Snapshot 저장을 확인했다.
- [ ] Snapshot이 두 개 이상 쌓인 뒤 `--analyze`를 수동 실행했다.
- [ ] 두 Wrapper를 동시에 실행해 한 번만 수행되는지 확인했다.
- [ ] timeout과 SIGTERM 이후 Playwright 또는 Python 자식 프로세스가 남지 않는지 확인했다.
- [ ] Gemini quota와 하루 분석 횟수를 계산했다.
- [ ] MySQL Snapshot 보존과 로그 Rotation 정책을 정했다.
- [ ] `1`, `78`, `124`에 대한 알림 경로를 정했다.

이 문서는 특정 호스트에 cron이 이미 등록되어 있다고 가정하지 않는다. 실제 crontab은
체크리스트를 완료한 뒤 등록한다.
