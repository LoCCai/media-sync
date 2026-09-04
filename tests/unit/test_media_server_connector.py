from __future__ import annotations

import json
import logging
import threading
import time
from collections.abc import Callable, Sequence
from urllib.parse import quote

import httpx
import pytest

from media_sync.config import MediaServerProfile
from media_sync.integrations.media_server import (
    MediaServerAddressResolver,
    MediaServerConnector,
    MediaServerLimits,
    MediaServerTarget,
)
from media_sync.ports.media_server import (
    MediaServerError,
    MediaServerItemLookupResult,
    MediaServerLookupTarget,
    MediaServerProbeResult,
    MediaServerScanResult,
)
from media_sync.security.secrets import SecretReference, SecretResolutionError, SecretValue


class _Resolver:
    def __init__(self, answers: Sequence[str] = ("10.20.30.5",)) -> None:
        self.answers = answers
        self.calls: list[tuple[str, int]] = []

    def resolve(self, hostname: str, port: int) -> Sequence[str]:
        self.calls.append((hostname, port))
        return self.answers


class _Secrets:
    def __init__(self, value: str = "api-key-private-sentinel") -> None:
        self.value = value
        self.calls: list[SecretReference | str] = []

    def resolve(self, reference: SecretReference | str) -> SecretValue:
        self.calls.append(reference)
        return SecretValue(self.value)


class _UnavailableSecrets:
    def resolve(self, _reference: SecretReference | str) -> SecretValue:
        raise SecretResolutionError("provider details must stay private")


class _BlockingResolver:
    def __init__(self) -> None:
        self.entered = threading.Event()
        self.release = threading.Event()
        self.returned = threading.Event()

    def resolve(self, _hostname: str, _port: int) -> Sequence[str]:
        self.entered.set()
        self.release.wait(5)
        self.returned.set()
        return ("10.20.30.5",)


class _BlockingSecrets:
    def __init__(self) -> None:
        self.entered = threading.Event()
        self.release = threading.Event()
        self.returned = threading.Event()

    def resolve(self, _reference: SecretReference | str) -> SecretValue:
        self.entered.set()
        self.release.wait(5)
        self.returned.set()
        return SecretValue("api-key-private-sentinel")


class _CloseFailingResponse(httpx.Response):
    def close(self) -> None:
        raise RuntimeError("close-private-sentinel")


def _profile(**overrides: object) -> MediaServerProfile:
    values: dict[str, object] = {
        "provider": "emby",
        "origin": "https://media.example:8443",
        "library_id": "library_123",
        "api_key_secret_reference": SecretReference.parse("env:SERVER_API_KEY_SENTINEL"),
        "library_path": "/srv/media/private-path-sentinel",
        "allowed_networks": ("10.0.0.0/8",),
        "verify_tls": True,
        "timeout_seconds": 10.0,
        "operations_enabled": True,
    }
    values.update(overrides)
    return MediaServerProfile(**values)  # type: ignore[arg-type]


def _system(provider: str = "emby", version: str = "4.8.10.0") -> httpx.Response:
    product = "Emby Server" if provider == "emby" else "Jellyfin Server"
    return httpx.Response(200, json={"ProductName": product, "Version": version})


def _folders(*items: object) -> httpx.Response:
    payload = list(items) or [
        {
            "ItemId": "library_123",
            "Name": "Private remote name is ignored",
            "Locations": ["/srv/media/private-path-sentinel"],
        }
    ]
    return httpx.Response(200, json=payload)


def _connector(
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    profile: MediaServerProfile | None = None,
    resolver: MediaServerAddressResolver | None = None,
    secrets: object | None = None,
    targets: list[MediaServerTarget] | None = None,
    limits: MediaServerLimits | None = None,
    monotonic: Callable[[], float] | None = None,
) -> MediaServerConnector:
    def factory(target: MediaServerTarget) -> httpx.BaseTransport:
        if targets is not None:
            targets.append(target)
        return httpx.MockTransport(handler)

    kwargs: dict[str, object] = {
        "resolver": resolver or _Resolver(),
        "transport_factory": factory,
        "limits": limits,
    }
    if monotonic is not None:
        kwargs["monotonic"] = monotonic
    return MediaServerConnector(
        profile or _profile(),
        secrets or _Secrets(),  # type: ignore[arg-type]
        **kwargs,  # type: ignore[arg-type]
    )


def _lookup_target(**overrides: str) -> MediaServerLookupTarget:
    values = {
        "provider_key": "media-sync-bili-creator",
        "provider_value": "creator-private-id-42",
        "server_path": "/srv/media/private-path-sentinel/bili-author-private-dir",
    }
    values.update(overrides)
    return MediaServerLookupTarget(**values)


def test_probe_uses_only_fixed_gets_with_pinned_host_and_final_auth_header() -> None:
    requests: list[httpx.Request] = []
    targets: list[MediaServerTarget] = []
    resolver = _Resolver(("10.20.30.8", "10.20.30.4"))
    secrets = _Secrets()

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/System/Info":
            return _system()
        if request.url.path == "/Library/VirtualFolders":
            return _folders()
        raise AssertionError("unexpected route")

    connector = _connector(handler, resolver=resolver, secrets=secrets, targets=targets)
    result = connector.probe()

    assert result == MediaServerProbeResult(
        provider="emby",
        server_version="4.8.10.0",
        library_id_digest=_profile().library_id_digest,
    )
    assert [(request.method, request.url.path, request.url.query) for request in requests] == [
        ("GET", "/System/Info", b""),
        ("GET", "/Library/VirtualFolders", b""),
    ]
    assert all(request.url.scheme == "https" and request.url.host == "media.example" for request in requests)
    assert all(request.headers["host"] == "media.example:8443" for request in requests)
    assert all(request.headers["x-emby-token"] == secrets.value for request in requests)
    assert all(request.headers["accept-encoding"] == "identity" for request in requests)
    assert resolver.calls == [("media.example", 8443), ("media.example", 8443)]
    assert [target.address for target in targets] == ["10.20.30.4", "10.20.30.4"]
    assert all(target.hostname == "media.example" and target.verify_tls for target in targets)
    assert len(secrets.calls) == 2


@pytest.mark.parametrize("provider", ["emby", "jellyfin"])
def test_probe_supports_both_closed_provider_variants(provider: str) -> None:
    profile = _profile(provider=provider)

    def handler(request: httpx.Request) -> httpx.Response:
        return _system(provider) if request.url.path == "/System/Info" else _folders()

    result = _connector(handler, profile=profile).probe()

    assert result.provider == provider
    assert result.server_version == "4.8.10.0"


