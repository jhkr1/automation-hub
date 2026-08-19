# Process, Shell, Environment와 운영 실행

이 문서는 터미널에서 Python을 실행했을 때 운영체제에서 무슨 일이 일어나는지,
그리고 같은 명령을 cron과 wrapper로 반복 실행하는 이유를 설명한다. 실제 운영 절차는
[Bus Monitor Operations](../operations/bus_monitor.md)와 [Cron Guide](../operations/cron.md)를
참조하고, 여기서는 “왜 그렇게 동작하는가”를 배운다.

## 1. Program과 Process

Program은 저장된 코드이고 Process는 그 코드가 실행 중인 인스턴스다.

```text
bus_monitor/main.py              → program code
python -m bus_monitor.main ...   → 실행 명령
운영체제                         → Python process 생성
```

하나의 program에서 여러 process가 생길 수 있다. 17:00 실행이 끝나지 않았는데 17:10
cron이 다시 시작하면 두 process가 같은 target을 처리할 수 있고, 이것이 `flock`이 필요한
이유다.

Parent process는 child process를 시작할 수 있다.

```text
cron daemon → shell wrapper → Python process
terminal    → run_bus_monitor.sh → python
```

## 2. Terminal, Shell, Shell Script

Terminal은 입력과 출력을 보여주는 인터페이스이고, Shell은 command를 해석하는 프로그램이다.
현재 wrapper의 shebang은 `#!/usr/bin/env bash`이므로 Bash로 실행된다. Bash, zsh,
PowerShell은 서로 다른 shell이며 문법과 환경변수 표기가 다를 수 있다.

직접 입력하면 다음 명령의 순서와 환경을 매번 기억해야 한다.

```bash
cd /home/kstec/projects/automation-hub
source .env
./.venv/bin/python -m bus_monitor.main --target-id 2
```

`run_bus_monitor.sh`는 root 계산, `.env` 로드, 필수 환경변수 검사, lock, timeout, log,
Python executable과 exit status 전달을 반복 가능한 한 경계로 묶는다. `run_dashboard.sh`는
장시간 Streamlit process를 실행하는 wrapper이지 cron batch wrapper가 아니다.

## 3. Working Directory와 Path

`pwd`가 보여주는 current working directory는 상대경로의 기준이다.

```text
logs/bus_monitor.log
```

는 실행 위치에 따라 다른 파일이 될 수 있다. Absolute path는 `/home/.../logs/...`처럼
기준이 고정되고, relative path는 짧지만 working directory에 의존한다. 실제 wrapper는
다음 방식으로 자기 위치를 root로 계산하고 `cd`한다.

```bash
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$SCRIPT_DIR"
cd "$REPO_ROOT"
```

그래서 cron의 예상 밖 working directory에서도 `.env`, `.venv`, `logs`와 package import가
같은 repository를 가리킨다.

## 4. Environment Variable과 `.env`

환경변수는 Process가 시작될 때 가진 key/value 설정이다. Parent shell이 child process를
시작하면 기본적으로 환경을 상속하지만, 이미 실행 중인 다른 process가 나중에 바뀐 값을
자동으로 받지는 않는다.

```text
Shell environment → 새 child process environment 상속
```

`.env`는 OS가 자동으로 읽는 특수 저장소가 아니라 `KEY=value` 텍스트 파일이다. 현재
`run_bus_monitor.sh`는 `.env`를 `source`하고 export한 뒤 Python child에 전달한다.
`bus_monitor/config.py`는 Pydantic Settings로 repository `.env`를 읽는다. 두 방식은 목적은
비슷하지만 읽는 주체가 다르다.

API key와 DB password는 source/README에 기록하지 않는다. `.env`에는 실제 secret을 두고,
`.env.example`에는 이름과 placeholder만 둔다. 환경변수 이름 자체는 secret이 아니다.

## 5. PATH와 Virtual Environment

Shell에서 `python`을 입력하면 PATH를 왼쪽부터 검색해 executable을 찾는다.

```bash
which python
which streamlit
PATH="$PWD/.venv/bin:$PATH"
```

위 설정은 현재 repository의 `.venv/bin`을 기존 PATH보다 앞에 추가한다. `source .venv/bin/activate`
는 Python 자체를 바꾸는 것이 아니라 현재 shell의 PATH와 관련 변수를 바꾸어 `python`과
`pip`가 virtual environment를 먼저 가리키게 한다.

반대로 다음처럼 executable을 직접 지정하면 activate하지 않아도 된다.

```bash
./.venv/bin/python scripts/verify.py
```

현재 환경에서는 시스템 `python` 명령이 없을 수 있지만 `.venv/bin/python`은 존재한다.

## 6. PYTHONPATH

PATH가 executable 검색 경로라면 `PYTHONPATH`는 Python module 검색 경로에 영향을 준다.

