"""Bounded, idempotent subscription synchronization orchestration."""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from media_sync.domain import (
    AccountRef,
    AdapterError,
    AuthStatus,
    Cursor,
    DomainError,
    DomainValidationError,
    RunStatus,
)
from media_sync.infrastructure.db import ContentOwnershipConflictError, LeaseLostError
from media_sync.ports import InteractionPort, PlatformAdapter, SyncRepository

_ADAPTER_ERROR_CODES = frozenset(
    {
        "auth_expired",
        "content_not_found",
        "interactive_challenge_required",
        "permanent_upstream",
        "rate_limited",
        "temporary_upstream",
        "upstream_schema_changed",
    }
)
_DOMAIN_ERROR_CODES = frozenset(
    {
        "domain_validation",
        "entity_not_found",
        "invalid_state_transition",
        "unsupported_capability",
    }
)
_MAX_RETRY_AFTER_SECONDS = 604_800


def _closed_error_code(value: object, *, allowed: frozenset[str]) -> str:
    """Return only a code owned by this application boundary."""

    return value if isinstance(value, str) and value in allowed else "unexpected_failure"


def _closed_adapter_error_code(error: AdapterError) -> str:
    """Retain auth/interaction disposition without trusting an open code."""

    if error.requires_interaction is True:
        return "interactive_challenge_required"
    if error.requires_auth is True:
        return "auth_expired"
    return _closed_error_code(error.code, allowed=_ADAPTER_ERROR_CODES)


def _closed_retry_after(value: object) -> float | None:
    """Keep scheduler hints numeric, finite and within the public retry bound."""

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    seconds = float(value)
    if not math.isfinite(seconds) or not 0 <= seconds <= _MAX_RETRY_AFTER_SECONDS:
        return None
    return seconds


@dataclass(frozen=True, slots=True)
class SyncRequest:
    """Inputs that are safe to place in a durable sync-job payload."""

    subscription_id: UUID
    account: AccountRef
    creator_reference: str
    cursor: Cursor | None = None
    max_items: int = 30
    page_size: int = 30
    max_pages: int = 100

    def __post_init__(self) -> None:
        if not self.creator_reference.strip():
            raise DomainValidationError("creator_reference must not be blank", field="creator_reference")
        if not 1 <= self.max_items <= 1_000:
            raise DomainValidationError("max_items must be between 1 and 1000", field="max_items")
        if not 1 <= self.page_size <= 1_000:
            raise DomainValidationError("page_size must be between 1 and 1000", field="page_size")
        if not 1 <= self.max_pages <= 10_000:
            raise DomainValidationError("max_pages must be between 1 and 10000", field="max_pages")


@dataclass(frozen=True, slots=True)
class SyncResult:
    """Redaction-safe outcome of one synchronization attempt."""

    run_id: UUID
    status: RunStatus
    processed_count: int = 0
    asset_count: int = 0
    final_cursor: Cursor | None = None
    watermark: datetime | None = None
    error_code: str | None = None
    retry_after_seconds: float | None = None