@pytest.mark.parametrize("version", ["0", "4.8.11.0", "10.10.7"])
def test_probe_accepts_normal_bounded_numeric_server_versions(version: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return _system(version=version) if request.url.path == "/System/Info" else _folders()

    assert _connector(handler).probe().server_version == version


@pytest.mark.parametrize(
    ("version", "profile", "secrets"),
    [
        ("api-key-private-sentinel", None, _Secrets()),
        ("library_123", None, _Secrets()),
        ("4", _profile(library_id="4"), _Secrets("4")),
        ("4.12345678.1", _profile(library_id="12345678"), _Secrets()),
        ("4.87654321.1", None, _Secrets("87654321")),
        ("4.8.0-beta.1", None, _Secrets()),
    ],
)
def test_probe_rejects_non_numeric_or_sensitive_server_versions(
    version: str,
    profile: MediaServerProfile | None,
    secrets: _Secrets,
) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return _system(version=version)

    with pytest.raises(MediaServerError) as caught:
        _connector(handler, profile=profile, secrets=secrets).probe()

    assert caught.value.code == "media_server_schema_invalid"
    assert caught.value.__cause__ is None
    assert version not in str(caught.value)


@pytest.mark.parametrize(
    ("version", "library_id", "api_key"),
    [
        ("4.8.10.0", "4", "4"),
        ("10.10.7", "library_123", "10.10"),
        ("1.1010.7", "1010", "api-key-private-sentinel"),
    ],
)
def test_probe_allows_short_selectors_that_are_only_version_substrings(
    version: str,
    library_id: str,
    api_key: str,
) -> None:
    profile = _profile(library_id=library_id)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/System/Info":
            return _system(version=version)
        return _folders(
            {
                "ItemId": library_id,
                "Locations": ["/srv/media/private-path-sentinel"],
            }
        )

    assert _connector(handler, profile=profile, secrets=_Secrets(api_key)).probe().server_version == version


def test_every_dns_answer_must_be_explicitly_allowed_before_secret_or_transport() -> None:
    resolver = _Resolver(("10.20.30.4", "192.168.1.2"))
    secrets = _Secrets()
    transport_calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal transport_calls
        transport_calls += 1
        return _system()

    with pytest.raises(MediaServerError) as caught:
        _connector(handler, resolver=resolver, secrets=secrets).probe()

    assert caught.value.code == "media_server_address_forbidden"
    assert caught.value.retryable is False
    assert secrets.calls == []
    assert transport_calls == 0


def test_explicitly_allowed_loopback_literal_is_supported_without_dns() -> None:
    resolver = _Resolver(())
    profile = _profile(origin="http://127.0.0.1:8096", allowed_networks=("127.0.0.1/32",))

    def handler(request: httpx.Request) -> httpx.Response:
        return _system() if request.url.path == "/System/Info" else _folders()

    assert _connector(handler, profile=profile, resolver=resolver).probe().library_present is True
    assert resolver.calls == []


@pytest.mark.parametrize(
    ("folders", "code"),
    [
        ([], "media_server_library_not_found"),
        (
            [
                {"ItemId": "library_123", "Locations": ["/srv/media/private-path-sentinel"]},
                {"ItemId": "library_123", "Locations": ["/srv/media/private-path-sentinel"]},
            ],
            "media_server_library_ambiguous",
        ),
        (
            [{"ItemId": "library_123", "Locations": ["/srv/media/a-different-private-path"]}],
            "media_server_library_path_mismatch",
        ),
    ],
)
def test_probe_requires_one_exact_item_id_and_path(folders: list[object], code: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return _system() if request.url.path == "/System/Info" else httpx.Response(200, json=folders)

    with pytest.raises(MediaServerError) as caught:
        _connector(handler).probe()

    assert caught.value.code == code


def test_provider_mismatch_and_unsafe_version_fail_with_fixed_safe_errors() -> None:
    remote_sentinel = "remote-private-body-sentinel"

    def mismatched(request: httpx.Request) -> httpx.Response:
        return _system("jellyfin") if request.url.path == "/System/Info" else _folders()

    with pytest.raises(MediaServerError) as caught:
        _connector(mismatched).probe()
    assert caught.value.code == "media_server_provider_mismatch"

    def unsafe(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"Version": f"4.8\n{remote_sentinel}"})

    with pytest.raises(MediaServerError) as caught:
        _connector(unsafe).probe()
    assert caught.value.code == "media_server_schema_invalid"
    assert remote_sentinel not in str(caught.value)
    assert remote_sentinel not in repr(caught.value)


def test_lookup_contracts_are_strict_and_repr_safe() -> None:
    target = _lookup_target()
    target_repr = repr(target)
    assert target.provider_key in target_repr
    assert target.provider_value not in target_repr
    assert target.server_path not in target_repr

    result = MediaServerItemLookupResult(
        lookup_state="matched",
        inspected_item_count=1,
        page_count=1,
        response_byte_count=128,
        item_id_set_fingerprint="a" * 64,
        item_id="remote-private-item-id",
        etag="remote-private-etag",
    )
    result_repr = repr(result)
    assert "remote-private-item-id" not in result_repr
    assert "remote-private-etag" not in result_repr
    with pytest.raises(ValueError):
        MediaServerItemLookupResult(
            lookup_state="not_found",
            inspected_item_count=0,
            page_count=1,
            response_byte_count=2,
            item_id_set_fingerprint="a" * 64,
            item_id="must-not-be-retained",
        )
    with pytest.raises(ValueError):
        _lookup_target(provider_key="imdb")


def test_emby_lookup_uses_exact_bounded_filters_and_local_dual_verification() -> None:
    target = _lookup_target()
    requests: list[httpx.Request] = []
    body = json.dumps(
        {
            "Items": [
                {
                    "Id": "remote-private-item-id",
                    "Path": target.server_path,
                    "ProviderIds": {target.provider_key: target.provider_value},
                    "Etag": "remote-private-etag",
                }
            ],
            "TotalRecordCount": 1,
            "StartIndex": 0,
        },
        separators=(",", ":"),
    ).encode()

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, headers={"Content-Type": "application/json"}, content=body)

    result = _connector(handler).lookup_item(target)

    assert result.lookup_state == "matched"
    assert result.item_id == "remote-private-item-id"
    assert result.etag == "remote-private-etag"
    assert result.inspected_item_count == 1
    assert result.page_count == 1
    assert result.response_byte_count == len(body)
    assert len(result.item_id_set_fingerprint) == 64
    assert result.item_id_set_fingerprint not in repr(result)
    assert len(requests) == 1
    assert requests[0].method == "GET"
    assert requests[0].url.path == "/Items"
    assert tuple(requests[0].url.params.multi_items()) == (
        ("Path", target.server_path),
        ("AnyProviderIdEquals", f"{target.provider_key}.{target.provider_value}"),
        ("ParentId", "library_123"),
        ("Recursive", "true"),
        ("Fields", "Path,ProviderIds"),
        ("EnableImages", "false"),
        ("EnableUserData", "false"),
        ("StartIndex", "0"),
        ("Limit", "2"),
    )