```bash
PYTHONPATH="$PWD" ./.venv/bin/streamlit run automation_dashboard/app.py
```

과거 Dashboard import 문제는 flat-layout repository root가 module search path에 없어서
발생했다. 현재 `run_dashboard.sh`는 root를 계산하고 다음을 명시한다.

```bash
export PYTHONPATH="$REPO_ROOT"
export PATH="$REPO_ROOT/.venv/bin:..."
exec "$STREAMLIT" run "$REPO_ROOT/automation_dashboard/app.py" "$@"
```

PATH와 PYTHONPATH는 서로 대체하지 않는다. 하나는 프로그램을 찾고 다른 하나는 Python
module을 찾는다.

## 7. stdout, stderr와 Logging

- stdout: 정상 결과와 사용자 출력
- stderr: 오류와 진단 메시지
- log file: 시간이 지난 뒤 운영 상태를 추적하는 기록

Shell redirection의 기본은 다음과 같다.

```bash
command >> app.log 2>&1
```

`>>`는 stdout을 append하고 `2>&1`은 stderr를 현재 stdout과 같은 곳으로 보낸다.

현재 batch wrapper는 `exec >>"$LOG_FILE" 2>&1`로 이후 출력과 오류를 log에 append한다.
로그에는 timestamp, target/mode, status, elapsed time과 exit code를 남기되 API key,
`.env` 원문, raw response는 남기지 않는다. Python logger는 `DEBUG`, `INFO`, `WARNING`,
`ERROR`, `CRITICAL` 같은 level을 사용할 수 있으며, 현재 project의 rotating logger와
wrapper log를 같은 것으로 보지 않는다. Log rotation은 일반적인 운영 기법이지만 이
Sprint에서 현재 wrapper에 구현됐다고 가정하지 않는다.

## 8. Exit Code

Process는 종료할 때 OS에 숫자를 반환한다.

- `0`: 일반적인 성공
- non-zero: 실패 또는 특별한 운영 상태

현재 실제 정책은 다음과 같다.

| code | 의미 |
|---:|---|
| 0 | 정상 종료, persisted target의 route failure snapshot 저장 완료도 포함 |
| 1 | CLI route/config/storage 오류 등 process 실패 |
| 2 | wrapper 사용법 오류 |
| 75 | `flock`이 이미 실행 중이라 건너뜀 |
| 78 | 필수 환경변수, Python, `.env`, timeout 설정 문제 |
| 130/143 | SIGINT/SIGTERM 중단 |

Domain `RouteStatus.FAILED`와 process exit code는 같은 개념이 아니다. cron은 Exception
class를 이해하지 않고 종료 code와 stdout/stderr/log를 관찰한다.

## 9. HTTP Timeout과 Process Timeout

HTTP timeout은 API 응답을 기다리는 시간이고, process timeout은 전체 command 실행 시간이다.

```text
HTTP:    requests get 응답 대기 제한
Process: timeout 600 python -m bus_monitor.main ...
```

둘은 모순이 아니다. API 하나가 10초 제한이어도 DB 저장·여러 단계·프로세스 정리까지 포함한
전체 작업은 더 긴 600초 한도가 필요할 수 있다. `run_bus_monitor.sh`는
`timeout --signal=TERM --kill-after=30s`로 child를 제한하고 종료 신호를 전달한다.

## 10. cron과 cron Environment

cron은 정해진 시간에 command를 실행하는 scheduler다.

```text
cron daemon → crontab → 시간 조건 만족 → command → 새 process
```

Bus Monitor의 실제 expression은 다음과 같다.

```cron
0,10,20 17 * * 1-5 /home/kstec/projects/automation-hub/run_bus_monitor.sh
```

순서는 `minute hour day-of-month month day-of-week`다. 즉 평일(1~5) 17시의 0, 10, 20분이다.

cron의 environment는 interactive terminal과 다를 수 있다. PATH, working directory,
`.env`, virtual environment가 달라질 수 있으므로 absolute root와 `.venv/bin/python`을
wrapper에 명시한다. VS Code를 꺼도 cron daemon과 WSL instance가 실행 중이면 cron은 별도
process를 만들 수 있다.

## 11. WSL, Daemon, Foreground/Background

Daemon은 사용자와 직접 상호작용하지 않고 background에서 서비스를 제공하는 process다.
cron daemon은 schedule에 따라 process를 시작하며 단순히 shell에서 `&`를 붙인 background
command와 같지 않다.

현재 운영 문서의 WSL 제약은 다음과 같다.

- WSL instance가 실행 중이어야 한다.
- 그 배포판의 cron daemon이 실행 중이어야 한다.
- Windows 재부팅 후 자동 시작 여부를 별도 확인해야 한다.
- WSL이 종료된 동안 cron 실행이 자동 보충되지는 않는다.

