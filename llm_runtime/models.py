"""Provider-neutral technical models. Domain data belongs to Packages."""

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum
from typing import Mapping


class LlmJob(StrEnum):
    NAMUWIKI = "namuwiki"
    GOOGLE_FINANCE = "google_finance"


class KeyProfile(StrEnum):
    PRODUCTION = "production"
    TEST = "test"


@dataclass(frozen=True)
class LlmResponseFormat:
    """Provider-neutral response format requested by an Application."""

    response_mime_type: str
    response_schema: Mapping[str, object] | None = None

    def __post_init__(self) -> None:
        if not self.response_mime_type.strip():
            raise ValueError("response_mime_type must not be empty")
        if self.response_schema is not None and not isinstance(self.response_schema, Mapping):
            raise TypeError("response_schema must be a mapping")


@dataclass(frozen=True)
class LlmCredential:
    """One resolved credential without exposing the secret in representation."""

    job: LlmJob
    profile: KeyProfile
    api_key: str = field(repr=False)
    model: str
    project_profile: str


@dataclass(frozen=True)
class LlmProviderResponse:
    text: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    finish_reason: str | None = None


@dataclass(frozen=True)
class LlmResponse:
    text: str
    provider: str
    model: str
    project_profile: str
    request_count: int
    retry_count: int
    input_tokens: int | None = None
    output_tokens: int | None = None
    finish_reason: str | None = None

@dataclass(frozen=True)
class LlmQuotaBudget:
    daily_requests: int
    requests_per_minute: int
    tokens_per_minute: int

@dataclass(frozen=True)
class LlmQuotaReservation:
    reservation_id: str
    reserved_at: datetime
    pacific_date: date
    project_profile: str
    provider: str
    model: str
    job: LlmJob
    estimated_tokens: int
    retry: bool
