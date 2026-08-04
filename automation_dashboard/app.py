"""Streamlit entry point for the read-only automation dashboard."""

import streamlit as st

from automation_dashboard.config import DashboardConfigurationError
from automation_dashboard.session import DashboardDatabaseError, probe_database


def main() -> None:
    """Render the Dashboard landing page without invoking automations."""
    st.set_page_config(page_title="Automation Hub Dashboard", layout="wide")
    st.title("Automation Hub Dashboard")
    st.caption("Persisted automation data only. This dashboard never runs jobs or writes data.")
    st.info("Read-only MVP: Google Finance snapshot data is currently available.")

    try:
        probe_database()
    except (DashboardConfigurationError, DashboardDatabaseError):
        st.error(
            "데이터베이스 연결에 실패했습니다. Operations 로그와 DATABASE_URL 설정을 확인하세요."
        )
        return

    st.success("데이터베이스 연결이 확인되었습니다.")
    st.page_link("pages/1_google_finance.py", label="Google Finance Dashboard로 이동")


if __name__ == "__main__":
    main()
