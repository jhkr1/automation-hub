import pytest

from llm_runtime.exceptions import (
    InvalidLlmJobError,
    LlmAuthenticationError,
    LlmBudgetExceededError,
    LlmDailyQuotaExceededError,
    LlmProviderResponseError,
    LlmProviderUnavailableError,
    LlmRateLimitError,
)
from llm_runtime.models import (
    KeyProfile,
    LlmCredential,
    LlmJob,
    LlmProviderResponse,
    LlmQuotaBudget,
)
from llm_runtime.quota import LocalFileQuotaLedger
from llm_runtime.runtime import LlmRuntime


class FakeProvider:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    def generate(self, *, prompt, credential, max_output_tokens=None):
        self.calls.append(
            {
                "prompt": prompt,
                "credential": credential,
                "max_output_tokens": max_output_tokens,
            }
        )
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


class FakeLedger:
    def __init__(self, fail_on_retry=False):
        self.reservations = []
        self.fail_on_retry = fail_on_retry

    def reserve(self, **kwargs):
        self.reservations.append(kwargs)
        if self.fail_on_retry and kwargs["retry"]:
            raise LlmBudgetExceededError("retry budget exceeded")


def response(text="ok", input_tokens=2, output_tokens=3):
    return LlmProviderResponse(
        text=text,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        finish_reason="STOP",
    )


def credential_resolver(job, profile):
    return LlmCredential(
        job=LlmJob(job),
        profile=KeyProfile(profile),
        api_key="secret-api-key",
        model="test-model",
        project_profile="production-project",
    )


def budget_resolver(profile):
    return LlmQuotaBudget(10, 10, 10_000)


def make_runtime(provider, ledger, sleep=None, **kwargs):
    return LlmRuntime(
        provider=provider,
        ledger=ledger,
        credential_resolver=credential_resolver,
        budget_resolver=budget_resolver,
        sleep=sleep or (lambda delay: None),
        **kwargs,
    )


def test_success_resolves_dependencies_once_and_returns_metadata():
    provider = FakeProvider([response()])
    ledger = FakeLedger()
    credential_calls = []
    budget_calls = []

    def resolve_credential(job, profile):
        credential_calls.append((job, profile))
        return credential_resolver(job, profile)

    def resolve_budget(profile):
        budget_calls.append(profile)
        return budget_resolver(profile)

    runtime = LlmRuntime(
        provider=provider,
        ledger=ledger,
        credential_resolver=resolve_credential,
        budget_resolver=resolve_budget,
        default_output_reserve=256,
    )
    result = runtime.generate(
        job=LlmJob.NAMUWIKI,
        profile=KeyProfile.TEST,
        prompt="safe prompt",
        estimated_input_tokens=100,
        max_output_tokens=64,
    )

    assert result.text == "ok"
    assert result.provider == "gemini"
    assert result.model == "test-model"
    assert result.project_profile == "production-project"
    assert result.request_count == 1
    assert result.retry_count == 0
    assert result.input_tokens == 2
    assert result.output_tokens == 3
    assert result.finish_reason == "STOP"
    assert credential_calls == [(LlmJob.NAMUWIKI, KeyProfile.TEST)]
    assert budget_calls == [KeyProfile.TEST]
    assert ledger.reservations[0]["estimated_tokens"] == 164
    assert ledger.reservations[0]["retry"] is False


def test_default_output_reserve_is_used_when_output_limit_is_absent():
    provider = FakeProvider([response()])
    ledger = FakeLedger()
    make_runtime(provider, ledger, default_output_reserve=256).generate(
        job=LlmJob.NAMUWIKI,
        profile=KeyProfile.TEST,
        prompt="safe prompt",
        estimated_input_tokens=100,
    )
    assert ledger.reservations[0]["estimated_tokens"] == 356


def test_transient_retry_sleeps_and_reserves_again():
    provider = FakeProvider([LlmRateLimitError("rate limited"), response()])
    ledger = FakeLedger()
    delays = []
    result = make_runtime(provider, ledger, delays.append).generate(
        job=LlmJob.NAMUWIKI,
        profile=KeyProfile.TEST,
        prompt="safe prompt",
        estimated_input_tokens=10,
        max_output_tokens=20,
    )

    assert result.request_count == 2
    assert result.retry_count == 1
    assert delays == [1.0]
    assert [item["retry"] for item in ledger.reservations] == [False, True]
    assert len(provider.calls) == 2


def test_repeated_transient_failures_stop_at_max_attempts():
    provider = FakeProvider(
        [
            LlmProviderUnavailableError("unavailable"),
            LlmRateLimitError("rate limited"),
            LlmProviderUnavailableError("unavailable"),
        ]
    )
    ledger = FakeLedger()
    delays = []
    with pytest.raises(LlmProviderUnavailableError):
        make_runtime(provider, ledger, delays.append).generate(
            job=LlmJob.NAMUWIKI,
            profile=KeyProfile.TEST,
            prompt="safe prompt",
            estimated_input_tokens=10,
        )
    assert len(provider.calls) == 3
    assert len(ledger.reservations) == 3
    assert delays == [1.0, 2.0]


