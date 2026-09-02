"""Offline XHS creator-video-to-playable-Emby qualification."""

from __future__ import annotations

import hashlib
import json
import shutil
from base64 import b64decode
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import ClassVar
from urllib.parse import urlsplit
from uuid import UUID

import httpx
import pytest
from sqlalchemy import select

from media_sync.application import mediacrawler_download as mediacrawler_runtime
from media_sync.application.downloads import AssetDownloadRequest, AssetDownloadService
from media_sync.application.emby import EmbyExportRequest, EmbyExportService
from media_sync.application.mediacrawler_download import LazyMediaCrawlerLocatorRefresher
from media_sync.domain import AssetKind, AuthStatus, ContentKind, LoginMethod, Platform, RunStatus
from media_sync.exporters.emby import EmbyExporter
from media_sync.infrastructure.db import (
    AccountRepository,
    AuthorRepository,
    AuthorUpsert,
    Database,
    IngestionMode,
    MediaCrawlerIngestionService,
    SubscriptionRepository,
    SyncRunRepository,
    upgrade_database,
)
from media_sync.infrastructure.db.asset_identity import asset_source_hint, stable_asset_key
from media_sync.infrastructure.db.models import (
    Account,
    Asset,
    AssetRefreshSource,
    Author,
    Content,
    ExportRecord,
    Job,
    Subscription,
    SyncRun,
)
from media_sync.integrations.mediacrawler import MediaCrawlerDetailRequest, MediaCrawlerDetailResult
from media_sync.integrations.mediacrawler.normalizers import (
    NormalizationContext,
    NormalizedMediaRecord,
    normalize_jsonl_bytes,
)
from media_sync.integrations.mediacrawler.xhs_live import XHS_LIVE_VIDEO_FIELD
from media_sync.media import (
    AdapterRefreshLocator,
    FFprobeMediaProbe,
    MediaRequestProfile,
    ProbeResult,
    ResolvedLocator,
    SafeHttpClient,
    SecureMediaDownloader,
    ValidatedTarget,
    parse_locator,
)
from media_sync.security import EnvironmentSecretProvider, SecretResolver, SecretScheme

FIXED_AT = datetime(2026, 9, 1, 12, 18, 0, tzinfo=UTC)
UPSTREAM_SHA = "d6f7c5bb906b6dac40ddf343ef9e26438a3de092"
AUTHOR_REMOTE_ID = "5f58bd990000000001003754"
CONTENT_ID = "66fad51c000000001b0224c8"
DISTRACTOR_ID = "66fad51c000000001b0224c9"
VIDEO_REMOTE_ID = f"{CONTENT_ID}:video:0"
IMAGE_REMOTE_ID = f"{CONTENT_ID}:image:0"
CREATOR_MAX_ITEMS = 8
CREATOR_SECRET_REF = "env:MEDIA_SYNC_EXECUTION0018_XHS_CREATOR_URL"
CREATOR_TOKEN = "EXECUTION0018XHSCREATORTOKEN"
CREATOR_REFERENCE = (
    f"https://www.xiaohongshu.com/user/profile/{AUTHOR_REMOTE_ID}?xsec_token={CREATOR_TOKEN}&xsec_source=pc_search"
)

VIDEO_HINT = f"https://sns-video-bd.xhscdn.com/execution-0018/{CONTENT_ID}.mp4"
IMAGE_HINT = f"https://sns-webpic-qc.xhscdn.com/execution-0018/{CONTENT_ID}.png"
DISCOVERY_V1_SIGNATURE = "EXECUTION0018DISCOVERYVIDEOSIGNATUREV1"
DISCOVERY_V2_SIGNATURE = "EXECUTION0018DISCOVERYVIDEOSIGNATUREV2"
DISCOVERY_IMAGE_V1_SIGNATURE = "EXECUTION0018DISCOVERYIMAGESIGNATUREV1"
DISCOVERY_IMAGE_V2_SIGNATURE = "EXECUTION0018DISCOVERYIMAGESIGNATUREV2"
REFRESH_VIDEO_SIGNATURE = "EXECUTION0018REFRESHVIDEOSIGNATURE"
REFRESH_IMAGE_SIGNATURE = "EXECUTION0018REFRESHIMAGESIGNATURE"
DISCOVERY_NOTE_TOKEN_V1 = "EXECUTION0018DISCOVERYNOTETOKENV1"
DISCOVERY_NOTE_TOKEN_V2 = "EXECUTION0018DISCOVERYNOTETOKENV2"
REFRESH_NOTE_TOKEN = "EXECUTION0018REFRESHNOTETOKEN"
DISTRACTOR_TOKEN = "EXECUTION0018DISTRACTORNOTETOKEN"
DISTRACTOR_VIDEO_URL = (
    "https://sns-video-bd.xhscdn.com/execution-0018/distractor.mp4?sign=EXECUTION0018DISTRACTORVIDEOSIGNATURE"
)

DISCOVERY_VIDEO_V1 = f"{VIDEO_HINT}?sign={DISCOVERY_V1_SIGNATURE}&quality=1080"
DISCOVERY_VIDEO_V2 = f"{VIDEO_HINT}?sign={DISCOVERY_V2_SIGNATURE}&quality=1080"
DISCOVERY_IMAGE_V1 = f"{IMAGE_HINT}?sign={DISCOVERY_IMAGE_V1_SIGNATURE}&size=large"
DISCOVERY_IMAGE_V2 = f"{IMAGE_HINT}?sign={DISCOVERY_IMAGE_V2_SIGNATURE}&size=large"
REFRESH_VIDEO_URL = f"{VIDEO_HINT}?sign={REFRESH_VIDEO_SIGNATURE}&quality=1080"
REFRESH_IMAGE_URL = f"{IMAGE_HINT}?sign={REFRESH_IMAGE_SIGNATURE}&size=large"