def test_emby_lookup_omits_lossy_provider_filter_but_still_checks_provider_locally() -> None:
    target = _lookup_target(provider_value="creator,value")
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "Items": [
                    {
                        "Id": "other-private-item",
                        "Path": target.server_path,
                        "ProviderIds": {target.provider_key: "different-creator"},
                    }
                ],
                "TotalRecordCount": 1,
                "StartIndex": 0,
            },
        )

    result = _connector(handler).lookup_item(target)

    assert result.lookup_state == "not_found"
    assert result.item_id is None
    assert "AnyProviderIdEquals" not in requests[0].url.params
    assert requests[0].url.params["Path"] == target.server_path


def test_emby_lookup_distinguishes_ambiguous_from_incomplete() -> None:
    target = _lookup_target()

    def response(*, path: str = target.server_path, total: int = 2) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "Items": [
                    {
                        "Id": "remote-item-one",
                        "Path": path,
                        "ProviderIds": {target.provider_key: target.provider_value},
                    },
                    {
                        "Id": "remote-item-two",
                        "Path": target.server_path,
                        "ProviderIds": {target.provider_key: target.provider_value},
                    },
                ],
                "TotalRecordCount": total,
                "StartIndex": 0,
            },
        )

    with pytest.raises(MediaServerError) as ambiguous:
        _connector(lambda _request: response()).lookup_item(target)
    assert ambiguous.value.code == "media_server_item_lookup_ambiguous"
    assert ambiguous.value.retryable is False

    with pytest.raises(MediaServerError) as incomplete:
        _connector(lambda _request: response(total=3)).lookup_item(target)
    assert incomplete.value.code == "media_server_item_lookup_incomplete"
    assert incomplete.value.retryable is False

    with pytest.raises(MediaServerError) as filter_violation:
        _connector(lambda _request: response(path="/server-returned/wrong-private-path")).lookup_item(target)
    assert filter_violation.value.code == "media_server_item_lookup_incomplete"


def test_jellyfin_lookup_exhaustively_pages_without_remote_selectors() -> None:
    target = _lookup_target()
    requests: list[httpx.Request] = []
    rows = [
        {
            "Id": f"remote-item-{index:03d}",
            "Path": f"/srv/media/other/item-{index:03d}",
            "ProviderIds": {},
        }
        for index in range(130)
    ]
    rows[-1] = {
        "Id": "remote-private-item-id",
        "Path": target.server_path,
        "ProviderIds": {target.provider_key: target.provider_value},
        "Etag": "remote-private-etag",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        start = int(request.url.params["startIndex"])
        limit = int(request.url.params["limit"])
        page = rows[start : start + limit]
        return httpx.Response(
            200,
            json={"Items": page, "TotalRecordCount": len(rows), "StartIndex": start},
        )

    result = _connector(handler, profile=_profile(provider="jellyfin")).lookup_item(target)

    assert result.lookup_state == "matched"
    assert result.item_id == "remote-private-item-id"
    assert result.inspected_item_count == 130
    assert result.page_count == 2
    assert [request.url.params["startIndex"] for request in requests] == ["0", "128"]
    for request in requests:
        assert tuple(request.url.params.keys()) == (
            "parentId",
            "recursive",
            "fields",
            "enableImages",
            "enableUserData",
            "enableTotalRecordCount",
            "startIndex",
            "limit",
        )
        assert request.url.params["parentId"] == "library_123"
        assert request.url.params["recursive"] == "true"
        assert request.url.params["fields"] == "Path,ProviderIds,Etag"
        assert "Path" not in request.url.params
        assert "AnyProviderIdEquals" not in request.url.params
        assert "SearchTerm" not in request.url.params


@pytest.mark.parametrize(
    ("path_matches", "provider_matches", "expected_state"),
    [
        (False, False, "not_found"),
        (True, False, "not_found"),
        (False, True, "not_found"),
        (True, True, "matched"),
    ],
)
def test_jellyfin_lookup_requires_an_exact_path_and_provider_match(
    path_matches: bool,
    provider_matches: bool,
    expected_state: str,
) -> None:
    target = _lookup_target()
    row = {
        "Id": "remote-private-item-id",
        "Path": target.server_path if path_matches else "/srv/media/near-match",
        "ProviderIds": {target.provider_key: target.provider_value if provider_matches else "other-private-creator"},
    }

    result = _connector(
        lambda _request: httpx.Response(
            200,
            json={"Items": [row], "TotalRecordCount": 1, "StartIndex": 0},
        ),
        profile=_profile(provider="jellyfin"),
    ).lookup_item(target)

    assert result.lookup_state == expected_state
    assert (result.item_id is not None) is (expected_state == "matched")


@pytest.mark.parametrize("failure", ["duplicate_id", "unstable_total", "wrong_start"])
def test_jellyfin_lookup_fails_closed_on_inconsistent_pagination(failure: str) -> None:
    target = _lookup_target()
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        start = int(request.url.params["startIndex"])
        if start == 0:
            rows = [{"Id": f"item-{index}", "Path": f"/other/{index}", "ProviderIds": {}} for index in range(128)]
            return httpx.Response(200, json={"Items": rows, "TotalRecordCount": 129, "StartIndex": 0})
        row_id = "item-0" if failure == "duplicate_id" else "item-128"
        total = 130 if failure == "unstable_total" else 129
        returned_start = 0 if failure == "wrong_start" else 128
        return httpx.Response(
            200,
            json={
                "Items": [{"Id": row_id, "Path": "/other/128", "ProviderIds": {}}],
                "TotalRecordCount": total,
                "StartIndex": returned_start,
            },
        )

    with pytest.raises(MediaServerError) as caught:
        _connector(handler, profile=_profile(provider="jellyfin")).lookup_item(target)

    assert caught.value.code == "media_server_item_lookup_incomplete"
    assert calls == 2


def test_jellyfin_lookup_stops_before_exceeding_page_budget() -> None:
    target = _lookup_target()
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            200,
            json={
                "Items": [{"Id": "item-0", "Path": "/other/0", "ProviderIds": {}}],
                "TotalRecordCount": 2,
                "StartIndex": int(request.url.params["startIndex"]),
            },
        )

    with pytest.raises(MediaServerError) as caught:
        _connector(
            handler,
            profile=_profile(provider="jellyfin"),
            limits=MediaServerLimits(jellyfin_lookup_page_size=1, max_lookup_pages=1),
        ).lookup_item(target)

    assert caught.value.code == "media_server_item_lookup_incomplete"
    assert calls == 1


