"""Application gate for one immutable media-server profile."""

from __future__ import annotations

from collections.abc import Callable

import httpx

from media_sync.config import MediaServerSafeSummary, Settings
from media_sync.integrations.media_server import (
    MediaServerAddressResolver,
    MediaServerConnector,
    MediaServerLimits,
    MediaServerSecretResolver,
    MediaServerTransportFactory,
)
from media_sync.ports.media_server import (
    MediaServerError,
    MediaServerPort,
    MediaServerProbeResult,
    MediaServerScanResult,
)


class MediaServerService:
    """Enforce the server-side operation gate before connector activity."""

    def __init__(
        self,
        connector: MediaServerPort | None,
        *,
        operations_enabled: bool = False,
        safe_summary: MediaServerSafeSummary | None = None,
    ) -> None:
        if connector is not None and not isinstance(connector, MediaServerPort):
            raise TypeError("connector must implement MediaServerPort")
        if not isinstance(operations_enabled, bool):
            raise TypeError("operations_enabled must be a bool")
        if safe_summary is not None and not isinstance(safe_summary, MediaServerSafeSummary):
            raise TypeError("safe_summary must be a MediaServerSafeSummary")
        self._connector = connector
        self._operations_enabled = operations_enabled
        connector_summary = getattr(connector, "safe_summary", None)
        self._safe_summary = safe_summary or (
            connector_summary if isinstance(connector_summary, MediaServerSafeSummary) else None
        )

    @classmethod
    def from_settings(
        cls,
        settings: Settings,
        secret_resolver: MediaServerSecretResolver,
        *,
        resolver: MediaServerAddressResolver | None = None,
        transport_factory: MediaServerTransportFactory | None = None,
        transport: httpx.BaseTransport | None = None,
        limits: MediaServerLimits | None = None,
        monotonic: Callable[[], float] | None = None,
    ) -> MediaServerService:
        """Compose the service without resolving credentials or touching the network."""

        if not isinstance(settings, Settings):
            raise TypeError("settings must be Settings")
        profile = settings.media_server_profile
        if profile is None:
            return cls(
                None,
                operations_enabled=False,
                safe_summary=settings.media_server_safe_summary,
            )
        connector_kwargs: dict[str, object] = {
            "resolver": resolver,
            "transport_factory": transport_factory,
            "transport": transport,
            "limits": limits,
        }
        if monotonic is not None:
            connector_kwargs["monotonic"] = monotonic
        connector = MediaServerConnector(
            profile,
            secret_resolver,
            **connector_kwargs,  # type: ignore[arg-type]
        )
        return cls(
            connector,
            operations_enabled=settings.media_server_operations_enabled,
            safe_summary=settings.media_server_safe_summary,
        )

    @property
    def configured(self) -> bool:
        return self._connector is not None

    @property
    def operations_enabled(self) -> bool:
        return self._operations_enabled

    @property
    def profile_fingerprint(self) -> str | None:
        connector = self._connector
        return connector.profile_fingerprint if connector is not None else None

    @property
    def safe_summary(self) -> MediaServerSafeSummary | None:
        return self._safe_summary

    def probe(self) -> MediaServerProbeResult:
        """Run the bounded read-only probe only when the server-side gate is open."""

        return self._require_connector().probe()

    def scan(self, cancel_requested: Callable[[], bool]) -> MediaServerScanResult:
        """Submit one targeted refresh; cancellation belongs to the connector boundary."""

        if not callable(cancel_requested):
            raise TypeError("cancel_requested must be callable")
        return self._require_connector().scan(cancel_requested)

    def _require_connector(self) -> MediaServerPort:
        if self._connector is None:
            raise MediaServerError("media_server_not_configured")
        if not self._operations_enabled:
            raise MediaServerError("media_server_operations_disabled")
        return self._connector


__all__ = [
    "MediaServerError",
    "MediaServerProbeResult",
    "MediaServerScanResult",
    "MediaServerService",
]