H264_MP4_BASE64 = (
    "AAAAIGZ0eXBpc29tAAACAGlzb21pc28yYXZjMW1wNDEAAALwbW9vdgAAAGxtdmhkAAAAAAAAAAAAAAAAAAAD6AAAA+gAAQAAAQAA"
    "AAAAAAAAAAAAAAEAAAAAAAAAAAAAAAAAAAABAAAAAAAAAAAAAAAAAABAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAgAA"
    "Aj90cmFrAAAAXHRraGQAAAADAAAAAAAAAAAAAAABAAAAAAAAA+gAAAAAAAAAAAAAAAAAAAAAAAEAAAAAAAAAAAAAAAAAAAABAAAA"
    "AAAAAAAAAAAAAABAAAAAABAAAAAQAAAAAAAkZWR0cwAAABxlbHN0AAAAAAAAAAEAAAPoAAAAAAABAAAAAAG3bWRpYQAAACBtZGhk"
    "AAAAAAAAAAAAAAAAAABAAAAAQABVxAAAAAAALWhkbHIAAAAAAAAAAHZpZGUAAAAAAAAAAAAAAABWaWRlb0hhbmRsZXIAAAABYm1p"
    "bmYAAAAUdm1oZAAAAAEAAAAAAAAAAAAAACRkaW5mAAAAHGRyZWYAAAAAAAAAAQAAAAx1cmwgAAAAAQAAASJzdGJsAAAAvnN0c2QA"
    "AAAAAAAAAQAAAK5hdmMxAAAAAAAAAAEAAAAAAAAAAAAAAAAAAAAAABAAEABIAAAASAAAAAAAAAABDExhdmMgbGlieDI2NAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAGP//AAAANGF2Y0MBZAAK/+EAF2dkAAqs2V7ARAAAAwAEAAADAAg8SJZYAQAGaOvjyyLA/fj4AAAAABBw"
    "YXNwAAAAAQAAAAEAAAAUYnRydAAAAAAAABW4AAAAAAAAABhzdHRzAAAAAAAAAAEAAAABAABAAAAAABxzdHNjAAAAAAAAAAEAAAAB"
    "AAAAAQAAAAEAAAAUc3RzegAAAAAAAAK3AAAAAQAAABRzdGNvAAAAAAAAAAEAAAMgAAAAPXVkdGEAAAA1bWV0YQAAAAAAAAAhaGRs"
    "cgAAAAAAAAAAbWRpcmFwcGwAAAAAAAAAAAAAAAAIaWxzdAAAAAhmcmVlAAACv21kYXQAAAKfBgX//5vcRem95tlIt5Ys2CDZI+7v"
    "eDI2NCAtIGNvcmUgMTY0IC0gSC4yNjQvTVBFRy00IEFWQyBjb2RlYyAtIENvcHlsZWZ0IDIwMDMtMjAyNSAtIGh0dHA6Ly93d3cu"
    "dmlkZW9sYW4ub3JnL3gyNjQuaHRtbCAtIG9wdGlvbnM6IGNhYmFjPTEgcmVmPTMgZGVibG9jaz0xOjA6MCBhbmFseXNlPTB4Mzow"
    "eDExMyBtZT1oZXggc3VibWU9NyBwc3k9MSBwc3lfcmQ9MS4wMDowLjAwIG1peGVkX3JlZj0xIG1lX3JhbmdlPTE2IGNocm9tYV9t"
    "ZT0xIHRyZWxsaXM9MSA4eDhkY3Q9MSBjcW09MCBkZWFkem9uZT0yMSwxMSBmYXN0X3Bza2lwPTEgY2hyb21hX3FwX29mZnNldD0t"
    "MiB0aHJlYWRzPTEgbG9va2FoZWFkX3RocmVhZHM9MSBzbGljZWRfdGhyZWFkcz0wIG5yPTAgZGVjaW1hdGU9MSBpbnRlcmxhY2Vk"
    "PTAgYmx1cmF5X2NvbXBhdD0wIGNvbnN0cmFpbmVkX2ludHJhPTAgYmZyYW1lcz0zIGJfcHlyYW1pZD0yIGJfYWRhcHQ9MSBiX2Jp"
    "YXM9MCBkaXJlY3Q9MSB3ZWlnaHRiPTEgb3Blbl9nb3A9MCB3ZWlnaHRwPTIga2V5aW50PTI1MCBrZXlpbnRfbWluPTEgc2NlbmVj"
    "dXQ9NDAgaW50cmFfcmVmcmVzaD0wIHJjX2xvb2thaGVhZD00MCByYz1jcmYgbWJ0cmVlPTEgY3JmPTIzLjAgcWNvbXA9MC42MCBx"
    "cG1pbj0wIHFwbWF4PTY5IHFwc3RlcD00IGlwX3JhdGlvPTEuNDAgYXE9MToxLjAwAIAAAAAQZYiEABX//vfJ78Cm69vfgQ=="
)
MP4 = b64decode(H264_MP4_BASE64, validate=True)
PNG = b"\x89PNG\r\n\x1a\n" + b"execution-0018-offline-xhs-poster"
FORBIDDEN_VALUES = (
    CREATOR_REFERENCE,
    CREATOR_TOKEN,
    DISCOVERY_V1_SIGNATURE,
    DISCOVERY_V2_SIGNATURE,
    DISCOVERY_IMAGE_V1_SIGNATURE,
    DISCOVERY_IMAGE_V2_SIGNATURE,
    REFRESH_VIDEO_SIGNATURE,
    REFRESH_IMAGE_SIGNATURE,
    DISCOVERY_NOTE_TOKEN_V1,
    DISCOVERY_NOTE_TOKEN_V2,
    REFRESH_NOTE_TOKEN,
    DISTRACTOR_TOKEN,
    "EXECUTION0018DISTRACTORVIDEOSIGNATURE",
    DISCOVERY_VIDEO_V1,
    DISCOVERY_VIDEO_V2,
    DISCOVERY_IMAGE_V1,
    DISCOVERY_IMAGE_V2,
    REFRESH_VIDEO_URL,
    REFRESH_IMAGE_URL,
    DISTRACTOR_VIDEO_URL,
    "xsec_token=",
    "?sign=",
)
CREATOR_AUTHORITY_VALUES = (CREATOR_REFERENCE, CREATOR_TOKEN, CREATOR_SECRET_REF)


