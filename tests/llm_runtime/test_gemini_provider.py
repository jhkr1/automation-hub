from types import SimpleNamespace

import pytest
from google.genai.errors import ClientError

from llm_runtime.exceptions import LlmDailyQuotaExceededError, LlmRateLimitError
from llm_runtime.models import KeyProfile, LlmCredential, LlmJob
from llm_runtime.providers.gemini import GeminiProvider


class Models:
    def __init__(self, outcome):
        self.outcome, self.calls = outcome, []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


def _credential():
    return LlmCredential(LlmJob.NAMUWIKI, KeyProfile.TEST, "secret", "model", "test")


def test_provider_converts_text_usage_and_keeps_secret_safe():
    models = Models(
        SimpleNamespace(
            text=" answer ",
            usage_metadata=SimpleNamespace(prompt_token_count=3, candidates_token_count=2),
            finish_reason="STOP",
        )
    )
    result = GeminiProvider(lambda _: SimpleNamespace(models=models)).generate(
        prompt="prompt", credential=_credential()
    )
    assert result.text == "answer" and result.input_tokens == 3 and result.output_tokens == 2
    assert models.calls[0]["model"] == "model"


def test_provider_rejects_empty_response():
    with pytest.raises(Exception, match="empty"):
        GeminiProvider(
            lambda _: SimpleNamespace(models=Models(SimpleNamespace(text=" ")))
        ).generate(prompt="prompt", credential=_credential())


@pytest.mark.parametrize(
    ("error", "error_type"),
    [
        (
            ClientError(
                429,
                {
                    "error": {
                        "details": [
                            {"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier"}
                        ]
                    }
                },
            ),
            LlmDailyQuotaExceededError,
        ),
        (ClientError(429, {}), LlmRateLimitError),
    ],
)
def test_provider_classifies_quota_errors(error, error_type):
    with pytest.raises(error_type) as raised:
        GeminiProvider(lambda _: SimpleNamespace(models=Models(error))).generate(
            prompt="private prompt", credential=_credential()
        )
    assert "secret" not in str(raised.value) and "private prompt" not in str(raised.value)
