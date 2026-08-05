import logging
from types import SimpleNamespace

import pytest
from google.genai.errors import ClientError, ServerError

from llm_runtime.exceptions import (
    LlmDailyQuotaExceededError,
    LlmProviderUnavailableError,
    LlmRateLimitError,
)
from llm_runtime.models import KeyProfile, LlmCredential, LlmJob, LlmResponseFormat
from llm_runtime.providers.gemini import GeminiProvider


class Models:
    def __init__(self, outcome):
        self.outcome, self.calls = outcome, []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


class Client:
    def __init__(self, outcome):
        self.models = Models(outcome)
        self.close_calls = 0

    def close(self):
        self.close_calls += 1


def _credential():
    return LlmCredential(LlmJob.NAMUWIKI, KeyProfile.TEST, "secret", "model", "test")


def test_provider_converts_text_usage_and_keeps_secret_safe():
    client = Client(
        SimpleNamespace(
            text=" answer ",
            usage_metadata=SimpleNamespace(prompt_token_count=3, candidates_token_count=2),
            finish_reason="STOP",
        )
    )
    result = GeminiProvider(lambda _: client).generate(
        prompt="prompt", credential=_credential()
    )
    assert result.text == "answer" and result.input_tokens == 3 and result.output_tokens == 2
    assert client.models.calls[0]["model"] == "model"
    assert client.close_calls == 1


def test_provider_rejects_empty_response():
    client = Client(SimpleNamespace(text=" "))
    with pytest.raises(Exception, match="empty"):
        GeminiProvider(lambda _: client).generate(prompt="prompt", credential=_credential())
    assert client.close_calls == 1


def test_provider_extracts_text_from_candidate_parts_when_response_text_is_empty():
    response = SimpleNamespace(
        text=None,
        candidates=[
            SimpleNamespace(
                finish_reason="STOP",
                content=SimpleNamespace(
                    parts=[SimpleNamespace(text="candidate answer")]
                ),
            )
        ],
    )
    client = Client(response)

    result = GeminiProvider(lambda _: client).generate(
        prompt="prompt", credential=_credential()
    )

    assert result.text == "candidate answer"
    assert result.finish_reason == "STOP"


def test_provider_rejects_response_without_candidate_text():
    response = SimpleNamespace(
        text=None,
        candidates=[
            SimpleNamespace(
                finish_reason="SAFETY",
                content=SimpleNamespace(parts=[]),
            )
        ],
    )
    client = Client(response)

    with pytest.raises(Exception, match="empty"):
        GeminiProvider(lambda _: client).generate(prompt="prompt", credential=_credential())

    assert client.close_calls == 1


def test_provider_debug_metadata_does_not_log_prompt_or_secret(caplog):
    caplog.set_level(logging.DEBUG, logger="llm_runtime.providers.gemini")
    client = Client(
        SimpleNamespace(
            text="answer",
            candidates=[
                SimpleNamespace(
                    finish_reason="STOP",
                    content=SimpleNamespace(parts=[SimpleNamespace(text="answer")]),
                )
            ],
        )
    )

    GeminiProvider(lambda _: client).generate(
        prompt="private prompt", credential=_credential()
    )

    messages = " ".join(record.getMessage() for record in caplog.records)
    assert "candidate_count=1" in messages
    assert "part_count=1" in messages
    assert "private prompt" not in messages
    assert "secret" not in messages


def test_provider_creates_and_closes_a_fresh_client_for_each_request():
    clients = [Client(SimpleNamespace(text="first")), Client(SimpleNamespace(text="second"))]

    def factory(_: str):
        return clients.pop(0)

    provider = GeminiProvider(factory)
    assert provider.generate(prompt="one", credential=_credential()).text == "first"
    assert provider.generate(prompt="two", credential=_credential()).text == "second"
    assert clients == []


def test_provider_passes_structured_output_config_to_gemini():
    client = Client(SimpleNamespace(text='{"items": []}'))
    response_format = LlmResponseFormat(
        response_mime_type="application/json",
        response_schema={"type": "OBJECT", "required": ["items"]},
    )

    GeminiProvider(lambda _: client).generate(
        prompt="prompt",
        credential=_credential(),
        max_output_tokens=4096,
        response_format=response_format,
    )

    config = client.models.calls[0]["config"]
    assert config["max_output_tokens"] == 4096
    assert config["response_mime_type"] == "application/json"
    assert config["response_schema"] == {"type": "OBJECT", "required": ["items"]}


def test_provider_closes_client_when_sdk_request_fails():
    error = ClientError(500, {})
    client = Client(error)

    with pytest.raises(Exception, match="unavailable"):
        GeminiProvider(lambda _: client).generate(prompt="prompt", credential=_credential())

    assert client.close_calls == 1


def test_provider_classifies_sdk_503_as_retryable_unavailable():
    error = ServerError(503, {"error": {"status": "UNAVAILABLE"}})
    client = Client(error)

    with pytest.raises(LlmProviderUnavailableError) as raised:
        GeminiProvider(lambda _: client).generate(
            prompt="private prompt", credential=_credential()
        )

    assert str(raised.value) == "gemini provider unavailable"
    assert "secret" not in str(raised.value)
    assert "private prompt" not in str(raised.value)


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