def _jsonl(*records: Mapping[str, object]) -> bytes:
    return b"".join(
        (json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()
        for record in records
    )


def _xhs_video_record(
    note_id: str,
    *,
    video_url: str,
    image_url: str,
    note_token: str,
    title: str,
) -> dict[str, object]:
    return {
        "note_id": note_id,
        "type": "video",
        "title": title,
        "desc": f"{title} offline fixture",
        "video_url": video_url,
        "time": 1788235200000,
        "last_update_time": 1788235260000,
        "creator_hash": "untrusted-xhs-creator",
        "nickname": "Untrusted nickname",
        "liked_count": "18",
        "collected_count": "3",
        "comment_count": "2",
        "share_count": "1",
        "image_list": image_url,
        "tag_list": "offline,video",
        "last_modify_ts": 1788235320000,
        "note_url": (f"https://www.xiaohongshu.com/explore/{note_id}?xsec_token={note_token}&xsec_source=pc_search"),
        "source_keyword": "fixture",
        "xsec_token": note_token,
    }


DISCOVERY_JSONL_V1 = _jsonl(
    _xhs_video_record(
        CONTENT_ID,
        video_url=DISCOVERY_VIDEO_V1,
        image_url=DISCOVERY_IMAGE_V1,
        note_token=DISCOVERY_NOTE_TOKEN_V1,
        title="Execution 0018 XHS playable video",
    )
)
DISCOVERY_JSONL_V2 = _jsonl(
    _xhs_video_record(
        CONTENT_ID,
        video_url=DISCOVERY_VIDEO_V2,
        image_url=DISCOVERY_IMAGE_V2,
        note_token=DISCOVERY_NOTE_TOKEN_V2,
        title="Execution 0018 XHS playable video",
    )
)
DETAIL_JSONL = _jsonl(
    _xhs_video_record(
        DISTRACTOR_ID,
        video_url=DISTRACTOR_VIDEO_URL,
        image_url="",
        note_token=DISTRACTOR_TOKEN,
        title="Distractor XHS video",
    ),
    _xhs_video_record(
        CONTENT_ID,
        video_url=REFRESH_VIDEO_URL,
        image_url=REFRESH_IMAGE_URL,
        note_token=REFRESH_NOTE_TOKEN,
        title="Execution 0018 XHS playable video",
    ),
)


def _normalization_context() -> NormalizationContext:
    return NormalizationContext(
        platform=Platform.XHS,
        creator_remote_id=AUTHOR_REMOTE_ID,
        creator_display_name="XHS Offline Video Creator",
        upstream_sha=UPSTREAM_SHA,
        ingested_at=FIXED_AT,
    )


def _policy() -> dict[str, object]:
    return {
        "mediacrawler": {
            "schema_version": 1,
            "allow_full_history": False,
            "request_delay_seconds": 1.0,
            "headless": True,
            "creator_input": {"secret_ref": CREATOR_SECRET_REF},
        }
    }


def _start_ingesting_run(database: Database, subscription_id: str) -> str:
    with database.session() as session:
        runs = SyncRunRepository(session)
        run = runs.create(subscription_id=subscription_id)
        runs.set_status(run.id, RunStatus.CLAIMED.value, expected_status=RunStatus.QUEUED.value)
        runs.set_status(run.id, RunStatus.RUNNING.value, expected_status=RunStatus.CLAIMED.value)
        runs.set_status(run.id, RunStatus.INGESTING.value, expected_status=RunStatus.RUNNING.value)
        return run.id


@dataclass(frozen=True, slots=True)
class _Seed:
    account_id: str
    author_id: str
    subscription_id: str


def _seed_subscription(database: Database) -> _Seed:
    with database.session() as session:
        account = AccountRepository(session).create(
            platform=Platform.XHS.value,
            adapter="mediacrawler",
            display_name="execution-0018-offline-account",
            login_method=LoginMethod.QR.value,
            auth_status=AuthStatus.AUTHENTICATED.value,
        )
        author = AuthorRepository(session).upsert(
            AuthorUpsert(
                platform=Platform.XHS.value,
                remote_id=AUTHOR_REMOTE_ID,
                display_name="XHS Offline Video Creator",
            ),
            seen_at=FIXED_AT,
        )
        subscription = SubscriptionRepository(session).create(
            account_id=account.id,
            author_id=author.id,
            policy=_policy(),
            max_items=CREATOR_MAX_ITEMS,
        )
        return _Seed(account.id, author.id, subscription.id)


class _FakeDetailRunner:
    instances: ClassVar[list[_FakeDetailRunner]] = []

    def __init__(self, **kwargs: object) -> None:
        self.constructor_kwargs = kwargs
        self.calls: list[MediaCrawlerDetailRequest] = []
        type(self).instances.append(self)

    def run(self, request: MediaCrawlerDetailRequest) -> MediaCrawlerDetailResult:
        self.calls.append(request)
        return MediaCrawlerDetailResult(DETAIL_JSONL, UPSTREAM_SHA)


@dataclass(slots=True)
class _RecordingRefresher:
    delegate: LazyMediaCrawlerLocatorRefresher
    results: list[ResolvedLocator] = field(default_factory=list)

    def resolve(self, locator: AdapterRefreshLocator) -> ResolvedLocator:
        resolved = self.delegate.resolve(locator)
        self.results.append(resolved)
        return resolved


class _RecordingPublicResolver:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []

    def resolve(self, hostname: str, port: int) -> Sequence[str]:
        self.calls.append((hostname, port))
        return ("8.8.8.8",)


class _ControlledMp4Probe:
    def __init__(self, *, expected_payloads: Mapping[str, bytes] | None = None) -> None:
        self.expected_payloads = expected_payloads
        self.calls: list[Path] = []

    def probe(self, path: Path, *, timeout_seconds: float, max_output_bytes: int) -> ProbeResult:
        assert timeout_seconds > 0
        assert max_output_bytes > 0
        self.calls.append(path)
        payload = path.read_bytes()
        if self.expected_payloads is None:
            assert payload == MP4
        else:
            assert payload in self.expected_payloads.values()
        return ProbeResult("video/mp4", "mp4")


@dataclass(frozen=True, slots=True)
class _DownloadHarness:
    service: AssetDownloadService
    request: AssetDownloadRequest
    refresher: _RecordingRefresher


def _download_harness(
    database: Database,
    *,
    asset_id: UUID,
    subscription_id: UUID,
    worker_id: str,
    tmp_path: Path,
    runtime_root: Path,
    download_work_root: Path,
    archive_root: Path,
    http: SafeHttpClient,
    probe: _ControlledMp4Probe,
    secret_resolver: SecretResolver,
) -> _DownloadHarness:
    lazy_refresher = LazyMediaCrawlerLocatorRefresher(
        database,
        asset_id=asset_id,
        subscription_id=subscription_id,
        lock_path=tmp_path / "upstreams.lock.json",
        integration_root=runtime_root,
        python_executable=tmp_path / "python",
        secret_resolver=secret_resolver,
        license_acknowledged=True,
    )
    refresher = _RecordingRefresher(lazy_refresher)
    return _DownloadHarness(
        service=AssetDownloadService(
            database,
            SecureMediaDownloader(http, refresher=refresher, probe=probe),
            clock=lambda: FIXED_AT,
        ),
        request=AssetDownloadRequest(
            asset_id=asset_id,
            worker_id=worker_id,
            work_root=download_work_root,
            archive_root=archive_root,
            lease_seconds=60,
        ),
        refresher=refresher,
    )


def _tree(root: Path) -> dict[str, bytes]:
    if not root.exists():
        return {}
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"), key=lambda item: item.as_posix())
        if path.is_file()
    }


def _assert_ephemeral_values_absent(*roots: Path) -> None:
    forbidden = tuple(value.encode() for value in FORBIDDEN_VALUES)
    for root in roots:
        retained = {root.name: root.read_bytes()} if root.is_file() else _tree(root)
        for relative_path, payload in retained.items():
            assert all(value not in payload for value in forbidden), relative_path


def _iter_strings(value: object) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, Mapping):
        for key, item in value.items():
            yield from _iter_strings(key)
            yield from _iter_strings(item)
    elif isinstance(value, Sequence) and not isinstance(value, bytes | bytearray):
        for item in value:
            yield from _iter_strings(item)


def _assert_transient_snapshot(
    record: NormalizedMediaRecord,
    *,
    video_url: str,
    image_url: str,
    note_token: str,
) -> None:
    raw_record = record.content.raw.get("record")
    assert isinstance(raw_record, Mapping)
    assert raw_record["type"] == "video"
    assert raw_record["video_url"] == video_url
    assert raw_record["image_list"] == image_url
    assert raw_record["note_url"] == (
        f"https://www.xiaohongshu.com/explore/{CONTENT_ID}?xsec_token={note_token}&xsec_source=pc_search"
    )
    assert raw_record["xsec_token"] == note_token

    expected_sources = tuple(value for value in (image_url, video_url) if value)
    actual_sources = tuple(asset.source_url for asset in record.assets)
    assert actual_sources == expected_sources
    assert all(source is not None and urlsplit(source).query for source in actual_sources)

    snapshot_strings = tuple(
        _iter_strings(
            (record.author.raw, record.content.raw, tuple(asset.raw for asset in record.assets), actual_sources)
        )
    )
    assert all(authority not in retained for authority in CREATOR_AUTHORITY_VALUES for retained in snapshot_strings)


def _assert_query_free_http_urls(*values: object) -> None:
    urls = tuple(
        value for root in values for value in _iter_strings(root) if urlsplit(value).scheme.lower() in {"http", "https"}
    )
    assert urls
    for url in urls:
        parsed = urlsplit(url)
        assert parsed.username is None
        assert parsed.password is None
        assert parsed.query == ""
        assert parsed.fragment == ""


def _assert_durable_xhs_raw(raw: Mapping[str, object]) -> None:
    record = raw.get("record")
    assert isinstance(record, Mapping)
    assert record["type"] == "video"
    assert record["video_url"] == VIDEO_HINT
    assert record["image_list"] == IMAGE_HINT
    assert record["note_url"] == f"https://www.xiaohongshu.com/explore/{CONTENT_ID}"
    assert "xsec_token" not in record
    assert "xsec_source" not in record


