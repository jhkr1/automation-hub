# Python Project Structure

## 1. 먼저 한 문장으로

Python 프로젝트 구조는 `.py` 파일을 어떤 실행 단위와 이름 공간으로 묶고, 필요한 의존성을 어디에서 찾을지 정하는 약속입니다.

## 2. 왜 필요한가?

작은 스크립트에서는 한 파일에 코드를 모두 넣어도 읽을 수 있습니다. 기능이 늘어나면 수집, 모델, 저장, 실행 진입점을 나누지 않을 때 다음 문제가 생깁니다.

- 어떤 파일이 프로그램을 시작하는지 알기 어렵습니다.
- 같은 이름의 함수가 어디에서 온 것인지 추적하기 어렵습니다.
- 한 기능을 수정할 때 관계없는 기능까지 함께 건드립니다.
- 실행한 Python과 설치한 dependency가 달라져 import 오류가 발생할 수 있습니다.

구조는 파일을 예쁘게 정리하는 목적만이 아니라, Python이 코드를 찾고 개발자가 책임 경계를 읽는 방법입니다.

## 3. 가장 간단한 예제

`foo.py`라는 파일이 다음과 같다고 하겠습니다.

```python
# foo.py
message = "hello"


def greet(name: str) -> str:
    return f"{message}, {name}"
```

이 파일은 `foo`라는 **module**입니다. 다른 파일에서 다음처럼 사용할 수 있습니다.

```python
from foo import greet

print(greet("Ada"))
```

파일 하나와 module 이름은 밀접하지만 완전히 같은 관점은 아닙니다. 파일은 저장된 소스이고, module은 Python interpreter가 import해 실행 환경에 올린 이름 공간입니다.

## 4. 핵심 개념

### Source file과 module

`.py` 파일은 Python source file입니다. Python이 그 파일을 import하면 파일의 전역 이름, 함수, class가 module 객체의 속성이 됩니다.

```text
foo.py
  └─ foo module
      ├─ message
      └─ greet
```

### Package와 module

Package는 관련 module을 하나의 import namespace 아래 묶는 디렉터리입니다.

```text
bus_monitor/
├── __init__.py
├── main.py
└── pipeline.py
```

여기서 의미는 다음과 같습니다.

```text
bus_monitor           → package
bus_monitor.main      → main.py module
bus_monitor.pipeline  → pipeline.py module
```

Package는 단순히 여러 파일을 담은 폴더가 아닙니다. `bus_monitor`라는 이름 아래에서 module을 발견하고 서로 import할 수 있게 하는 경계입니다.

### `__init__.py`

`__init__.py`는 디렉터리를 package로 인식시키던 전통적인 표식이며, package가 import될 때 실행될 초기화 코드를 둘 수 있는 파일입니다. 현대 Python에는 namespace package도 있으므로 모든 import 가능한 디렉터리에 반드시 필요하다고 단정할 수는 없습니다.

`automation-hub`의 `bus_monitor/`, `google_finance/`, `namuwiki_trend/`, `automation_dashboard/`에는 실제로 `__init__.py`가 있습니다. 현재 이 파일들은 큰 초기화 로직보다 package 경계를 명시하는 역할로 읽으면 됩니다.

### `import` 읽기

```python
from bus_monitor.db_models import BusRouteSnapshot
```

이 한 줄을 세 부분으로 나누면 다음과 같습니다.

```text
bus_monitor       → package
db_models         → package 안의 module(db_models.py)
BusRouteSnapshot  → 그 module이 공개하는 class
```

Import는 파일 문자열을 검색하는 단순 기능이 아닙니다. Python은 module 이름을 `sys.path`에 있는 각 검색 위치에서 찾고, 찾은 module을 실행한 뒤 객체를 가져옵니다.

### `sys.path`와 `PYTHONPATH`

`sys.path`는 Python이 import 대상을 찾는 순서가 담긴 목록입니다. 일반적으로 실행한 script의 위치, 설치된 package 위치, 표준 라이브러리 위치 등이 포함됩니다. `PYTHONPATH`는 이 검색 목록에 추가할 경로를 실행 전에 지정하는 환경변수입니다.

이 차이는 Dashboard에서 실제로 드러났습니다.

```bash
streamlit run automation_dashboard/app.py
```

에서는 실행 방식에 따라 repository root가 import 검색 경로에 포함되지 않아 `ModuleNotFoundError: No module named 'bus_monitor'`가 발생했습니다. 반면 다음 실행은 root를 명시적으로 검색 경로에 넣습니다.

