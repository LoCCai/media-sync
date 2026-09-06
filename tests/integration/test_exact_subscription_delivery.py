"""Offline exact subscription-to-directory delivery without a media server."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import httpx
import pytest
from sqlalchemy import select

from media_sync.adapters.fake import FakePlatformAdapter
from media_sync.application.pipeline_runtime import LocalPipelineRuntimeConfig, SubscriptionPipelineExecutor
from media_sync.application.subscription_delivery import (
    build_subscription_delivery_result,
    pipeline_delivery_receipt,
)
from media_sync.domain import AssetKind, AssetSnapshot, AuthorSnapshot, ContentKind, ContentSnapshot, Platform
from media_sync.infrastructure.db import (
    AccountRepository,
    AuthorRepository,
    AuthorUpsert,
    Database,
    SubscriptionRepository,
    upgrade_database,
)
from media_sync.infrastructure.db.models import Job, Subscription
from media_sync.media import SafeHttpClient
from media_sync.scheduler import (
    DurableSchedulerService,
    FakeSubscriptionHandler,
    PipelineHandlerResult,
    PipelineJobRepository,
    PipelineSubscriptionClaim,
    PipelineSubscriptionWorker,
    SubscriptionHandlerRegistry,
    SubscriptionWorker,
)
from media_sync.security import SecretResolver

NOW = datetime(2026, 9, 6, 8, tzinfo=UTC)
ASSET_URL = "https://media.exact-delivery.invalid/image.png"
PNG = b"\x89PNG\r\n\x1a\nexact-subscription-delivery"
AUTHOR = AuthorSnapshot(
    platform=Platform.BILI,
    remote_id="exact-delivery-author",
    display_name="Exact Delivery Author",
)
CONTENT = ContentSnapshot(
    platform=Platform.BILI,
    remote_id="exact-delivery-content",
    author_remote_id=AUTHOR.remote_id,
    remote_type="post",
    kind=ContentKind.GALLERY,
    title="Exact delivery",
    body="offline fixture",
    published_at=NOW,
)
ASSET = AssetSnapshot(
    platform=Platform.BILI,
    remote_id="exact-delivery-image",
    content_remote_id=CONTENT.remote_id,
    kind=AssetKind.IMAGE,
    source_url=ASSET_URL,
    position=0,
    mime_type="image/png",
)


class _PublicResolver:
    def resolve(self, _hostname: str, _port: int) -> Sequence[str]:
        return ("8.8.8.8",)


def _seed(database: Database) -> tuple[str, str]:
    with database.session() as session:
        account = AccountRepository(session).create(
            platform="bili",
            adapter="fake",
            display_name="exact delivery account",
            login_method="cookie",
            auth_status="authenticated",
        )
        author = AuthorRepository(session).upsert(
            AuthorUpsert(platform="bili", remote_id=AUTHOR.remote_id, display_name="placeholder"),
            seen_at=NOW,
        )
        subscription = SubscriptionRepository(session).create(
            account_id=account.id,
            author_id=author.id,
            max_items=1,
            interval_seconds=3_600,
            next_run_at=None,
        )
        return subscription.id, author.id


def _adapter(platform: Platform) -> FakePlatformAdapter:
    assert platform is Platform.BILI
    return FakePlatformAdapter(
        platform,
        author=AUTHOR,
        contents=(CONTENT,),
        assets={CONTENT.remote_id: (ASSET,)},
    )


@pytest.mark.asyncio
async def test_exact_delivery_downloads_then_reuses_directory_without_media_server(tmp_path: Path) -> None:
    database_url = f"sqlite+pysqlite:///{(tmp_path / 'exact-delivery.sqlite3').as_posix()}"
    upgrade_database(database_url)
    database = Database(database_url)
    network_calls: list[str] = []

    def transport(request: httpx.Request) -> httpx.Response:
        network_calls.append(str(request.url))
        return httpx.Response(
            200,
            headers={"Content-Type": "image/png", "Content-Length": str(len(PNG))},
            content=PNG,
        )

    config = LocalPipelineRuntimeConfig(
        work_root=tmp_path / "jobs" / "downloads",
        archive_root=tmp_path / "archive",
        export_root=tmp_path / "library",
        export_staging_root=tmp_path / "jobs" / "emby-export",
        mediacrawler_lock_path=tmp_path / "upstreams.lock.json",
        mediacrawler_runtime_root=tmp_path / "mediacrawler",
        mediacrawler_python_executable=None,
        secret_resolver=SecretResolver.local(file_root=tmp_path / "secrets"),
        http_client_factory=lambda: SafeHttpClient(
            _PublicResolver(),
            transport_factory=lambda _target: httpx.MockTransport(transport),
        ),
    )

    try:
        subscription_id, author_id = _seed(database)
        executor = SubscriptionPipelineExecutor(database, config)

        for generation, at in enumerate((NOW, NOW + timedelta(seconds=10))):
            scheduler = DurableSchedulerService(database, clock=lambda current=at: current)
            cycle = scheduler.materialize_one(
                subscription_id,
                expected_schedule_revision=generation,
            )
            discovery_worker = SubscriptionWorker(
                database,
                SubscriptionHandlerRegistry({"fake": FakeSubscriptionHandler(database, adapter_factory=_adapter)}),
                clock=lambda current=at: current,
                random_fraction=lambda: 0,
            )
            discovery = await discovery_worker.run_exact(
                cycle.job_id,
                expected_subscription_id=subscription_id,
                worker_id=f"exact-discovery-{generation}",
                global_capacity=1,
                lease_seconds=60,
            )
            assert discovery.status == "succeeded"
            assert discovery.run_id is not None

            with database.session() as session:
                pipeline_job = PipelineJobRepository(session).get_for_succeeded_sync(
                    cycle.job_id,
                    run_id=discovery.run_id,
                    expected_subscription_id=subscription_id,
                )
            assert pipeline_job is not None

            def handle(
                claim: PipelineSubscriptionClaim,
                _generation: int = generation,
            ) -> PipelineHandlerResult:
                outcome = executor.run(
                    UUID(claim.subscription_id),
                    expected_account_id=UUID(claim.account_id),
                    expected_platform=claim.platform,
                    worker_id=f"exact-pipeline-{_generation}",
                )
                return PipelineHandlerResult.success(pipeline_delivery_receipt(outcome))

            delivery = await PipelineSubscriptionWorker(
                database,
                handle,
                clock=lambda current=at: current,
            ).run_exact(
                pipeline_job.job_id,
                expected_subscription_id=subscription_id,
                expected_sync_job_id=cycle.job_id,
                expected_run_id=discovery.run_id,
                worker_id=f"exact-pipeline-{generation}",
                lease_seconds=60,
            )
            assert delivery.status == "succeeded"
            assert delivery.receipt is not None
            result = build_subscription_delivery_result(
                database,
                subscription_id=subscription_id,
                sync_job_id=cycle.job_id,
                run_id=discovery.run_id,
                pipeline_job_id=pipeline_job.job_id,
                pipeline_receipt=delivery.receipt,
            )
            assert result["directory_verified"] is True
            assert result["selection_scope"] == "author_active_snapshot"
            assert result["selected_asset_count"] == result["verified_asset_count"] == 1
            assert result["downloaded_count"] == (1 if generation == 0 else 0)
            assert result["already_verified_count"] == (0 if generation == 0 else 1)
            assert result["publication_disposition"] == ("published" if generation == 0 else "already_exported")

        assert network_calls == [ASSET_URL]
        assert (tmp_path / "archive").is_dir()
        assert (tmp_path / "library").is_dir()
        assert any(path.is_file() for path in (tmp_path / "library").rglob("*"))
        with database.session() as session:
            subscription = session.get(Subscription, subscription_id)
            assert subscription is not None and subscription.schedule_revision == 2
            jobs = list(session.scalars(select(Job)).all())
            assert [job.job_type for job in jobs].count("sync.subscription") == 2
            assert [job.job_type for job in jobs].count("pipeline.subscription") == 2
            assert {job.status for job in jobs} == {"succeeded"}
            assert any(job.job_type == "export.emby" and job.payload.get("author_id") == author_id for job in jobs)
    finally:
        database.dispose()
