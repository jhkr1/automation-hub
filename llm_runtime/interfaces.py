"""Minimal future provider boundary; no SDK adapter is implemented yet."""

from typing import Protocol

from llm_runtime.models import LlmCredential, LlmProviderResponse


class LlmProvider(Protocol):
    """Generate text using a resolved credential."""

    def generate(
        self, *, prompt: str, credential: LlmCredential, max_output_tokens: int | None = None
    ) -> LlmProviderResponse:
        """Return provider text for one prompt."""
