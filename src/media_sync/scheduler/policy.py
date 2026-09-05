"""Pure retry, failure-classification, and circuit-breaker policy."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Final

RETRY_POLICY_SCHEMA_VERSION: Final = 1
MAX_RETRY_SECONDS: Final = 604_800
MAX_POLICY_ATTEMPTS: Final = 100
MAX_COOLDOWN_SECONDS: Final = 604_800
_FIXED_CODE = re.compile(r"[a-z][a-z0-9_]{0,127}\Z")


def _strict_int(value: object, *, name: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be an integer between {minimum} and {maximum}")
    return value


def _aware_utc(value: datetime, *, name: str = "datetime") -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value.astimezone(UTC)


def _safe_add(value: datetime, seconds: float, *, name: str) -> datetime:
    if not math.isfinite(seconds) or seconds < 0 or seconds > MAX_RETRY_SECONDS:
        raise ValueError(f"{name} is outside the supported range")
    try:
        return value + timedelta(seconds=seconds)
    except OverflowError as exc:
        raise ValueError(f"{name} overflows datetime") from exc


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """Closed v1 retry policy frozen into each scheduled Job payload."""

    base_seconds: int = 30
    cap_seconds: int = 1_800
    max_attempts: int = 5
    jitter: str = "equal"

    def __post_init__(self) -> None:
        base = _strict_int(self.base_seconds, name="base_seconds", minimum=1, maximum=MAX_RETRY_SECONDS)
        cap = _strict_int(self.cap_seconds, name="cap_seconds", minimum=1, maximum=MAX_RETRY_SECONDS)
        _strict_int(self.max_attempts, name="max_attempts", minimum=1, maximum=MAX_POLICY_ATTEMPTS)
        if cap < base:
            raise ValueError("cap_seconds must be greater than or equal to base_seconds")
        if self.jitter != "equal":
            raise ValueError("jitter must be 'equal'")

    def to_payload(self) -> dict[str, object]:
        return {
            "schema_version": RETRY_POLICY_SCHEMA_VERSION,
            "base_seconds": self.base_seconds,
            "cap_seconds": self.cap_seconds,
            "max_attempts": self.max_attempts,
            "jitter": self.jitter,
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> RetryPolicy:
        expected = {"schema_version", "base_seconds", "cap_seconds", "max_attempts", "jitter"}
        if set(payload) != expected or payload.get("schema_version") != RETRY_POLICY_SCHEMA_VERSION:
            raise ValueError("retry policy payload is not closed schema v1")
        jitter = payload.get("jitter")
        if not isinstance(jitter, str):
            raise ValueError("jitter must be 'equal'")
        return cls(
            base_seconds=_strict_int(
                payload.get("base_seconds"),
                name="base_seconds",
                minimum=1,
                maximum=MAX_RETRY_SECONDS,
            ),
            cap_seconds=_strict_int(
                payload.get("cap_seconds"),
                name="cap_seconds",
                minimum=1,
                maximum=MAX_RETRY_SECONDS,
            ),
            max_attempts=_strict_int(
                payload.get("max_attempts"),
                name="max_attempts",
                minimum=1,
                maximum=MAX_POLICY_ATTEMPTS,
            ),
            jitter=jitter,
        )


def attempts_remain(policy: RetryPolicy, attempt: int) -> bool:
    """Return whether a completed attempt may be retried."""

    normalized = _strict_int(attempt, name="attempt", minimum=1, maximum=MAX_POLICY_ATTEMPTS)
    return normalized < policy.max_attempts


def _retry_after_seconds(value: object, *, now: datetime) -> float:
    if isinstance(value, datetime):
        return max(0.0, (_aware_utc(value, name="retry_after") - now).total_seconds())
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("retry_after must be seconds or a timezone-aware datetime")
    seconds = float(value)
    if not math.isfinite(seconds) or not 0 <= seconds <= MAX_RETRY_SECONDS:
        raise ValueError("retry_after is outside the supported range")
    return seconds


def retry_delay_seconds(
    policy: RetryPolicy,
    *,
    attempt: int,
    jitter_value: float,
    retry_after: int | float | datetime | None = None,
    now: datetime | None = None,
) -> float:
    """Calculate bounded equal-jitter delay after one completed attempt."""

    normalized_attempt = _strict_int(attempt, name="attempt", minimum=1, maximum=MAX_POLICY_ATTEMPTS)
    if normalized_attempt >= policy.max_attempts:
        raise ValueError("retry budget is exhausted")
    if isinstance(jitter_value, bool) or not isinstance(jitter_value, (int, float)):
        raise ValueError("jitter_value must be a finite number between zero and one")
    random_fraction = float(jitter_value)
    if not math.isfinite(random_fraction) or not 0 <= random_fraction <= 1:
        raise ValueError("jitter_value must be a finite number between zero and one")

    exponent = normalized_attempt - 1
    exponential = policy.cap_seconds if exponent >= 63 else min(policy.cap_seconds, policy.base_seconds * (2**exponent))
    delay = (exponential / 2.0) + (exponential / 2.0 * random_fraction)
    if retry_after is not None:
        current = _aware_utc(now or datetime.now(UTC), name="now")
        delay = max(delay, _retry_after_seconds(retry_after, now=current))
    if not math.isfinite(delay) or not 0 <= delay <= MAX_RETRY_SECONDS:
        raise ValueError("retry delay is outside the supported range")
    return delay


def retry_at(
    policy: RetryPolicy,
    *,
    attempt: int,
    now: datetime,
    jitter_value: float,
    retry_after: int | float | datetime | None = None,
) -> datetime:
    current = _aware_utc(now, name="now")
    delay = retry_delay_seconds(
        policy,
        attempt=attempt,
        jitter_value=jitter_value,
        retry_after=retry_after,
        now=current,
    )
    return _safe_add(current, delay, name="retry delay")


class FailureDisposition(StrEnum):
    RETRY = "retry"
    WAITING_AUTH = "waiting_auth"
    WAITING_USER = "waiting_user"
    TERMINAL = "terminal"


@dataclass(frozen=True, slots=True)
class FailureClassification:
    code: str
    disposition: FailureDisposition
    affects_circuit: bool


_TEMPORARY_CODES: Final = frozenset(
    {
        "rate_limited",
        "risk_controlled",
        "temporary_upstream",
        "upstream_timeout",
        "upstream_unavailable",
    }
)
_WAITING_AUTH_CODES: Final = frozenset({"auth_expired", "credentials_unavailable"})
_WAITING_USER_CODES: Final = frozenset(
    {"captcha_required", "interactive_required", "license_acknowledgement_required", "qr_required"}
)
_TERMINAL_CODES: Final = frozenset(
    {
        "configuration_invalid",
        "handler_unsupported",
        "output_security_failed",
        "schema_invalid",
        "scheduler_heartbeat_failed",
        "scheduler_heartbeat_storage_busy",
        "scheduler_finalize_failed",
    }
)


def classify_failure(code: str) -> FailureClassification:
    """Classify one fixed handler code without accepting raw exception text."""

    if not isinstance(code, str) or _FIXED_CODE.fullmatch(code) is None:
        code = "unexpected_handler_failure"
    if code in _TEMPORARY_CODES:
        return FailureClassification(code, FailureDisposition.RETRY, True)
    if code == "account_busy":
        return FailureClassification(code, FailureDisposition.RETRY, False)
    if code in _WAITING_AUTH_CODES:
        return FailureClassification(code, FailureDisposition.WAITING_AUTH, True)
    if code in _WAITING_USER_CODES:
        return FailureClassification(code, FailureDisposition.WAITING_USER, False)
    if code in _TERMINAL_CODES:
        return FailureClassification(code, FailureDisposition.TERMINAL, True)
    return FailureClassification("unexpected_handler_failure", FailureDisposition.RETRY, True)


class CircuitState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass(frozen=True, slots=True)
class CircuitSnapshot:
    state: CircuitState = CircuitState.CLOSED
    consecutive_failures: int = 0
    open_until: datetime | None = None
    half_open_job_id: str | None = None

    def __post_init__(self) -> None:
        _strict_int(
            self.consecutive_failures,
            name="consecutive_failures",
            minimum=0,
            maximum=2_147_483_647,
        )
        if self.open_until is not None:
            _aware_utc(self.open_until, name="open_until")
        if self.half_open_job_id is not None and (
            not self.half_open_job_id
            or len(self.half_open_job_id) > 128
            or any(ord(ch) < 0x20 for ch in self.half_open_job_id)
        ):
            raise ValueError("half_open_job_id is invalid")
        if self.state is CircuitState.CLOSED and (self.open_until is not None or self.half_open_job_id is not None):
            raise ValueError("closed circuit cannot retain open state")
        if self.state is CircuitState.OPEN and (self.open_until is None or self.half_open_job_id is not None):
            raise ValueError("open circuit requires only open_until")
        if self.state is CircuitState.HALF_OPEN and (self.open_until is not None or self.half_open_job_id is None):
            raise ValueError("half-open circuit requires one probe job")


@dataclass(frozen=True, slots=True)
class CircuitClaimDecision:
    allowed: bool
    snapshot: CircuitSnapshot
    transition_required: bool = False


def decide_circuit_claim(snapshot: CircuitSnapshot, *, job_id: str, now: datetime) -> CircuitClaimDecision:
    """Return the claim decision and any open-to-half-open CAS target."""

    current = _aware_utc(now, name="now")
    if not job_id or len(job_id) > 128 or any(ord(character) < 0x20 for character in job_id):
        raise ValueError("job_id is invalid")
    if snapshot.state is CircuitState.CLOSED:
        return CircuitClaimDecision(True, snapshot)
    if snapshot.state is CircuitState.HALF_OPEN:
        return CircuitClaimDecision(snapshot.half_open_job_id == job_id, snapshot)
    assert snapshot.open_until is not None
    if snapshot.open_until > current:
        return CircuitClaimDecision(False, snapshot)
    probe = CircuitSnapshot(
        state=CircuitState.HALF_OPEN,
        consecutive_failures=snapshot.consecutive_failures,
        half_open_job_id=job_id,
    )
    return CircuitClaimDecision(True, probe, transition_required=True)


def circuit_success(_snapshot: CircuitSnapshot) -> CircuitSnapshot:
    return CircuitSnapshot()


def circuit_failure(
    snapshot: CircuitSnapshot,
    *,
    now: datetime,
    affects_circuit: bool,
    failure_threshold: int = 3,
    cooldown_seconds: int = 900,
) -> CircuitSnapshot:
    """Apply one classified failure to a circuit snapshot."""

    current = _aware_utc(now, name="now")
    threshold = _strict_int(
        failure_threshold,
        name="failure_threshold",
        minimum=1,
        maximum=2_147_483_647,
    )
    cooldown = _strict_int(
        cooldown_seconds,
        name="cooldown_seconds",
        minimum=1,
        maximum=MAX_COOLDOWN_SECONDS,
    )
    if not affects_circuit:
        return snapshot
    failures = min(2_147_483_647, snapshot.consecutive_failures + 1)
    should_open = snapshot.state is CircuitState.HALF_OPEN or failures >= threshold
    if not should_open:
        return CircuitSnapshot(state=CircuitState.CLOSED, consecutive_failures=failures)
    return CircuitSnapshot(
        state=CircuitState.OPEN,
        consecutive_failures=failures,
        open_until=_safe_add(current, float(cooldown), name="circuit cooldown"),
    )


__all__ = [
    "MAX_RETRY_SECONDS",
    "RETRY_POLICY_SCHEMA_VERSION",
    "CircuitClaimDecision",
    "CircuitSnapshot",
    "CircuitState",
    "FailureClassification",
    "FailureDisposition",
    "RetryPolicy",
    "attempts_remain",
    "circuit_failure",
    "circuit_success",
    "classify_failure",
    "decide_circuit_claim",
    "retry_at",
    "retry_delay_seconds",
]
