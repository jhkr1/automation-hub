"""Secret-safe adapter for the repository's google-genai SDK usage."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from google import genai
from google.genai import types
from google.genai.errors import ClientError, ServerError

from llm_runtime.exceptions import (
    LlmAuthenticationError,
    LlmDailyQuotaExceededError,
    LlmProviderResponseError,
    LlmProviderUnavailableError,
    LlmRateLimitError,
    LlmRuntimeError,
)
from llm_runtime.models import LlmCredential, LlmProviderResponse, LlmResponseFormat

DAILY_MARKER = "GenerateRequestsPerDayPerProjectPerModel-FreeTier"
LOGGER = logging.getLogger(__name__)


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
        response_format: LlmResponseFormat | None = None,
    ) -> LlmProviderResponse:
        client: Any | None = None
        try:
            client = self._client_factory(credential.api_key)
            kwargs: dict[str, Any] = {"model": credential.model, "contents": prompt}
            config: dict[str, Any] = {}
            if max_output_tokens is not None:
                config["max_output_tokens"] = max_output_tokens
            if response_format is not None:
                config["response_mime_type"] = response_format.response_mime_type
                if response_format.response_schema is not None:
                    config["response_json_schema"] = dict(response_format.response_schema)
            if config:
                kwargs["config"] = types.GenerateContentConfig(**config)
            response = client.models.generate_content(**kwargs)
        except (ClientError, ServerError) as exc:
            raise self._classify(exc, credential, response_format) from exc
        except (TimeoutError, OSError) as exc:
            raise LlmProviderUnavailableError("gemini provider unavailable") from exc
        finally:
            if client is not None:
                close = getattr(client, "close", None)
                if callable(close):
                    close()

        text, finish_reason, candidate_count, part_count = self._extract_response(response)
        usage = getattr(response, "usage_metadata", None)
        LOGGER.debug(
            "Gemini response metadata: finish_reason=%s candidate_count=%s "
            "part_count=%s has_text=%s usage_metadata=%s",
            finish_reason,
            candidate_count,
            part_count,
            bool(text and text.strip()),
            usage is not None,
        )
        if not isinstance(text, str) or not text.strip():
            raise LlmProviderResponseError("gemini provider returned an empty response")
        return LlmProviderResponse(
            text=text.strip(),
            input_tokens=getattr(usage, "prompt_token_count", None) if usage else None,
            output_tokens=getattr(usage, "candidates_token_count", None) if usage else None,
            finish_reason=finish_reason,
        )

    @staticmethod
    def _extract_response(response: Any) -> tuple[str | None, Any, int, int]:
        """Extract text and safe response metadata from an SDK response."""
        text = getattr(response, "text", None)
        candidates = getattr(response, "candidates", None) or []
        candidate_count = len(candidates) if isinstance(candidates, list) else 0
        part_count = 0
        finish_reason = getattr(response, "finish_reason", None)
        part_texts: list[str] = []

        for candidate in candidates if isinstance(candidates, list) else []:
            candidate_finish_reason = getattr(candidate, "finish_reason", None)
            if finish_reason is None and candidate_finish_reason is not None:
                finish_reason = candidate_finish_reason
            content = getattr(candidate, "content", None)
            parts = getattr(content, "parts", None) or []
            if not isinstance(parts, list):
                continue
            part_count += len(parts)
            for part in parts:
                part_text = getattr(part, "text", None)
                if isinstance(part_text, str) and part_text.strip():
                    part_texts.append(part_text)

        if not isinstance(text, str) or not text.strip():
            text = "\n".join(part_texts) if part_texts else None
        return text, finish_reason, candidate_count, part_count

    @staticmethod
    def _classify(
        error: ClientError | ServerError,
        credential: LlmCredential,
        response_format: LlmResponseFormat | None,
    ) -> LlmRuntimeError:
        details = repr(getattr(error, "details", ""))
        if error.code == 429 and DAILY_MARKER in details:
            return LlmDailyQuotaExceededError("gemini daily quota exceeded")
        if error.code == 429:
            return LlmRateLimitError("gemini rate limited")
        if error.code in {401, 403}:
            return LlmAuthenticationError("gemini authentication or permission failed")
        if error.code >= 500:
            return LlmProviderUnavailableError("gemini provider unavailable")
        structured_output = response_format is not None
        has_schema = (
            response_format is not None and response_format.response_schema is not None
        )
        response_mime_type = (
            response_format.response_mime_type if response_format is not None else None
        )
        schema_transport = "json_schema" if has_schema else None
        schema_type = None
        if has_schema:
            assert response_format is not None
            schema_type = response_format.response_schema.get("type")
            if isinstance(schema_type, str):
                schema_type = schema_type.lower()
        category = {
            400: "invalid_argument",
            404: "not_found",
        }.get(error.code, "client_error")
        safe_message = (
            "gemini request rejected: "
            f"status={error.code} category={category} model={credential.model} "
            f"structured_output={structured_output} "
            f"schema_transport={schema_transport} has_schema={has_schema} "
            f"mime_type={response_mime_type} "
            f"schema_type={schema_type} sdk_exception={type(error).__name__}"
        )
        LOGGER.warning(safe_message)
        return LlmProviderResponseError(safe_message)
