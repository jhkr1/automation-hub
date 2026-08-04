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
./run_google_finance.sh --analyze
```

timeout은 필요하면 실행 환경에서 `GOOGLE_FINANCE_TIMEOUT_SECONDS`로 조정할 수 있다.
기본값은 600초이며, 이 값은 `.env`에 기록하지 않고 Wrapper 실행 환경에서만 설정한다.

## Cron 권장 예시

Google Finance는 수집과 분석을 분리한다. 수집은 Snapshot을 쌓고, 분석은 저장된 최신
두 Snapshot과 News를 사용한다. Watchlist가 4종목인 경우 분석은 실행당 최대 4회의
Gemini 호출을 발생시킬 수 있으므로 무료 quota를 고려해 하루 1회부터 시작한다.

```cron
# 매시간 현재 가격을 수집하고 Snapshot을 저장한다.
7 * * * * /srv/automation-hub/run_google_finance.sh --collect

# quota reset 이후 여유를 두고 하루 한 번 저장된 Snapshot을 분석한다.
10 18 * * * /srv/automation-hub/run_google_finance.sh --analyze
```

첫 분석 시점에 동일 종목의 Snapshot이 두 개 미만이면 `MOVEMENT_UNAVAILABLE`이
정상적으로 반환된다. Gemini 무료 quota가 20 requests/day인 환경에서는 다른 Gemini
사용량과 Namuwiki 실행을 합산해야 하며, quota가 확정되기 전에는 분석 주기를 늘리지
않는다.

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
- [ ] `GEMINI_API_KEY`는 `--analyze` 실행 환경에만 전달된다.
- [ ] `--collect`를 수동 실행해 DB Snapshot 저장을 확인했다.
- [ ] Snapshot이 두 개 이상 쌓인 뒤 `--analyze`를 수동 실행했다.
- [ ] 두 Wrapper를 동시에 실행해 한 번만 수행되는지 확인했다.
- [ ] timeout과 SIGTERM 이후 Playwright 또는 Python 자식 프로세스가 남지 않는지 확인했다.
- [ ] Gemini quota와 하루 분석 횟수를 계산했다.
- [ ] MySQL Snapshot 보존과 로그 Rotation 정책을 정했다.
- [ ] `1`, `78`, `124`에 대한 알림 경로를 정했다.

이 문서는 특정 호스트에 cron이 이미 등록되어 있다고 가정하지 않는다. 실제 crontab은
체크리스트를 완료한 뒤 등록한다.
