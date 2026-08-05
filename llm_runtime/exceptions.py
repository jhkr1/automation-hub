"""Secret-safe LLM runtime configuration errors."""


class LlmRuntimeError(ValueError):
    """Base configuration error safe to show at a process boundary."""


class InvalidLlmJobError(LlmRuntimeError):
    """Raised for an unsupported runtime job."""


class InvalidKeyProfileError(LlmRuntimeError):
    """Raised for an unsupported credential profile."""


class MissingLlmCredentialError(LlmRuntimeError):
    """Raised when the exact selected credential variable is empty."""


class InvalidLlmConfigurationError(LlmRuntimeError):
    """Raised for an empty non-secret runtime setting."""


class LlmBudgetExceededError(LlmRuntimeError):
    """Reserved for the local ledger Sprint."""


class LlmRateLimitError(LlmRuntimeError):
    """A transient provider-side request limit."""


class LlmDailyQuotaExceededError(LlmRuntimeError):
    """A provider response identified a daily request quota exhaustion."""


class LlmAuthenticationError(LlmRuntimeError):
    """Authentication or permission was rejected without exposing credentials."""


class LlmProviderUnavailableError(LlmRuntimeError):
    """The provider could not serve the request."""


class LlmProviderResponseError(LlmRuntimeError):
    """The provider response was empty, malformed, or rejected."""


class LlmLedgerError(LlmRuntimeError):
    """Reserved for the local ledger Sprint."""