def test_lookup_counts_true_response_bytes_and_enforces_aggregate_byte_budget() -> None:
    target = _lookup_target()
    body = json.dumps({"Items": [], "TotalRecordCount": 0, "StartIndex": 0}).encode()

    successful = _connector(
        lambda _request: httpx.Response(200, headers={"Content-Type": "application/json"}, content=body)
    ).lookup_item(target)
    assert successful.response_byte_count == len(body)

    with pytest.raises(MediaServerError) as caught:
        _connector(
            lambda _request: httpx.Response(200, headers={"Content-Type": "application/json"}, content=body),
            limits=MediaServerLimits(max_lookup_bytes=len(body) - 1),
        ).lookup_item(target)
    assert caught.value.code == "media_server_item_lookup_incomplete"


def test_item_id_set_fingerprint_is_deterministic_context_bound_and_repr_hidden() -> None:
    target = _lookup_target()

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"Items": [], "TotalRecordCount": 0, "StartIndex": 0})

    first = _connector(handler).lookup_item(target)
    repeated = _connector(handler).lookup_item(target)
    other_profile = _connector(handler, profile=_profile(library_id="other_library")).lookup_item(target)
    other_selector = _connector(handler).lookup_item(_lookup_target(provider_value="other-creator"))

    assert first.item_id_set_fingerprint == repeated.item_id_set_fingerprint
    assert first.item_id_set_fingerprint != other_profile.item_id_set_fingerprint
    assert first.item_id_set_fingerprint != other_selector.item_id_set_fingerprint
    assert first.item_id_set_fingerprint not in repr(first)


def test_duplicate_json_keys_are_rejected_including_nested_provider_ids() -> None:
    with pytest.raises(MediaServerError) as probe_failure:
        _connector(
            lambda _request: httpx.Response(
                200,
                headers={"Content-Type": "application/json"},
                content=b'{"ProductName":"Emby Server","Version":"4.8.10.0","Version":"9.9.9"}',
            )
        ).probe()
    assert probe_failure.value.code == "media_server_response_invalid"

    target = _lookup_target()
    duplicate_provider = (
        '{"Items":[{"Id":"item-1","Path":'
        + json.dumps(target.server_path)
        + ',"ProviderIds":{"media-sync-bili-creator":"first","media-sync-bili-creator":"second"}}],'
        '"TotalRecordCount":1,"StartIndex":0}'
    ).encode()
    with pytest.raises(MediaServerError) as lookup_failure:
        _connector(
            lambda _request: httpx.Response(
                200,
                headers={"Content-Type": "application/json"},
                content=duplicate_provider,
            )
        ).lookup_item(target)
    assert lookup_failure.value.code == "media_server_item_lookup_incomplete"


def test_lookup_replaces_entire_dependency_wire_record_for_encoded_selectors(
    caplog: pytest.LogCaptureFixture,
) -> None:
    target = _lookup_target(
        provider_value="creator/value with space",
        server_path="/srv/media/private path/作者目录",
    )
    caplog.set_level(logging.DEBUG)
    original_make_record = logging.Logger.makeRecord

    def handler(request: httpx.Request) -> httpx.Response:
        logging.getLogger("httpcore.lookup").warning(
            "selector url=%s encoded_path=%s",
            request.url,
            quote(target.server_path, safe=""),
            exc_info=RuntimeError(target.provider_value),
            extra={
                "request_url": str(request.url),
                "selector_context": {"path": target.server_path, "provider": target.provider_value},
            },
        )
        return httpx.Response(200, json={"Items": [], "TotalRecordCount": 0, "StartIndex": 0})

    result = _connector(handler).lookup_item(target)

    assert result.lookup_state == "not_found"
    wire_records = [
        record
        for record in caplog.records
        if record.name == "httpx" or record.name.startswith("httpx.") or record.name.startswith("httpcore")
    ]
    assert wire_records
    assert {record.getMessage() for record in wire_records} == {"[REDACTED MEDIA-SERVER WIRE EVENT]"}
    rendered = "\n".join(record.getMessage() for record in wire_records)
    assert target.provider_value not in rendered
    assert target.server_path not in rendered
    assert quote(target.server_path, safe="") not in rendered
    assert all(record.args == () and record.exc_info is None and record.exc_text is None for record in wire_records)
    retained_records = "\n".join(repr(record.__dict__) for record in wire_records)
    assert target.provider_value not in retained_records
    assert target.server_path not in retained_records
    assert quote(target.server_path, safe="") not in retained_records
    assert all(record.__dict__.get("request_url") in {None, "[REDACTED]"} for record in wire_records)
    assert logging.Logger.makeRecord is original_make_record


def test_lookup_rejects_unpaired_unicode_surrogates_as_incomplete() -> None:
    target = _lookup_target()
    body = (
        '{"Items":[{"Id":"\\ud800","Path":'
        + json.dumps(target.server_path)
        + ',"ProviderIds":'
        + json.dumps({target.provider_key: target.provider_value})
        + '}],"TotalRecordCount":1,"StartIndex":0}'
    ).encode()

    with pytest.raises(MediaServerError) as caught:
        _connector(
            lambda _request: httpx.Response(
                200,
                headers={"Content-Type": "application/json"},
                content=body,
            )
        ).lookup_item(target)

    assert caught.value.code == "media_server_item_lookup_incomplete"
    assert caught.value.retryable is False


def test_scan_discovers_then_dispatches_only_the_exact_fixed_post_once() -> None:
    requests: list[httpx.Request] = []
    cancellation_checks = 0

    def not_cancelled() -> bool:
        nonlocal cancellation_checks
        cancellation_checks += 1
        return False

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/System/Info":
            return _system()
        if request.url.path == "/Library/VirtualFolders":
            return _folders()
        assert request.url.path == "/Items/library_123/Refresh"
        return httpx.Response(204)

    result = _connector(handler).scan(not_cancelled)

    assert result == MediaServerScanResult(
        provider="emby",
        server_version="4.8.10.0",
        library_id_digest=_profile().library_id_digest,
    )
    assert [request.method for request in requests] == ["GET", "GET", "POST"]
    assert requests[-1].url.path == "/Items/library_123/Refresh"
    assert tuple(requests[-1].url.params.multi_items()) == (
        ("Recursive", "true"),
        ("MetadataRefreshMode", "Default"),
        ("ImageRefreshMode", "Default"),
        ("ReplaceAllMetadata", "false"),
        ("ReplaceAllImages", "false"),
    )
    assert all(request.url.path != "/Library/Refresh" for request in requests)
    assert cancellation_checks >= 5


