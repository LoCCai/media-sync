"""Creator discovery and normalized catalog ports."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from media_sync.domain import AccountRef, AuthorSnapshot, CapabilitySet, ContentSnapshot, Cursor, Page


@runtime_checkable
class CatalogPort(Protocol):
    """Resolve creators and fetch bounded, cursor-addressable content pages."""

    @property
    def name(self) -> str:
        """Return the stable adapter implementation name."""
        ...

    def capabilities(self) -> CapabilitySet:
        """Return qualified capabilities for this adapter instance."""
        ...

    async def resolve_author(self, account: AccountRef, reference: str) -> AuthorSnapshot:
        """Resolve a platform ID or canonical profile URL."""
        ...

    async def fetch_author_page(
        self,
        account: AccountRef,
        author: AuthorSnapshot,
        cursor: Cursor | None,
        *,
        limit: int,
    ) -> Page[ContentSnapshot]:
        """Fetch one bounded page without applying persistence-side deduplication."""
        ...


__all__ = ["CatalogPort"]
