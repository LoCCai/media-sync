"""Normalized content-asset discovery port."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from media_sync.domain import AccountRef, AssetSnapshot, CapabilitySet, ContentSnapshot


@runtime_checkable
class AssetResolverPort(Protocol):
    """Resolve ordered remote assets without downloading them."""

    @property
    def name(self) -> str:
        """Return the stable adapter implementation name."""
        ...

    def capabilities(self) -> CapabilitySet:
        """Return qualified capabilities for this adapter instance."""
        ...

    async def resolve_assets(
        self,
        account: AccountRef,
        content: ContentSnapshot,
    ) -> tuple[AssetSnapshot, ...]:
        """Return deterministically ordered asset snapshots for one item."""
        ...


__all__ = ["AssetResolverPort"]
