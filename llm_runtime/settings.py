"""Resolve job/profile-specific Gemini credentials from an injected mapping."""

import os
from collections.abc import Mapping

from llm_runtime.exceptions import (
    InvalidKeyProfileError,
    InvalidLlmConfigurationError,
    InvalidLlmJobError,
    MissingLlmCredentialError,
)
from llm_runtime.models import (
    KeyProfile,
    LlmCredential,
    LlmJob,
    LlmQuotaBudget,
)

DEFAULT_GEMINI_MODEL = "gemini-3.5-flash"
DEFAULT_PRODUCTION_DAILY_BUDGET = 16
DEFAULT_TEST_DAILY_BUDGET = 5
DEFAULT_REQUESTS_PER_MINUTE_BUDGET = 4
DEFAULT_TOKENS_PER_MINUTE_BUDGET = 200_000


def _job(value: LlmJob | str) -> LlmJob:
    try:
        return LlmJob(value)
    except ValueError as exc:
        raise InvalidLlmJobError("unsupported LLM job") from exc


def _profile(value: KeyProfile | str) -> KeyProfile:
    try:
        return KeyProfile(value)
    except ValueError as exc:
        raise InvalidKeyProfileError("unsupported key profile") from exc


def resolve_llm_credential(
    job: LlmJob | str,
    profile: KeyProfile | str,
    *,
    env: Mapping[str, str] | None = None,
) -> LlmCredential:
    """Resolve exactly one key; no cross-job or cross-profile fallback occurs."""
    selected_job = _job(job)
    selected_profile = _profile(profile)
    values = os.environ if env is None else env
    suffix = "PROD" if selected_profile is KeyProfile.PRODUCTION else "TEST"
    job_part = "NAMUWIKI" if selected_job is LlmJob.NAMUWIKI else "GOOGLE_FINANCE"
    key_name = f"GEMINI_{job_part}_API_KEY_{suffix}"
    api_key = values.get(key_name, "").strip()
    if not api_key:
        raise MissingLlmCredentialError(f"missing required environment variable: {key_name}")
    model = values.get("GEMINI_MODEL", DEFAULT_GEMINI_MODEL).strip()
    if not model:
        raise InvalidLlmConfigurationError("GEMINI_MODEL must not be empty")
    project_name = f"GEMINI_PROJECT_PROFILE_{suffix}"
    project_profile = values.get(project_name, selected_profile.value).strip()
    if not project_profile:
        raise InvalidLlmConfigurationError(f"{project_name} must not be empty")
    return LlmCredential(selected_job, selected_profile, api_key, model, project_profile)


def resolve_quota_budget(
    profile: KeyProfile | str,
    *,
    env: Mapping[str, str] | None = None,
) -> LlmQuotaBudget:
    """Resolve profile-specific local quota budgets from an injected mapping."""
    selected_profile = _profile(profile)
    values = os.environ if env is None else env
    suffix = "PROD" if selected_profile is KeyProfile.PRODUCTION else "TEST"
    daily_default = (
        DEFAULT_PRODUCTION_DAILY_BUDGET
        if selected_profile is KeyProfile.PRODUCTION
        else DEFAULT_TEST_DAILY_BUDGET
    )
    daily = _positive_int_setting(
        values,
        f"GEMINI_DAILY_REQUEST_BUDGET_{suffix}",
        daily_default,
    )
    requests_per_minute = _positive_int_setting(
        values,
        "GEMINI_REQUESTS_PER_MINUTE_BUDGET",
        DEFAULT_REQUESTS_PER_MINUTE_BUDGET,
    )
    tokens_per_minute = _positive_int_setting(
        values,
        "GEMINI_TOKENS_PER_MINUTE_BUDGET",
        DEFAULT_TOKENS_PER_MINUTE_BUDGET,
    )
    return LlmQuotaBudget(daily, requests_per_minute, tokens_per_minute)


def _positive_int_setting(
    values: Mapping[str, str], name: str, default: int
) -> int:
    raw = values.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise InvalidLlmConfigurationError(f"{name} must be a positive integer") from exc
    if value <= 0:
        raise InvalidLlmConfigurationError(f"{name} must be a positive integer")
    return value