def test_observation_scan_runs_the_authority_hook_once_at_transport_entry() -> None:
    requests: list[httpx.Request] = []
    hook_request_counts: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/System/Info":
            return _system()
        if request.url.path == "/Library/VirtualFolders":
            return _folders()
        assert request.url.path == "/Items/library_123/Refresh"
        return httpx.Response(204)

    def before_transport_entry() -> bool:
        hook_request_counts.append(len(requests))
        return True

    result = _connector(handler).scan_observation(lambda: False, before_transport_entry)

    assert result.scan_state == "accepted"
    assert hook_request_counts == [2]
    assert [request.method for request in requests] == ["GET", "GET", "POST"]


@pytest.mark.parametrize("disposition", ["cancel", "changed"])
def test_observation_scan_hook_failure_never_enters_the_post(disposition: str) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return _system() if request.url.path == "/System/Info" else _folders()

    def before_transport_entry() -> bool:
        if disposition == "changed":
            raise MediaServerError("media_server_publication_changed")
        return False

    with pytest.raises(MediaServerError) as caught:
        _connector(handler).scan_observation(lambda: False, before_transport_entry)

    assert caught.value.code == (
        "media_server_publication_changed" if disposition == "changed" else "media_server_scan_cancelled"
    )
    assert [request.method for request in requests] == ["GET", "GET"]


def test_caller_deadline_bounds_a_blocking_lookup() -> None:
    entered = threading.Event()
    release = threading.Event()

    def handler(_request: httpx.Request) -> httpx.Response:
        entered.set()
        release.wait(5)
        return httpx.Response(200, json={"Items": [], "TotalRecordCount": 0, "StartIndex": 0})

    started = time.monotonic()
    try:
        with pytest.raises(MediaServerError) as caught:
            _connector(handler).lookup_item(
                _lookup_target(),
                deadline=time.monotonic() + 0.1,
            )
        elapsed = time.monotonic() - started
    finally:
        release.set()

    assert entered.wait(1)
    assert caught.value.code == "media_server_item_lookup_incomplete"
    assert elapsed < 0.75


def test_caller_deadline_expires_a_blocking_observation_fence_before_post() -> None:
    hook_entered = threading.Event()
    release_hook = threading.Event()
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return _system() if request.url.path == "/System/Info" else _folders()

    def before_transport_entry() -> bool:
        hook_entered.set()
        release_hook.wait(5)
        return True

    started = time.monotonic()
    try:
        with pytest.raises(MediaServerError) as caught:
            _connector(handler).scan_observation(
                lambda: False,
                before_transport_entry,
                deadline=time.monotonic() + 0.1,
            )
        elapsed = time.monotonic() - started
    finally:
        release_hook.set()

    assert hook_entered.wait(1)
    assert caught.value.code == "media_server_timeout"
    assert elapsed < 0.75
    time.sleep(0.05)
    assert [request.method for request in requests] == ["GET", "GET"]


def test_jellyfin_refresh_uses_only_its_documented_provider_specific_query() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/System/Info":
            return _system("jellyfin", "10.10.7")
        if request.url.path == "/Library/VirtualFolders":
            return _folders()
        return httpx.Response(204)

    result = _connector(handler, profile=_profile(provider="jellyfin")).scan(lambda: False)

    assert result.provider == "jellyfin"
    assert tuple(requests[-1].url.params.multi_items()) == (
        ("metadataRefreshMode", "Default"),
        ("imageRefreshMode", "Default"),
        ("replaceAllMetadata", "false"),
        ("replaceAllImages", "false"),
    )
    assert "Recursive" not in requests[-1].url.params
    assert "recursive" not in requests[-1].url.params


def test_scan_pre_dispatch_cancellation_never_reaches_the_post() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return _system() if request.url.path == "/System/Info" else _folders()

    with pytest.raises(MediaServerError) as caught:
        _connector(handler).scan(lambda: True)
    assert caught.value.code == "media_server_scan_cancelled"
    assert requests == []

    checks = iter((False, True))
    with pytest.raises(MediaServerError) as caught:
        _connector(handler).scan(lambda: next(checks))
    assert caught.value.code == "media_server_scan_cancelled"
    assert [request.method for request in requests] == ["GET", "GET"]


def test_scan_checks_cancellation_again_after_post_preparation_and_before_dispatch() -> None:
    requests: list[httpx.Request] = []
    cancelled = False

    class CancellingThirdResolution(_Resolver):
        def resolve(self, hostname: str, port: int) -> Sequence[str]:
            nonlocal cancelled
            answers = super().resolve(hostname, port)
            if len(self.calls) == 3:
                cancelled = True
            return answers

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return _system() if request.url.path == "/System/Info" else _folders()

    with pytest.raises(MediaServerError) as caught:
        _connector(handler, resolver=CancellingThirdResolution()).scan(lambda: cancelled)

    assert caught.value.code == "media_server_scan_cancelled"
    assert [request.method for request in requests] == ["GET", "GET"]


def test_transport_gate_rejects_cancellation_at_the_actual_post_entry() -> None:
    requests: list[httpx.Request] = []
    cancellation_checks = 0

    def cancel_at_transport_entry() -> bool:
        nonlocal cancellation_checks
        cancellation_checks += 1
        return cancellation_checks >= 4

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return _system() if request.url.path == "/System/Info" else _folders()

    with pytest.raises(MediaServerError) as caught:
        _connector(handler).scan(cancel_at_transport_entry)

    assert caught.value.code == "media_server_scan_cancelled"
    assert [request.method for request in requests] == ["GET", "GET"]
    assert cancellation_checks == 4