이는 이 프로젝트의 WSL 운영 조건이지 Windows 전체의 일반 법칙으로 확대하지 않는다.

## 12. flock과 File Lock

Lock은 critical section을 한 번에 하나의 실행만 사용하게 하는 제어다. `flock`은 OS/file
lock이고 DB row lock과 같은 개념이 아니다.

현재 wrapper는 다음 lock을 non-blocking으로 획득한다.

```bash
exec 9>"$LOCK_FILE"
flock -n 9
```

`-n`은 lock이 풀릴 때까지 기다리지 않고 즉시 실패한다. Bus Monitor lock file은
`logs/bus_monitor_target_2.lock`이며, 이미 17:00 process가 실행 중이면 17:10 process는
API/DB를 호출하지 않고 exit 75로 종료한다.

## 13. Wrapper Script

왜 crontab에 직접 `python -m bus_monitor.main --target-id 2`를 쓰지 않고 wrapper를
호출하는가?

실제 `run_bus_monitor.sh`는 다음을 한 경계에서 관리한다.

1. shebang과 Bash 실행
2. repository root 계산
3. log redirection
4. timeout 값 검증
5. flock 중복 실행 방지
6. `.venv/bin/python` 확인
7. `.env` source/export
8. 필수 environment 확인
9. `bus_monitor.main --target-id 2` 실행
10. child exit status 기록/전달

반면 `run_dashboard.sh`는 `streamlit` long-running process를 실행하고 root `PYTHONPATH`를
설정한다. batch lock, `.env` source, process timeout을 같은 방식으로 수행하지 않는다.

## 14. automation-hub 실제 실행 흐름

Batch:

```text
cron daemon
  ↓
crontab
  ↓
run_bus_monitor.sh
  ↓ root / .env / PATH / log
  ↓ flock
  ↓ timeout
  ↓ .venv/bin/python
  ↓ bus_monitor.main
  ↓ exit code + log
```

Dashboard:

```text
user
  ↓
run_dashboard.sh
  ↓ repository root + PYTHONPATH + .venv streamlit
  ↓
Streamlit process
  ↓
Dashboard
```

## 15. 코드/운영 파일 읽기 훈련

1. `run_bus_monitor.sh`: shebang, root, env, PATH, lock, timeout, log, exit
2. `docs/operations/bus_monitor.md`: target 2, schedule, 수동 실행, DB 확인
3. `docs/operations/cron.md`: cron 환경과 WSL 조건
4. `bus_monitor/main.py`: Python process의 mode와 반환 code
5. `.env.example`: 설정 이름과 secret placeholder
6. `run_dashboard.sh`: Streamlit, root, PYTHONPATH 차이
7. `scripts/verify.py`: 검증 process의 child command와 return code

## 16. 자주 헷갈리는 것과 30초 설명

- Program vs Process: 저장된 코드 vs 실행 중 인스턴스
- Terminal vs Shell: 화면/입력 인터페이스 vs 명령 해석기
- PATH vs PYTHONPATH: executable 검색 vs Python module 검색
- Environment Variable vs `.env`: process 값 vs 값을 담은 파일
- activate vs 직접 executable: shell PATH 변경 vs 특정 interpreter 직접 실행
- stdout/stderr vs log: stream 목적 vs 장기 운영 기록
- HTTP timeout vs process timeout: API 대기 vs 전체 작업 대기
- cron vs Python loop: daemon scheduler vs 애플리케이션 내부 반복
- flock vs DB lock: file/OS 실행 제어 vs DB transaction 동시성

“cron은 별도 process로 wrapper를 시작하고, wrapper가 root·환경·virtualenv·lock·timeout을
정한 뒤 Python을 실행합니다. PATH는 실행 파일을, PYTHONPATH는 module을 찾게 합니다.
stdout/stderr는 process stream이고 log는 운영 기록이며, exit code는 cron이 이해하는
숫자 결과입니다.”

## 17. 이해도 체크

1. VS Code를 종료해도 cron이 실행될 수 있는 이유는?
2. `.venv`를 activate하지 않고 `.venv/bin/python`을 실행할 수 있는 이유는?
3. Terminal A에서 export한 값을 이미 실행 중인 Process B가 자동으로 받는가?
4. cron에서만 실패하면 PATH, working directory, env 중 무엇을 먼저 확인할 것인가?
5. `flock -n`이 lock을 기다리지 않는 이유는?
6. `command >> log 2>&1`의 각 부분은 무엇인가?
7. HTTP 10초 timeout과 process 600초 timeout이 함께 필요한 이유는?

## 다음 읽기

- [Python Project Structure](python-project-structure.md)
- [Scheduler](scheduler.md)
- [Logging](logging.md)
- [Bus Monitor Operations](../operations/bus_monitor.md)
- [Cron Guide](../operations/cron.md)
