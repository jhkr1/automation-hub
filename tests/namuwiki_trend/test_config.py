"""namuwiki_trend 설정의 실행 경계 테스트."""

from namuwiki_trend.config import Settings


def test_naver_credentials_are_optional_for_current_google_news_flows() -> None:
    """현재 Google News RSS 경로는 사용하지 않는 Naver 설정을 요구하지 않는다."""
    settings = Settings(_env_file=None, gemini_api_key="test-key")

    assert settings.naver_client_id is None
    assert settings.naver_client_secret is None
