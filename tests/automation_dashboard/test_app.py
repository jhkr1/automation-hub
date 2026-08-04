"""Minimal Streamlit entrypoint smoke contract."""

from automation_dashboard import app


def test_dashboard_entrypoint_exposes_main() -> None:
    """The dashboard package exports an importable Streamlit entrypoint."""
    assert callable(app.main)
