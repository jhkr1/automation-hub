"""프로젝트의 공통 검증 명령을 순서대로 실행하는 Harness entry point."""

import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
Command = tuple[str, ...]
CommandRunner = Callable[[Command], int]
VERIFY_COMMANDS: tuple[Command, ...] = (
    ("ruff", "check", "."),
    ("pytest", "-q"),
    (sys.executable, "-m", "compileall", "namuwiki_trend", "tests"),
    ("git", "diff", "--check"),
)


def _run_command(command: Command) -> int:
    """프로젝트 루트에서 단일 검증 명령을 실행한다."""
    completed = subprocess.run(command, cwd=PROJECT_ROOT, check=False)
    return completed.returncode


def run_verification(runner: CommandRunner = _run_command) -> int:
    """검증 명령을 순서대로 실행하고 첫 실패 code를 반환한다."""
    for command in VERIFY_COMMANDS:
        print(f"[verify] 실행: {' '.join(command)}")
        try:
            return_code = runner(command)
        except OSError as exc:
            print(f"[verify] 명령 실행 실패: {exc}")
            return 1
        if return_code != 0:
            print(f"[verify] 실패: exit code {return_code}")
            return return_code

    print("[verify] 모든 검증을 통과했습니다.")
    return 0


def main() -> int:
    """검증 Harness를 실행한다."""
    return run_verification()


if __name__ == "__main__":
    raise SystemExit(main())