def test_transport_gate_rejects_expiration_that_wins_before_post_entry() -> None:
    callback_entered = threading.Event()
    release_callback = threading.Event()
    requests: list[httpx.Request] = []
    cancellation_checks = 0

    def block_after_post_preparation() -> bool:
        nonlocal cancellation_checks
        cancellation_checks += 1
        if cancellation_checks == 3:
            callback_entered.set()
            release_callback.wait(5)
        return False

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return _system() if request.url.path == "/System/Info" else _folders()

    try:
        with pytest.raises(MediaServerError) as caught:
            _connector(handler, profile=_profile(timeout_seconds=0.1)).scan(block_after_post_preparation)
    finally:
        release_callback.set()

    assert callback_entered.wait(1)
    assert caught.value.code == "media_server_timeout"
    assert caught.value.retryable is True
    time.sleep(0.05)
    assert [request.method for request in requests] == ["GET", "GET"]


def test_cancellation_observed_after_post_entry_is_acceptance_unknown() -> None:
    cancelled = False
    post_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal cancelled, post_calls
        if request.url.path == "/System/Info":
            return _system()
        if request.url.path == "/Library/VirtualFolders":
            return _folders()
        post_calls += 1
        cancelled = True
        return httpx.Response(204)

    with pytest.raises(MediaServerError) as caught:
        _connector(handler).scan(lambda: cancelled)

    assert caught.value.code == "media_server_scan_acceptance_unknown"
    assert caught.value.retryable is False
    assert post_calls == 1


def test_absolute_deadline_bounds_blocking_dns_and_late_completion_cannot_continue() -> None:
    resolver = _BlockingResolver()
    secrets = _Secrets()
    requests: list[httpx.Request] = []
    started = time.monotonic()
    try:
        with pytest.raises(MediaServerError) as caught:
            _connector(
                lambda request: requests.append(request) or _system(),
                profile=_profile(timeout_seconds=0.1),
                resolver=resolver,
                secrets=secrets,
            ).probe()
        elapsed = time.monotonic() - started
    finally:
        resolver.release.set()

    assert resolver.entered.wait(1)
    assert caught.value.code == "media_server_timeout"
    assert caught.value.retryable is True
    assert elapsed < 0.75
    assert resolver.returned.wait(1)
    time.sleep(0.05)
    assert secrets.calls == []
    assert requests == []


def test_timed_out_worker_holds_single_flight_gate_until_it_safely_exits() -> None:
    class CountingBlockingResolver(_BlockingResolver):
        def __init__(self) -> None:
            super().__init__()
            self.calls = 0

        def resolve(self, hostname: str, port: int) -> Sequence[str]:
            self.calls += 1
            return super().resolve(hostname, port)

    resolver = CountingBlockingResolver()

    def handler(request: httpx.Request) -> httpx.Response:
        return _system() if request.url.path == "/System/Info" else _folders()

    connector = _connector(
        handler,
        profile=_profile(timeout_seconds=0.1),
        resolver=resolver,
    )
    try:
        with pytest.raises(MediaServerError) as first:
            connector.probe()

        rejected_started = time.monotonic()
        for _ in range(2):
            with pytest.raises(MediaServerError) as rejected:
                connector.probe()
            assert rejected.value.code == "media_server_transport"
            assert rejected.value.retryable is True
        rejected_elapsed = time.monotonic() - rejected_started

        assert first.value.code == "media_server_timeout"
        assert resolver.calls == 1
        assert rejected_elapsed < 0.25
    finally:
        resolver.release.set()

    assert resolver.returned.wait(1)
    retry_deadline = time.monotonic() + 1
    while True:
        try:
            recovered = connector.probe()
        except MediaServerError as error:
            if error.code != "media_server_transport" or time.monotonic() >= retry_deadline:
                raise
            time.sleep(0.01)
        else:
            break

    assert recovered.server_version == "4.8.10.0"
    assert resolver.calls == 3


def test_worker_completion_before_deadline_wins_even_if_caller_resumes_late(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    in_worker = False
    caller_clock_reads = 0

    class InlineThread:
        def __init__(self, *, target: Callable[[], None], **_kwargs: object) -> None:
            self._target = target

        def start(self) -> None:
            nonlocal in_worker
            in_worker = True
            try:
                self._target()
            finally:
                in_worker = False

    def clock() -> float:
        nonlocal caller_clock_reads
        if in_worker:
            return 1.0
        caller_clock_reads += 1
        return 0.0 if caller_clock_reads == 1 else 20.0

    monkeypatch.setattr(threading, "Thread", InlineThread)

    def handler(request: httpx.Request) -> httpx.Response:
        return _system() if request.url.path == "/System/Info" else _folders()

    result = _connector(handler, monotonic=clock).probe()

    assert result.server_version == "4.8.10.0"
    assert caller_clock_reads == 2


def test_absolute_deadline_bounds_blocking_secret_resolution() -> None:
    secrets = _BlockingSecrets()
    requests: list[httpx.Request] = []
    started = time.monotonic()
    try:
        with pytest.raises(MediaServerError) as caught:
            _connector(
                lambda request: requests.append(request) or _system(),
                profile=_profile(timeout_seconds=0.1),
                secrets=secrets,
            ).probe()
        elapsed = time.monotonic() - started
    finally:
        secrets.release.set()

    assert secrets.entered.wait(1)
    assert caught.value.code == "media_server_timeout"
    assert elapsed < 0.75
    assert secrets.returned.wait(1)
    time.sleep(0.05)
    assert requests == []


def test_absolute_deadline_bounds_blocking_response_headers() -> None:
    entered = threading.Event()
    release = threading.Event()
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        entered.set()
        release.wait(5)
        return _system()

    started = time.monotonic()
    try:
        with pytest.raises(MediaServerError) as caught:
            _connector(handler, profile=_profile(timeout_seconds=0.1)).probe()
        elapsed = time.monotonic() - started
    finally:
        release.set()

    assert entered.wait(1)
    assert caught.value.code == "media_server_timeout"
    assert elapsed < 0.75
    time.sleep(0.05)
    assert len(requests) == 1


def test_absolute_deadline_bounds_blocking_response_body() -> None:
    entered = threading.Event()
    release = threading.Event()
    requests: list[httpx.Request] = []

    class BlockingBody(httpx.SyncByteStream):
        def __iter__(self):  # type: ignore[no-untyped-def]
            entered.set()
            release.wait(5)
            yield b'{"ProductName":"Emby Server","Version":"4.8.10.0"}'

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, headers={"Content-Type": "application/json"}, stream=BlockingBody())

    started = time.monotonic()
    try:
        with pytest.raises(MediaServerError) as caught:
            _connector(handler, profile=_profile(timeout_seconds=0.1)).probe()
        elapsed = time.monotonic() - started
    finally:
        release.set()

    assert entered.wait(1)
    assert caught.value.code == "media_server_timeout"
    assert elapsed < 0.75
    time.sleep(0.05)
    assert len(requests) == 1