```bash
PYTHONPATH="$PWD" ./.venv/bin/streamlit run automation_dashboard/app.py
```

현재 [run_dashboard.sh](../../run_dashboard.sh)는 이 문제를 실행 환경에서 해결합니다.

```bash
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$SCRIPT_DIR"
cd "$REPO_ROOT"
export PYTHONPATH="$REPO_ROOT"
exec "$REPO_ROOT/.venv/bin/streamlit" run "$REPO_ROOT/automation_dashboard/app.py"
```

이것은 module을 코드 안에서 억지로 찾게 만드는 `sys.path.append()`가 아닙니다. 실행 wrapper가 repository root를 Python의 정상적인 import search path로 제공하는 방식입니다.

### Virtual Environment

`.venv`는 이 프로젝트 전용 Python interpreter와 설치 package를 모아 두는 virtual environment입니다. system Python과 분리하므로 프로젝트마다 dependency 버전이 충돌하는 문제를 줄일 수 있습니다.

```text
system Python                 → 운영체제가 제공하는 기본 interpreter
.venv/bin/python              → automation-hub가 사용하는 interpreter
.venv/bin/pip                 → 그 interpreter에 package를 설치하는 도구
.venv/bin/streamlit           → 같은 환경에서 실행되는 Streamlit entrypoint
```

`pip`를 system Python에 실행하고 `.venv/bin/python`으로 프로그램을 시작하면 설치 위치와 실행 위치가 달라질 수 있습니다. 운영 wrapper가 `.venv/bin/python` 또는 `.venv/bin/streamlit`을 명시하는 이유가 여기에 있습니다.

### Dependency

Dependency는 프로그램이 직접 작성하지 않고 외부에서 제공받아 사용하는 library나 실행 도구입니다. 현재 `pyproject.toml`에는 예를 들어 다음 dependency가 있습니다.

| Dependency | 현재 사용 맥락 |
|---|---|
| `requests` | HTTP 요청 경계 |
| `SQLAlchemy` | ORM·DB Session |
| `streamlit` | Dashboard optional dependency |
| `playwright` | Collector·browser automation 테스트와 기능 |

Dependency를 추가한다는 것은 import 한 줄을 추가하는 것보다 설치·버전·보안·검증 부담을 저장소에 추가한다는 뜻입니다.

### `pyproject.toml`을 읽는 법

현재 파일에서 먼저 볼 곳은 네 군데입니다.

1. `[project]`: 이름, 버전, Python 최소 버전 같은 metadata
2. `dependencies`: 기본 실행에 필요한 package
3. `[project.optional-dependencies]`: `dashboard`, `dev`처럼 선택 설치 묶음
4. `[tool.setuptools.packages.find]`: flat layout에서 설치 대상 package discovery

현재 package discovery에는 `namuwiki_trend*`, `google_finance*`, `bus_monitor*`, `database*`, `automation_dashboard*`가 포함됩니다. 따라서 새 package를 추가했는데 이 목록이나 discovery 규칙에 포함되지 않으면 editable install 후에도 import가 되지 않을 수 있습니다.

### Editable install

```bash
pip install -e ".[dashboard,dev]"
```

일반 설치는 source를 site-packages에 복사하거나 wheel을 설치해 설치 시점의 결과를 사용합니다. Editable install(`-e`)은 package metadata를 설치하면서 source 디렉터리를 가리키므로 source를 수정한 뒤 다시 build하지 않아도 개발 과정에서 변경을 볼 수 있습니다.

Editable install도 package discovery가 올바르다는 전제가 필요합니다. 과거에 `bus_monitor`가 package discovery 설정에 포함되기 전 metadata가 만들어졌다면, 소스 디렉터리가 있어도 기존 editable metadata가 새 package를 모를 수 있습니다. 이 경우 설정을 고친 뒤 editable install을 다시 실행해 설치 metadata를 갱신해야 합니다.

Editable install은 `PYTHONPATH`와 같은 개념이 아닙니다. 전자는 package를 환경에 설치하는 개발 방식이고, 후자는 이번 실행에서 import 검색 경로를 추가하는 실행 환경 설정입니다. Dashboard wrapper는 flat layout의 root import를 보장하기 위해 후자를 명시적으로 사용합니다.

## 5. automation-hub에서는?

실제 구조를 읽을 때 다음 package를 출발점으로 삼습니다.

```text
bus_monitor/
├── main.py       → target 또는 좌표 실행 entry point
├── pipeline.py   → route·realtime 흐름 조정
├── models.py     → 내부 결과 계약
├── storage.py    → snapshot 저장 경계
└── __init__.py   → package 경계
```

