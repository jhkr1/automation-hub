"""Static contracts for the local Dashboard launcher."""

from subprocess import run

from automation_dashboard.config import PROJECT_ROOT


def test_dashboard_wrapper_has_valid_shell_syntax_and_fixed_runtime_paths() -> None:
    """The launcher must not depend on a caller's working directory or PYTHONPATH."""
    wrapper = PROJECT_ROOT / "run_dashboard.sh"

    result = run(["bash", "-n", str(wrapper)], check=False, capture_output=True, text=True)
    content = wrapper.read_text(encoding="utf-8")

    assert result.returncode == 0, result.stderr
    assert 'STREAMLIT="$REPO_ROOT/.venv/bin/streamlit"' in content
    assert 'export PYTHONPATH="$REPO_ROOT"' in content
    assert 'exec "$STREAMLIT" run "$REPO_ROOT/automation_dashboard/app.py"' in content
