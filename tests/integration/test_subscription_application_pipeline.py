"""Focused exact-scope tests for the scheduler-independent media pipeline."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from media_sync.application.downloads import AssetDownloadOutcome, AssetDownloadRequest
from media_sync.application.emby import EmbyExportOutcome, EmbyExportRequest
from media_sync.application.pipeline import (
    SelectedPipelineAsset,
    SubscriptionAssetSelection,
    SubscriptionAssetSelector,
    SubscriptionPipelineError,
    SubscriptionPipelineRequest,
    SubscriptionPipelineService,
)
from media_sync.domain import AssetStatus, Platform
from media_sync.infrastructure.db import (
    AccountRepository,
    AssetRefreshSourceRepository,
    AssetRepository,
    AssetUpsert,
    AuthorRepository,
    AuthorUpsert,
    ContentUpsert,
    Database,
    SubscriptionRepository,
)
from media_sync.infrastructure.db.asset_identity import stable_asset_key
from media_sync.infrastructure.db.models import Asset, Content
from media_sync.media import AdapterRefreshLocator

NOW = datetime(2026, 8, 31, 1, 2, 3, tzinfo=UTC)


@pytest.fixture
def database(tmp_path: Path) -> Iterator[Database]:
    instance = Database(f"sqlite+pysqlite:///{(tmp_path / 'pipeline.sqlite3').as_posix()}")
    instance.create_schema()
    try:
        yield instance
    finally:
        instance.dispose()


@dataclass(frozen=True, slots=True)
class _SeededScope:
    subscription_id: UUID
    account_id: UUID
    author_id: UUID
    platform: str
    assets_by_remote_content: dict[str, tuple[UUID, ...]]


def _seed_direct_scope(
    database: Database,
    *,
    suffix: str,
    content_assets: tuple[tuple[str, tuple[tuple[str, int], ...]], ...],
    tombstoned_remote_ids: frozenset[str] = frozenset(),
) -> _SeededScope:
    with database.session() as session:
        account = AccountRepository(session).create(
            platform=Platform.BILI.value,
            adapter="fake",
            display_name=f"fake-account-{suffix}",
        )
        author, contents = AuthorRepository(session).upsert_with_contents(
            AuthorUpsert(
                platform=Platform.BILI.value,
                remote_id=f"author-{suffix}",
                display_name=f"Author {suffix}",
            ),
            tuple(
                ContentUpsert(remote_id=remote_id, remote_type="post", kind="mixed")
                for remote_id, _assets in content_assets
            ),
            seen_at=NOW,
        )
        subscription = SubscriptionRepository(session).create(account_id=account.id, author_id=author.id)
        repository = AssetRepository(session)
        assets_by_remote_content: dict[str, tuple[UUID, ...]] = {}
        for content, (_remote_id, asset_specs) in zip(contents, content_assets, strict=True):
            persisted: list[UUID] = []
            for kind, position in asset_specs:
                asset = repository.upsert_for_content(
                    content.id,
                    AssetUpsert(
                        platform=Platform.BILI.value,
                        kind=kind,
                        position=position,
                        remote_id=f"{content.remote_id}:{kind}:{position}",
                        source_url=f"https://fixture.invalid/{suffix}/{content.remote_id}/{kind}/{position}",
                    ),
                )
                persisted.append(UUID(asset.id))
            assets_by_remote_content[content.remote_id] = tuple(persisted)
            if content.remote_id in tombstoned_remote_ids:
                content.tombstoned_at = NOW
        return _SeededScope(
            subscription_id=UUID(subscription.id),
            account_id=UUID(account.id),
            author_id=UUID(author.id),
            platform=account.platform,
            assets_by_remote_content=assets_by_remote_content,
        )


def test_selector_enumerates_zero_one_many_in_stable_exact_author_scope(database: Database) -> None:
    zero = _seed_direct_scope(database, suffix="zero", content_assets=())
    many = _seed_direct_scope(
        database,
        suffix="many",
        content_assets=(
            ("z-content", (("video", 0), ("image", 1))),
            ("a-content", (("cover", 0),)),
            ("tombstoned", (("audio", 0),)),
        ),
        tombstoned_remote_ids=frozenset({"tombstoned"}),
    )
    other = _seed_direct_scope(
        database,
        suffix="other",
        content_assets=(("other-content", (("video", 0),)),),
    )

    selector = SubscriptionAssetSelector(database)
    assert selector.select(zero.subscription_id).assets == ()
    selection = selector.select(many.subscription_id)

    expected = (
        many.assets_by_remote_content["a-content"][0],
        many.assets_by_remote_content["z-content"][1],
        many.assets_by_remote_content["z-content"][0],
    )
    assert tuple(asset.asset_id for asset in selection.assets) == expected
    assert all(not asset.requires_mediacrawler_refresh for asset in selection.assets)
    assert set(expected).isdisjoint(other.assets_by_remote_content["other-content"])
    assert selection.platform == Platform.BILI.value


def test_selector_requires_current_provenance_from_the_exact_subscription(database: Database) -> None:
    with database.session() as session:
        author, contents = AuthorRepository(session).upsert_with_contents(
            AuthorUpsert(
                platform=Platform.BILI.value,
                remote_id="shared-media-author",
                display_name="Shared Media Author",
            ),
            (ContentUpsert(remote_id="historical-content", remote_type="post", kind="video"),),
            seen_at=NOW,
        )
        account_a = AccountRepository(session).create(
            platform=Platform.BILI.value,
            adapter="mediacrawler",
            display_name="media-account-a",
        )
        account_b = AccountRepository(session).create(
            platform=Platform.BILI.value,
            adapter="mediacrawler",
            display_name="media-account-b",
        )
        subscription_a = SubscriptionRepository(session).create(account_id=account_a.id, author_id=author.id)
        subscription_b = SubscriptionRepository(session).create(account_id=account_b.id, author_id=author.id)
        content = contents[0]
        direct = AssetRepository(session).upsert_for_content(
            content.id,
            AssetUpsert(
                platform=Platform.BILI.value,
                kind="cover",
                position=0,
                remote_id="direct-cover",
                source_url="https://fixture.invalid/shared/direct-cover.jpg",
            ),
        )
        refresh_key = stable_asset_key(
            platform=Platform.BILI.value,
            content_remote_type=content.remote_type,
            content_remote_id=content.remote_id,
            kind="video",
            position=1,
            remote_id="refresh-video-v1",
        )
        refresh = AssetRepository(session).upsert_for_content(
            content.id,
            AssetUpsert(
                platform=Platform.BILI.value,
                content_remote_type=content.remote_type,
                content_remote_id=content.remote_id,
                kind="video",
                position=1,
                remote_id="refresh-video-v1",
                locator=AdapterRefreshLocator(adapter="mediacrawler", asset_key=refresh_key).as_dict(),
            ),
        )
        AssetRefreshSourceRepository(session).upsert_observation(
            asset_id=refresh.id,
            subscription_id=subscription_b.id,
            seen_at=NOW,
        )
        subscription_a_id = UUID(subscription_a.id)
        subscription_b_id = UUID(subscription_b.id)
        content_id = UUID(content.id)
        direct_id = UUID(direct.id)
        refresh_id = UUID(refresh.id)

    selector = SubscriptionAssetSelector(database)
    with pytest.raises(SubscriptionPipelineError, match="pipeline_asset_source_ineligible") as absent:
        selector.select(subscription_a_id)
    assert absent.value.retryable is True
    assert {asset.asset_id for asset in selector.select(subscription_b_id).assets} == {direct_id, refresh_id}

    with database.session() as session:
        AssetRefreshSourceRepository(session).upsert_observation(
            asset_id=str(refresh_id),
            subscription_id=str(subscription_a_id),
            seen_at=NOW,
        )
    assert {asset.asset_id for asset in selector.select(subscription_a_id).assets} == {direct_id, refresh_id}

    with database.session() as session:
        content = session.get(Content, str(content_id))
        assert content is not None
        replacement_key = stable_asset_key(
            platform=Platform.BILI.value,
            content_remote_type=content.remote_type,
            content_remote_id=content.remote_id,
            kind="video",
            position=1,
            remote_id="refresh-video-v2",
        )
        replacement = AssetRepository(session).upsert_for_content(
            content.id,
            AssetUpsert(
                platform=Platform.BILI.value,
                content_remote_type=content.remote_type,
                content_remote_id=content.remote_id,
                kind="video",
                position=1,
                remote_id="refresh-video-v2",
                locator=AdapterRefreshLocator(adapter="mediacrawler", asset_key=replacement_key).as_dict(),
            ),
        )
        assert replacement.id == str(refresh_id)
        assert replacement.generation == 2

    for subscription_id in (subscription_a_id, subscription_b_id):
        with pytest.raises(SubscriptionPipelineError, match="pipeline_asset_source_ineligible"):
            selector.select(subscription_id)

    with database.session() as session:
        AssetRefreshSourceRepository(session).upsert_observation(
            asset_id=str(refresh_id),
            subscription_id=str(subscription_a_id),
            seen_at=NOW,
        )
    refreshed = selector.select(subscription_a_id)
    assert next(asset for asset in refreshed.assets if asset.asset_id == refresh_id).generation == 2
    with pytest.raises(SubscriptionPipelineError, match="pipeline_asset_source_ineligible"):
        selector.select(subscription_b_id)


class _OneTimeFailure(RuntimeError):
    pass


class _RecordingDownloadService:
    def __init__(self, database: Database, archive_root: Path, *, fail_once_for: UUID | None = None) -> None:
        self._database = database
        self._archive_root = archive_root
        self._fail_once_for = fail_once_for
        self.calls: list[UUID] = []

    def run(self, request: AssetDownloadRequest) -> AssetDownloadOutcome:
        self.calls.append(request.asset_id)
        if request.asset_id == self._fail_once_for:
            self._fail_once_for = None
            raise _OneTimeFailure("synthetic retryable download failure")
        with self._database.session() as session:
            asset = session.get(Asset, str(request.asset_id))
            assert asset is not None
            already_verified = asset.status == AssetStatus.VERIFIED.value
            archive_path = (self._archive_root / f"{asset.id}.bin").absolute()
            asset.status = AssetStatus.VERIFIED.value
            asset.local_path = str(archive_path)
            asset.checksum_sha256 = "a" * 64
            asset.size_bytes = 1
            asset.mime_type = "application/octet-stream"
            asset.verified_at = NOW
            generation = asset.generation
        return AssetDownloadOutcome(
            asset_id=request.asset_id,
            generation=generation,
            job_id=None,
            status=AssetStatus.VERIFIED,
            disposition="already_verified" if already_verified else "downloaded",
            archive_path=archive_path,
            checksum_sha256="a" * 64,
            size_bytes=1,
            mime_type="application/octet-stream",
        )


class _RecordingExportService:
    def __init__(self) -> None:
        self.calls: list[EmbyExportRequest] = []

    def export_author(self, request: EmbyExportRequest) -> EmbyExportOutcome:
        self.calls.append(request)
        return EmbyExportOutcome(
            job_id=str(uuid4()),
            source_fingerprint="b" * 64,
            output_path="bili-author",
            rendered_fingerprint="c" * 64,
            managed_file_count=1,
            already_exported=False,
        )


def _download_factory(tmp_path: Path) -> Callable[[SelectedPipelineAsset], AssetDownloadRequest]:
    def create(asset: SelectedPipelineAsset) -> AssetDownloadRequest:
        return AssetDownloadRequest(
            asset_id=asset.asset_id,
            worker_id="pipeline-download-worker",
            work_root=tmp_path / "work",
            archive_root=tmp_path / "archive",
            lease_seconds=60,
        )

    return create


def _export_factory(selection: SubscriptionAssetSelection) -> EmbyExportRequest:
    return EmbyExportRequest(str(selection.author_id), "pipeline-export-worker", lease_seconds=60)


def _pipeline_request(
    scope: _SeededScope,
    *,
    expected_account_id: UUID | None = None,
    expected_platform: str | None = None,
) -> SubscriptionPipelineRequest:
    return SubscriptionPipelineRequest(
        subscription_id=scope.subscription_id,
        expected_account_id=(scope.account_id if expected_account_id is None else expected_account_id),
        expected_platform=(scope.platform if expected_platform is None else expected_platform),
    )


def test_pipeline_stops_before_export_then_restart_reuses_verified_assets(
    database: Database,
    tmp_path: Path,
) -> None:
    scope = _seed_direct_scope(
        database,
        suffix="restart",
        content_assets=(("one", (("image", 0),)), ("two", (("video", 0),))),
    )
    ordered = tuple(
        asset.asset_id for asset in SubscriptionAssetSelector(database).select(scope.subscription_id).assets
    )
    downloader = _RecordingDownloadService(database, tmp_path / "archive", fail_once_for=ordered[1])
    exporter = _RecordingExportService()
    service = SubscriptionPipelineService(
        SubscriptionAssetSelector(database),
        downloader,
        exporter,
        download_request_factory=_download_factory(tmp_path),
        export_request_factory=_export_factory,
    )

    with pytest.raises(_OneTimeFailure):
        service.run(_pipeline_request(scope))
    assert downloader.calls == [ordered[0], ordered[1]]
    assert exporter.calls == []

    outcome = service.run(_pipeline_request(scope))
    assert downloader.calls == [ordered[0], ordered[1], ordered[0], ordered[1]]
    assert [item.disposition for item in outcome.downloads] == ["already_verified", "downloaded"]
    assert outcome.selection.author_id == scope.author_id
    assert len(exporter.calls) == 1


def test_pipeline_zero_asset_snapshot_exports_without_download(database: Database, tmp_path: Path) -> None:
    scope = _seed_direct_scope(database, suffix="empty-run", content_assets=())
    downloader = _RecordingDownloadService(database, tmp_path / "archive")
    exporter = _RecordingExportService()
    service = SubscriptionPipelineService(
        SubscriptionAssetSelector(database),
        downloader,
        exporter,
        download_request_factory=_download_factory(tmp_path),
        export_request_factory=_export_factory,
    )

    outcome = service.run(_pipeline_request(scope))

    assert outcome.downloads == ()
    assert downloader.calls == []
    assert len(exporter.calls) == 1


@pytest.mark.parametrize("mismatch", ["account", "platform"])
def test_pipeline_rejects_durable_scope_drift_before_any_child_side_effect(
    database: Database,
    tmp_path: Path,
    mismatch: str,
) -> None:
    scope = _seed_direct_scope(
        database,
        suffix=f"scope-drift-{mismatch}",
        content_assets=(("one", (("image", 0),)),),
    )
    downloader = _RecordingDownloadService(database, tmp_path / "archive")
    exporter = _RecordingExportService()
    service = SubscriptionPipelineService(
        SubscriptionAssetSelector(database),
        downloader,
        exporter,
        download_request_factory=_download_factory(tmp_path),
        export_request_factory=_export_factory,
    )
    request = _pipeline_request(
        scope,
        expected_account_id=uuid4() if mismatch == "account" else scope.account_id,
        expected_platform=Platform.XHS.value if mismatch == "platform" else scope.platform,
    )

    with pytest.raises(SubscriptionPipelineError) as rejected:
        service.run(request)

    assert rejected.value.code == "pipeline_subscription_invalid"
    assert rejected.value.retryable is False
    assert downloader.calls == []
    assert exporter.calls == []


def test_download_result_scope_mismatch_is_terminal() -> None:
    error = SubscriptionPipelineError("pipeline_download_result_scope_mismatch")

    assert error.retryable is False
