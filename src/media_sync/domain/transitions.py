"""Validated state transitions for durable domain lifecycles."""

from __future__ import annotations

from collections.abc import Mapping, Set
from typing import TypeVar

from media_sync.domain.enums import AssetStatus, AuthStatus, JobStatus, RunStatus
from media_sync.domain.errors import InvalidStateTransitionError

StateT = TypeVar("StateT", AssetStatus, AuthStatus, JobStatus, RunStatus)

RUN_TRANSITIONS: Mapping[RunStatus, frozenset[RunStatus]] = {
    RunStatus.QUEUED: frozenset({RunStatus.CLAIMED, RunStatus.CANCELLED}),
    RunStatus.CLAIMED: frozenset(
        {
            RunStatus.AWAITING_AUTH,
            RunStatus.RUNNING,
            RunStatus.FAILED_RETRYABLE,
            RunStatus.FAILED_TERMINAL,
            RunStatus.CANCELLED,
        }
    ),
    RunStatus.AWAITING_AUTH: frozenset(
        {
            RunStatus.RUNNING,
            RunStatus.FAILED_RETRYABLE,
            RunStatus.FAILED_TERMINAL,
            RunStatus.CANCELLED,
        }
    ),
    RunStatus.RUNNING: frozenset(
        {
            RunStatus.AWAITING_AUTH,
            RunStatus.INGESTING,
            RunStatus.FAILED_RETRYABLE,
            RunStatus.FAILED_TERMINAL,
            RunStatus.CANCELLED,
        }
    ),
    RunStatus.INGESTING: frozenset(
        {
            RunStatus.AWAITING_AUTH,
            RunStatus.SUCCEEDED,
            RunStatus.FAILED_RETRYABLE,
            RunStatus.FAILED_TERMINAL,
            RunStatus.CANCELLED,
        }
    ),
    RunStatus.FAILED_RETRYABLE: frozenset({RunStatus.QUEUED, RunStatus.CANCELLED}),
    RunStatus.SUCCEEDED: frozenset(),
    RunStatus.FAILED_TERMINAL: frozenset(),
    RunStatus.CANCELLED: frozenset(),
}

ASSET_TRANSITIONS: Mapping[AssetStatus, frozenset[AssetStatus]] = {
    AssetStatus.DISCOVERED: frozenset({AssetStatus.QUEUED, AssetStatus.FAILED_RETRYABLE, AssetStatus.FAILED_TERMINAL}),
    AssetStatus.QUEUED: frozenset({AssetStatus.DOWNLOADING, AssetStatus.FAILED_RETRYABLE, AssetStatus.FAILED_TERMINAL}),
    AssetStatus.DOWNLOADING: frozenset(
        {AssetStatus.DOWNLOADED, AssetStatus.FAILED_RETRYABLE, AssetStatus.FAILED_TERMINAL}
    ),
    AssetStatus.DOWNLOADED: frozenset(
        {AssetStatus.VERIFIED, AssetStatus.FAILED_RETRYABLE, AssetStatus.FAILED_TERMINAL}
    ),
    AssetStatus.VERIFIED: frozenset({AssetStatus.EXPORTED, AssetStatus.FAILED_RETRYABLE, AssetStatus.FAILED_TERMINAL}),
    AssetStatus.FAILED_RETRYABLE: frozenset({AssetStatus.QUEUED}),
    AssetStatus.EXPORTED: frozenset(),
    AssetStatus.FAILED_TERMINAL: frozenset(),
}

JOB_TRANSITIONS: Mapping[JobStatus, frozenset[JobStatus]] = {
    JobStatus.QUEUED: frozenset({JobStatus.CLAIMED, JobStatus.CANCELLED}),
    JobStatus.CLAIMED: frozenset(
        {
            JobStatus.RUNNING,
            JobStatus.RETRY_WAIT,
            JobStatus.WAITING_AUTH,
            JobStatus.WAITING_USER,
            JobStatus.FAILED_RETRYABLE,
            JobStatus.FAILED_TERMINAL,
            JobStatus.CANCELLED,
        }
    ),
    JobStatus.RUNNING: frozenset(
        {
            JobStatus.SUCCEEDED,
            JobStatus.RETRY_WAIT,
            JobStatus.WAITING_AUTH,
            JobStatus.WAITING_USER,
            JobStatus.FAILED_RETRYABLE,
            JobStatus.FAILED_TERMINAL,
            JobStatus.CANCELLED,
        }
    ),
    JobStatus.RETRY_WAIT: frozenset({JobStatus.QUEUED, JobStatus.CANCELLED}),
    JobStatus.WAITING_AUTH: frozenset({JobStatus.QUEUED, JobStatus.CANCELLED}),
    JobStatus.WAITING_USER: frozenset({JobStatus.QUEUED, JobStatus.CANCELLED}),
    JobStatus.FAILED_RETRYABLE: frozenset({JobStatus.QUEUED, JobStatus.CANCELLED}),
    JobStatus.SUCCEEDED: frozenset(),
    JobStatus.FAILED_TERMINAL: frozenset(),
    JobStatus.CANCELLED: frozenset(),
}

AUTH_TRANSITIONS: Mapping[AuthStatus, frozenset[AuthStatus]] = {
    AuthStatus.UNKNOWN: frozenset(
        {AuthStatus.REQUIRED, AuthStatus.AUTHENTICATING, AuthStatus.AUTHENTICATED, AuthStatus.EXPIRED}
    ),
    AuthStatus.REQUIRED: frozenset({AuthStatus.AUTHENTICATING, AuthStatus.FAILED}),
    AuthStatus.AUTHENTICATING: frozenset({AuthStatus.AUTHENTICATED, AuthStatus.REQUIRED, AuthStatus.FAILED}),
    AuthStatus.AUTHENTICATED: frozenset({AuthStatus.EXPIRED}),
    AuthStatus.EXPIRED: frozenset({AuthStatus.REQUIRED, AuthStatus.AUTHENTICATING}),
    AuthStatus.FAILED: frozenset({AuthStatus.REQUIRED, AuthStatus.AUTHENTICATING}),
}


def _validated_transition(
    entity: str,
    current: StateT,
    target: StateT,
    allowed: Mapping[StateT, Set[StateT]],
) -> StateT:
    if target not in allowed[current]:
        raise InvalidStateTransitionError(entity, current.value, target.value)
    return target


def transition_run(current: RunStatus, target: RunStatus) -> RunStatus:
    """Validate and return a sync-run transition target."""

    return _validated_transition("sync_run", current, target, RUN_TRANSITIONS)


def transition_asset(current: AssetStatus, target: AssetStatus) -> AssetStatus:
    """Validate and return an asset transition target."""

    return _validated_transition("asset", current, target, ASSET_TRANSITIONS)


def transition_job(current: JobStatus, target: JobStatus) -> JobStatus:
    """Validate and return a job transition target."""

    return _validated_transition("job", current, target, JOB_TRANSITIONS)


def transition_auth(current: AuthStatus, target: AuthStatus) -> AuthStatus:
    """Validate and return an authentication transition target."""

    return _validated_transition("auth", current, target, AUTH_TRANSITIONS)


__all__ = [
    "ASSET_TRANSITIONS",
    "AUTH_TRANSITIONS",
    "JOB_TRANSITIONS",
    "RUN_TRANSITIONS",
    "transition_asset",
    "transition_auth",
    "transition_job",
    "transition_run",
]
