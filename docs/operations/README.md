# 운영 문서

공통 개발 검증은 저장소 루트에서 다음 명령으로 수행한다.

```bash
python scripts/verify.py
```

패키지별 실행과 외부 서비스 설정은 각 패키지 문서에서 관리한다. Production Wrapper,
cron, 로그와 종료 코드 같은 반복 운영 절차는 이 디렉터리의 문서에서 관리한다.

Gemini key는 job과 profile로 선택한다. 같은 Google Cloud Project의 여러 key는 quota를
공유하며, production/test quota를 분리하려면 별도 Project가 필요하다.

## 운영 문서

- [`namuwiki_trend 운영 절차`](namuwiki_trend.md): Snapshot, MySQL, 전체 enrichment와 Wrapper
- [`google_finance 운영 절차`](google_finance.md): Watchlist 수집·분석 Wrapper와 quota 고려사항

## 공통 종료 코드

| 코드 | 의미 |
|---:|---|
| `0` | 실행 성공. Google Finance의 `MOVEMENT_UNAVAILABLE`은 정상 결과로 포함된다. |
| `1` | 애플리케이션 또는 외부 서비스 실패. Google Finance 분석 불가도 포함된다. |
| `2` | CLI 인자 오류 또는 Wrapper 사용법 오류 |
| `75` | `flock`으로 이미 실행 중인 작업을 건너뜀 |
| `78` | Python 실행 파일 또는 `.env` 등 운영 환경 오류 |
| `124` | 전체 timeout 초과 |
| `130` | SIGINT로 중단 |
| `143` | SIGTERM으로 중단 |

`75`는 중복 실행을 막기 위한 정상적인 건너뜀 상태지만, cron 알림에서는 일반 실패와
구분해야 한다. `1`, `78`, `124`, `130`, `143`은 운영 확인 대상이다.

## 공통 로그

- Namuwiki: `logs/namuwiki_trend.log`
- Namuwiki Snapshot Wrapper: `logs/namuwiki_snapshot.log`
- Google Finance Wrapper: `logs/google_finance_wrapper.log`
- Google Finance Python logger: `logs/google_finance.log`

두 Wrapper는 저장소 루트를 기준으로 `.venv/bin/python`을 호출하고 `.env`를 자식
프로세스에 전달한다. 로그에는 API key와 `.env`의 원문을 기록하지 않는다.

## Production 등록 전 체크리스트

- [ ] 서버에서 Wrapper를 수동으로 한 번 성공시켰다.
- [ ] 실제 `.env` 권한과 `.venv/bin/python` 실행 권한을 확인했다.
- [ ] 같은 Wrapper를 동시에 실행해 `75`가 반환되는지 확인했다.
- [ ] timeout, SIGINT, SIGTERM 후 자식 프로세스가 남지 않는지 확인했다.
- [ ] 로그 보존 기간과 MySQL Snapshot 보존 정책을 정했다.
- [ ] Gemini 무료 quota를 기준으로 실행 주기를 정했다.
- [ ] `1`, `78`, `124` 발생 시 알림 경로를 정했다.

실제 호스트의 crontab은 이 체크리스트를 완료한 뒤 등록한다.
