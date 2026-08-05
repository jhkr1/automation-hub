import pytest

from llm_runtime.exceptions import MissingLlmCredentialError
from llm_runtime.models import KeyProfile, LlmJob
from llm_runtime.settings import resolve_llm_credential


@pytest.mark.parametrize(
    ("job", "profile", "key_name"),
    [
        (LlmJob.NAMUWIKI, KeyProfile.PRODUCTION, "GEMINI_NAMUWIKI_API_KEY_PROD"),
        (LlmJob.GOOGLE_FINANCE, KeyProfile.PRODUCTION, "GEMINI_GOOGLE_FINANCE_API_KEY_PROD"),
        (LlmJob.NAMUWIKI, KeyProfile.TEST, "GEMINI_NAMUWIKI_API_KEY_TEST"),
        (LlmJob.GOOGLE_FINANCE, KeyProfile.TEST, "GEMINI_GOOGLE_FINANCE_API_KEY_TEST"),
    ],
)
def test_resolves_exact_job_profile_key(job, profile, key_name):
    env = {key_name: "secret", "GEMINI_MODEL": "test-model"}
    credential = resolve_llm_credential(job, profile, env=env)
    assert credential.job is job
    assert credential.profile is profile
    assert credential.model == "test-model"
    assert "secret" not in repr(credential)


def test_never_falls_back_across_keys_or_exposes_secret():
    env = {"GEMINI_GOOGLE_FINANCE_API_KEY_PROD": "secret"}
    with pytest.raises(MissingLlmCredentialError) as raised:
        resolve_llm_credential("namuwiki", "production", env=env)
    assert "GEMINI_NAMUWIKI_API_KEY_PROD" in str(raised.value)
    assert "secret" not in str(raised.value)