def test_scan_timeout_before_post_dispatch_cannot_send_later() -> None:
    release = threading.Event()
    resolver_calls = 0
    third_entered = threading.Event()
    requests: list[httpx.Request] = []

    class BlockingPostResolution(_Resolver):
        def resolve(self, hostname: str, port: int) -> Sequence[str]:
            nonlocal resolver_calls
            resolver_calls += 1
            if resolver_calls == 3:
                third_entered.set()
                release.wait(5)
            return super().resolve(hostname, port)

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return _system() if request.url.path == "/System/Info" else _folders()

    try:
        with pytest.raises(MediaServerError) as caught:
            _connector(
                handler,
                profile=_profile(timeout_seconds=0.1),
                resolver=BlockingPostResolution(),
            ).scan(lambda: False)
    finally:
        release.set()

    assert third_entered.wait(1)
    assert caught.value.code == "media_server_timeout"
    assert caught.value.retryable is True
    time.sleep(0.05)
    assert [request.method for request in requests] == ["GET", "GET"]


@pytest.mark.parametrize("status", [404, 405, 501])
def test_scan_unsupported_never_falls_back_or_retries(status: int) -> None:
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.url.path == "/System/Info":
            return _system()
        if request.url.path == "/Library/VirtualFolders":
            return _folders()
        return httpx.Response(status, content=b"remote-private-body-sentinel")

    with pytest.raises(MediaServerError) as caught:
        _connector(handler).scan(lambda: False)

    assert caught.value.code == "media_server_targeted_scan_unsupported"
    assert caught.value.retryable is False
    assert paths == ["/System/Info", "/Library/VirtualFolders", "/Items/library_123/Refresh"]


@pytest.mark.parametrize(
    "failure",
    [
        httpx.ConnectError("remote-private-transport-sentinel"),
        httpx.ReadTimeout("remote-private-timeout-sentinel"),
    ],
)
def test_scan_post_dispatch_transport_ambiguity_is_terminal_and_never_retried(failure: httpx.HTTPError) -> None:
    post_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal post_calls
        if request.url.path == "/System/Info":
            return _system()
        if request.url.path == "/Library/VirtualFolders":
            return _folders()
        post_calls += 1
        raise failure

    with pytest.raises(MediaServerError) as caught:
        _connector(handler).scan(lambda: False)

    assert caught.value.code == "media_server_scan_acceptance_unknown"
    assert caught.value.retryable is False
    assert post_calls == 1
    assert "remote-private" not in str(caught.value)
    assert "remote-private" not in repr(caught.value)


def test_scan_post_dispatch_absolute_timeout_is_acceptance_unknown() -> None:
    post_entered = threading.Event()
    release = threading.Event()
    post_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal post_calls
        if request.url.path == "/System/Info":
            return _system()
        if request.url.path == "/Library/VirtualFolders":
            return _folders()
        post_calls += 1
        post_entered.set()
        release.wait(5)
        return httpx.Response(204)

    started = time.monotonic()
    try:
        with pytest.raises(MediaServerError) as caught:
            _connector(handler, profile=_profile(timeout_seconds=0.1)).scan(lambda: False)
        elapsed = time.monotonic() - started
    finally:
        release.set()

    assert post_entered.wait(1)
    assert caught.value.code == "media_server_scan_acceptance_unknown"
    assert caught.value.retryable is False
    assert caught.value.__cause__ is None
    assert elapsed < 0.75
    assert post_calls == 1


def test_scan_post_dispatch_response_close_failure_is_acceptance_unknown() -> None:
    post_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal post_calls
        if request.url.path == "/System/Info":
            return _system()
        if request.url.path == "/Library/VirtualFolders":
            return _folders()
        post_calls += 1
        return _CloseFailingResponse(204)

    with pytest.raises(MediaServerError) as caught:
        _connector(handler).scan(lambda: False)

    assert caught.value.code == "media_server_scan_acceptance_unknown"
    assert caught.value.retryable is False
    assert caught.value.__cause__ is None
    assert "close-private-sentinel" not in str(caught.value)
    assert repr(caught.value) == "MediaServerError(code='media_server_scan_acceptance_unknown', retryable=False)"
    assert post_calls == 1


def test_probe_transport_failure_is_safe_and_retryable_without_automatic_retry() -> None:
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ConnectError("remote-private-transport-sentinel")

    with pytest.raises(MediaServerError) as caught:
        _connector(handler).probe()

    assert caught.value.code == "media_server_transport"
    assert caught.value.retryable is True
    assert calls == 1
    assert "remote-private" not in str(caught.value)


def test_redirect_secret_failure_and_remote_body_never_escape() -> None:
    def redirected(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"Location": "http://forbidden.test/?api_key=redirect-secret"})

    with pytest.raises(MediaServerError) as caught:
        _connector(redirected).probe()
    assert caught.value.code == "media_server_redirect_forbidden"
    assert "redirect-secret" not in str(caught.value)

    with pytest.raises(MediaServerError) as caught:
        _connector(lambda _request: _system(), secrets=_UnavailableSecrets()).probe()
    assert caught.value.code == "media_server_secret_unavailable"
    assert "provider details" not in str(caught.value)


def test_invalid_header_secret_is_rejected_without_leaking_through_exception_chain() -> None:
    secret = "api-key-private-sentinel\r\nX-Injected: private"

    with pytest.raises(MediaServerError) as caught:
        _connector(
            lambda _request: pytest.fail("invalid secret must fail before HTTP"), secrets=_Secrets(secret)
        ).probe()

    assert caught.value.code == "media_server_secret_unavailable"
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None
    assert secret not in str(caught.value)
    assert "api-key-private-sentinel" not in repr(caught.value)


