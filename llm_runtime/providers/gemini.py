"""Secret-safe adapter for the repository's google-genai SDK usage."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from google import genai
from google.genai.errors import ClientError

from llm_runtime.exceptions import (
    LlmAuthenticationError,
    LlmDailyQuotaExceededError,
    LlmProviderResponseError,
    LlmProviderUnavailableError,
    LlmRateLimitError,
    LlmRuntimeError,
)
from llm_runtime.models import LlmCredential, LlmProviderResponse

DAILY_MARKER = "GenerateRequestsPerDayPerProjectPerModel-FreeTier"


class GeminiProvider:
    """Adapt one Gemini SDK call to a provider-neutral response DTO."""

    def __init__(self, client_factory: Callable[[str], Any] | None = None) -> None:
        self._client_factory = client_factory or (lambda api_key: genai.Client(api_key=api_key))

    def generate(
        self,
        *,
        prompt: str,
        credential: LlmCredential,
        max_output_tokens: int | None = None,
    ) -> LlmProviderResponse:
        try:
            kwargs: dict[str, Any] = {"model": credential.model, "contents": prompt}
            if max_output_tokens is not None:
                kwargs["config"] = {"max_output_tokens": max_output_tokens}
            response = self._client_factory(credential.api_key).models.generate_content(**kwargs)
        except ClientError as exc:
            raise self._classify(exc, credential) from exc
        except (TimeoutError, OSError) as exc:
            raise LlmProviderUnavailableError("gemini provider unavailable") from exc
        text = getattr(response, "text", None)
        if not isinstance(text, str) or not text.strip():
            raise LlmProviderResponseError("gemini provider returned an empty response")
        usage = getattr(response, "usage_metadata", None)
        return LlmProviderResponse(
            text=text.strip(),
            input_tokens=getattr(usage, "prompt_token_count", None) if usage else None,
            output_tokens=getattr(usage, "candidates_token_count", None) if usage else None,
            finish_reason=getattr(response, "finish_reason", None),
        )

    @staticmethod
    def _classify(error: ClientError, credential: LlmCredential) -> LlmRuntimeError:
        details = repr(getattr(error, "details", ""))
        if error.code == 429 and DAILY_MARKER in details:
            return LlmDailyQuotaExceededError("gemini daily quota exceeded")
        if error.code == 429:
            return LlmRateLimitError("gemini rate limited")
        if error.code in {401, 403}:
            return LlmAuthenticationError("gemini authentication or permission failed")
        if error.code >= 500:
            return LlmProviderUnavailableError("gemini provider unavailable")
        return LlmProviderResponseError("gemini request rejected")
