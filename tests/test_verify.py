"""검증 Harness의 네트워크 비의존 테스트."""

from scripts.verify import VERIFY_COMMANDS, run_verification


def test_run_verification_runs_all_commands_in_order(capsys) -> None:
    """모든 명령이 정의된 순서대로 실행되고 성공 code를 반환한다."""
    calls: list[tuple[str, ...]] = []

    def runner(command: tuple[str, ...]) -> int:
        calls.append(command)
        return 0

    assert run_verification(runner) == 0
    assert calls == list(VERIFY_COMMANDS)
    assert "모든 검증을 통과했습니다" in capsys.readouterr().out


def test_run_verification_stops_at_first_failure(capsys) -> None:
    """실패한 명령 뒤의 명령을 실행하지 않고 실패 code를 반환한다."""
    calls: list[tuple[str, ...]] = []

    def runner(command: tuple[str, ...]) -> int:
        calls.append(command)
        return 7 if len(calls) == 2 else 0

    assert run_verification(runner) == 7
    assert calls == list(VERIFY_COMMANDS[:2])
    assert "실패: exit code 7" in capsys.readouterr().out


def test_run_verification_returns_nonzero_when_command_cannot_start() -> None:
    """명령을 시작하지 못한 경우 non-zero code를 반환한다."""
    def runner(command: tuple[str, ...]) -> int:
        raise FileNotFoundError(command[0])

    assert run_verification(runner) == 1