`google_finance/`와 `namuwiki_trend/`도 각각 `main.py`, `models.py`, pipeline·provider module을 가진 독립 package입니다. `automation_dashboard/`는 Streamlit app과 pages를 담는 별도 package입니다.

`bus_monitor/main.py`의 실행 방식은 좌표 직접 실행과 `--target-id` 실행으로 나뉩니다. 이 module이 `BusMonitorSettings`, `OdsayRouteProvider`, `GyeonggiProvider`, `BusMonitorPipeline`, `BusMonitorStorage`를 import하는 것을 보면 entry point가 전체 흐름을 조립한다는 사실을 확인할 수 있습니다.

## 6. 실제 코드를 읽는 방법

1. `pyproject.toml`에서 package discovery와 optional dependency를 확인합니다.
2. `bus_monitor/__init__.py`와 `bus_monitor/main.py`를 열어 package와 entry point를 구분합니다.
3. `main.py`의 import 목록에서 실제 흐름에 참여하는 module을 찾습니다.
4. `bus_monitor.models`로 이동해 내부 모델을 확인합니다.
5. `run_dashboard.sh`에서 root 계산, `.venv/bin/streamlit`, `PYTHONPATH` 설정을 확인합니다.
6. 같은 방식으로 `google_finance/main.py`와 `namuwiki_trend/main.py`의 entry point를 비교합니다.

## 7. 장점과 단점

| 선택 | 장점 | 단점 |
|---|---|---|
| 독립 package | 책임과 import 경계가 명확함 | package 간 공유가 필요하면 연결 코드가 생김 |
| flat layout | 처음 읽기 쉽고 실행이 단순함 | 설치 metadata와 import path를 주의해야 함 |
| virtual environment | dependency 충돌을 줄임 | 환경을 별도로 만들고 관리해야 함 |
| editable install | 개발 중 source 변경을 바로 확인함 | 설치 상태가 오래되면 metadata가 낡을 수 있음 |

## 8. 언제 쓰지 않아도 되는가?

일회성으로 실행하고 버릴 짧은 script에 여러 package와 editable install을 도입하는 것은 과할 수 있습니다. 반대로 여러 entry point, 테스트, 운영 wrapper가 있는 현재 `automation-hub`에서는 구조와 환경을 명시하는 편이 유지보수 비용을 줄입니다.

## 9. 자주 헷갈리는 개념

- **module vs package**: module은 보통 하나의 Python 파일 단위이고, package는 관련 module을 묶는 import namespace입니다.
- **virtual environment vs `PYTHONPATH`**: virtual environment는 interpreter와 설치 package를 분리하고, `PYTHONPATH`는 module 검색 경로를 조정합니다.
- **editable install vs `PYTHONPATH`**: editable install은 설치 metadata를 만들고, `PYTHONPATH`는 특정 실행의 검색 경로를 보장합니다.
- **entry point vs application logic**: entry point는 실행을 시작하고 의존성을 조립하며, 실제 규칙은 다른 module에 둡니다.

## 10. 내가 설명해본다면

“`bus_monitor`는 package이고 `bus_monitor.pipeline`은 그 안의 module입니다. `main.py`는 실행 entry point라서 설정과 Provider를 조립한 뒤 Pipeline을 호출합니다. Python이 이 package를 찾으려면 repository root가 import path에 있어야 하므로 Dashboard wrapper가 `.venv/bin/streamlit`과 `PYTHONPATH`를 함께 명시합니다. 설치 환경은 `.venv`로 분리하고, 개발 중에는 `pip install -e`로 source를 연결합니다.”

## 11. 이해도 체크

1. `bus_monitor.main`은 package인가, module인가? `bus_monitor`와 어떻게 다른가요?
2. `.venv/bin/pip`로 설치했는데 system Python으로 실행하면 어떤 문제가 생길 수 있나요?
3. `PYTHONPATH`를 추가하는 것과 package를 editable install하는 것은 왜 같은 해결책이 아닌가요?
4. `pyproject.toml`의 package discovery에 `bus_monitor*`가 빠지면 어떤 상황이 생길 수 있나요?
5. `run_dashboard.sh`가 애플리케이션 내부에 `sys.path.insert()`를 넣지 않고 wrapper에서 root를 설정하는 이유는 무엇인가요?

## 다음 읽기

[Python Data Contracts](python-data-contracts.md)에서 type hint, dataclass, Enum과 외부 데이터를 내부 계약으로 바꾸는 방법을 읽습니다.
