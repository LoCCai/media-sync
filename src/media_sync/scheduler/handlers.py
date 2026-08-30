"""Closed subscription-handler contracts and the deterministic Fake handler."""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from inspect import iscoroutinefunction
from types import MappingProxyType
from typing import Protocol, runtime_checkable
from uuid import UUID

from sqlalchemy.orm import Session

from media_sync.adapters.fake import FakePlatformAdapter
from media_sync.application.sync import SyncRequest, SyncService
from media_sync.domain import AccountRef, Cursor, LoginMethod, Platform, RunStatus
from media_sync.infrastructure.db import Database, LeaseLostError, SQLAlchemySyncRepository
from media_sync.ports import PlatformAdapter

from .policy import MAX_RETRY_SECONDS, FailureDisposition, classify_failure

_HANDLER_KEY = re.compile(r"[a-z][a-z0-9_.-]{0,127}\Z")

RetryAfter = int | float


def _required_text(value: str, *, name: str, maximum: int) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} is invalid")
    normalized = value.strip()
    if (
        not normalized
        or len(normalized) > maximum
        or any(ord(character) < 0x20 or ord(character) == 0x7F for character in normalized)
    ):
        raise ValueError(f"{name} is invalid")
    return normalized


def _bounded_int(value: int, *, name: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be an integer between {minimum} and {maximum}")
    return value


@dataclass(frozen=True, slots=True)
class SubscriptionJobContext:
    """In-memory handler input; none of these values are copied to Job payloads."""

    job_id: UUID
    subscription_id: UUID
    account: AccountRef
    creator_reference: str = field(repr=False)
    cursor: Cursor | None = field(default=None, repr=False)
    subscription_policy: Mapping[str, object] = field(
        default_factory=lambda: MappingProxyType({}),
        repr=False,
    )
    schedule_revision: int = 0
    max_items: int = 30
    attempt: int = 1
    current_run_id: UUID | None = None
    ownership_guard: Callable[[Session], None] | None = field(default=None, repr=False, compare=False)
    run_attacher: Callable[[Session, UUID, UUID | None], None] | None = field(
        default=None,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        if not isinstance(self.job_id, UUID) or not isinstance(self.subscription_id, UUID):
            raise ValueError("job_id and subscription_id must be UUID values")
        if not isinstance(self.account, AccountRef):
            raise ValueError("account must be an AccountRef")
        if self.cursor is not None and not isinstance(self.cursor, Cursor):
            raise ValueError("cursor must be a Cursor")
        if not isinstance(self.subscription_policy, Mapping):
            raise ValueError("subscription_policy must be a mapping")
        if self.ownership_guard is not None and not callable(self.ownership_guard):
            raise ValueError("ownership_guard must be callable")
        if self.current_run_id is not None and not isinstance(self.current_run_id, UUID):
            raise ValueError("current_run_id must be a UUID")
        if self.run_attacher is not None and not callable(self.run_attacher):
            raise ValueError("run_attacher must be callable")
        object.__setattr__(
            self,
            "creator_reference",
            _required_text(self.creator_reference, name="creator_reference", maximum=2_048),
        )
        object.__setattr__(
            self,
            "subscription_policy",
            MappingProxyType(dict(self.subscription_policy)),
        )
        _bounded_int(self.schedule_revision, name="schedule_revision", minimum=0, maximum=2_147_483_647)
        _bounded_int(self.max_items, name="max_items", minimum=1, maximum=1_000)
        _bounded_int(self.attempt, name="attempt", minimum=1, maximum=100)


@dataclass(frozen=True, slots=True)
class SubscriptionHandlerResult:
    """Redaction-safe result returned by one closed subscription handler."""

    succeeded: bool
    run_id: UUID | None = None
    error_code: str | None = None
    retry_after: RetryAfter | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.succeeded, bool):
            raise ValueError("succeeded must be a boolean")
        if self.run_id is not None and not isinstance(self.run_id, UUID):
            raise ValueError("run_id must be a UUID")
        if self.succeeded:
            if self.error_code is not None or self.retry_after is not None:
                raise ValueError("successful handler results cannot carry failure fields")
            return
        if self.error_code is None:
            raise ValueError("failed handler results require a fixed error code")
        classified = classify_failure(self.error_code)
        if classified.code != self.error_code:
            raise ValueError("handler error_code is outside the closed scheduler vocabulary")
        if self.retry_after is not None:
            if classified.disposition is not FailureDisposition.RETRY:
                raise ValueError("retry_after is valid only for retryable handler failures")
            if (
                isinstance(self.retry_after, bool)
                or not isinstance(self.retry_after, (int, float))
                or not math.isfinite(float(self.retry_after))
                or not 0 <= float(self.retry_after) <= MAX_RETRY_SECONDS
            ):
                raise ValueError("retry_after seconds are outside the supported range")

    @classmethod
    def success(cls, run_id: UUID | None = None) -> SubscriptionHandlerResult:
        return cls(succeeded=True, run_id=run_id)

    @classmethod
    def failure(
        cls,
        error_code: str,
        *,
        run_id: UUID | None = None,
        retry_after: RetryAfter | None = None,
    ) -> SubscriptionHandlerResult:
        return cls(
            succeeded=False,
            run_id=run_id,
            error_code=error_code,
            retry_after=retry_after,
        )


@runtime_checkable
class SubscriptionHandler(Protocol):
    """One scheduler-safe subscription implementation."""

    async def run(self, context: SubscriptionJobContext) -> SubscriptionHandlerResult:
        """Execute one attempt without owning the scheduler lease transaction."""


class SubscriptionHandlerRegistry:
    """Immutable handler map; execution 0006 intentionally has no dynamic registration."""

    def __init__(self, handlers: Mapping[str, SubscriptionHandler]) -> None:
        normalized: dict[str, SubscriptionHandler] = {}
        for raw_key, handler in handlers.items():
            if not isinstance(raw_key, str):
                raise ValueError("handler key is invalid")
            key = raw_key.strip()
            if _HANDLER_KEY.fullmatch(key) is None:
                raise ValueError("handler key is invalid")
            if not isinstance(handler, SubscriptionHandler):
                raise TypeError(f"handler {key!r} does not implement SubscriptionHandler")
            if not iscoroutinefunction(handler.run):
                raise TypeError(f"handler {key!r} run method must be async")
            if key in normalized:
                raise ValueError(f"duplicate handler key: {key}")
            normalized[key] = handler
        self._handlers: Mapping[str, SubscriptionHandler] = MappingProxyType(normalized)

    @classmethod
    def fake_only(cls, database: Database) -> SubscriptionHandlerRegistry:
        return cls({"fake": FakeSubscriptionHandler(database)})

    def resolve(self, key: str) -> SubscriptionHandler | None:
        if not isinstance(key, str) or _HANDLER_KEY.fullmatch(key) is None:
            return None
        return self._handlers.get(key)

    @property
    def keys(self) -> tuple[str, ...]:
        return tuple(sorted(self._handlers))


class FakeSubscriptionHandler:
    """Run the existing application SyncService against its offline Fake adapter."""

    def __init__(
        self,
        database: Database,
        *,
        adapter_factory: Callable[[Platform], PlatformAdapter] = FakePlatformAdapter,
    ) -> None:
        self.database = database
        self.adapter_factory = adapter_factory

    async def run(self, context: SubscriptionJobContext) -> SubscriptionHandlerResult:
        request = SyncRequest(
            subscription_id=context.subscription_id,
            account=context.account,
            creator_reference=context.creator_reference,
            cursor=context.cursor,
            max_items=context.max_items,
            page_size=min(context.max_items, 30),
        )
        try:
            with self.database.session() as session:

                def guard_persistence() -> None:
                    if context.ownership_guard is not None:
                        context.ownership_guard(session)

                result = await SyncService(
                    self.adapter_factory(context.account.platform),
                    SQLAlchemySyncRepository(session),
                ).run(
                    request,
                    persistence_guard=guard_persistence,
                    external_io_boundary=session.commit,
                )
        except LeaseLostError:
            raise
        except Exception:
            # Database and adapter exceptions may contain paths, signed URLs or
            # credential material.  The scheduler persists only this fixed code.
            return SubscriptionHandlerResult.failure("unexpected_handler_failure")

        if result.status is RunStatus.SUCCEEDED:
            return SubscriptionHandlerResult.success(result.run_id)
        if result.status is RunStatus.AWAITING_AUTH:
            if result.error_code == "interactive_challenge_required":
                error_code = "interactive_required"
            elif result.error_code == "auth_expired":
                error_code = "auth_expired"
            else:
                error_code = "qr_required" if context.account.login_method is LoginMethod.QR else "auth_expired"
            return SubscriptionHandlerResult.failure(error_code, run_id=result.run_id)
        if result.status is RunStatus.FAILED_TERMINAL:
            if result.error_code in {"entity_not_found", "content_not_found", "permanent_upstream"}:
                error_code = "configuration_invalid"
            elif result.error_code == "unsupported_capability":
                error_code = "handler_unsupported"
            else:
                error_code = "schema_invalid"
            return SubscriptionHandlerResult.failure(error_code, run_id=result.run_id)
        if result.status is RunStatus.FAILED_RETRYABLE:
            if result.error_code == "authentication_unavailable":
                return SubscriptionHandlerResult.failure("credentials_unavailable", run_id=result.run_id)
            classified = classify_failure(result.error_code or "")
            error_code = (
                classified.code if classified.disposition is FailureDisposition.RETRY else "unexpected_handler_failure"
            )
            return SubscriptionHandlerResult.failure(
                error_code,
                run_id=result.run_id,
                retry_after=result.retry_after_seconds,
            )
        return SubscriptionHandlerResult.failure("unexpected_handler_failure", run_id=result.run_id)


__all__ = [
    "FakeSubscriptionHandler",
    "RetryAfter",
    "SubscriptionHandler",
    "SubscriptionHandlerRegistry",
    "SubscriptionHandlerResult",
    "SubscriptionJobContext",
]
