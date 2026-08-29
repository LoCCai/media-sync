"""Minimal persistence port required by the first synchronization use case."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Protocol, runtime_checkable
from uuid import UUID

from media_sync.domain import (
    AssetSnapshot,
    AuthorSnapshot,
    ContentSnapshot,
    Cursor,
    RunStatus,
)


@runtime_checkable
class SyncRepository(Protocol):
    """Transaction-scoped normalized persistence, independent of any ORM."""

    def upsert_author(self, snapshot: AuthorSnapshot) -> UUID:
        """Atomically insert or refresh an author and return its local ID."""
        ...

    def upsert_content_with_assets(
        self,
        snapshot: ContentSnapshot,
        assets: Sequence[AssetSnapshot],
    ) -> UUID:
        """Atomically upsert content and its ordered discovered assets."""
        ...

    def create_run(
        self,
        subscription_id: UUID,
        manifest: Mapping[str, object] | None = None,
    ) -> UUID:
        """Create a queued sync run with a redaction-safe manifest."""
        ...

    def transition_run(
        self,
        run_id: UUID,
        target: RunStatus,
        *,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> None:
        """Persist a validated run transition and optional classified error."""
        ...

    def advance_cursor(
        self,
        subscription_id: UUID,
        cursor: Cursor | None,
        *,
        watermark: datetime | None = None,
    ) -> None:
        """Advance the subscription cursor and publish-time watermark atomically."""
        ...


__all__ = ["SyncRepository"]
