from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest

from media_sync.application.media_server import MediaServerService
from media_sync.config import Settings
from media_sync.ports.media_server import (
    MediaServerError,
    MediaServerItemLookupResult,
    MediaServerLookupTarget,
    MediaServerProbeResult,
    MediaServerScanResult,
)
from media_sync.security.secrets import SecretReference, SecretValue


class _Connector:
    profile_fingerprint = "f" * 64

    def __init__(self) -> None:
        self.probe_calls = 0
        self.scan_calls = 0
        self.observation_scan_calls = 0
        self.observation_deadlines: list[float] = []
        self.lookup_calls = 0
        self.lookup_deadlines: list[float] = []

    def probe(self) -> MediaServerProbeResult:
        self.probe_calls += 1
        return MediaServerProbeResult("emby", "4.8.0", "a" * 64)

    def scan(self, cancel_requested: Callable[[], bool]) -> MediaServerScanResult:
        self.scan_calls += 1
        assert cancel_requested() is False
        return MediaServerScanResult("emby", "4.8.0", "a" * 64)

    def lookup_item(
        self,
        target: MediaServerLookupTarget,
        *,
        deadline: float | None = None,
    ) -> MediaServerItemLookupResult:
        self.lookup_calls += 1
        if deadline is not None:
            self.lookup_deadlines.append(deadline)
        assert target.provider_key == "media-sync-xhs-creator"
        return MediaServerItemLookupResult(
            "not_found",
            inspected_item_count=0,
            page_count=1,
            response_byte_count=2,
            item_id_set_fingerprint="b" * 64,
        )

    def scan_observation(
        self,
        cancel_requested: Callable[[], bool],
        before_transport_entry: Callable[[], bool],
        *,
        deadline: float | None = None,
    ) -> MediaServerScanResult:
        self.observation_scan_calls += 1
        if deadline is not None:
            self.observation_deadlines.append(deadline)
        assert cancel_requested() is False
        assert before_transport_entry() is True
        return MediaServerScanResult("emby", "4.8.0", "a" * 64)


class _Resolver:
    def resolve(self, _hostname: str, _port: int) -> tuple[str, ...]:
        return ("127.0.0.1",)


class _Secrets:
    def __init__(self) -> None:
        self.calls = 0

    def resolve(self, _reference: SecretReference | str) -> SecretValue:
        self.calls += 1
        return SecretValue("private-key-sentinel")


def _configured_settings(*, enabled: bool) -> Settings:
    return Settings(
        media_server_provider="emby",
        media_server_base_url="http://127.0.0.1:8096",
        media_server_library_id="library",
        media_server_api_key_secret_ref="env:SERVER_KEY",
        media_server_library_path="/srv/media",
        media_server_allowed_cidrs=("127.0.0.1/32",),
        media_server_operations_enabled=enabled,
        _env_file=None,
    )


def test_service_operation_gate_is_default_off_and_precedes_connector_calls() -> None:
    connector = _Connector()
    service = MediaServerService(connector)

    assert service.configured is True
    assert service.operations_enabled is False
    assert service.profile_fingerprint == "f" * 64
    with pytest.raises(MediaServerError) as caught:
        service.probe()
    assert caught.value.code == "media_server_operations_disabled"
    with pytest.raises(MediaServerError) as caught:
        service.scan(lambda: False)
    assert caught.value.code == "media_server_operations_disabled"
    with pytest.raises(MediaServerError) as caught:
        service.lookup_item(MediaServerLookupTarget("media-sync-xhs-creator", "remote", "/srv/media/author"))
    assert caught.value.code == "media_server_operations_disabled"
    with pytest.raises(MediaServerError) as caught:
        service.scan_observation(lambda: False, lambda: True)
    assert caught.value.code == "media_server_operations_disabled"
    assert connector.probe_calls == 0
    assert connector.scan_calls == 0
    assert connector.lookup_calls == 0


def test_service_delegates_probe_scan_lookup_and_observation_when_gate_is_open() -> None:
    connector = _Connector()
    service = MediaServerService(connector, operations_enabled=True)

    assert service.probe() == MediaServerProbeResult("emby", "4.8.0", "a" * 64)
    assert service.scan(lambda: False) == MediaServerScanResult("emby", "4.8.0", "a" * 64)
    target = MediaServerLookupTarget("media-sync-xhs-creator", "remote", "/srv/media/author")
    assert service.lookup_item(target).lookup_state == "not_found"
    assert service.scan_observation(lambda: False, lambda: True).scan_state == "accepted"
    assert service.lookup_item(target, deadline=123.0).lookup_state == "not_found"
    assert service.scan_observation(lambda: False, lambda: True, deadline=456.0).scan_state == "accepted"
    assert connector.probe_calls == 1
    assert connector.scan_calls == 1
    assert connector.lookup_calls == 2
    assert connector.lookup_deadlines == [123.0]
    assert connector.observation_scan_calls == 2
    assert connector.observation_deadlines == [456.0]


def test_unconfigured_service_fails_before_operation_gate() -> None:
    service = MediaServerService(None, operations_enabled=True)

    assert service.configured is False
    assert service.profile_fingerprint is None
    with pytest.raises(MediaServerError) as caught:
        service.probe()
    assert caught.value.code == "media_server_not_configured"
    with pytest.raises(MediaServerError) as caught:
        service.lookup_item(MediaServerLookupTarget("media-sync-xhs-creator", "remote", "/srv/media/author"))
    assert caught.value.code == "media_server_not_configured"
    with pytest.raises(MediaServerError) as caught:
        service.scan_observation(lambda: False, lambda: True)
    assert caught.value.code == "media_server_not_configured"


def test_from_settings_is_network_and_secret_free_until_an_enabled_operation() -> None:
    secrets = _Secrets()
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/System/Info":
            return httpx.Response(200, json={"ProductName": "Emby Server", "Version": "4.8.0"})
        return httpx.Response(200, json=[{"ItemId": "library", "Locations": ["/srv/media"]}])

    disabled = MediaServerService.from_settings(
        _configured_settings(enabled=False),
        secrets,
        resolver=_Resolver(),
        transport=httpx.MockTransport(handler),
    )
    assert disabled.safe_summary is not None
    assert disabled.safe_summary.operations_enabled is False
    assert secrets.calls == 0
    assert requests == []
    with pytest.raises(MediaServerError) as caught:
        disabled.probe()
    assert caught.value.code == "media_server_operations_disabled"
    assert secrets.calls == 0
    assert requests == []

    enabled = MediaServerService.from_settings(
        _configured_settings(enabled=True),
        secrets,
        resolver=_Resolver(),
        transport=httpx.MockTransport(handler),
    )
    assert enabled.probe().library_present is True
    assert [request.url.path for request in requests] == ["/System/Info", "/Library/VirtualFolders"]
    assert secrets.calls == 2


def test_from_unconfigured_settings_exposes_explicit_safe_summary() -> None:
    service = MediaServerService.from_settings(Settings(_env_file=None), _Secrets())

    assert service.configured is False
    assert service.safe_summary is not None
    assert service.safe_summary.as_dict()["configured"] is False
    with pytest.raises(MediaServerError) as caught:
        service.probe()
    assert caught.value.code == "media_server_not_configured"