@pytest.mark.parametrize(
    "error",
    [
        LlmDailyQuotaExceededError("daily quota"),
        LlmAuthenticationError("authentication failed"),
        LlmProviderResponseError("invalid response"),
    ],
)
def test_non_retryable_provider_errors_are_not_retried(error):
    provider = FakeProvider([error])
    ledger = FakeLedger()
    delays = []
    with pytest.raises(type(error)):
        make_runtime(provider, ledger, delays.append).generate(
            job=LlmJob.NAMUWIKI,
            profile=KeyProfile.TEST,
            prompt="safe prompt",
            estimated_input_tokens=10,
        )
    assert len(provider.calls) == 1
    assert len(ledger.reservations) == 1
    assert delays == []


def test_budget_error_is_not_retried():
    provider = FakeProvider([response()])
    ledger = FakeLedger()
    ledger.reservations = []
    ledger.fail_on_retry = False

    def reject_budget(**kwargs):
        raise LlmBudgetExceededError("daily budget exceeded")

    ledger.reserve = reject_budget
    with pytest.raises(LlmBudgetExceededError):
        make_runtime(provider, ledger).generate(
            job=LlmJob.NAMUWIKI,
            profile=KeyProfile.TEST,
            prompt="safe prompt",
            estimated_input_tokens=10,
        )
    assert provider.calls == []


def test_retry_reservation_budget_error_prevents_second_provider_call():
    provider = FakeProvider([LlmRateLimitError("rate limited"), response()])
    ledger = FakeLedger(fail_on_retry=True)
    delays = []
    with pytest.raises(LlmBudgetExceededError):
        make_runtime(provider, ledger, delays.append).generate(
            job=LlmJob.NAMUWIKI,
            profile=KeyProfile.TEST,
            prompt="safe prompt",
            estimated_input_tokens=10,
        )
    assert len(provider.calls) == 1
    assert len(ledger.reservations) == 2
    assert delays == [1.0]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("prompt", ""),
        ("prompt", "   "),
        ("estimated_input_tokens", 0),
        ("estimated_input_tokens", -1),
        ("estimated_input_tokens", True),
        ("max_output_tokens", 0),
        ("max_output_tokens", -1),
        ("max_output_tokens", False),
    ],
)
def test_invalid_input_is_rejected_before_dependencies(field, value):
    provider = FakeProvider([response()])
    ledger = FakeLedger()
    kwargs = {
        "job": LlmJob.NAMUWIKI,
        "profile": KeyProfile.TEST,
        "prompt": "safe prompt",
        "estimated_input_tokens": 10,
    }
    kwargs[field] = value
    with pytest.raises(ValueError):
        make_runtime(provider, ledger).generate(**kwargs)
    assert provider.calls == []
    assert ledger.reservations == []


def test_invalid_max_attempts_is_rejected():
    with pytest.raises(ValueError):
        make_runtime(FakeProvider([]), FakeLedger(), max_attempts=0)
    with pytest.raises(ValueError):
        make_runtime(FakeProvider([]), FakeLedger(), max_attempts=True)


def test_invalid_job_uses_existing_settings_error():
    with pytest.raises(InvalidLlmJobError):
        LlmRuntime(
            provider=FakeProvider([]),
            ledger=FakeLedger(),
        ).generate(
            job="unknown",
            profile="test",
            prompt="safe prompt",
            estimated_input_tokens=10,
        )


def test_secret_prompt_and_response_are_not_in_runtime_repr_or_error():
    secret = "super-secret-api-key"
    prompt = "private prompt that must not be echoed"
    provider = FakeProvider([LlmProviderResponse(text="safe result")])
    credential = LlmCredential(
        LlmJob.NAMUWIKI,
        KeyProfile.TEST,
        secret,
        "test-model",
        "test-project",
    )
    runtime = LlmRuntime(
        provider=provider,
        ledger=FakeLedger(),
        credential_resolver=lambda job, profile: credential,
        budget_resolver=budget_resolver,
    )
    assert secret not in repr(runtime)
    result = runtime.generate(
        job=LlmJob.NAMUWIKI,
        profile=KeyProfile.TEST,
        prompt=prompt,
        estimated_input_tokens=10,
    )
    assert secret not in repr(result)
    assert prompt not in repr(result)


def test_local_ledger_integration_records_first_reservation(tmp_path):
    path = tmp_path / "quota-ledger.json"
    provider = FakeProvider([response()])
    ledger = LocalFileQuotaLedger(path)
    make_runtime(provider, ledger).generate(
        job=LlmJob.NAMUWIKI,
        profile=KeyProfile.TEST,
        prompt="safe prompt",
        estimated_input_tokens=10,
        max_output_tokens=20,
    )
    payload = __import__("json").loads(path.read_text())
    rows = payload["reservations"]
    assert len(rows) == 1
    assert rows[0]["retry"] is False
    assert rows[0]["project_profile"] == "production-project"
    assert "secret-api-key" not in path.read_text()
    assert "safe prompt" not in path.read_text()


def test_local_ledger_integration_records_retry_reservation(tmp_path):
    path = tmp_path / "quota-ledger.json"
    provider = FakeProvider([LlmRateLimitError("rate limited"), response()])
    ledger = LocalFileQuotaLedger(path)
    make_runtime(provider, ledger).generate(
        job=LlmJob.NAMUWIKI,
        profile=KeyProfile.TEST,
        prompt="safe prompt",
        estimated_input_tokens=10,
        max_output_tokens=20,
    )
    rows = __import__("json").loads(path.read_text())["reservations"]
    assert [row["retry"] for row in rows] == [False, True]
    assert all(row["project_profile"] == "production-project" for row in rows)
