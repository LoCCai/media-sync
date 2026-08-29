"""Composite platform adapter contract."""

from typing import Protocol, runtime_checkable

from media_sync.ports.assets import AssetResolverPort
from media_sync.ports.auth import AuthPort
from media_sync.ports.catalog import CatalogPort


@runtime_checkable
class PlatformAdapter(AuthPort, CatalogPort, AssetResolverPort, Protocol):
    """Composition of independently testable auth, catalog and asset ports."""


__all__ = ["PlatformAdapter"]
