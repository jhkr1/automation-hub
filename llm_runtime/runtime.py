"""Provider-neutral orchestration for one LLM generation request."""

from __future__ import annotations

import time
from collections.abc import Callable

from llm_runtime.exceptions import (
    LlmProviderUnavailableError,
    LlmRateLimitError,
)
from llm_runtime.interfaces import LlmProvider
from llm_runtime.models import (
    KeyProfile,
    LlmCredential,
    LlmJob,
    LlmProviderResponse,
    LlmQuotaBudget,
    LlmResponse,
    LlmResponseFormat,
)
from llm_runtime.quota import LocalFileQuotaLedger
from llm_runtime.settings import resolve_llm_credential, resolve_quota_budget

CredentialResolver = Callable[[LlmJob, KeyProfile], LlmCredential]
BudgetResolver = Callable[[KeyProfile], LlmQuotaBudget]
Sleep = Callable[[float], None]


class LlmRuntime:
    """Coordinate credentials, local quota reservations, provider calls, and retry."""

    def __init__(
        self,
        *,
        provider: LlmProvider,
        ledger: LocalFileQuotaLedger,
        credential_resolver: CredentialResolver = resolve_llm_credential,
        budget_resolver: BudgetResolver = resolve_quota_budget,
        sleep: Sleep = time.sleep,
        max_attempts: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 30.0,
        default_output_reserve: int = 1_024,
        provider_name: str = "gemini",
    ) -> None:
        if type(max_attempts) is not int or max_attempts < 1:
            raise ValueError("max_attempts must be a positive integer")
        if type(default_output_reserve) is not int or default_output_reserve <= 0:
            raise ValueError("default_output_reserve must be a positive integer")
        if not isinstance(base_delay, (int, float)) or base_delay < 0:
            raise ValueError("base_delay must not be negative")
        if not isinstance(max_delay, (int, float)) or max_delay < 0:
            raise ValueError("max_delay must not be negative")
        if not isinstance(provider_name, str) or not provider_name.strip():
            raise ValueError("provider_name must not be empty")
        self._provider = provider
        self._ledger = ledger
        self._credential_resolver = credential_resolver
        self._budget_resolver = budget_resolver
        self._sleep = sleep
        self._max_attempts = max_attempts
        self._base_delay = base_delay
        self._max_delay = max_delay
        self._default_output_reserve = default_output_reserve
        self._provider_name = provider_name

    def generate(
        self,
        *,
        job: LlmJob,
        profile: KeyProfile,
        prompt: str,
        estimated_input_tokens: int,
        max_output_tokens: int | None = None,
        response_format: LlmResponseFormat | None = None,
    ) -> LlmResponse:
        """Generate text with one reservation per provider attempt."""
        self._validate_input(
            job, profile, prompt, estimated_input_tokens, max_output_tokens
        )
        credential = self._credential_resolver(job, profile)
        budget = self._budget_resolver(profile)
        reserved_tokens = estimated_input_tokens + (
            max_output_tokens or self._default_output_reserve
        )
        request_count = 0
        retry_count = 0

        for attempt in range(self._max_attempts):
            if attempt:
                self._sleep(self._backoff(attempt - 1))
            self._ledger.reserve(
                project_profile=credential.project_profile,
                provider=self._provider_name,
                model=credential.model,
                job=job,
                estimated_tokens=reserved_tokens,
                budget=budget,
                retry=attempt > 0,
            )
            try:
                provider_kwargs = {
                    "prompt": prompt,
                    "credential": credential,
                    "max_output_tokens": max_output_tokens,
                }
                if response_format is not None:
                    provider_kwargs["response_format"] = response_format
                response = self._provider.generate(**provider_kwargs)
            except (LlmRateLimitError, LlmProviderUnavailableError) as exc:
                request_count += 1
                if attempt + 1 == self._max_attempts:
                    raise exc
                retry_count += 1
                continue
            except TimeoutError:
                request_count += 1
                unavailable = LlmProviderUnavailableError(
                    "llm provider unavailable"
                )
                if attempt + 1 == self._max_attempts:
                    raise unavailable from None
                retry_count += 1
                continue
            request_count += 1
            return self._response(
                response,
                credential,
                request_count,
                retry_count,
            )
        raise RuntimeError("unreachable runtime retry state")

    def _backoff(self, retry_index: int) -> float:
        return min(self._base_delay * (2**retry_index), self._max_delay)

    @staticmethod
    def _validate_input(
        job: LlmJob,
        profile: KeyProfile,
        prompt: str,
        estimated_input_tokens: int,
        max_output_tokens: int | None,
    ) -> None:
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("prompt must not be empty")
        if type(estimated_input_tokens) is not int or estimated_input_tokens <= 0:
            raise ValueError("estimated_input_tokens must be a positive integer")
        if max_output_tokens is not None and (
            type(max_output_tokens) is not int or max_output_tokens <= 0
        ):
            raise ValueError("max_output_tokens must be a positive integer")

    def _response(
        self,
        response: LlmProviderResponse,
        credential: LlmCredential,
        request_count: int,
        retry_count: int,
    ) -> LlmResponse:
        return LlmResponse(
            text=response.text,
            provider=self._provider_name,
            model=credential.model,
            project_profile=credential.project_profile,
            request_count=request_count,
            retry_count=retry_count,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            finish_reason=response.finish_reason,
        )
