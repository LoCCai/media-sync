"""Offline production-composition coverage for the local pipeline executor."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from pathlib import Path
from uuid import UUID

import httpx
import pytest
from sqlalchemy import select

import media_sync.application.pipeline_runtime as pipeline_runtime
from media_sync.application.pipeline import SubscriptionPipelineError
from media_sync.application.pipeline_runtime import (
    LocalPipelineRuntimeConfig,
    SubscriptionPipelineExecutor,
)
from media_sync.domain import Platform
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
from media_sync.infrastructure.db.models import Asset, ExportRecord, Job
from media_sync.media import AdapterRefreshLocator, DirectLocator, SafeHttpClient, ValidatedTarget
from media_sync.security import SecretResolver

ASSET_URL = "https://media.pipeline-runtime.test/image.png"
PNG = b"\x89PNG\r\n\x1a\n" + b"pipeline-runtime-image"


class _PublicResolver:
    def resolve(self, _hostname: str, _port: int) -> Sequence[str]:
        return ("8.8.8.8",)


@pytest.fixture
def database(tmp_path: Path) -> Iterator[Database]:
    instance = Database(f"sqlite+pysqlite:///{(tmp_path / 'pipeline.sqlite3').as_posix()}")
    instance.create_schema()
    try:
        yield instance
    finally:
        instance.dispose()


def _seed_direct_asset(database: Database, *, kind: str = "image") -> tuple[UUID, UUID, UUID]:
    with database.session() as session:
        account = AccountRepository(session).create(
            platform="bili",
            adapter="fake",
            display_name="pipeline runtime account",
            login_method="cookie",
            auth_status="authenticated",
        )
        author, contents = AuthorRepository(session).upsert_with_contents(
            AuthorUpsert(
                platform="bili",
                remote_id="pipeline-runtime-author",
                display_name="Pipeline Runtime Author",
            ),
            (
                ContentUpsert(
                    remote_id="pipeline-runtime-content",
                    remote_type="post",
                    kind=kind,
                    title="Pipeline Runtime Image",
                ),
            ),
        )
        asset = AssetRepository(session).upsert_for_content(
            contents[0].id,
            AssetUpsert(
                platform="bili",
                content_remote_type="post",
                content_remote_id="pipeline-runtime-content",
                remote_id="pipeline-runtime-image",
                kind=kind,
                position=0,
                source_url=ASSET_URL,
                locator=DirectLocator(ASSET_URL).as_dict(),
            ),
        )
        subscription = SubscriptionRepository(session).create(
            account_id=account.id,
            author_id=author.id,
        )
        return UUID(subscription.id), UUID(account.id), UUID(asset.id)


def _seed_refresh_asset(
    database: Database,
    *,
    platform: str,
    kind: str,
    suffix: str,
) -> tuple[UUID, UUID, UUID]:
    with database.session() as session:
        account = AccountRepository(session).create(
            platform=platform,
            adapter="mediacrawler",
            display_name=f"pipeline refresh account {suffix}",
            login_method="qr",
            auth_status="authenticated",
        )
        author, contents = AuthorRepository(session).upsert_with_contents(
            AuthorUpsert(
                platform=platform,
                remote_id=f"pipeline-refresh-author-{suffix}",
                display_name=f"Pipeline Refresh Author {suffix}",
            ),
            (
                ContentUpsert(
                    remote_id=f"pipeline-refresh-content-{suffix}",
                    remote_type="post",
                    kind="image",
                ),
            ),
        )
        content = contents[0]
        remote_id = f"pipeline-refresh-asset-{suffix}"
        locator = AdapterRefreshLocator(
            adapter="mediacrawler",
            asset_key=stable_asset_key(
                platform=platform,
                content_remote_type=content.remote_type,
                content_remote_id=content.remote_id,
                kind=kind,
                position=0,
                remote_id=remote_id,
            ),
        )
        asset = AssetRepository(session).upsert_for_content(
            content.id,
            AssetUpsert(
                platform=platform,
                content_remote_type=content.remote_type,
                content_remote_id=content.remote_id,
                remote_id=remote_id,
                kind=kind,
                position=0,
                source_url=f"https://media.pipeline-runtime.test/{suffix}.bin",
                locator=locator.as_dict(),
            ),
        )
        subscription = SubscriptionRepository(session).create(
            account_id=account.id,
            author_id=author.id,
        )
        AssetRefreshSourceRepository(session).upsert_observation(
            asset_id=asset.id,
            subscription_id=subscription.id,
        )
        return UUID(subscription.id), UUID(account.id), UUID(asset.id)


def test_executor_downloads_exports_and_reuses_durable_results(
    database: Database,
    tmp_path: Path,
) -> None:
    subscription_id, account_id, asset_id = _seed_direct_asset(database)
    network_calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        network_calls.append(str(request.url))
        return httpx.Response(
            200,
            headers={"Content-Length": str(len(PNG)), "Content-Type": "image/png"},
            content=PNG,
        )

    def transport_factory(_target: ValidatedTarget) -> httpx.BaseTransport:
        return httpx.MockTransport(handler)

    config = LocalPipelineRuntimeConfig(
        work_root=tmp_path / "download-work",
        archive_root=tmp_path / "archive",
        export_root=tmp_path / "emby",
        export_staging_root=tmp_path / "export-work",
        mediacrawler_lock_path=tmp_path / "upstreams.lock.json",
        mediacrawler_runtime_root=tmp_path / "mediacrawler",
        mediacrawler_python_executable=None,
        secret_resolver=SecretResolver.local(file_root=tmp_path / "secrets"),
        http_client_factory=lambda: SafeHttpClient(
            _PublicResolver(),
            transport_factory=transport_factory,
        ),
    )
    executor = SubscriptionPipelineExecutor(database, config)

    first = executor.run(
        subscription_id,
        expected_account_id=account_id,
        expected_platform="bili",
        worker_id="pipeline-runtime-first",
    )
    second = executor.run(
        subscription_id,
        expected_account_id=account_id,
        expected_platform="bili",
        worker_id="pipeline-runtime-second",
    )

    assert [item.asset_id for item in first.selection.assets] == [asset_id]
    assert [item.disposition for item in first.downloads] == ["downloaded"]
    assert first.export.already_exported is False
    assert [item.disposition for item in second.downloads] == ["already_verified"]
    assert second.export.already_exported is True
    assert network_calls == [ASSET_URL]
    assert (tmp_path / "emby" / first.export.output_path).is_dir()
    with database.session() as session:
        asset = session.get(Asset, str(asset_id))
        assert asset is not None and asset.status == "verified"
        assert session.scalar(select(ExportRecord)) is not None
        assert {job.job_type for job in session.scalars(select(Job)).all()} == {"asset_download", "export.emby"}


def test_direct_pipeline_does_not_require_mediacrawler_enablement(
    database: Database,
    tmp_path: Path,
) -> None:
    subscription_id, account_id, _asset_id = _seed_direct_asset(database)
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, headers={"Content-Type": "image/png"}, content=PNG)

    config = LocalPipelineRuntimeConfig(
        work_root=tmp_path / "work",
        archive_root=tmp_path / "archive",
        export_root=tmp_path / "emby",
        export_staging_root=tmp_path / "export-work",
        mediacrawler_lock_path=tmp_path / "missing-lock.json",
        mediacrawler_runtime_root=tmp_path / "missing-runtime",
        mediacrawler_python_executable=None,
        secret_resolver=SecretResolver.local(file_root=tmp_path / "secrets"),
        enable_mediacrawler=False,
        http_client_factory=lambda: SafeHttpClient(
            _PublicResolver(),
            transport_factory=lambda _target: httpx.MockTransport(handler),
        ),
    )

    outcome = SubscriptionPipelineExecutor(database, config).run(
        subscription_id,
        expected_account_id=account_id,
        expected_platform="bili",
        worker_id="direct-only-worker",
    )

    assert outcome.export.already_exported is False
    assert calls == 1


def test_runtime_preflight_blocks_missing_mediacrawler_capabilities_without_child_mutation(
    database: Database,
    tmp_path: Path,
) -> None:
    subscription_id, account_id, asset_id = _seed_refresh_asset(
        database,
        platform=Platform.BILI.value,
        kind="cover",
        suffix="preflight-bili",
    )
    common = {
        "work_root": tmp_path / "work",
        "archive_root": tmp_path / "archive",
        "export_root": tmp_path / "emby",
        "export_staging_root": tmp_path / "export-work",
        "mediacrawler_lock_path": tmp_path / "upstreams.lock.json",
        "mediacrawler_runtime_root": tmp_path / "mediacrawler",
        "secret_resolver": SecretResolver.local(file_root=tmp_path / "secrets"),
    }
    cases = (
        (
            LocalPipelineRuntimeConfig(
                **common,
                mediacrawler_python_executable=tmp_path / "python",
            ),
            "pipeline_mediacrawler_not_enabled",
        ),
        (
            LocalPipelineRuntimeConfig(
                **common,
                mediacrawler_python_executable=tmp_path / "python",
                enable_mediacrawler=True,
            ),
            "pipeline_mediacrawler_license_required",
        ),
        (
            LocalPipelineRuntimeConfig(
                **common,
                mediacrawler_python_executable=None,
                enable_mediacrawler=True,
                accept_mediacrawler_license=True,
            ),
            "pipeline_mediacrawler_runtime_unavailable",
        ),
    )

    for index, (config, expected_code) in enumerate(cases):
        with pytest.raises(SubscriptionPipelineError, match=expected_code):
            SubscriptionPipelineExecutor(database, config).run(
                subscription_id,
                expected_account_id=account_id,
                expected_platform=Platform.BILI.value,
                worker_id=f"preflight-bili-{index}",
            )

    with database.session() as session:
        asset = session.get(Asset, str(asset_id))
        assert asset is not None and (asset.status, asset.download_job_id) == ("discovered", None)
        assert list(session.scalars(select(Job)).all()) == []


@pytest.mark.parametrize("invalid_stage", ["checkout", "python"])
def test_runtime_preflight_rejects_invalid_mediacrawler_runtime_without_child_mutation(
    database: Database,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    invalid_stage: str,
) -> None:
    subscription_id, account_id, asset_id = _seed_refresh_asset(
        database,
        platform=Platform.BILI.value,
        kind="cover",
        suffix=f"invalid-runtime-{invalid_stage}",
    )
    calls: list[str] = []
    network_calls = 0

    def verify_checkout(_lock_path: Path, *, license_acknowledged: bool) -> object:
        calls.append("checkout")
        assert license_acknowledged is True
        if invalid_stage == "checkout":
            raise pipeline_runtime.CheckoutValidationError("invalid checkout")
        return object()

    def verify_python(_python_executable: Path) -> object:
        calls.append("python")
        if invalid_stage == "python":
            raise pipeline_runtime.CheckoutValidationError("invalid Python")
        return object()

    def client_factory() -> SafeHttpClient:
        nonlocal network_calls
        network_calls += 1
        return SafeHttpClient(_PublicResolver())

    monkeypatch.setattr(pipeline_runtime, "verify_mediacrawler_checkout", verify_checkout)
    monkeypatch.setattr(pipeline_runtime, "verify_mediacrawler_python", verify_python)
    config = LocalPipelineRuntimeConfig(
        work_root=tmp_path / "work",
        archive_root=tmp_path / "archive",
        export_root=tmp_path / "emby",
        export_staging_root=tmp_path / "export-work",
        mediacrawler_lock_path=tmp_path / "upstreams.lock.json",
        mediacrawler_runtime_root=tmp_path / "mediacrawler",
        mediacrawler_python_executable=tmp_path / "configured-python",
        secret_resolver=SecretResolver.local(file_root=tmp_path / "secrets"),
        enable_mediacrawler=True,
        accept_mediacrawler_license=True,
        http_client_factory=client_factory,
    )

    with pytest.raises(SubscriptionPipelineError) as captured:
        SubscriptionPipelineExecutor(database, config).run(
            subscription_id,
            expected_account_id=account_id,
            expected_platform=Platform.BILI.value,
            worker_id=f"invalid-runtime-{invalid_stage}",
        )

    assert captured.value.code == "pipeline_mediacrawler_runtime_unavailable"
    assert calls == (["checkout"] if invalid_stage == "checkout" else ["checkout", "python"])
    assert network_calls == 0
    with database.session() as session:
        asset = session.get(Asset, str(asset_id))
        assert asset is not None and (asset.status, asset.download_job_id) == ("discovered", None)
        assert list(session.scalars(select(Job)).all()) == []


def test_runtime_preflight_rejects_invalid_ffprobe_without_child_mutation(
    database: Database,
    tmp_path: Path,
) -> None:
    subscription_id, account_id, asset_id = _seed_direct_asset(database, kind="video")
    network_calls = 0

    def client_factory() -> SafeHttpClient:
        nonlocal network_calls
        network_calls += 1
        return SafeHttpClient(_PublicResolver())

    config = LocalPipelineRuntimeConfig(
        work_root=tmp_path / "work",
        archive_root=tmp_path / "archive",
        export_root=tmp_path / "emby",
        export_staging_root=tmp_path / "export-work",
        mediacrawler_lock_path=tmp_path / "upstreams.lock.json",
        mediacrawler_runtime_root=tmp_path / "mediacrawler",
        mediacrawler_python_executable=None,
        secret_resolver=SecretResolver.local(file_root=tmp_path / "secrets"),
        ffprobe_executable=str(tmp_path / "missing-ffprobe"),
        http_client_factory=client_factory,
    )

    with pytest.raises(SubscriptionPipelineError) as captured:
        SubscriptionPipelineExecutor(database, config).run(
            subscription_id,
            expected_account_id=account_id,
            expected_platform=Platform.BILI.value,
            worker_id="invalid-ffprobe",
        )

    assert captured.value.code == "pipeline_media_probe_unavailable"
    assert network_calls == 0
    with database.session() as session:
        asset = session.get(Asset, str(asset_id))
        assert asset is not None and (asset.status, asset.download_job_id) == ("discovered", None)
        assert list(session.scalars(select(Job)).all()) == []


def test_runtime_preflight_requires_xhs_detail_authority_and_ffprobe_without_child_jobs(
    database: Database,
    tmp_path: Path,
) -> None:
    xhs_subscription_id, xhs_account_id, xhs_asset_id = _seed_refresh_asset(
        database,
        platform=Platform.XHS.value,
        kind="image",
        suffix="preflight-xhs",
    )
    xhs_config = LocalPipelineRuntimeConfig(
        work_root=tmp_path / "xhs-work",
        archive_root=tmp_path / "xhs-archive",
        export_root=tmp_path / "xhs-emby",
        export_staging_root=tmp_path / "xhs-export-work",
        mediacrawler_lock_path=tmp_path / "upstreams.lock.json",
        mediacrawler_runtime_root=tmp_path / "mediacrawler",
        mediacrawler_python_executable=tmp_path / "python",
        secret_resolver=SecretResolver.local(file_root=tmp_path / "secrets"),
        enable_mediacrawler=True,
        accept_mediacrawler_license=True,
    )
    with pytest.raises(SubscriptionPipelineError, match="pipeline_xhs_detail_authority_required"):
        SubscriptionPipelineExecutor(database, xhs_config).run(
            xhs_subscription_id,
            expected_account_id=xhs_account_id,
            expected_platform=Platform.XHS.value,
            worker_id="preflight-xhs",
        )

    video_subscription_id, video_account_id, video_asset_id = _seed_direct_asset(database, kind="video")
    network_calls = 0

    def client_factory() -> SafeHttpClient:
        nonlocal network_calls
        network_calls += 1
        return SafeHttpClient(_PublicResolver())

    video_config = LocalPipelineRuntimeConfig(
        work_root=tmp_path / "video-work",
        archive_root=tmp_path / "video-archive",
        export_root=tmp_path / "video-emby",
        export_staging_root=tmp_path / "video-export-work",
        mediacrawler_lock_path=tmp_path / "upstreams.lock.json",
        mediacrawler_runtime_root=tmp_path / "mediacrawler",
        mediacrawler_python_executable=None,
        secret_resolver=SecretResolver.local(file_root=tmp_path / "secrets"),
        http_client_factory=client_factory,
    )
    with pytest.raises(SubscriptionPipelineError, match="pipeline_media_probe_unavailable"):
        SubscriptionPipelineExecutor(database, video_config).run(
            video_subscription_id,
            expected_account_id=video_account_id,
            expected_platform=Platform.BILI.value,
            worker_id="preflight-video",
        )

    with database.session() as session:
        for asset_id in (xhs_asset_id, video_asset_id):
            asset = session.get(Asset, str(asset_id))
            assert asset is not None and (asset.status, asset.download_job_id) == ("discovered", None)
        assert list(session.scalars(select(Job)).all()) == []
    assert network_calls == 0


def test_xhs_detail_reference_is_not_forwarded_to_non_xhs_refresh_assets(
    database: Database,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    subscription_id, _account_id, asset_id = _seed_refresh_asset(
        database,
        platform=Platform.BILI.value,
        kind="cover",
        suffix="bili-with-xhs-option",
    )
    captured: dict[str, object] = {}

    class _CapturedRefresher:
        def __init__(self, _database: Database, **kwargs: object) -> None:
            captured.update(kwargs)

    monkeypatch.setattr(pipeline_runtime, "LazyMediaCrawlerLocatorRefresher", _CapturedRefresher)
    config = LocalPipelineRuntimeConfig(
        work_root=tmp_path / "work",
        archive_root=tmp_path / "archive",
        export_root=tmp_path / "emby",
        export_staging_root=tmp_path / "export-work",
        mediacrawler_lock_path=tmp_path / "upstreams.lock.json",
        mediacrawler_runtime_root=tmp_path / "mediacrawler",
        mediacrawler_python_executable=tmp_path / "python",
        secret_resolver=SecretResolver.local(file_root=tmp_path / "secrets"),
        enable_mediacrawler=True,
        accept_mediacrawler_license=True,
        xhs_detail_reference_ref="env:XHS_NOTE_DETAIL_URL",
    )

    refresher = pipeline_runtime._PerAssetDownloadRunner(database, subscription_id, config)._refresher(asset_id)

    assert isinstance(refresher, _CapturedRefresher)
    assert captured["detail_reference_ref"] is None