def test_embedded_h264_fixture_is_accepted_by_production_ffprobe(tmp_path: Path) -> None:
    executable = shutil.which("ffprobe")
    if executable is None:
        pytest.skip("ffprobe is not installed")
    fixture = tmp_path / "execution-0018-real-h264.mp4"
    fixture.write_bytes(MP4)

    result = FFprobeMediaProbe(executable).probe(
        fixture,
        timeout_seconds=5.0,
        max_output_bytes=16 * 1024,
    )

    assert result == ProbeResult("video/mp4", "mp4")


def test_xhs_creator_video_reaches_emby_and_replays_without_live_work(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    video_only = normalize_jsonl_bytes(
        _jsonl(
            _xhs_video_record(
                CONTENT_ID,
                video_url=DISCOVERY_VIDEO_V1,
                image_url="",
                note_token=DISCOVERY_NOTE_TOKEN_V1,
                title="Execution 0018 XHS video without artwork",
            )
        ),
        _normalization_context(),
    )
    assert not video_only.quarantined and not video_only.truncated_tail
    assert len(video_only.records) == 1
    assert video_only.records[0].content.kind is ContentKind.VIDEO
    assert [(asset.kind, asset.position, asset.remote_id) for asset in video_only.records[0].assets] == [
        (AssetKind.VIDEO, 0, VIDEO_REMOTE_ID)
    ]
    assert asset_source_hint(video_only.records[0].assets[0].source_url) == VIDEO_HINT
    _assert_transient_snapshot(
        video_only.records[0],
        video_url=DISCOVERY_VIDEO_V1,
        image_url="",
        note_token=DISCOVERY_NOTE_TOKEN_V1,
    )

    database_path = tmp_path / "xhs-playable-video.sqlite3"
    database_url = f"sqlite+pysqlite:///{database_path.as_posix()}"
    archive_root = tmp_path / "archive"
    library_root = tmp_path / "library"
    runtime_root = tmp_path / "mediacrawler-runtime"
    download_work_root = tmp_path / "download-work"
    export_work_root = tmp_path / "export-work"
    runtime_root.mkdir()
    upgrade_database(database_url)
    database = Database(database_url)
    _FakeDetailRunner.instances = []
    monkeypatch.setattr(mediacrawler_runtime, "MediaCrawlerDetailProcessRunner", _FakeDetailRunner)

    try:
        seed = _seed_subscription(database)
        normalized_v1 = normalize_jsonl_bytes(DISCOVERY_JSONL_V1, _normalization_context())
        assert not normalized_v1.quarantined and not normalized_v1.truncated_tail
        assert len(normalized_v1.records) == 1
        record = normalized_v1.records[0]
        assert record.author.remote_id == AUTHOR_REMOTE_ID
        assert record.content.kind is ContentKind.MIXED
        assert [(asset.kind, asset.position, asset.remote_id) for asset in record.assets] == [
            (AssetKind.IMAGE, 0, IMAGE_REMOTE_ID),
            (AssetKind.VIDEO, 0, VIDEO_REMOTE_ID),
        ]
        assert [asset.mime_type for asset in record.assets] == ["image/png", "video/mp4"]
        assert [asset_source_hint(asset.source_url) for asset in record.assets] == [IMAGE_HINT, VIDEO_HINT]
        _assert_transient_snapshot(
            record,
            video_url=DISCOVERY_VIDEO_V1,
            image_url=DISCOVERY_IMAGE_V1,
            note_token=DISCOVERY_NOTE_TOKEN_V1,
        )

        first_run_id = _start_ingesting_run(database, seed.subscription_id)
        first_ingest = MediaCrawlerIngestionService(database).ingest(
            normalized_v1.records,
            subscription_id=seed.subscription_id,
            run_id=first_run_id,
            expected_revision=0,
            mode=IngestionMode.FORWARD,
        )
        assert (first_ingest.accepted_count, first_ingest.discovered_count, first_ingest.asset_count) == (1, 1, 2)

        with database.session() as session:
            account = session.get(Account, seed.account_id)
            subscription = session.get(Subscription, seed.subscription_id)
            assets = {asset.kind: asset for asset in session.scalars(select(Asset)).all()}
            sources = {source.asset_id: source for source in session.scalars(select(AssetRefreshSource)).all()}
            assert account is not None and subscription is not None
            assert (
                account.platform,
                account.adapter,
                account.login_method,
                account.auth_status,
                account.credential_ref,
            ) == (
                Platform.XHS.value,
                "mediacrawler",
                LoginMethod.QR.value,
                AuthStatus.AUTHENTICATED.value,
                None,
            )
            assert (subscription.account_id, subscription.author_id) == (seed.account_id, seed.author_id)
            assert subscription.max_items == CREATOR_MAX_ITEMS
            assert subscription.policy == _policy()
            assert set(assets) == {AssetKind.IMAGE.value, AssetKind.VIDEO.value}
            for kind, remote_id, source_hint in (
                (AssetKind.IMAGE, IMAGE_REMOTE_ID, IMAGE_HINT),
                (AssetKind.VIDEO, VIDEO_REMOTE_ID, VIDEO_HINT),
            ):
                asset = assets[kind.value]
                locator = parse_locator(asset.locator)
                assert isinstance(locator, AdapterRefreshLocator)
                assert locator.adapter == "mediacrawler"
                assert locator.asset_key == stable_asset_key(
                    platform=Platform.XHS.value,
                    content_remote_type="content",
                    content_remote_id=CONTENT_ID,
                    kind=kind.value,
                    position=0,
                    remote_id=remote_id,
                )
                assert (asset.remote_id, asset.position, asset.generation, asset.source_url) == (
                    remote_id,
                    0,
                    1,
                    source_hint,
                )
                source = sources[asset.id]
                assert source.subscription_id == seed.subscription_id
                assert source.last_run_id == first_run_id
                assert source.observation_kind == "ingested"
                assert source.observed_generation == 1
                assert source.observed_semantic_fingerprint == asset.semantic_fingerprint
                assert source.observed_locator_fingerprint == asset.locator_fingerprint
            asset_ids = {kind: UUID(asset.id) for kind, asset in assets.items()}

        resolver = _RecordingPublicResolver()
        targets: list[ValidatedTarget] = []
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            assert set(request.headers) == {"accept", "accept-encoding", "connection", "host", "user-agent"}
            assert request.headers["accept-encoding"] == "identity"
            assert not request.headers["user-agent"].startswith("Mozilla/5.0")
            for forbidden_header in ("cookie", "authorization", "referer", "origin"):
                assert forbidden_header not in request.headers
            if str(request.url) == REFRESH_VIDEO_URL:
                assert request.headers["host"] == "sns-video-bd.xhscdn.com"
                return httpx.Response(
                    200,
                    headers={
                        "Content-Length": str(len(MP4)),
                        "Content-Type": "video/mp4",
                        "ETag": '"execution-0018-xhs-video-v1"',
                    },
                    content=MP4,
                )
            if str(request.url) == REFRESH_IMAGE_URL:
                assert request.headers["host"] == "sns-webpic-qc.xhscdn.com"
                return httpx.Response(
                    200,
                    headers={
                        "Content-Length": str(len(PNG)),
                        "Content-Type": "image/png",
                        "ETag": '"execution-0018-xhs-image-v1"',
                    },
                    content=PNG,
                )
            raise AssertionError("unexpected XHS media URL")

        def transport_factory(target: ValidatedTarget) -> httpx.BaseTransport:
            targets.append(target)
            return httpx.MockTransport(handler)

        probe = _ControlledMp4Probe()
        http = SafeHttpClient(resolver, transport_factory=transport_factory)
        secret_resolver = SecretResolver(
            {
                SecretScheme.ENV: EnvironmentSecretProvider(
                    {"MEDIA_SYNC_EXECUTION0018_XHS_CREATOR_URL": CREATOR_REFERENCE}
                )
            }
        )
        video_harness = _download_harness(
            database,
            asset_id=asset_ids[AssetKind.VIDEO.value],
            subscription_id=UUID(seed.subscription_id),
            worker_id="execution-0018-xhs-video-download",
            tmp_path=tmp_path,
            runtime_root=runtime_root,
            download_work_root=download_work_root,
            archive_root=archive_root,
            http=http,
            probe=probe,
            secret_resolver=secret_resolver,
        )
        image_harness = _download_harness(
            database,
            asset_id=asset_ids[AssetKind.IMAGE.value],
            subscription_id=UUID(seed.subscription_id),
            worker_id="execution-0018-xhs-image-download",
            tmp_path=tmp_path,
            runtime_root=runtime_root,
            download_work_root=download_work_root,
            archive_root=archive_root,
            http=http,
            probe=probe,
            secret_resolver=secret_resolver,
        )

        first_video = video_harness.service.run(video_harness.request)
        first_image = image_harness.service.run(image_harness.request)
        video_checksum = hashlib.sha256(MP4).hexdigest()
        image_checksum = hashlib.sha256(PNG).hexdigest()
        expected_video_archive = archive_root / "sha256" / video_checksum[:2] / f"{video_checksum}.mp4"
        expected_image_archive = archive_root / "sha256" / image_checksum[:2] / f"{image_checksum}.png"
        assert first_video.disposition == first_image.disposition == "downloaded"
        assert (first_video.archive_path, first_video.checksum_sha256, first_video.mime_type) == (
            expected_video_archive.absolute(),
            video_checksum,
            "video/mp4",
        )
        assert (first_image.archive_path, first_image.checksum_sha256, first_image.mime_type) == (
            expected_image_archive.absolute(),
            image_checksum,
            "image/png",
        )
        assert expected_video_archive.read_bytes() == MP4
        assert expected_image_archive.read_bytes() == PNG
        assert len(probe.calls) == 1
        assert resolver.calls == [
            ("sns-video-bd.xhscdn.com", 443),
            ("sns-webpic-qc.xhscdn.com", 443),
        ]
        assert [target.address for target in targets] == ["8.8.8.8", "8.8.8.8"]
        assert [str(request.url) for request in requests] == [REFRESH_VIDEO_URL, REFRESH_IMAGE_URL]
        assert video_harness.refresher.results[0].url == REFRESH_VIDEO_URL
        assert image_harness.refresher.results[0].url == REFRESH_IMAGE_URL
        resolved_results = video_harness.refresher.results + image_harness.refresher.results
        assert all(result.request_profile is MediaRequestProfile.DEFAULT for result in resolved_results)
        assert all(REFRESH_VIDEO_SIGNATURE not in repr(result) for result in resolved_results)
        assert all(REFRESH_IMAGE_SIGNATURE not in repr(result) for result in resolved_results)

        assert len(_FakeDetailRunner.instances) == 2
        first_detail_instances = tuple(_FakeDetailRunner.instances)
        first_detail_calls = tuple(call for runner in first_detail_instances for call in runner.calls)
        assert len(first_detail_calls) == 2
        expected_runner_kwargs = {
            "integration_root": runtime_root,
            "license_acknowledged": True,
            "lock_path": tmp_path / "upstreams.lock.json",
            "python_executable": tmp_path / "python",
        }
        assert all(runner.constructor_kwargs == expected_runner_kwargs for runner in first_detail_instances)
        for detail_request in first_detail_calls:
            assert detail_request.account_id == UUID(seed.account_id)
            assert detail_request.subscription_id == UUID(seed.subscription_id)
            assert detail_request.platform is Platform.XHS
            assert detail_request.login_method is LoginMethod.QR
            assert detail_request.content_remote_id == CONTENT_ID
            assert detail_request.author_remote_id == AUTHOR_REMOTE_ID
            assert detail_request.detail_reference is None
            assert detail_request.creator_reference is not None
            assert detail_request.creator_reference.reveal() == CREATOR_REFERENCE
            assert detail_request.creator_max_items == CREATOR_MAX_ITEMS
            assert detail_request.bili_progressive_detail is False
            assert CREATOR_TOKEN not in repr(detail_request)
        assert all(
            value not in repr(MediaCrawlerDetailResult(DETAIL_JSONL, UPSTREAM_SHA)) for value in FORBIDDEN_VALUES
        )

        first_live_counts = (
            len(_FakeDetailRunner.instances),
            sum(len(runner.calls) for runner in _FakeDetailRunner.instances),
            len(requests),
            len(targets),
            len(resolver.calls),
            len(probe.calls),
        )
        assert first_live_counts == (2, 2, 2, 2, 2, 1)

        export_service = EmbyExportService(
            database,
            EmbyExporter(library_root, staging_root=export_work_root),
            clock=lambda: FIXED_AT,
        )
        first_export = export_service.export_author(
            EmbyExportRequest(seed.author_id, "execution-0018-xhs-export", lease_seconds=60)
        )
        assert first_export.already_exported is False
        author_directory = library_root / first_export.output_path
        exported_video = next(author_directory.glob("Season */*.mp4"))
        exported_poster = next(author_directory.glob("Season */*-poster.png"))
        assert exported_video.read_bytes() == MP4
        assert exported_poster.read_bytes() == PNG
        assert (author_directory / "tvshow.nfo").is_file()
        episode_nfo = next(author_directory.glob("Season */*.nfo"))
        assert CONTENT_ID.encode() in episode_nfo.read_bytes()
        assert exported_poster.name.encode() in episode_nfo.read_bytes()
        assert (author_directory / ".media-sync-managed-v1.json").is_file()
        source_path = next(author_directory.glob("Season */*.assets/source.json"))
        source_document = json.loads(source_path.read_text("utf-8"))
        assert source_document["platform"] == Platform.XHS.value
        assert source_document["remote_id"] == CONTENT_ID
        assert {
            (item["kind"], item["position"], item["remote_id"], item["checksum_sha256"])
            for item in source_document["assets"]
        } == {
            (AssetKind.IMAGE.value, 0, IMAGE_REMOTE_ID, image_checksum),
            (AssetKind.VIDEO.value, 0, VIDEO_REMOTE_ID, video_checksum),
        }
        assert not {"canonical_url", "locator", "raw", "source_url"} & source_document.keys()

        first_archive_tree = _tree(archive_root)
        first_library_tree = _tree(author_directory)
        _assert_ephemeral_values_absent(
            runtime_root,
            download_work_root,
            archive_root,
            export_work_root,
            library_root,
        )

        normalized_v2 = normalize_jsonl_bytes(DISCOVERY_JSONL_V2, _normalization_context())
        assert not normalized_v2.quarantined and not normalized_v2.truncated_tail
        assert [asset_source_hint(asset.source_url) for asset in normalized_v2.records[0].assets] == [
            IMAGE_HINT,
            VIDEO_HINT,
        ]
        _assert_transient_snapshot(
            normalized_v2.records[0],
            video_url=DISCOVERY_VIDEO_V2,
            image_url=DISCOVERY_IMAGE_V2,
            note_token=DISCOVERY_NOTE_TOKEN_V2,
        )
        second_run_id = _start_ingesting_run(database, seed.subscription_id)
        second_ingest = MediaCrawlerIngestionService(database).ingest(
            normalized_v2.records,
            subscription_id=seed.subscription_id,
            run_id=second_run_id,
            expected_revision=1,
            mode=IngestionMode.FORWARD,
        )
        assert (second_ingest.accepted_count, second_ingest.discovered_count, second_ingest.asset_count) == (0, 0, 0)
        assert second_ingest.checkpoint_revision == 2

        replay_video = video_harness.service.run(video_harness.request)
        replay_image = image_harness.service.run(image_harness.request)
        replay_export = export_service.export_author(
            EmbyExportRequest(seed.author_id, "execution-0018-xhs-export-replay", lease_seconds=60)
        )
        assert replay_video.disposition == replay_image.disposition == "already_verified"
        assert replay_video.job_id == first_video.job_id
        assert replay_image.job_id == first_image.job_id
        assert replay_video.archive_path == first_video.archive_path
        assert replay_image.archive_path == first_image.archive_path
        assert replay_export.already_exported is True
        assert replay_export.job_id == first_export.job_id
        assert replay_export.source_fingerprint == first_export.source_fingerprint
        assert replay_export.rendered_fingerprint == first_export.rendered_fingerprint

        replay_detail_instances = tuple(_FakeDetailRunner.instances)
        replay_detail_calls = tuple(call for runner in _FakeDetailRunner.instances for call in runner.calls)
        replay_live_counts = (
            len(_FakeDetailRunner.instances),
            sum(len(runner.calls) for runner in _FakeDetailRunner.instances),
            len(requests),
            len(targets),
            len(resolver.calls),
            len(probe.calls),
        )
        assert replay_detail_instances == first_detail_instances
        assert replay_detail_calls == first_detail_calls
        assert replay_live_counts == first_live_counts
        assert _tree(archive_root) == first_archive_tree
        assert _tree(author_directory) == first_library_tree

        with database.session() as session:
            final_account = session.get(Account, seed.account_id)
            final_author = session.get(Author, seed.author_id)
            final_subscription = session.get(Subscription, seed.subscription_id)
            final_assets = {asset.kind: asset for asset in session.scalars(select(Asset)).all()}
            final_content = session.scalar(select(Content))
            final_sources = list(session.scalars(select(AssetRefreshSource)).all())
            jobs = list(session.scalars(select(Job).order_by(Job.job_type, Job.natural_key)).all())
            runs = list(session.scalars(select(SyncRun).order_by(SyncRun.created_at)).all())
            exports = list(session.scalars(select(ExportRecord)).all())
            assert final_account is not None
            assert final_author is not None
            assert final_subscription is not None
            assert final_content is not None
            assert set(final_assets) == {AssetKind.IMAGE.value, AssetKind.VIDEO.value}
            assert all(asset.status == "verified" and asset.generation == 1 for asset in final_assets.values())
            assert final_assets[AssetKind.VIDEO.value].source_url == VIDEO_HINT
            assert final_assets[AssetKind.IMAGE.value].source_url == IMAGE_HINT
            assert final_assets[AssetKind.VIDEO.value].local_path == str(expected_video_archive.absolute())
            assert final_assets[AssetKind.IMAGE.value].local_path == str(expected_image_archive.absolute())
            assert final_assets[AssetKind.VIDEO.value].checksum_sha256 == video_checksum
            assert final_assets[AssetKind.IMAGE.value].checksum_sha256 == image_checksum
            assert final_assets[AssetKind.VIDEO.value].mime_type == "video/mp4"
            assert final_assets[AssetKind.IMAGE.value].mime_type == "image/png"
            assert len(final_sources) == 2
            assert all(
                source.subscription_id == seed.subscription_id and source.observed_generation == 1
                for source in final_sources
            )
            assert final_subscription.checkpoint_revision == 2
            assert [run.status for run in runs] == ["succeeded", "succeeded"]
            assert [job.job_type for job in jobs].count("asset_download") == 2
            assert [job.job_type for job in jobs].count("export.emby") == 1
            assert all(job.status == "succeeded" and job.attempts == 1 for job in jobs)
            assert len(exports) == 1 and exports[0].status == "succeeded"
            durable_raw_values = (
                final_author.raw,
                final_content.raw,
                *(asset.raw for asset in final_assets.values()),
            )
            for raw in durable_raw_values:
                assert isinstance(raw, Mapping)
                _assert_durable_xhs_raw(raw)
            _assert_query_free_http_urls(
                {
                    "author": {
                        "avatar_url": final_author.avatar_url,
                        "profile_url": final_author.profile_url,
                        "raw": final_author.raw,
                    },
                    "content": {"canonical_url": final_content.canonical_url, "raw": final_content.raw},
                    "assets": [{"source_url": asset.source_url, "raw": asset.raw} for asset in final_assets.values()],
                }
            )
            durable_json = json.dumps(
                {
                    "account": {
                        "credential_ref": final_account.credential_ref,
                        "profile_path": final_account.profile_path,
                    },
                    "author": {
                        "avatar_url": final_author.avatar_url,
                        "profile_url": final_author.profile_url,
                        "raw": final_author.raw,
                    },
                    "assets": [
                        {"locator": asset.locator, "raw": asset.raw, "source_url": asset.source_url}
                        for asset in final_assets.values()
                    ],
                    "content": {"canonical_url": final_content.canonical_url, "raw": final_content.raw},
                    "jobs": [job.payload for job in jobs],
                    "runs": [run.manifest for run in runs],
                    "subscription": {
                        "backfill_cursor": final_subscription.backfill_cursor,
                        "cursor": final_subscription.cursor,
                        "policy": final_subscription.policy,
                    },
                },
                ensure_ascii=False,
                sort_keys=True,
            )
            assert all(value not in durable_json for value in FORBIDDEN_VALUES)

        _assert_ephemeral_values_absent(
            runtime_root,
            download_work_root,
            archive_root,
            export_work_root,
            library_root,
        )
    finally:
        database.dispose()

    sqlite_artifacts = [path for path in tmp_path.glob(f"{database_path.name}*") if path.is_file()]
    assert sqlite_artifacts
    _assert_ephemeral_values_absent(*sqlite_artifacts)


MULTI_VIDEO_FIRST_HINT = "http://sns-video-bd.xhscdn.com/multi-first.mp4"
MULTI_VIDEO_SECOND_HINT = "http://sns-video-bd.xhscdn.com/multi-second.mp4"
MULTI_VIDEO_SENTINEL = "EXECUTION0037-" + "MULTI-VIDEO-SIGNATURE-MUST-STAY-EPHEMERAL"
MULTI_VIDEO_FIRST_DETAIL = f"{MULTI_VIDEO_FIRST_HINT}?sign={MULTI_VIDEO_SENTINEL}"
MULTI_VIDEO_SECOND_DETAIL = f"{MULTI_VIDEO_SECOND_HINT}?sign={MULTI_VIDEO_SENTINEL}"
SECOND_MP4 = b"\x00\x00\x00\x18ftypisom" + b"execution-0037-offline-xhs-multi-second"


def _xhs_multi_video_detail_jsonl() -> bytes:
    return _jsonl(
        _xhs_video_record(
            CONTENT_ID,
            video_url=f"{MULTI_VIDEO_FIRST_DETAIL},{MULTI_VIDEO_SECOND_DETAIL}",
            image_url="",
            note_token=REFRESH_NOTE_TOKEN,
            title="Execution 0037 XHS multi video",
        )
    )


def test_xhs_multi_video_note_materializes_bounded_ordered_assets() -> None:
    normalized = normalize_jsonl_bytes(
        _jsonl(
            _xhs_video_record(
                CONTENT_ID,
                video_url=f"{MULTI_VIDEO_FIRST_HINT},{MULTI_VIDEO_SECOND_HINT}",
                image_url="",
                note_token=REFRESH_NOTE_TOKEN,
                title="Execution 0037 XHS multi video",
            )
        ),
        _normalization_context(),
    )

    assert not normalized.quarantined and not normalized.truncated_tail
    record = normalized.records[0]
    assert record.content.kind is ContentKind.VIDEO
    assert [(asset.kind, asset.position, asset.remote_id) for asset in record.assets] == [
        (AssetKind.VIDEO, 0, f"{CONTENT_ID}:video:0"),
        (AssetKind.VIDEO, 1, f"{CONTENT_ID}:video:1"),
    ]

    above = _xhs_video_record(
        CONTENT_ID,
        video_url=",".join(f"http://sns-video-bd.xhscdn.com/over-{i}.mp4" for i in range(17)),
        image_url="",
        note_token=REFRESH_NOTE_TOKEN,
        title="Execution 0037 XHS over-bound video",
    )
    quarantined = normalize_jsonl_bytes(_jsonl(above), _normalization_context())
    assert len(quarantined.quarantined) == 1


def test_xhs_multi_video_reaches_emby_with_zero_work_replay(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "xhs-multi-video.sqlite3"
    database_url = f"sqlite+pysqlite:///{database_path.as_posix()}"
    archive_root = tmp_path / "archive"
    library_root = tmp_path / "library"
    runtime_root = tmp_path / "mediacrawler-runtime"
    download_work_root = tmp_path / "download-work"
    export_work_root = tmp_path / "export-work"
    runtime_root.mkdir()
    upgrade_database(database_url)
    database = Database(database_url)
    detail_jsonl = _xhs_multi_video_detail_jsonl()

    class _MultiVideoDetailRunner(_FakeDetailRunner):
        def run(self, request: MediaCrawlerDetailRequest) -> MediaCrawlerDetailResult:
            self.calls.append(request)
            return MediaCrawlerDetailResult(detail_jsonl, UPSTREAM_SHA)

    _MultiVideoDetailRunner.instances = []
    monkeypatch.setattr(mediacrawler_runtime, "MediaCrawlerDetailProcessRunner", _MultiVideoDetailRunner)
    try:
        seed = _seed_subscription(database)
        normalized = normalize_jsonl_bytes(
            _jsonl(
                _xhs_video_record(
                    CONTENT_ID,
                    video_url=f"{MULTI_VIDEO_FIRST_HINT},{MULTI_VIDEO_SECOND_HINT}",
                    image_url="",
                    note_token=REFRESH_NOTE_TOKEN,
                    title="Execution 0037 XHS multi video",
                )
            ),
            _normalization_context(),
        )
        run_id = _start_ingesting_run(database, seed.subscription_id)
        ingestion = MediaCrawlerIngestionService(database).ingest(
            normalized.records,
            subscription_id=seed.subscription_id,
            run_id=run_id,
            expected_revision=0,
            mode=IngestionMode.FORWARD,
        )
        assert (ingestion.accepted_count, ingestion.discovered_count, ingestion.asset_count) == (1, 1, 2)

        with database.session() as session:
            assets = tuple(session.scalars(select(Asset).order_by(Asset.position, Asset.id)).all())
            assert tuple(asset.source_url for asset in assets) == (
                MULTI_VIDEO_FIRST_HINT,
                MULTI_VIDEO_SECOND_HINT,
            )
            asset_ids = [UUID(asset.id) for asset in assets]

        resolver = _RecordingPublicResolver()
        requests: list[httpx.Request] = []
        payloads = {MULTI_VIDEO_FIRST_DETAIL: MP4, MULTI_VIDEO_SECOND_DETAIL: SECOND_MP4}

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            url = str(request.url)
            assert url in payloads
            payload = payloads[url]
            return httpx.Response(
                200,
                headers={
                    "Content-Length": str(len(payload)),
                    "Content-Type": "video/mp4",
                    "ETag": f'"execution-0037-{url.rsplit("/", 1)[-1].split(".")[0]}"',
                },
                content=payload,
            )

        def transport_factory(target: ValidatedTarget) -> httpx.BaseTransport:
            del target
            return httpx.MockTransport(handler)

        http = SafeHttpClient(resolver, transport_factory=transport_factory)
        secret_resolver = SecretResolver(
            {
                SecretScheme.ENV: EnvironmentSecretProvider(
                    {"MEDIA_SYNC_EXECUTION0018_XHS_CREATOR_URL": CREATOR_REFERENCE}
                )
            }
        )
        harnesses = []

        for index, asset_id in enumerate(asset_ids):
            harnesses.append(
                _download_harness(
                    database,
                    asset_id=asset_id,
                    subscription_id=UUID(seed.subscription_id),
                    worker_id=f"execution-0037-multi-download-{index}",
                    tmp_path=tmp_path,
                    runtime_root=runtime_root,
                    download_work_root=download_work_root,
                    archive_root=archive_root,
                    http=http,
                    probe=_ControlledMp4Probe(expected_payloads=payloads),
                    secret_resolver=secret_resolver,
                )
            )

        downloaded = [harness.service.run(harness.request) for harness in harnesses]

        assert [result.disposition for result in downloaded] == ["downloaded", "downloaded"]
        assert [result.mime_type for result in downloaded] == ["video/mp4", "video/mp4"]
        assert [result.archive_path.read_bytes() for result in downloaded] == [MP4, SECOND_MP4]
        assert [str(request.url) for request in requests] == [MULTI_VIDEO_FIRST_DETAIL, MULTI_VIDEO_SECOND_DETAIL]
        assert len(_MultiVideoDetailRunner.instances) == 2
        assert all(len(runner.calls) == 1 for runner in _MultiVideoDetailRunner.instances)

        export_service = EmbyExportService(
            database,
            EmbyExporter(library_root, staging_root=export_work_root),
            clock=lambda: FIXED_AT,
        )
        exported = export_service.export_author(
            EmbyExportRequest(seed.author_id, "execution-0037-export", lease_seconds=60)
        )
        assert exported.already_exported is False
        author_directory = library_root / exported.output_path
        episodes = tuple(sorted(author_directory.glob("Season */*.mp4")))
        assert len(episodes) == 2
        assert sorted(path.read_bytes() for path in episodes) == sorted((MP4, SECOND_MP4))

        archive_tree = _tree(archive_root)
        library_tree = _tree(author_directory)
        replayed = [harness.service.run(harness.request) for harness in harnesses]
        replayed_export = export_service.export_author(
            EmbyExportRequest(seed.author_id, "execution-0037-export-replay", lease_seconds=60)
        )
        assert [result.disposition for result in replayed] == ["already_verified", "already_verified"]
        assert replayed_export.already_exported is True
        assert len(requests) == 2
        assert _tree(archive_root) == archive_tree
        assert _tree(author_directory) == library_tree

        _assert_ephemeral_values_absent(
            runtime_root,
            download_work_root,
            archive_root,
            export_work_root,
            library_root,
        )
    finally:
        database.dispose()

    sqlite_artifacts = [path for path in tmp_path.glob(f"{database_path.name}*") if path.is_file()]
    assert sqlite_artifacts
    _assert_ephemeral_values_absent(*sqlite_artifacts)


LIVE_IMAGE_HINT = "https://sns-webpic-qc.xhscdn.com/live-photo.jpg"
LIVE_VIDEO_HINT = "http://sns-video-bd.xhscdn.com/live-photo-stream.mp4"
LIVE_SENTINEL = "EXECUTION0038-" + "LIVE-SIGNATURE-MUST-STAY-EPHEMERAL"
LIVE_VIDEO_DETAIL = f"{LIVE_VIDEO_HINT}?sign={LIVE_SENTINEL}"


def _xhs_live_record() -> dict[str, object]:
    return {
        "note_id": CONTENT_ID,
        "type": "normal",
        "title": "Execution 0038 XHS live photo",
        "desc": "Execution 0038 XHS live photo offline fixture",
        "video_url": "",
        "image_list": LIVE_IMAGE_HINT,
        "time": 1788235200000,
        "last_update_time": 1788235260000,
        "creator_hash": "untrusted-xhs-creator",
        "nickname": "Untrusted nickname",
        "liked_count": "38",
        "collected_count": "3",
        "comment_count": "2",
        "share_count": "1",
        "tag_list": "offline,live",
        "last_modify_ts": 1788235320000,
        "note_url": (
            f"https://www.xiaohongshu.com/explore/{CONTENT_ID}?xsec_token={REFRESH_NOTE_TOKEN}&xsec_source=pc_search"
        ),
        "source_keyword": "fixture",
        "xsec_token": REFRESH_NOTE_TOKEN,
        XHS_LIVE_VIDEO_FIELD: {"url": LIVE_VIDEO_DETAIL},
    }


def test_xhs_live_photo_reaches_emby_with_zero_work_replay(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "xhs-live-photo.sqlite3"
    database_url = f"sqlite+pysqlite:///{database_path.as_posix()}"
    archive_root = tmp_path / "archive"
    library_root = tmp_path / "library"
    runtime_root = tmp_path / "mediacrawler-runtime"
    download_work_root = tmp_path / "download-work"
    export_work_root = tmp_path / "export-work"
    runtime_root.mkdir()
    upgrade_database(database_url)
    database = Database(database_url)
    detail_jsonl = _jsonl(_xhs_live_record())

    class _LiveDetailRunner(_FakeDetailRunner):
        def run(self, request: MediaCrawlerDetailRequest) -> MediaCrawlerDetailResult:
            self.calls.append(request)
            return MediaCrawlerDetailResult(detail_jsonl, UPSTREAM_SHA)

    _LiveDetailRunner.instances = []
    monkeypatch.setattr(mediacrawler_runtime, "MediaCrawlerDetailProcessRunner", _LiveDetailRunner)
    try:
        seed = _seed_subscription(database)
        normalized = normalize_jsonl_bytes(detail_jsonl, _normalization_context())
        assert not normalized.quarantined and not normalized.truncated_tail
        record = normalized.records[0]
        assert record.content.kind is ContentKind.MIXED
        assert [(asset.kind, asset.position, asset.remote_id) for asset in record.assets] == [
            (AssetKind.IMAGE, 0, f"{CONTENT_ID}:image:0"),
            (AssetKind.VIDEO, 0, f"{CONTENT_ID}:video:0"),
        ]

        run_id = _start_ingesting_run(database, seed.subscription_id)
        ingestion = MediaCrawlerIngestionService(database).ingest(
            normalized.records,
            subscription_id=seed.subscription_id,
            run_id=run_id,
            expected_revision=0,
            mode=IngestionMode.FORWARD,
        )
        assert (ingestion.accepted_count, ingestion.discovered_count, ingestion.asset_count) == (1, 1, 2)

        with database.session() as session:
            assets = tuple(session.scalars(select(Asset).order_by(Asset.kind, Asset.id)).all())
            assert tuple(asset.source_url for asset in assets) == (LIVE_IMAGE_HINT, LIVE_VIDEO_HINT)
            asset_ids = [UUID(asset.id) for asset in assets]

        resolver = _RecordingPublicResolver()
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            if str(request.url) == LIVE_IMAGE_HINT:
                return httpx.Response(
                    200,
                    headers={
                        "Content-Length": str(len(PNG)),
                        "Content-Type": "image/png",
                        "ETag": '"execution-0038-live-image"',
                    },
                    content=PNG,
                )
            assert str(request.url) == LIVE_VIDEO_DETAIL
            return httpx.Response(
                200,
                headers={
                    "Content-Length": str(len(MP4)),
                    "Content-Type": "video/mp4",
                    "ETag": '"execution-0038-live-video"',
                },
                content=MP4,
            )

        def transport_factory(target: ValidatedTarget) -> httpx.BaseTransport:
            del target
            return httpx.MockTransport(handler)

        http = SafeHttpClient(resolver, transport_factory=transport_factory)
        secret_resolver = SecretResolver(
            {
                SecretScheme.ENV: EnvironmentSecretProvider(
                    {"MEDIA_SYNC_EXECUTION0018_XHS_CREATOR_URL": CREATOR_REFERENCE}
                )
            }
        )
        harnesses = []
        for index, asset_id in enumerate(asset_ids):
            harnesses.append(
                _download_harness(
                    database,
                    asset_id=asset_id,
                    subscription_id=UUID(seed.subscription_id),
                    worker_id=f"execution-0038-live-download-{index}",
                    tmp_path=tmp_path,
                    runtime_root=runtime_root,
                    download_work_root=download_work_root,
                    archive_root=archive_root,
                    http=http,
                    probe=_ControlledMp4Probe(),
                    secret_resolver=secret_resolver,
                )
            )

        downloaded = [harness.service.run(harness.request) for harness in harnesses]

        assert [result.disposition for result in downloaded] == ["downloaded", "downloaded"]
        assert sorted(result.mime_type for result in downloaded) == ["image/png", "video/mp4"]
        assert sorted(result.archive_path.read_bytes() for result in downloaded) == sorted((MP4, PNG))
        assert sorted(str(request.url) for request in requests) == [LIVE_VIDEO_DETAIL, LIVE_IMAGE_HINT]
        assert len(_LiveDetailRunner.instances) == 2
        assert all(len(runner.calls) == 1 for runner in _LiveDetailRunner.instances)

        export_service = EmbyExportService(
            database,
            EmbyExporter(library_root, staging_root=export_work_root),
            clock=lambda: FIXED_AT,
        )
        exported = export_service.export_author(
            EmbyExportRequest(seed.author_id, "execution-0038-export", lease_seconds=60)
        )
        assert exported.already_exported is False
        author_directory = library_root / exported.output_path
        assert next(author_directory.glob("Season */*.mp4")).read_bytes() == MP4
        assert next(author_directory.glob("Season */*-poster.png")).read_bytes() == PNG

        archive_tree = _tree(archive_root)
        library_tree = _tree(author_directory)
        replayed = [harness.service.run(harness.request) for harness in harnesses]
        replayed_export = export_service.export_author(
            EmbyExportRequest(seed.author_id, "execution-0038-export-replay", lease_seconds=60)
        )
        assert [result.disposition for result in replayed] == ["already_verified", "already_verified"]
        assert replayed_export.already_exported is True
        assert len(requests) == 2
        assert _tree(archive_root) == archive_tree
        assert _tree(author_directory) == library_tree

        _assert_ephemeral_values_absent(
            runtime_root,
            download_work_root,
            archive_root,
            export_work_root,
            library_root,
        )
    finally:
        database.dispose()

    sqlite_artifacts = [path for path in tmp_path.glob(f"{database_path.name}*") if path.is_file()]
    assert sqlite_artifacts
    _assert_ephemeral_values_absent(*sqlite_artifacts)
