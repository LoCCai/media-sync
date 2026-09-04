"""Application-facing ports for platform and persistence adapters."""

from media_sync.ports.assets import AssetResolverPort
from media_sync.ports.auth import AuthPort, InteractionPort
from media_sync.ports.catalog import CatalogPort
from media_sync.ports.media_server import (
    MediaServerError,
    MediaServerItemLookupResult,
    MediaServerLookupPort,
    MediaServerLookupTarget,
    MediaServerPort,
    MediaServerProbeResult,
    MediaServerProvider,
    MediaServerScanResult,
    validate_media_server_version,
)
from media_sync.ports.platform import PlatformAdapter
from media_sync.ports.repositories import SyncRepository

__all__ = [
    "AssetResolverPort",
    "AuthPort",
    "CatalogPort",
    "InteractionPort",
    "MediaServerError",
    "MediaServerItemLookupResult",
    "MediaServerLookupPort",
    "MediaServerLookupTarget",
    "MediaServerPort",
    "MediaServerProbeResult",
    "MediaServerProvider",
    "MediaServerScanResult",
    "PlatformAdapter",
    "SyncRepository",
    "validate_media_server_version",
]