class SyncService:
    """Coordinate one adapter and transaction-scoped repository port."""

    def __init__(self, adapter: PlatformAdapter, repository: SyncRepository) -> None:
        self.adapter = adapter
        self.repository = repository

    async def run(
        self,
        request: SyncRequest,
        *,
        interaction: InteractionPort | None = None,
        persistence_guard: Callable[[], None] | None = None,
        external_io_boundary: Callable[[], None] | None = None,
    ) -> SyncResult:
        """Run one sync, with optional short-transaction scheduler hooks.

        Ordinary callers omit both hooks and retain the original single outer
        transaction.  A durable worker can guard each mutation and commit the
        current transaction immediately before an adapter await.
        """

        def guard_persistence() -> None:
            if persistence_guard is not None:
                persistence_guard()

        def before_external_io() -> None:
            if external_io_boundary is not None:
                external_io_boundary()

        capabilities = self.adapter.capabilities()
        if capabilities.platform is not request.account.platform:
            raise DomainValidationError(
                "adapter platform does not match account platform",
                field="account.platform",
            )
        if not capabilities.supports_login(request.account.login_method):
            raise DomainValidationError(
                "account login method is not supported by the adapter",
                field="account.login_method",
            )

        guard_persistence()
        run_id = self.repository.create_run(
            request.subscription_id,
            {
                "adapter": self.adapter.name,
                "platform": request.account.platform.value,
                "max_items": request.max_items,
                "page_size": request.page_size,
            },
        )
        guard_persistence()
        self.repository.transition_run(run_id, RunStatus.CLAIMED)

        try:
            before_external_io()
            auth = await self.adapter.ensure_session(request.account, interaction)
            if auth.status in {AuthStatus.REQUIRED, AuthStatus.AUTHENTICATING}:
                guard_persistence()
                self.repository.transition_run(run_id, RunStatus.AWAITING_AUTH)
                return SyncResult(run_id=run_id, status=RunStatus.AWAITING_AUTH)
            if auth.status is not AuthStatus.AUTHENTICATED:
                guard_persistence()
                self.repository.transition_run(
                    run_id,
                    RunStatus.FAILED_RETRYABLE,
                    error_code="authentication_unavailable",
                    error_message="The adapter could not establish an authenticated session.",
                )
                return SyncResult(
                    run_id=run_id,
                    status=RunStatus.FAILED_RETRYABLE,
                    error_code="authentication_unavailable",
                )

            guard_persistence()
            self.repository.transition_run(run_id, RunStatus.RUNNING)
            before_external_io()
            author = await self.adapter.resolve_author(request.account, request.creator_reference)
            if author.platform is not request.account.platform:
                raise DomainValidationError("resolved author platform mismatch", field="author.platform")
            guard_persistence()
            self.repository.upsert_author(author)
            guard_persistence()
            self.repository.transition_run(run_id, RunStatus.INGESTING)

            processed_ids: set[str] = set()
            visited_cursors: set[str] = set()
            current_cursor = request.cursor
            final_cursor = current_cursor
            watermark: datetime | None = None
            asset_count = 0

            for _page_number in range(request.max_pages):
                if len(processed_ids) >= request.max_items:
                    break
                if current_cursor is not None:
                    if current_cursor.value in visited_cursors:
                        raise DomainValidationError("adapter returned a repeated cursor", field="cursor")
                    visited_cursors.add(current_cursor.value)

                requested_limit = min(request.page_size, request.max_items - len(processed_ids))
                before_external_io()
                page = await self.adapter.fetch_author_page(
                    request.account,
                    author,
                    current_cursor,
                    limit=requested_limit,
                )
                if len(page.items) > requested_limit:
                    raise DomainValidationError(
                        "adapter returned more content than the requested page limit",
                        field="page.items",
                    )
                if page.has_more and page.next_cursor is not None and page.next_cursor.value in visited_cursors:
                    raise DomainValidationError(
                        "adapter returned a repeated cursor",
                        field="cursor",
                    )
                for content in page.items:
                    if content.remote_id in processed_ids:
                        continue
                    if content.platform is not author.platform or content.author_remote_id != author.remote_id:
                        raise DomainValidationError(
                            "adapter returned content outside the resolved author",
                            field="content.author_remote_id",
                        )
                    before_external_io()
                    assets = await self.adapter.resolve_assets(request.account, content)
                    for asset in assets:
                        if asset.content_remote_id != content.remote_id or asset.platform is not content.platform:
                            raise DomainValidationError(
                                "adapter returned an asset outside its content",
                                field="asset.content_remote_id",
                            )
                    guard_persistence()
                    self.repository.upsert_content_with_assets(content, assets)
                    processed_ids.add(content.remote_id)
                    asset_count += len(assets)
                    if content.published_at is not None and (watermark is None or content.published_at > watermark):
                        watermark = content.published_at
                    if len(processed_ids) >= request.max_items:
                        break

                final_cursor = page.next_cursor
                if not page.has_more or len(processed_ids) >= request.max_items:
                    break
                current_cursor = page.next_cursor
            else:
                raise DomainValidationError("adapter exceeded the maximum page count", field="max_pages")

            guard_persistence()
            self.repository.advance_cursor(request.subscription_id, final_cursor, watermark=watermark)
            guard_persistence()
            self.repository.transition_run(run_id, RunStatus.SUCCEEDED)
            return SyncResult(
                run_id=run_id,
                status=RunStatus.SUCCEEDED,
                processed_count=len(processed_ids),
                asset_count=asset_count,
                final_cursor=final_cursor,
                watermark=watermark,
            )
        except LeaseLostError:
            # Ownership fencing must escape unchanged; attempting an error
            # transition would be a second unauthorized persistence attempt.
            raise
        except ContentOwnershipConflictError:
            guard_persistence()
            self.repository.transition_run(
                run_id,
                RunStatus.FAILED_TERMINAL,
                error_code="content_ownership_conflict",
                error_message="Content remains assigned to its existing creator; check the subscription and source.",
            )
            return SyncResult(
                run_id=run_id,
                status=RunStatus.FAILED_TERMINAL,
                error_code="content_ownership_conflict",
            )
        except AdapterError as error:
            if error.requires_auth is True or error.requires_interaction is True:
                target = RunStatus.AWAITING_AUTH
            elif error.retryable is True:
                target = RunStatus.FAILED_RETRYABLE
            else:
                target = RunStatus.FAILED_TERMINAL
            error_code = _closed_adapter_error_code(error)
            guard_persistence()
            self.repository.transition_run(
                run_id,
                target,
                error_code=error_code,
                error_message="The adapter reported a classified synchronization failure.",
            )
            return SyncResult(
                run_id=run_id,
                status=target,
                error_code=error_code,
                retry_after_seconds=_closed_retry_after(error.retry_after),
            )
        except DomainError as error:
            error_code = _closed_error_code(error.code, allowed=_DOMAIN_ERROR_CODES)
            guard_persistence()
            self.repository.transition_run(
                run_id,
                RunStatus.FAILED_TERMINAL,
                error_code=error_code,
                error_message="Synchronization stopped after a classified domain failure.",
            )
            return SyncResult(
                run_id=run_id,
                status=RunStatus.FAILED_TERMINAL,
                error_code=error_code,
            )
        except Exception:
            # Raw exceptions may contain Cookie values or signed URLs. Preserve
            # the class for operators, never the untrusted message.
            guard_persistence()
            self.repository.transition_run(
                run_id,
                RunStatus.FAILED_RETRYABLE,
                error_code="unexpected_failure",
                error_message="Unexpected adapter or persistence failure; inspect redacted worker logs.",
            )
            return SyncResult(
                run_id=run_id,
                status=RunStatus.FAILED_RETRYABLE,
                error_code="unexpected_failure",
            )