def test_dependency_wire_loggers_cannot_emit_reflected_key_or_library_id(
    caplog: pytest.LogCaptureFixture,
) -> None:
    secrets = _Secrets()
    caplog.set_level(logging.DEBUG)
    dynamic_logger_name = f"httpcore.created_during_request_{time.monotonic_ns()}"
    assert dynamic_logger_name not in logging.root.manager.loggerDict
    wire_loggers = tuple(logging.getLogger(name) for name in ("httpcore", "httpcore.http11", "httpx"))
    original_states = tuple(
        (
            logger.disabled,
            logger.level,
            logger.propagate,
            tuple(logger.handlers),
            tuple(logger.filters),
        )
        for logger in wire_loggers
    )
    original_global_disable = logging.root.manager.disable
    original_factory = logging.getLogRecordFactory()

    def handler(request: httpx.Request) -> httpx.Response:
        logging.getLogger("httpcore.http11").debug(
            "receive_response_headers.complete return_value=%r",
            [(b"X-Echo", secrets.value.encode())],
        )
        logging.getLogger("httpx").info("HTTP Request: %s library=%s", request.url, "library_123")
        logging.getLogger(dynamic_logger_name).warning(
            "created-during-request key=%s library=%s",
            secrets.value,
            "library_123",
        )
        if request.url.path == "/System/Info":
            return _system()
        return _folders()

    try:
        logging.disable(logging.NOTSET)
        for logger in wire_loggers:
            logger.disabled = False
            logger.setLevel(logging.DEBUG)
            logger.propagate = False
            logger.handlers[:] = [caplog.handler]
            logger.filters.clear()

        assert _connector(handler, secrets=secrets).probe().library_present is True

        rendered = "\n".join(record.getMessage() for record in caplog.records)
        assert secrets.value not in rendered
        assert "library_123" not in rendered
        assert "receive_response_headers.complete" in rendered
        assert "HTTP Request:" in rendered
        assert "created-during-request" in rendered
        assert "[REDACTED]" in rendered
    finally:
        for logger, state in zip(wire_loggers, original_states, strict=True):
            disabled, level, propagate, handlers, filters = state
            logger.disabled = disabled
            logger.setLevel(level)
            logger.propagate = propagate
            logger.handlers[:] = handlers
            logger.filters[:] = filters
        logging.disable(original_global_disable)

    assert (
        tuple(
            (
                logger.disabled,
                logger.level,
                logger.propagate,
                tuple(logger.handlers),
                tuple(logger.filters),
            )
            for logger in wire_loggers
        )
        == original_states
    )
    assert logging.getLogRecordFactory() is original_factory


def test_overlapping_wire_redaction_scopes_keep_factory_until_the_last_request_exits(
    caplog: pytest.LogCaptureFixture,
) -> None:
    first_key = "concurrent-private-key-alpha"
    second_key = "concurrent-private-key-bravo"
    first_request_entered = threading.Event()
    second_request_entered = threading.Event()
    first_probe_completed = threading.Event()
    original_factory = logging.getLogRecordFactory()
    results: list[MediaServerProbeResult] = []
    failures: list[BaseException] = []
    caplog.set_level(logging.DEBUG)

    def first_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/System/Info":
            first_request_entered.set()
            assert second_request_entered.wait(2)
            logging.getLogger("httpcore.concurrent.first").warning("first-wire-event key=%s", first_key)
            return _system()
        return _folders()

    def second_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/System/Info":
            second_request_entered.set()
            assert first_request_entered.wait(2)
            assert first_probe_completed.wait(2)
            logging.getLogger("httpcore.concurrent.second").warning("second-wire-event key=%s", second_key)
            return _system()
        return _folders()

    first = _connector(first_handler, secrets=_Secrets(first_key))
    second = _connector(second_handler, secrets=_Secrets(second_key))

    def run_probe(connector: MediaServerConnector, *, completed: threading.Event | None = None) -> None:
        try:
            results.append(connector.probe())
        except BaseException as error:
            failures.append(error)
        finally:
            if completed is not None:
                completed.set()

    threads = (
        threading.Thread(target=run_probe, args=(first,), kwargs={"completed": first_probe_completed}),
        threading.Thread(target=run_probe, args=(second,)),
    )
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(3)

    assert all(not thread.is_alive() for thread in threads)
    assert failures == []
    assert len(results) == 2
    rendered = "\n".join(record.getMessage() for record in caplog.records)
    assert "first-wire-event" in rendered
    assert "second-wire-event" in rendered
    assert first_key not in rendered
    assert second_key not in rendered
    assert logging.getLogRecordFactory() is original_factory


@pytest.mark.parametrize(
    ("handler", "limits", "code"),
    [
        (
            lambda _request: httpx.Response(200, content=b"{"),
            None,
            "media_server_response_invalid",
        ),
        (
            lambda _request: httpx.Response(200, content=b"x" * 9),
            MediaServerLimits(max_body_bytes=8),
            "media_server_body_limit",
        ),
        (
            lambda _request: httpx.Response(200, headers={"X-Large": "x" * 20}, json={"Version": "1"}),
            MediaServerLimits(max_header_line_bytes=16),
            "media_server_header_limit",
        ),
        (
            lambda _request: httpx.Response(200, json={"Version": "x" * 65}),
            None,
            "media_server_schema_invalid",
        ),
    ],
)
def test_probe_response_budgets_and_json_schema_are_bounded(
    handler: Callable[[httpx.Request], httpx.Response],
    limits: MediaServerLimits | None,
    code: str,
) -> None:
    with pytest.raises(MediaServerError) as caught:
        _connector(handler, limits=limits).probe()

    assert caught.value.code == code


def test_json_item_and_virtual_folder_limits_fail_closed() -> None:
    def many_items(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/System/Info":
            return _system()
        return httpx.Response(200, json=[{"ItemId": str(index), "Locations": []} for index in range(3)])

    with pytest.raises(MediaServerError) as caught:
        _connector(many_items, limits=MediaServerLimits(max_virtual_folders=2)).probe()
    assert caught.value.code == "media_server_schema_invalid"

    nested = json.dumps({"Version": "1", "extra": [1, 2, 3]}).encode()
    with pytest.raises(MediaServerError) as caught:
        _connector(
            lambda _request: httpx.Response(200, content=nested),
            limits=MediaServerLimits(max_json_items=4),
        ).probe()
    assert caught.value.code == "media_server_schema_invalid"


def test_media_server_result_and_error_contracts_are_strict_and_safe() -> None:
    digest = "a" * 64
    assert MediaServerProbeResult("emby", "4.8.0", digest).library_present is True
    assert MediaServerScanResult("jellyfin", "10.10.7", digest).scan_state == "accepted"
    with pytest.raises(ValueError):
        MediaServerProbeResult("emby", "unsafe version", digest)
    with pytest.raises(ValueError):
        MediaServerScanResult("jellyfin", "10.10.7", digest, scan_state="complete")  # type: ignore[arg-type]

    error = MediaServerError("media_server_timeout", retryable=True)
    assert error.code == "media_server_timeout"
    assert error.retryable is True
    assert str(error) == "media_server_timeout: media-server request deadline was exceeded"
    assert repr(error) == "MediaServerError(code='media_server_timeout', retryable=True)"
    with pytest.raises(ValueError):
        MediaServerError("api-key-private-sentinel")
