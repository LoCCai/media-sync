"""Pure retry and circuit policy coverage."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from media_sync.scheduler import (
    CircuitSnapshot,
    CircuitState,
    FailureDisposition,
    RetryPolicy,
    attempts_remain,
    circuit_failure,
    circuit_success,
    classify_failure,
    decide_circuit_claim,
    retry_at,
    retry_delay_seconds,
)

NOW = datetime(2026, 8, 30, 11, 0, tzinfo=UTC)


def test_retry_policy_round_trips_closed_schema() -> None:
    policy = RetryPolicy()

    assert policy.to_payload() == {
        "schema_version": 1,
        "base_seconds": 30,
        "cap_seconds": 1_800,
        "max_attempts": 5,
        "jitter": "equal",
    }
    assert RetryPolicy.from_payload(policy.to_payload()) == policy


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"schema_version": 2, "base_seconds": 30, "cap_seconds": 60, "max_attempts": 2, "jitter": "equal"},
        {
            "schema_version": 1,
            "base_seconds": 30,
            "cap_seconds": 60,
            "max_attempts": 2,
            "jitter": "equal",
            "extra": True,
        },
    ],
)
def test_retry_policy_rejects_open_or_wrong_schema(payload: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        RetryPolicy.from_payload(payload)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"base_seconds": True},
        {"base_seconds": 0},
        {"cap_seconds": 0},
        {"base_seconds": 31, "cap_seconds": 30},
        {"max_attempts": True},
        {"max_attempts": 0},
        {"max_attempts": 101},
        {"jitter": "full"},
    ],
)
def test_retry_policy_rejects_invalid_controls(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        RetryPolicy(**kwargs)  # type: ignore[arg-type]


def test_equal_jitter_exponential_cap_and_attempt_budget() -> None:
    policy = RetryPolicy(base_seconds=30, cap_seconds=100, max_attempts=6)

    assert retry_delay_seconds(policy, attempt=1, jitter_value=0) == 15
    assert retry_delay_seconds(policy, attempt=2, jitter_value=1) == 60
    assert retry_delay_seconds(policy, attempt=3, jitter_value=0) == 50
    assert retry_delay_seconds(policy, attempt=5, jitter_value=1) == 100
    assert attempts_remain(policy, 5) is True
    assert attempts_remain(policy, 6) is False
    with pytest.raises(ValueError, match="exhausted"):
        retry_delay_seconds(policy, attempt=6, jitter_value=0.5)


def test_retry_after_is_lower_bound_for_seconds_and_datetime() -> None:
    policy = RetryPolicy(base_seconds=30, cap_seconds=30, max_attempts=3)

    assert retry_delay_seconds(policy, attempt=1, jitter_value=0, retry_after=40, now=NOW) == 40
    assert retry_at(
        policy,
        attempt=1,
        jitter_value=0,
        retry_after=NOW + timedelta(seconds=45),
        now=NOW,
    ) == NOW + timedelta(seconds=45)
    assert (
        retry_delay_seconds(
            policy,
            attempt=1,
            jitter_value=0,
            retry_after=NOW - timedelta(seconds=1),
            now=NOW,
        )
        == 15
    )


@pytest.mark.parametrize("value", [True, -0.1, float("nan"), float("inf"), 1.1, "0.5"])
def test_retry_rejects_invalid_jitter(value: object) -> None:
    with pytest.raises(ValueError):
        retry_delay_seconds(RetryPolicy(), attempt=1, jitter_value=value)  # type: ignore[arg-type]


@pytest.mark.parametrize("value", [True, -1, float("nan"), float("inf"), 604_801, "30"])
def test_retry_rejects_invalid_retry_after(value: object) -> None:
    with pytest.raises(ValueError):
        retry_delay_seconds(RetryPolicy(), attempt=1, jitter_value=0.5, retry_after=value, now=NOW)  # type: ignore[arg-type]


def test_retry_rejects_naive_time_and_datetime_overflow() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        retry_at(RetryPolicy(), attempt=1, now=NOW.replace(tzinfo=None), jitter_value=0.5)
    with pytest.raises(ValueError, match="overflows"):
        retry_at(
            RetryPolicy(base_seconds=604_800, cap_seconds=604_800, max_attempts=2),
            attempt=1,
            now=datetime.max.replace(tzinfo=UTC),
            jitter_value=1,
        )


@pytest.mark.parametrize(
    ("code", "disposition", "affects_circuit"),
    [
        ("rate_limited", FailureDisposition.RETRY, True),
        ("temporary_upstream", FailureDisposition.RETRY, True),
        ("account_busy", FailureDisposition.RETRY, False),
        ("auth_expired", FailureDisposition.WAITING_AUTH, True),
        ("captcha_required", FailureDisposition.WAITING_USER, False),
        ("license_acknowledgement_required", FailureDisposition.WAITING_USER, False),
        ("schema_invalid", FailureDisposition.TERMINAL, True),
        ("content_ownership_conflict", FailureDisposition.TERMINAL, False),
        ("scheduler_heartbeat_failed", FailureDisposition.TERMINAL, True),
        ("scheduler_heartbeat_storage_busy", FailureDisposition.TERMINAL, True),
        ("scheduler_finalize_failed", FailureDisposition.TERMINAL, True),
        ("unknown-provider-text", FailureDisposition.RETRY, True),
        ("raw exception\nsecret", FailureDisposition.RETRY, True),
    ],
)
def test_failure_classification_is_fixed_and_redaction_safe(
    code: str,
    disposition: FailureDisposition,
    affects_circuit: bool,
) -> None:
    classified = classify_failure(code)

    assert classified.disposition is disposition
    assert classified.affects_circuit is affects_circuit
    if code not in {
        "rate_limited",
        "temporary_upstream",
        "account_busy",
        "auth_expired",
        "captcha_required",
        "license_acknowledgement_required",
        "schema_invalid",
        "content_ownership_conflict",
        "scheduler_heartbeat_failed",
        "scheduler_heartbeat_storage_busy",
        "scheduler_finalize_failed",
    }:
        assert classified.code == "unexpected_handler_failure"
    else:
        assert classified.code == code


def test_closed_open_and_single_half_open_claim_decisions() -> None:
    closed = CircuitSnapshot()
    assert decide_circuit_claim(closed, job_id="job-a", now=NOW).allowed is True

    opened = CircuitSnapshot(
        state=CircuitState.OPEN,
        consecutive_failures=3,
        open_until=NOW + timedelta(seconds=30),
    )
    assert decide_circuit_claim(opened, job_id="job-a", now=NOW).allowed is False

    probe = decide_circuit_claim(opened, job_id="job-a", now=NOW + timedelta(seconds=30))
    assert probe.allowed is True
    assert probe.transition_required is True
    assert probe.snapshot.state is CircuitState.HALF_OPEN
    assert probe.snapshot.half_open_job_id == "job-a"
    assert decide_circuit_claim(probe.snapshot, job_id="job-a", now=NOW).allowed is True
    assert decide_circuit_claim(probe.snapshot, job_id="job-b", now=NOW).allowed is False


def test_circuit_failure_threshold_reopen_and_success_close() -> None:
    first = circuit_failure(CircuitSnapshot(), now=NOW, affects_circuit=True)
    second = circuit_failure(first, now=NOW, affects_circuit=True)
    opened = circuit_failure(second, now=NOW, affects_circuit=True)

    assert first == CircuitSnapshot(consecutive_failures=1)
    assert second == CircuitSnapshot(consecutive_failures=2)
    assert opened.state is CircuitState.OPEN
    assert opened.open_until == NOW + timedelta(seconds=900)

    probe = decide_circuit_claim(opened, job_id="probe", now=opened.open_until).snapshot
    reopened = circuit_failure(probe, now=NOW + timedelta(seconds=901), affects_circuit=True)
    assert reopened.state is CircuitState.OPEN
    assert reopened.consecutive_failures == 4
    assert circuit_success(reopened) == CircuitSnapshot()


def test_non_circuit_failure_preserves_exact_snapshot() -> None:
    snapshot = CircuitSnapshot(consecutive_failures=2)
    assert circuit_failure(snapshot, now=NOW, affects_circuit=False) is snapshot


def test_content_ownership_conflict_does_not_retry_reauthenticate_or_open_circuit() -> None:
    classified = classify_failure("content_ownership_conflict")
    assert classified.code == "content_ownership_conflict"
    assert classified.disposition is FailureDisposition.TERMINAL
    snapshot = CircuitSnapshot(consecutive_failures=2)
    assert circuit_failure(snapshot, now=NOW, affects_circuit=classified.affects_circuit) is snapshot


@pytest.mark.parametrize(
    "snapshot",
    [
        CircuitSnapshot,
    ],
)
def test_circuit_snapshot_constructor_is_available(snapshot: type[CircuitSnapshot]) -> None:
    assert snapshot() == CircuitSnapshot()


def test_circuit_rejects_invalid_shapes_and_times() -> None:
    with pytest.raises(ValueError):
        CircuitSnapshot(state=CircuitState.CLOSED, open_until=NOW)
    with pytest.raises(ValueError):
        CircuitSnapshot(state=CircuitState.OPEN)
    with pytest.raises(ValueError):
        CircuitSnapshot(state=CircuitState.HALF_OPEN)
    with pytest.raises(ValueError):
        CircuitSnapshot(state=CircuitState.OPEN, open_until=NOW.replace(tzinfo=None))
    with pytest.raises(ValueError):
        decide_circuit_claim(CircuitSnapshot(), job_id="bad\njob", now=NOW)
    with pytest.raises(ValueError):
        circuit_failure(CircuitSnapshot(), now=NOW.replace(tzinfo=None), affects_circuit=True)
