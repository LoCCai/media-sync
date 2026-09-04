"""Offline acceptance for the lease-fenced scheduled MediaCrawler handler."""

from __future__ import annotations

import asyncio
import hashlib
import os
import subprocess
import sys
import textwrap
from collections.abc import Callable, Iterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Event, get_ident
from types import SimpleNamespace
from typing import cast
from uuid import UUID, uuid4, uuid5

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from media_sync.application.authentication import AccountLoginRequest, MediaCrawlerQrLoginService
from media_sync.application.mediacrawler import NormalizedMediaCrawlerOutput, load_normalized_output
from media_sync.domain import AccountRef, LoginMethod, Platform
from media_sync.infrastructure.db import (
    AccountRepository,
    AuthorRepository,
    AuthorUpsert,
    Database,
    IngestionMode,
    MediaCrawlerIngestionResult,
    MediaCrawlerIngestionService,
    SubscriptionRepository,
    SyncRunRepository,
)
from media_sync.infrastructure.db.models import Account, Asset, Content, Job, Subscription, SyncRun
from media_sync.integrations.mediacrawler import bridge as bridge_module
from media_sync.integrations.mediacrawler import policies as policies_module
from media_sync.integrations.mediacrawler import receipt as receipt_module
from media_sync.integrations.mediacrawler import runner as runner_module
from media_sync.integrations.mediacrawler.bridge import (
    MANIFEST_SCHEMA_VERSION,
    BridgeConfigurationError,
    BridgeRequest,
    MediaCrawlerBridge,
    MediaCrawlerRunMode,
    MediaCrawlerRunSpec,
    RunnerManifest,
    SavedSessionUnavailableError,
)
from media_sync.integrations.mediacrawler.checkout import VerifiedPython
from media_sync.integrations.mediacrawler.login import (
    MediaCrawlerLoginRequest,
    MediaCrawlerLoginResult,
    MediaCrawlerLoginStatus,
)
from media_sync.integrations.mediacrawler.normalizers import (
    NormalizationContext,
    NormalizedMediaRecord,
    normalize_jsonl_bytes,
)
from media_sync.integrations.mediacrawler.policies import WatchdogLimits, build_run_paths
from media_sync.integrations.mediacrawler.receipt import (
    COMPLETION_RECEIPT_SCHEMA_VERSION,
    ValidatedOutputSnapshot,
    load_validated_output_snapshot,
)
from media_sync.integrations.mediacrawler.runner import (
    AttemptCleanupError,
    AttemptCleanupStatus,
    MediaCrawlerProcessResult,
    MediaCrawlerProcessRunner,
    MediaCrawlerProcessStatus,
    attempt_cleanup_incident_paths,
    is_attempt_cleanup_blocked,
)
from media_sync.integrations.mediacrawler.subscription_policy import MediaCrawlerSubscriptionPolicy
from media_sync.scheduler import mediacrawler_handler as mediacrawler_handler_module
from media_sync.scheduler.handlers import SubscriptionHandlerRegistry, SubscriptionJobContext
from media_sync.scheduler.mediacrawler_handler import (
    MediaCrawlerCleanupBlockedError,
    MediaCrawlerScheduledHandler,
)
from media_sync.scheduler.repository import SchedulerLeaseLostError, SchedulerRepository
from media_sync.scheduler.service import DurableSchedulerService, SubscriptionWorker
from media_sync.security import SecretResolutionError, SecretValue

NOW = datetime(2026, 8, 30, 8, 0, tzinfo=UTC)
PINNED_SHA = "d6f7c5bb906b6dac40ddf343ef9e26438a3de092"
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "mediacrawler"
FIXTURES = {
    Platform.XHS: "xhs/contents.v1.jsonl",
    Platform.DY: "dy/contents.v1.jsonl",
    Platform.KS: "ks/contents.v1.jsonl",
    Platform.BILI: "bili/contents.v1.jsonl",
    Platform.WB: "wb/contents.v1.jsonl",
    Platform.TIEBA: "tieba/contents.v1.jsonl",
    Platform.ZHIHU: "zhihu/contents.v1.jsonl",
}


class _Clock:
    def __init__(self, value: datetime = NOW) -> None:
        self.value = value

    def __call__(self) -> datetime:
        return self.value


class _Resolver:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[str] = []
        self.thread_ids: list[int] = []

    def resolve(self, reference: str) -> SecretValue:
        self.calls.append(reference)
        self.thread_ids.append(get_ident())
        if self.fail:
            raise SecretResolutionError("fixture secret is unavailable")
        return SecretValue("fixture-cookie-value")


def _manifest_for_request(request: BridgeRequest) -> RunnerManifest:
    """Return a structural manifest double without touching a checkout."""

    return cast(
        RunnerManifest,
        SimpleNamespace(
            schema_version=MANIFEST_SCHEMA_VERSION,
            account_id=request.account_id,
            subscription_id=request.subscription_id,
            scheduler_job_id=request.job_id,
            job_id=request.job_id,
            schedule_revision=request.schedule_revision,
            attempt=request.attempt,
            execution_id=request.execution_id,
            sync_run_id=request.sync_run_id,
            checkpoint_revision_before=request.checkpoint_revision_before,
            intended_mode=request.intended_mode,
            platform=request.platform,
            login_method=request.login_method,
            max_items=request.max_items,
            allow_full_history=request.allow_full_history,
            headless=request.headless,
            request_delay_seconds=request.request_delay_seconds,
            watchdogs=request.watchdogs,
            integration_root=request.integration_root.resolve(),
            lock_path=request.lock_path.resolve(),
            license_acknowledged=request.license_acknowledged,
            author_remote_id_fingerprint_sha256=hashlib.sha256(request.author_remote_id.encode("utf-8")).hexdigest(),
            creator_fingerprint_sha256="unused-by-fresh-attempt",
            upstream_sha=PINNED_SHA,
        ),
    )


class _Bridge:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.requests: list[BridgeRequest] = []
        self.thread_ids: list[int] = []

    def prepare(self, request: BridgeRequest) -> MediaCrawlerRunSpec:
        self.requests.append(request)
        self.thread_ids.append(get_ident())
        if self.error is not None:
            raise self.error
        assert request.execution_id is not None
        paths = build_run_paths(
            request.integration_root,
            request.platform,
            request.account_id,
            request.execution_id,
        )
        paths.integration_root.mkdir(parents=True, exist_ok=True)
        (paths.integration_root / "jobs").mkdir(exist_ok=True)
        paths.job_root.mkdir()
        paths.output_root.mkdir()
        return cast(
            MediaCrawlerRunSpec,
            SimpleNamespace(manifest=_manifest_for_request(request), paths=paths),
        )


class _LateFailingBridge(_Bridge):
    def prepare(self, request: BridgeRequest) -> MediaCrawlerRunSpec:
        self.requests.append(request)
        assert request.execution_id is not None
        paths = build_run_paths(
            request.integration_root,
            request.platform,
            request.account_id,
            request.execution_id,
        )
        paths.integration_root.mkdir(parents=True, exist_ok=True)
        (paths.integration_root / "jobs").mkdir(exist_ok=True)
        paths.job_root.mkdir()
        paths.output_root.mkdir()
        (paths.job_root / "private-sentinel.tmp").write_text("attempt-secret", encoding="utf-8")
        raise BridgeConfigurationError("fixture bridge failed after root creation")


class _Runner:
    def __init__(
        self,
        statuses: list[MediaCrawlerProcessStatus] | None = None,
    ) -> None:
        self.statuses = list(statuses or [MediaCrawlerProcessStatus.SUCCEEDED])
        self.calls: list[tuple[MediaCrawlerRunSpec, bool]] = []
        self.thread_ids: list[int] = []

    def run(
        self,
        spec: MediaCrawlerRunSpec,
        cancellation: Event | None = None,
    ) -> MediaCrawlerProcessResult:
        self.thread_ids.append(get_ident())
        cancelled = cancellation is not None and cancellation.is_set()
        self.calls.append((spec, cancelled))
        status = MediaCrawlerProcessStatus.CANCELLED if cancelled else self.statuses.pop(0)
        return MediaCrawlerProcessResult(status=status, message="fixed fixture outcome")


class _SuccessfulLoginRunner:
    def run(
        self,
        request: MediaCrawlerLoginRequest,
        *,
        on_account_locked: Callable[[], None] | None = None,
        cancellation: Event | None = None,
    ) -> MediaCrawlerLoginResult:
        del request, cancellation
        assert on_account_locked is not None
        on_account_locked()
        return MediaCrawlerLoginResult(MediaCrawlerLoginStatus.AUTHENTICATED, PINNED_SHA)


class _ProtocolRecordingRunner:
    """Run the real supervisor while retaining only its public artifact identities."""

    def __init__(self) -> None:
        self.manifests: list[RunnerManifest] = []
        self.results: list[MediaCrawlerProcessResult] = []
        self.snapshots: list[ValidatedOutputSnapshot] = []
        self._inner = MediaCrawlerProcessRunner()

    def run(
        self,
        spec: MediaCrawlerRunSpec,
        cancellation: Event | None = None,
    ) -> MediaCrawlerProcessResult:
        self.manifests.append(RunnerManifest.load(spec.paths.manifest_path))
        result = self._inner.run(spec, cancellation)
        self.results.append(result)
        if result.succeeded:
            self.snapshots.append(load_validated_output_snapshot(spec.manifest))
        return result


def _write_protocol_fixture_child(
    path: Path,
    *,
    fail: bool = False,
    delay_seconds: float = 0.0,
    probe_path: Path | None = None,
) -> Path:
    """Write a repository-owned child that speaks only the parent control protocol."""

    fixture_paths = {platform.value: str(FIXTURE_ROOT / relative) for platform, relative in FIXTURES.items()}
    source = f"""
    import json
    from pathlib import Path
    import sys
    import time

    START = b"media-sync-start-v1\\n"
    FIXTURES = {fixture_paths!r}
    FAIL = {fail!r}
    DELAY_SECONDS = {delay_seconds!r}
    PROBE_PATH = {str(probe_path) if probe_path is not None else None!r}

    if sys.stdin.buffer.readline(64) != START:
        raise SystemExit(20)
    manifest = json.loads(Path(sys.argv[-1]).read_text(encoding="utf-8"))
    if PROBE_PATH is not None:
        Path(PROBE_PATH).write_text("started", encoding="utf-8")
    if DELAY_SECONDS:
        time.sleep(DELAY_SECONDS)
    if FAIL:
        raise SystemExit(30)
    fixture = Path(FIXTURES[manifest["platform"]])
    target = Path(manifest["output_root"]) / manifest["platform"] / "jsonl" / fixture.name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(fixture.read_bytes())
    raise SystemExit(0)
    """
    path.write_text(textwrap.dedent(source).lstrip(), encoding="utf-8", newline="\n")
    return path.resolve()


def _protocol_handler(
    database: Database,
    runtime_root: Path,
    *,
    runner: _ProtocolRecordingRunner,
    clock: Callable[[], datetime],
    normalizer: Callable[..., NormalizedMediaCrawlerOutput] = load_normalized_output,
    ingestion_factory: Callable[[Database], object] = MediaCrawlerIngestionService,
) -> MediaCrawlerScheduledHandler:
    return MediaCrawlerScheduledHandler(
        database,
        lock_path=REPOSITORY_ROOT / "upstreams.lock.json",
        integration_root=runtime_root,
        python_executable=Path(sys.executable),
        secret_resolver=_Resolver(),
        enabled=True,
        license_acknowledged=True,
        bridge=MediaCrawlerBridge(lambda executable: VerifiedPython(executable.expanduser().resolve())),
        runner=runner,
        clock=clock,
        normalizer=normalizer,  # type: ignore[arg-type]
        ingestion_factory=ingestion_factory,  # type: ignore[arg-type]
    )


class _BlockingPostSealNormalizer:
    """Pause after validating a sealed snapshot but before returning it."""

    def __init__(self) -> None:
        self.entered = Event()
        self.release = Event()
        self.finished = Event()
        self.manifests: list[RunnerManifest] = []
        self.receipt_schema_versions: list[int] = []

    def __call__(
        self,
        manifest: RunnerManifest,
        *,
        creator_remote_id: str,
        creator_display_name: str,
        ingested_at: datetime,
    ) -> NormalizedMediaCrawlerOutput:
        output = load_normalized_output(
            manifest,
            creator_remote_id=creator_remote_id,
            creator_display_name=creator_display_name,
            ingested_at=ingested_at,
        )
        snapshot = load_validated_output_snapshot(manifest)
        self.manifests.append(manifest)
        self.receipt_schema_versions.append(snapshot.receipt.schema_version)
        self.entered.set()
        try:
            assert self.release.wait(timeout=5)
            return output
        finally:
            self.finished.set()


class _IngestionSpy:
    def __init__(self) -> None:
        self.calls = 0

    def ingest(self, records: object, **kwargs: object) -> MediaCrawlerIngestionResult:
        del records, kwargs
        self.calls += 1
        raise AssertionError("ingestion must not start after post-seal cancellation")


class _NoEntryNormalizer:
    """Fail if a pre-seal cancellation ever crosses into normalization."""

    def __init__(self) -> None:
        self.calls = 0

    def __call__(
        self,
        manifest: RunnerManifest,
        *,
        creator_remote_id: str,
        creator_display_name: str,
        ingested_at: datetime,
    ) -> NormalizedMediaCrawlerOutput:
        del manifest, creator_remote_id, creator_display_name, ingested_at
        self.calls += 1
        raise AssertionError("normalization must not start after pre-seal cancellation")


class _BlockingRunner:
    def __init__(self) -> None:
        self.entered = Event()
        self.finished = Event()
        self.saw_cancellation = Event()
        self.specs: list[MediaCrawlerRunSpec] = []

    def run(
        self,
        spec: MediaCrawlerRunSpec,
        cancellation: Event | None = None,
    ) -> MediaCrawlerProcessResult:
        assert cancellation is not None
        self.specs.append(spec)
        self.entered.set()
        cancellation.wait(timeout=10)
        if cancellation.is_set():
            self.saw_cancellation.set()
        self.finished.set()
        return MediaCrawlerProcessResult(
            status=MediaCrawlerProcessStatus.CANCELLED,
            message="fixed cancellation",
        )


class _RepeatedCancelRunner:
    """Remain alive after observing cancellation until the test releases the join."""

    def __init__(self) -> None:
        self.entered = Event()
        self.saw_cancellation = Event()
        self.release = Event()
        self.finished = Event()
        self.specs: list[MediaCrawlerRunSpec] = []

    def run(
        self,
        spec: MediaCrawlerRunSpec,
        cancellation: Event | None = None,
    ) -> MediaCrawlerProcessResult:
        assert cancellation is not None
        self.specs.append(spec)
        self.entered.set()
        assert cancellation.wait(timeout=5)
        self.saw_cancellation.set()
        try:
            assert self.release.wait(timeout=5)
        finally:
            self.finished.set()
        return MediaCrawlerProcessResult(
            status=MediaCrawlerProcessStatus.CANCELLED,
            message="fixed repeated cancellation",
        )


class _UnresolvedCleanupRunner:
    def __init__(self, secret: str) -> None:
        self.secret = secret
        self.calls: list[MediaCrawlerRunSpec] = []

    def run(
        self,
        spec: MediaCrawlerRunSpec,
        cancellation: Event | None = None,
    ) -> MediaCrawlerProcessResult:
        del cancellation
        self.calls.append(spec)
        leaked = spec.paths.output_root / "unresolved-private.tmp"
        leaked.write_text(self.secret, encoding="utf-8")
        raise AttemptCleanupError(f"untrusted fixture text: {self.secret}")


class _NoopIngestionService:
    """Return a plausible summary without performing its required commit."""

    def ingest(self, records: object, **kwargs: object) -> MediaCrawlerIngestionResult:
        del records
        expected_revision = cast(int, kwargs["expected_revision"])
        return MediaCrawlerIngestionResult(
            mode=IngestionMode.FORWARD,
            input_count=0,
            accepted_count=0,
            skipped_count=0,
            discovered_count=0,
            asset_count=0,
            committed_batches=1,
            checkpoint_revision=expected_revision + 1,
            watermarked_at=None,
            watermark_remote_ids=(),
        )


class _InvalidSummaryAfterCommitIngestionService:
    def __init__(self, database: Database) -> None:
        self.inner = MediaCrawlerIngestionService(database)

    def ingest(
        self,
        records: tuple[NormalizedMediaRecord, ...],
        *,
        subscription_id: str | UUID,
        run_id: str | UUID,
        expected_revision: int,
        crawl_revision_before: int | None = None,
        mode: str,
        ownership_guard: Callable[[Session], None] | None = None,
    ) -> MediaCrawlerIngestionResult:
        result = self.inner.ingest(
            records,
            subscription_id=subscription_id,
            run_id=run_id,
            expected_revision=expected_revision,
            crawl_revision_before=crawl_revision_before,
            mode=mode,
            ownership_guard=ownership_guard,
        )
        return replace(result, committed_batches=result.committed_batches + 1)


class _BetweenBatchIngestionService:
    """Pause at the ownership guard immediately before the second real batch."""

    def __init__(
        self,
        database: Database,
        *,
        entered: Event,
        release: Event,
        finished: Event,
    ) -> None:
        self.inner = MediaCrawlerIngestionService(database, batch_size=1)
        self.entered = entered
        self.release = release
        self.finished = finished

    def ingest(
        self,
        records: tuple[NormalizedMediaRecord, ...],
        *,
        subscription_id: str | UUID,
        run_id: str | UUID,
        expected_revision: int,
        crawl_revision_before: int | None = None,
        mode: str,
        ownership_guard: Callable[[Session], None] | None = None,
    ) -> MediaCrawlerIngestionResult:
        guard_calls = 0

        def pause_before_second_batch(session: Session) -> None:
            nonlocal guard_calls
            guard_calls += 1
            if guard_calls == 3:
                self.entered.set()
                assert self.release.wait(timeout=5)
            if ownership_guard is not None:
                ownership_guard(session)

        try:
            return self.inner.ingest(
                records,
                subscription_id=subscription_id,
                run_id=run_id,
                expected_revision=expected_revision,
                crawl_revision_before=crawl_revision_before,
                mode=mode,
                ownership_guard=pause_before_second_batch,
            )
        finally:
            self.finished.set()


def _fixture_normalizer(
    manifest: RunnerManifest,
    *,
    creator_remote_id: str,
    creator_display_name: str,
    ingested_at: datetime,
) -> NormalizedMediaCrawlerOutput:
    fixture = FIXTURE_ROOT / FIXTURES[manifest.platform]
    payload = fixture.read_bytes()
    batch = normalize_jsonl_bytes(
        payload,
        NormalizationContext(
            platform=manifest.platform,
            creator_remote_id=creator_remote_id,
            creator_display_name=creator_display_name,
            upstream_sha=manifest.upstream_sha,
            ingested_at=ingested_at,
        ),
        max_bytes=1_048_576,
        max_records=1_000,
        max_line_bytes=1_048_576,
    )
    assert not batch.quarantined
    assert not batch.truncated_tail
    return NormalizedMediaCrawlerOutput(
        records=batch.records,
        output_fingerprint_sha256=hashlib.sha256(payload).hexdigest(),
        input_records=batch.records_seen,
    )


def _empty_normalizer(
    manifest: RunnerManifest,
    *,
    creator_remote_id: str,
    creator_display_name: str,
    ingested_at: datetime,
) -> NormalizedMediaCrawlerOutput:
    del manifest, creator_remote_id, creator_display_name, ingested_at
    return NormalizedMediaCrawlerOutput(
        records=(),
        output_fingerprint_sha256="0" * 64,
        input_records=0,
    )


@pytest.fixture
def database(tmp_path: Path) -> Iterator[Database]:
    instance = Database(f"sqlite+pysqlite:///{(tmp_path / 'scheduled-mediacrawler.sqlite3').as_posix()}")
    instance.create_schema()
    try:
        yield instance
    finally:
        instance.dispose()


def _seed(
    database: Database,
    *,
    platform: Platform = Platform.BILI,
    login_method: LoginMethod = LoginMethod.COOKIE,
    credential_ref: str | None = "env:MEDIACRAWLER_TEST_COOKIE",
    creator_remote_id: str = "creator-001",
    next_run_at: datetime | None = NOW - timedelta(seconds=1),
    auth_status: str = "authenticated",
) -> str:
    with database.session() as session:
        account = AccountRepository(session).create(
            platform=platform.value,
            adapter="mediacrawler",
            display_name=f"scheduled-{platform.value}-{login_method.value}-{uuid4()}",
            login_method=login_method.value,
            credential_ref=credential_ref,
            auth_status=auth_status,
        )
        author = AuthorRepository(session).upsert(
            AuthorUpsert(
                platform=platform.value,
                remote_id=creator_remote_id,
                display_name=f"Fixture creator {platform.value}",
            )
        )
        subscription = SubscriptionRepository(session).create(
            account_id=account.id,
            author_id=author.id,
            interval_seconds=60,
            max_items=30,
            policy={
                "mediacrawler": MediaCrawlerSubscriptionPolicy(
                    allow_full_history=True,
                    request_delay_seconds=3.5,
                    headless=True,
                ).to_payload()
            },
            next_run_at=next_run_at,
        )
        return subscription.id


def _handler(
    database: Database,
    tmp_path: Path,
    *,
    resolver: _Resolver | None = None,
    bridge: _Bridge | None = None,
    runner: _Runner | _BlockingRunner | _RepeatedCancelRunner | _UnresolvedCleanupRunner | None = None,
    enabled: bool = True,
    license_acknowledged: bool = True,
    python_executable: Path | None = Path("fixture-python"),
    clock: Callable[[], datetime] | None = None,
    manifest_loader: Callable[[Path], RunnerManifest] = RunnerManifest.load,
    checkout_verifier: Callable[[RunnerManifest], object] = lambda _manifest: object(),
    normalizer: Callable[..., NormalizedMediaCrawlerOutput] = _fixture_normalizer,
    ingestion_factory: Callable[[Database], object] = MediaCrawlerIngestionService,
) -> MediaCrawlerScheduledHandler:
    return MediaCrawlerScheduledHandler(
        database,
        lock_path=tmp_path / "fixture-lock.json",
        integration_root=tmp_path / "runtime",
        python_executable=python_executable,
        secret_resolver=resolver or _Resolver(),
        enabled=enabled,
        license_acknowledged=license_acknowledged,
        bridge=bridge or _Bridge(),
        runner=runner or _Runner(),
        clock=clock or _Clock(),
        normalizer=normalizer,  # type: ignore[arg-type]
        manifest_loader=manifest_loader,
        checkout_verifier=checkout_verifier,
        ingestion_factory=ingestion_factory,  # type: ignore[arg-type]
    )


@pytest.mark.skipif(os.name == "nt", reason="POSIX venv launchers use symlinks")
def test_handler_preserves_posix_venv_launcher_symlink(database: Database, tmp_path: Path) -> None:
    base_python = tmp_path / "base" / "python3"
    base_python.parent.mkdir()
    base_python.write_text("#!/bin/sh\n", encoding="utf-8")
    base_python.chmod(0o700)
    launcher = tmp_path / "venv" / "bin" / "python"
    launcher.parent.mkdir(parents=True)
    launcher.symlink_to(base_python)

    handler = _handler(database, tmp_path, python_executable=launcher)

    assert handler.python_executable == launcher.absolute()
    assert handler.python_executable != launcher.resolve()


async def _run_worker(
    database: Database,
    handler: MediaCrawlerScheduledHandler,
    *,
    clock: _Clock | None = None,
    worker_id: str = "mediacrawler-worker",
    heartbeat_interval_seconds: float | None = None,
) -> object:
    active_clock = clock or _Clock()
    DurableSchedulerService(database, clock=active_clock).tick(limit=1)
    return await SubscriptionWorker(
        database,
        SubscriptionHandlerRegistry({"mediacrawler": handler}),
        clock=active_clock,
        random_fraction=lambda: 0.0,
    ).run_once(
        worker_id=worker_id,
        heartbeat_interval_seconds=heartbeat_interval_seconds,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("platform", tuple(Platform))
async def test_all_platform_fixtures_prepare_v3_and_ingest_forward_off_loop(
    database: Database,
    tmp_path: Path,
    platform: Platform,
) -> None:
    subscription_id = _seed(database, platform=platform)
    resolver = _Resolver()
    bridge = _Bridge()
    runner = _Runner()
    event_loop_thread = get_ident()
    result = await _run_worker(
        database,
        _handler(database, tmp_path, resolver=resolver, bridge=bridge, runner=runner),
    )

    assert result.status == "succeeded"  # type: ignore[attr-defined]
    assert result.run_id is not None  # type: ignore[attr-defined]
    assert len(bridge.requests) == 1
    request = bridge.requests[0]
    assert request.subscription_id == UUID(subscription_id)
    assert request.platform is platform
    assert request.intended_mode is MediaCrawlerRunMode.FORWARD
    assert request.scheduler_job_id == request.job_id
    assert request.execution_id == uuid5(
        request.job_id,
        f"media-sync/mediacrawler/attempt/{request.attempt}",
    )
    assert request.sync_run_id == UUID(result.run_id)  # type: ignore[attr-defined]
    assert request.schedule_revision == 0
    assert request.attempt == 1
    assert request.allow_full_history is True
    assert request.request_delay_seconds == 3.5
    assert request.headless is True
    assert bridge.thread_ids and all(thread != event_loop_thread for thread in bridge.thread_ids)
    assert resolver.thread_ids and all(thread != event_loop_thread for thread in resolver.thread_ids)
    assert runner.thread_ids and all(thread != event_loop_thread for thread in runner.thread_ids)

    with database.session() as session:
        run = session.get(SyncRun, result.run_id)  # type: ignore[attr-defined]
        job = session.scalar(select(Job).where(Job.job_type == "sync.subscription"))
        subscription = session.get(Subscription, subscription_id)
        assert run is not None and run.status == "succeeded"
        assert run.attempt == 1
        assert run.manifest["artifact_schema_version"] == MANIFEST_SCHEMA_VERSION
        assert run.manifest["mode"] == "forward"
        assert job is not None and job.run_id == run.id and job.status == "succeeded"
        assert subscription is not None and subscription.checkpoint_revision >= 1
        assert session.scalar(select(func.count()).select_from(Content)) >= 1


@pytest.mark.asyncio
@pytest.mark.parametrize("platform", tuple(Platform))
async def test_all_platforms_cross_real_v3_v2_process_protocol_retry_and_idempotent_restart(
    database: Database,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    platform: Platform,
) -> None:
    """Exercise the complete offline protocol without importing or launching upstream."""

    subscription_id = _seed(database, platform=platform)
    runtime_root = (tmp_path / "protocol-runtime").resolve()
    clock = _Clock()
    scheduler = DurableSchedulerService(database, clock=clock)
    assert scheduler.tick(limit=1).materialized_count == 1

    failing_child = _write_protocol_fixture_child(tmp_path / "protocol-fail-child.py", fail=True)
    monkeypatch.setattr(bridge_module, "RUNNER_SCRIPT", failing_child)
    first_runner = _ProtocolRecordingRunner()
    first_worker = SubscriptionWorker(
        database,
        SubscriptionHandlerRegistry(
            {"mediacrawler": _protocol_handler(database, runtime_root, runner=first_runner, clock=clock)}
        ),
        clock=clock,
        random_fraction=lambda: 0.0,
    )

    first = await first_worker.run_once(worker_id=f"protocol-{platform.value}-first")

    assert (first.status, first.error_code) == ("retry_wait", "temporary_upstream")
    assert len(first_runner.manifests) == len(first_runner.results) == 1
    first_manifest = first_runner.manifests[0]
    assert first_manifest.schema_version == MANIFEST_SCHEMA_VERSION
    assert first_manifest.attempt == 1
    assert first_runner.results[0].status is MediaCrawlerProcessStatus.UPSTREAM_FAILED
    assert not first_manifest.job_root.exists()
    with database.session() as session:
        retry_job = session.scalar(select(Job).where(Job.subscription_id == subscription_id))
        assert retry_job is not None
        durable_job_id = UUID(retry_job.id)
        retry_at = retry_job.available_at

    successful_child = _write_protocol_fixture_child(tmp_path / "protocol-success-child.py")
    monkeypatch.setattr(bridge_module, "RUNNER_SCRIPT", successful_child)
    clock.value = retry_at + timedelta(seconds=1)
    second_runner = _ProtocolRecordingRunner()
    restarted_worker = SubscriptionWorker(
        database,
        SubscriptionHandlerRegistry(
            {"mediacrawler": _protocol_handler(database, runtime_root, runner=second_runner, clock=clock)}
        ),
        clock=clock,
        random_fraction=lambda: 0.0,
    )

    second = await restarted_worker.run_once(worker_id=f"protocol-{platform.value}-restart")

    assert second.status == "succeeded"
    assert len(second_runner.manifests) == len(second_runner.results) == 1
    second_manifest = second_runner.manifests[0]
    assert second_manifest.schema_version == MANIFEST_SCHEMA_VERSION
    assert second_manifest.scheduler_job_id == first_manifest.scheduler_job_id == durable_job_id
    assert second_manifest.attempt == 2
    assert second_manifest.execution_id != first_manifest.execution_id
    assert second_manifest.sync_run_id != first_manifest.sync_run_id
    assert second_runner.results[0].status is MediaCrawlerProcessStatus.SUCCEEDED
    assert len(second_runner.snapshots) == 1
    snapshot = second_runner.snapshots[0]
    assert snapshot.receipt.schema_version == COMPLETION_RECEIPT_SCHEMA_VERSION
    assert snapshot.receipt.scheduler_job_id == durable_job_id
    assert snapshot.receipt.attempt == 2
    assert snapshot.receipt.execution_id == second_manifest.execution_id
    assert snapshot.receipt.sync_run_id == second_manifest.sync_run_id
    assert tuple(item.payload for item in snapshot.files) == ((FIXTURE_ROOT / FIXTURES[platform]).read_bytes(),)
    assert not second_manifest.job_root.exists() and not second_manifest.job_root.is_symlink()

    with database.session() as session:
        subscription = session.get(Subscription, subscription_id)
        assert subscription is not None and subscription.next_run_at is not None
        content_identity = tuple(
            session.execute(
                select(Content.id, Content.remote_type, Content.remote_id).order_by(
                    Content.remote_type,
                    Content.remote_id,
                )
            ).all()
        )
        asset_identity = tuple(
            session.execute(
                select(Asset.id, Asset.content_id, Asset.kind, Asset.position).order_by(
                    Asset.content_id,
                    Asset.kind,
                    Asset.position,
                )
            ).all()
        )
        checkpoint_after_retry = subscription.checkpoint_revision
        watermark_after_retry = tuple(subscription.watermark_remote_ids)
        next_run_at = subscription.next_run_at
        assert content_identity

    clock.value = next_run_at + timedelta(seconds=1)
    assert scheduler.tick(limit=1).materialized_count == 1
    replay_runner = _ProtocolRecordingRunner()
    replay_worker = SubscriptionWorker(
        database,
        SubscriptionHandlerRegistry(
            {"mediacrawler": _protocol_handler(database, runtime_root, runner=replay_runner, clock=clock)}
        ),
        clock=clock,
    )

    replay = await replay_worker.run_once(worker_id=f"protocol-{platform.value}-replay")

    assert replay.status == "succeeded"
    assert len(replay_runner.manifests) == 1
    replay_manifest = replay_runner.manifests[0]
    assert replay_manifest.schema_version == MANIFEST_SCHEMA_VERSION
    assert replay_manifest.scheduler_job_id != durable_job_id
    assert replay_manifest.attempt == 1
    assert len(replay_runner.snapshots) == 1
    replay_snapshot = replay_runner.snapshots[0]
    assert replay_snapshot.receipt.schema_version == COMPLETION_RECEIPT_SCHEMA_VERSION
    assert not replay_manifest.job_root.exists() and not replay_manifest.job_root.is_symlink()
    with database.session() as session:
        subscription = session.get(Subscription, subscription_id)
        replay_run = session.get(SyncRun, replay.run_id)
        assert subscription is not None and replay_run is not None
        assert (
            tuple(
                session.execute(
                    select(Content.id, Content.remote_type, Content.remote_id).order_by(
                        Content.remote_type,
                        Content.remote_id,
                    )
                ).all()
            )
            == content_identity
        )
        assert (
            tuple(
                session.execute(
                    select(Asset.id, Asset.content_id, Asset.kind, Asset.position).order_by(
                        Asset.content_id,
                        Asset.kind,
                        Asset.position,
                    )
                ).all()
            )
            == asset_identity
        )
        assert replay_run.discovered_count == 0 and replay_run.asset_count == 0
        assert subscription.checkpoint_revision > checkpoint_after_retry
        assert tuple(subscription.watermark_remote_ids) == watermark_after_retry


@pytest.mark.asyncio
async def test_real_handler_process_wait_keeps_heartbeat_and_independent_sqlite_writer_live(
    database: Database,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A real supervised child wait must not retain the handler's SQLite writer slot."""

    subscription_id = _seed(database, platform=Platform.XHS)
    runtime_root = (tmp_path / "heartbeat-runtime").resolve()
    probe = tmp_path / "slow-child.started"
    helper = _write_protocol_fixture_child(
        tmp_path / "protocol-slow-child.py",
        delay_seconds=2.0,
        probe_path=probe,
    )
    monkeypatch.setattr(bridge_module, "RUNNER_SCRIPT", helper)
    clock = _Clock()
    scheduler = DurableSchedulerService(database, clock=clock)
    assert scheduler.tick(limit=1).materialized_count == 1
    protocol_runner = _ProtocolRecordingRunner()
    worker = SubscriptionWorker(
        database,
        SubscriptionHandlerRegistry(
            {"mediacrawler": _protocol_handler(database, runtime_root, runner=protocol_runner, clock=clock)}
        ),
        clock=clock,
    )
    running = asyncio.create_task(
        worker.run_once(
            worker_id="mediacrawler-real-wait-worker",
            lease_seconds=2,
            heartbeat_interval_seconds=0.05,
        )
    )
    for _ in range(300):
        if probe.is_file():
            break
        await asyncio.sleep(0.01)
    assert probe.is_file() and running.done() is False

    def independent_write() -> None:
        independent = Database(database.url)
        try:
            with independent.session() as session:
                account = session.scalar(select(Account).join(Subscription).where(Subscription.id == subscription_id))
                assert account is not None
                account.display_name = "independent-writer-committed-during-child-wait"
        finally:
            independent.dispose()

    await asyncio.wait_for(asyncio.to_thread(independent_write), timeout=1.5)
    assert running.done() is False
    clock.value = NOW + timedelta(seconds=1)
    expected_expiry = NOW + timedelta(seconds=3)
    observed_expiry: datetime | None = None
    for _ in range(200):
        with database.session() as session:
            job = session.scalar(select(Job).where(Job.subscription_id == subscription_id))
            assert job is not None
            observed_expiry = job.lease_expires_at
        if observed_expiry == expected_expiry:
            break
        await asyncio.sleep(0.01)
    assert observed_expiry == expected_expiry
    assert running.done() is False

    result = await asyncio.wait_for(running, timeout=5)

    assert result.status == "succeeded"
    assert len(protocol_runner.manifests) == 1
    assert len(protocol_runner.snapshots) == 1
    snapshot = protocol_runner.snapshots[0]
    assert snapshot.receipt.schema_version == COMPLETION_RECEIPT_SCHEMA_VERSION
    assert not protocol_runner.manifests[0].job_root.exists()


@pytest.mark.asyncio
async def test_empty_normalized_delta_is_a_successful_guarded_checkpoint(
    database: Database,
    tmp_path: Path,
) -> None:
    subscription_id = _seed(database, platform=Platform.XHS)
    result = await _run_worker(
        database,
        _handler(database, tmp_path, normalizer=_empty_normalizer),
    )

    assert result.status == "succeeded"  # type: ignore[attr-defined]
    with database.session() as session:
        run = session.get(SyncRun, result.run_id)  # type: ignore[attr-defined]
        subscription = session.get(Subscription, subscription_id)
        assert run is not None and run.status == "succeeded"
        assert run.discovered_count == 0 and run.asset_count == 0
        assert subscription is not None and subscription.checkpoint_revision == 1
        assert session.scalar(select(func.count()).select_from(Content)) == 0


@pytest.mark.asyncio
async def test_injected_ingestion_summary_cannot_fake_a_committed_success(
    database: Database,
    tmp_path: Path,
) -> None:
    _seed(database, platform=Platform.XHS)
    result = await _run_worker(
        database,
        _handler(
            database,
            tmp_path,
            normalizer=_empty_normalizer,
            ingestion_factory=lambda _database: _NoopIngestionService(),
        ),
    )

    assert (result.status, result.error_code) == ("failed_terminal", "output_security_failed")  # type: ignore[attr-defined]
    with database.session() as session:
        run = session.scalar(select(SyncRun))
        assert run is not None and run.status == "failed_terminal"
        assert run.error_code == "output_security_failed"
        assert session.scalar(select(Subscription.checkpoint_revision)) == 0


@pytest.mark.asyncio
async def test_committed_sync_run_truth_wins_over_invalid_returned_summary(
    database: Database,
    tmp_path: Path,
) -> None:
    _seed(database, platform=Platform.XHS)
    result = await _run_worker(
        database,
        _handler(
            database,
            tmp_path,
            ingestion_factory=_InvalidSummaryAfterCommitIngestionService,
        ),
    )

    assert (result.status, result.error_code) == ("succeeded", None)  # type: ignore[attr-defined]
    with database.session() as session:
        job = session.scalar(select(Job))
        run = session.scalar(select(SyncRun))
        assert job is not None and job.status == "succeeded"
        assert run is not None and run.status == "succeeded"
        assert job.run_id == run.id


@pytest.mark.asyncio
async def test_transient_job_success_finalize_cannot_replace_committed_run_with_failure(
    database: Database,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed(database, platform=Platform.XHS)
    original_succeed = SchedulerRepository.succeed
    original_cleanup = mediacrawler_handler_module._cleanup_exact_attempt
    calls = 0
    cleanup_observations: list[tuple[Path, AttemptCleanupStatus]] = []
    ingestion_factories = 0

    def fail_once(self: SchedulerRepository, *args: object, **kwargs: object) -> object:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("POST-INGESTION-FINALIZE-SENTINEL-0007")
        return original_succeed(self, *args, **kwargs)  # type: ignore[arg-type]

    def observe_cleanup(paths: policies_module.RunPaths) -> AttemptCleanupStatus:
        status = original_cleanup(paths)
        cleanup_observations.append((paths.job_root, status))
        return status

    def ingestion_factory(active_database: Database) -> MediaCrawlerIngestionService:
        nonlocal ingestion_factories
        ingestion_factories += 1
        return MediaCrawlerIngestionService(active_database)

    monkeypatch.setattr(SchedulerRepository, "succeed", fail_once)
    monkeypatch.setattr(mediacrawler_handler_module, "_cleanup_exact_attempt", observe_cleanup)
    bridge = _Bridge()
    runner = _Runner()

    result = await _run_worker(
        database,
        _handler(
            database,
            tmp_path,
            bridge=bridge,
            runner=runner,
            ingestion_factory=ingestion_factory,
        ),
    )

    assert calls == 2
    assert len(bridge.requests) == len(runner.calls) == ingestion_factories == 1
    source_root = runner.calls[0][0].paths.job_root
    assert cleanup_observations == [(source_root, AttemptCleanupStatus.REMOVED)]
    assert not source_root.exists() and not source_root.is_symlink()
    assert (result.status, result.error_code) == ("succeeded", None)  # type: ignore[attr-defined]
    with database.session() as session:
        job = session.scalar(select(Job))
        run = session.scalar(select(SyncRun))
        subscription = session.scalar(select(Subscription))
        assert job is not None and job.status == "succeeded"
        assert run is not None and run.status == "succeeded"
        assert job.run_id == run.id
        assert subscription is not None and subscription.consecutive_failures == 0


@pytest.mark.asyncio
async def test_already_succeeded_handler_restart_cleans_same_source_without_reingest_or_spawn(
    database: Database,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed(database, platform=Platform.XHS)
    clock = _Clock()
    DurableSchedulerService(database, clock=clock).tick(limit=1)
    with database.session() as session:
        repository = SchedulerRepository(session)
        claimed = repository.claim_next(
            worker_id="terminal-restart-owner",
            global_capacity=1,
            lease_seconds=60,
            now=clock(),
        )
        assert claimed is not None
        started = repository.start(
            claimed.job_id,
            worker_id="terminal-restart-owner",
            lease_token=claimed.lease_token,
            now=clock(),
        )

    bridge = _Bridge()
    runner = _Runner()
    ingestion_factories = 0
    cleanup_observations: list[tuple[Path, AttemptCleanupStatus]] = []
    original_cleanup = mediacrawler_handler_module._cleanup_exact_attempt

    def ingestion_factory(active_database: Database) -> MediaCrawlerIngestionService:
        nonlocal ingestion_factories
        ingestion_factories += 1
        return MediaCrawlerIngestionService(active_database)

    def observe_cleanup(paths: policies_module.RunPaths) -> AttemptCleanupStatus:
        status = original_cleanup(paths)
        cleanup_observations.append((paths.job_root, status))
        return status

    monkeypatch.setattr(mediacrawler_handler_module, "_cleanup_exact_attempt", observe_cleanup)
    handler = _handler(
        database,
        tmp_path,
        bridge=bridge,
        runner=runner,
        clock=clock,
        ingestion_factory=ingestion_factory,
    )
    worker = SubscriptionWorker(
        database,
        SubscriptionHandlerRegistry({"mediacrawler": handler}),
        clock=clock,
    )
    first_context, handler_key = worker._load_context(started, worker_id="terminal-restart-owner")
    assert first_context is not None and handler_key == "mediacrawler"

    first = await handler.run(first_context)

    assert first.succeeded is True and first.run_id is not None
    with database.session() as session:
        refreshed = SchedulerRepository(session).heartbeat(
            started.job_id,
            worker_id="terminal-restart-owner",
            lease_token=started.lease_token,
            lease_seconds=60,
            now=clock(),
        )
    restart_context, handler_key = worker._load_context(refreshed, worker_id="terminal-restart-owner")
    assert restart_context is not None and handler_key == "mediacrawler"

    restarted = await handler.run(restart_context)

    assert restarted.succeeded is True and restarted.run_id == first.run_id
    assert len(bridge.requests) == len(runner.calls) == ingestion_factories == 1
    source_root = runner.calls[0][0].paths.job_root
    assert cleanup_observations == [
        (source_root, AttemptCleanupStatus.REMOVED),
        (source_root, AttemptCleanupStatus.ABSENT),
    ]
    assert not source_root.exists() and not source_root.is_symlink()
    with database.session() as session:
        run = session.get(SyncRun, str(first.run_id))
        assert run is not None and run.status == "succeeded"


@pytest.mark.asyncio
async def test_bridge_late_failure_removes_the_exact_attempt_root(
    database: Database,
    tmp_path: Path,
) -> None:
    _seed(database, platform=Platform.XHS)
    bridge = _LateFailingBridge()
    result = await _run_worker(database, _handler(database, tmp_path, bridge=bridge))

    assert (result.status, result.error_code) == ("failed_terminal", "configuration_invalid")  # type: ignore[attr-defined]
    assert len(bridge.requests) == 1
    request = bridge.requests[0]
    assert request.execution_id is not None
    attempt_root = tmp_path / "runtime" / "jobs" / str(request.execution_id)
    assert not attempt_root.exists()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("enabled", "license_acknowledged", "python_executable", "expected_code"),
    [
        (False, False, Path("fixture-python"), "handler_unsupported"),
        (True, False, Path("fixture-python"), "license_acknowledgement_required"),
        (True, True, None, "configuration_invalid"),
    ],
)
async def test_enablement_license_and_runtime_fail_closed_before_spawn(
    database: Database,
    tmp_path: Path,
    enabled: bool,
    license_acknowledged: bool,
    python_executable: Path | None,
    expected_code: str,
) -> None:
    _seed(database)
    bridge = _Bridge()
    runner = _Runner()
    result = await _run_worker(
        database,
        _handler(
            database,
            tmp_path,
            bridge=bridge,
            runner=runner,
            enabled=enabled,
            license_acknowledged=license_acknowledged,
            python_executable=python_executable,
        ),
    )

    assert result.error_code == expected_code  # type: ignore[attr-defined]
    expected_status = "waiting_user" if expected_code == "license_acknowledgement_required" else "failed_terminal"
    assert result.status == expected_status  # type: ignore[attr-defined]
    assert not bridge.requests
    assert not runner.calls
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(SyncRun)) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    (
        "login_method",
        "credential_ref",
        "bridge_error",
        "expected_status",
        "expected_code",
        "expected_run_status",
        "expected_account_status",
    ),
    [
        (LoginMethod.QR, None, None, "waiting_user", "qr_required", None, None),
        (LoginMethod.COOKIE, None, None, "waiting_auth", "credentials_unavailable", None, None),
        (
            LoginMethod.SAVED_SESSION,
            None,
            SavedSessionUnavailableError("fixture profile is unavailable"),
            "waiting_auth",
            "auth_expired",
            "awaiting_auth",
            "expired",
        ),
        (
            LoginMethod.SAVED_SESSION,
            None,
            BridgeConfigurationError("fixture manifest is invalid"),
            "failed_terminal",
            "configuration_invalid",
            "failed_terminal",
            "authenticated",
        ),
    ],
)
async def test_scheduled_auth_paths_wait_without_fake_interaction(
    database: Database,
    tmp_path: Path,
    login_method: LoginMethod,
    credential_ref: str | None,
    bridge_error: Exception | None,
    expected_status: str,
    expected_code: str,
    expected_run_status: str | None,
    expected_account_status: str | None,
) -> None:
    _seed(database, login_method=login_method, credential_ref=credential_ref)
    bridge = _Bridge(bridge_error)
    runner = _Runner()
    result = await _run_worker(
        database,
        _handler(database, tmp_path, bridge=bridge, runner=runner),
    )

    assert (result.status, result.error_code) == (expected_status, expected_code)  # type: ignore[attr-defined]
    assert not runner.calls
    assert len(bridge.requests) == (1 if login_method is LoginMethod.SAVED_SESSION else 0)
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(SyncRun)) == (1 if expected_run_status else 0)
        if expected_run_status is not None:
            run = session.scalar(select(SyncRun))
            assert run is not None and run.status == expected_run_status
            assert run.error_code == expected_code and run.error_message is None
        if expected_account_status is not None:
            account = session.scalar(select(Account))
            assert account is not None and account.auth_status == expected_account_status


@pytest.mark.asyncio
async def test_qr_login_handoff_resumes_existing_job_as_saved_session(
    database: Database,
    tmp_path: Path,
) -> None:
    subscription_id = _seed(
        database,
        login_method=LoginMethod.QR,
        credential_ref=None,
        auth_status="required",
    )
    clock = _Clock()
    scheduler = DurableSchedulerService(database, clock=clock)
    scheduler.tick(limit=1)
    first = await SubscriptionWorker(
        database,
        SubscriptionHandlerRegistry({"mediacrawler": _handler(database, tmp_path)}),
        clock=clock,
        random_fraction=lambda: 0.0,
    ).run_once(worker_id="qr-required-worker")
    assert (first.status, first.error_code) == ("waiting_user", "qr_required")

    with database.session() as session:
        subscription = SubscriptionRepository(session).get(subscription_id)
        assert subscription is not None
        account_id = UUID(subscription.account_id)
    login = MediaCrawlerQrLoginService(database, _SuccessfulLoginRunner()).run(
        AccountLoginRequest(account_id=account_id)
    )
    assert login.authenticated

    clock.value += timedelta(days=1)
    resumed = scheduler.resume_job(first.job_id or "")
    bridge = _Bridge()
    crawler = _Runner()
    second = await SubscriptionWorker(
        database,
        SubscriptionHandlerRegistry({"mediacrawler": _handler(database, tmp_path, bridge=bridge, runner=crawler)}),
        clock=clock,
        random_fraction=lambda: 0.0,
    ).run_once(worker_id="saved-session-worker")

    assert resumed.status == "queued"
    assert second.status == "succeeded"
    assert second.attempt == 2
    assert len(bridge.requests) == len(crawler.calls) == 1
    assert bridge.requests[0].login_method is LoginMethod.SAVED_SESSION
    with database.session() as session:
        subscription = SubscriptionRepository(session).get(subscription_id)
        assert subscription is not None
        assert (subscription.account.login_method, subscription.account.auth_status) == (
            "saved_session",
            "authenticated",
        )


@pytest.mark.asyncio
async def test_expired_saved_session_reauthentication_resumes_existing_job(
    database: Database,
    tmp_path: Path,
) -> None:
    subscription_id = _seed(
        database,
        login_method=LoginMethod.SAVED_SESSION,
        credential_ref=None,
    )
    clock = _Clock()
    scheduler = DurableSchedulerService(database, clock=clock)
    scheduler.tick(limit=1)
    first = await SubscriptionWorker(
        database,
        SubscriptionHandlerRegistry(
            {
                "mediacrawler": _handler(
                    database,
                    tmp_path,
                    runner=_Runner([MediaCrawlerProcessStatus.AUTH_EXPIRED]),
                )
            }
        ),
        clock=clock,
        random_fraction=lambda: 0.0,
    ).run_once(worker_id="expired-session-worker")
    assert (first.status, first.error_code) == ("waiting_auth", "auth_expired")

    with database.session() as session:
        subscription = SubscriptionRepository(session).get(subscription_id)
        assert subscription is not None
        account_id = UUID(subscription.account_id)
        assert (subscription.account.login_method, subscription.account.auth_status) == (
            "saved_session",
            "expired",
        )

    login = MediaCrawlerQrLoginService(database, _SuccessfulLoginRunner()).run(
        AccountLoginRequest(account_id=account_id)
    )
    assert login.authenticated

    clock.value += timedelta(days=1)
    resumed = scheduler.resume_job(first.job_id or "")
    bridge = _Bridge()
    crawler = _Runner()
    second = await SubscriptionWorker(
        database,
        SubscriptionHandlerRegistry({"mediacrawler": _handler(database, tmp_path, bridge=bridge, runner=crawler)}),
        clock=clock,
        random_fraction=lambda: 0.0,
    ).run_once(worker_id="reauthenticated-session-worker")

    assert resumed.status == "queued"
    assert second.status == "succeeded"
    assert second.attempt == 2
    assert len(bridge.requests) == len(crawler.calls) == 1
    assert bridge.requests[0].login_method is LoginMethod.SAVED_SESSION
    with database.session() as session:
        subscription = SubscriptionRepository(session).get(subscription_id)
        assert subscription is not None
        assert (subscription.account.login_method, subscription.account.auth_status) == (
            "saved_session",
            "authenticated",
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("process_status", "expected_code", "expected_job_status", "expected_run_status"),
    [
        (MediaCrawlerProcessStatus.ACCOUNT_BUSY, "account_busy", "retry_wait", "failed_retryable"),
        (MediaCrawlerProcessStatus.TIMED_OUT, "upstream_timeout", "retry_wait", "failed_retryable"),
        (MediaCrawlerProcessStatus.START_FAILED, "upstream_unavailable", "retry_wait", "failed_retryable"),
        (MediaCrawlerProcessStatus.UPSTREAM_FAILED, "temporary_upstream", "retry_wait", "failed_retryable"),
        (MediaCrawlerProcessStatus.AUTH_EXPIRED, "auth_expired", "waiting_auth", "awaiting_auth"),
        (
            MediaCrawlerProcessStatus.CONFIGURATION_FAILED,
            "configuration_invalid",
            "failed_terminal",
            "failed_terminal",
        ),
        (
            MediaCrawlerProcessStatus.OUTPUT_TREE_INVALID,
            "output_security_failed",
            "failed_terminal",
            "failed_terminal",
        ),
        (
            MediaCrawlerProcessStatus.COMPLETION_FAILED,
            "output_security_failed",
            "failed_terminal",
            "failed_terminal",
        ),
    ],
)
async def test_process_outcomes_use_only_the_fixed_failure_mapping(
    database: Database,
    tmp_path: Path,
    process_status: MediaCrawlerProcessStatus,
    expected_code: str,
    expected_job_status: str,
    expected_run_status: str,
) -> None:
    _seed(database)
    runner = _Runner([process_status])
    result = await _run_worker(database, _handler(database, tmp_path, runner=runner))

    assert (result.status, result.error_code) == (expected_job_status, expected_code)  # type: ignore[attr-defined]
    spec = runner.calls[0][0]
    assert not spec.paths.job_root.exists()
    with database.session() as session:
        run = session.scalar(select(SyncRun))
        assert run is not None and run.status == expected_run_status
        assert run.error_code == expected_code and run.error_message is None


@pytest.mark.asyncio
async def test_saved_session_probe_failure_expires_account_and_waits_for_auth(
    database: Database,
    tmp_path: Path,
) -> None:
    _seed(database, login_method=LoginMethod.SAVED_SESSION, credential_ref=None)
    runner = _Runner([MediaCrawlerProcessStatus.AUTH_EXPIRED])

    result = await _run_worker(database, _handler(database, tmp_path, runner=runner))

    assert (result.status, result.error_code) == ("waiting_auth", "auth_expired")  # type: ignore[attr-defined]
    with database.session() as session:
        account = session.scalar(select(Account))
        run = session.scalar(select(SyncRun))
        assert account is not None and account.auth_status == "expired"
        assert run is not None and (run.status, run.error_code) == ("awaiting_auth", "auth_expired")


@pytest.mark.asyncio
async def test_retry_reuses_job_but_changes_attempt_execution_identity(
    database: Database,
    tmp_path: Path,
) -> None:
    _seed(database)
    clock = _Clock()
    bridge = _Bridge()
    runner = _Runner(
        [
            MediaCrawlerProcessStatus.ACCOUNT_BUSY,
            MediaCrawlerProcessStatus.SUCCEEDED,
        ]
    )
    handler = _handler(database, tmp_path, bridge=bridge, runner=runner, clock=clock)
    scheduler = DurableSchedulerService(database, clock=clock)
    scheduler.tick(limit=1)
    worker = SubscriptionWorker(
        database,
        SubscriptionHandlerRegistry({"mediacrawler": handler}),
        clock=clock,
        random_fraction=lambda: 0.0,
    )

    first = await worker.run_once(worker_id="attempt-worker")
    assert first.status == "retry_wait"
    clock.value += timedelta(hours=1)
    second = await worker.run_once(worker_id="attempt-worker")
    assert second.status == "succeeded"

    assert len(bridge.requests) == 2
    assert bridge.requests[0].job_id == bridge.requests[1].job_id
    assert [request.attempt for request in bridge.requests] == [1, 2]
    assert bridge.requests[0].execution_id != bridge.requests[1].execution_id
    assert bridge.requests[0].sync_run_id != bridge.requests[1].sync_run_id
    with database.session() as session:
        runs = list(session.scalars(select(SyncRun).order_by(SyncRun.attempt)).all())
        assert [run.status for run in runs] == ["cancelled", "succeeded"]
        assert runs[0].error_code == "scheduler_replaced"


@pytest.mark.asyncio
async def test_unresolved_cleanup_fences_current_and_recovery_without_successor_or_spawn(
    database: Database,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "UNRESOLVED-HANDLER-SECRET-SENTINEL-0007"
    subscription_id = _seed(database)
    clock = _Clock()
    resolver = _Resolver()
    bridge = _Bridge()
    runner = _UnresolvedCleanupRunner(secret)
    monkeypatch.setattr(
        mediacrawler_handler_module,
        "_cleanup_exact_attempt",
        lambda _paths: AttemptCleanupStatus.UNRESOLVED,
    )
    handler = _handler(
        database,
        tmp_path,
        resolver=resolver,
        bridge=bridge,
        runner=runner,
        clock=clock,
    )
    DurableSchedulerService(database, clock=clock).tick(limit=1)
    worker = SubscriptionWorker(
        database,
        SubscriptionHandlerRegistry({"mediacrawler": handler}),
        clock=clock,
    )

    first = await worker.run_once(worker_id="cleanup-owner")

    assert issubclass(MediaCrawlerCleanupBlockedError, SchedulerLeaseLostError)
    assert (first.status, first.error_code) == ("fenced", None)
    assert len(bridge.requests) == len(runner.calls) == len(resolver.calls) == 1
    paths = runner.calls[0].paths
    assert (paths.output_root / "unresolved-private.tmp").read_text(encoding="utf-8") == secret
    account_block, incident = attempt_cleanup_incident_paths(paths)
    assert account_block.is_file() and incident.is_file()
    assert is_attempt_cleanup_blocked(paths)
    with database.session() as session:
        first_job = session.scalar(select(Job).where(Job.subscription_id == subscription_id))
        first_run = session.scalar(select(SyncRun).where(SyncRun.subscription_id == subscription_id))
        subscription = session.get(Subscription, subscription_id)
        assert first_job is not None and first_run is not None and subscription is not None
        assert first_job.status == "running" and first_job.run_id == first_run.id
        assert first_job.last_error_code is None
        assert first_run.status == "running" and first_run.error_code is None
        assert subscription.consecutive_failures == 0
        first_lease_token = first_job.lease_token

    marker_bytes = account_block.read_bytes() + incident.read_bytes()
    assert secret.encode() not in marker_bytes
    assert b"cleanup-owner" not in marker_bytes
    assert first_lease_token is not None and first_lease_token.encode() not in marker_bytes

    clock.value += timedelta(seconds=61)
    replacement = await worker.run_once(worker_id="cleanup-recovery")

    assert (replacement.status, replacement.error_code) == ("fenced", None)
    assert len(bridge.requests) == len(runner.calls) == len(resolver.calls) == 1
    with database.session() as session:
        replacement_job = session.scalar(select(Job).where(Job.subscription_id == subscription_id))
        runs = list(session.scalars(select(SyncRun).where(SyncRun.subscription_id == subscription_id)).all())
        subscription = session.get(Subscription, subscription_id)
        assert replacement_job is not None and subscription is not None
        assert replacement_job.status == "running"
        assert replacement_job.attempts == 2
        assert replacement_job.run_id == runs[0].id
        assert len(runs) == 1
        assert subscription.consecutive_failures == 0
        replacement_lease_token = replacement_job.lease_token
    assert b"cleanup-recovery" not in marker_bytes
    assert replacement_lease_token is not None and replacement_lease_token.encode() not in marker_bytes


@pytest.mark.asyncio
async def test_cleanup_incident_persistence_failure_still_fences_without_terminal_write(
    database: Database,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    subscription_id = _seed(database)
    runner = _UnresolvedCleanupRunner("INCIDENT-WRITE-FAILURE-SENTINEL-0007")
    monkeypatch.setattr(
        mediacrawler_handler_module,
        "_cleanup_exact_attempt",
        lambda _paths: AttemptCleanupStatus.UNRESOLVED,
    )

    def denied_incident(_paths: object) -> None:
        raise AttemptCleanupError("fixture incident persistence denial")

    monkeypatch.setattr(
        mediacrawler_handler_module,
        "record_attempt_cleanup_incident",
        denied_incident,
    )

    result = await _run_worker(
        database,
        _handler(database, tmp_path, runner=runner),
        worker_id="incident-write-failure-owner",
    )

    assert (result.status, result.error_code) == ("fenced", None)  # type: ignore[attr-defined]
    assert len(runner.calls) == 1
    account_block, incident = attempt_cleanup_incident_paths(runner.calls[0].paths)
    assert not account_block.exists() and not incident.exists()
    with database.session() as session:
        job = session.scalar(select(Job).where(Job.subscription_id == subscription_id))
        run = session.scalar(select(SyncRun).where(SyncRun.subscription_id == subscription_id))
        assert job is not None and job.status == "running" and job.last_error_code is None
        assert run is not None and run.status == "running" and run.error_code is None


@pytest.mark.asyncio
async def test_lease_loss_cancels_and_joins_runner_before_worker_returns(
    database: Database,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed(database)
    runner = _BlockingRunner()
    clock = _Clock()
    monkeypatch.setattr(
        mediacrawler_handler_module,
        "_cleanup_exact_attempt",
        lambda _paths: AttemptCleanupStatus.UNRESOLVED,
    )
    handler = _handler(database, tmp_path, runner=runner, clock=clock)
    DurableSchedulerService(database, clock=clock).tick(limit=1)
    worker = SubscriptionWorker(
        database,
        SubscriptionHandlerRegistry({"mediacrawler": handler}),
        clock=clock,
    )
    task = asyncio.create_task(
        worker.run_once(
            worker_id="lease-loss-worker",
            heartbeat_interval_seconds=0.05,
        )
    )
    assert await asyncio.to_thread(runner.entered.wait, 5)
    with database.session() as session:
        job_id = session.scalar(select(Job.id).where(Job.job_type == "sync.subscription"))
    assert job_id is not None
    DurableSchedulerService(database, clock=clock).cancel_job(job_id)

    result = await asyncio.wait_for(task, timeout=5)
    assert result.status == "cancelled"
    assert runner.saw_cancellation.is_set()
    assert runner.finished.is_set()
    assert len(runner.specs) == 1
    account_block, incident = attempt_cleanup_incident_paths(runner.specs[0].paths)
    assert account_block.is_file() and incident.is_file()
    marker_bytes = account_block.read_bytes() + incident.read_bytes()
    assert b"fixture-cookie-value" not in marker_bytes
    assert b"lease-loss-worker" not in marker_bytes
    with database.session() as session:
        run = session.scalar(select(SyncRun))
        job = session.scalar(select(Job).where(Job.job_type == "sync.subscription"))
        assert run is not None and run.status == "cancelled"
        assert run.error_code == "scheduler_cancelled"
        assert job is not None and job.status == "cancelled"
        assert job.last_error_code is None


@pytest.mark.asyncio
async def test_task_cancellation_signals_and_joins_runner(
    database: Database,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed(database)
    runner = _BlockingRunner()
    monkeypatch.setattr(
        mediacrawler_handler_module,
        "_cleanup_exact_attempt",
        lambda _paths: AttemptCleanupStatus.UNRESOLVED,
    )
    handler = _handler(database, tmp_path, runner=runner)
    task = asyncio.create_task(_run_worker(database, handler, worker_id="cancelled-worker"))
    assert await asyncio.to_thread(runner.entered.wait, 5)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, timeout=5)
    assert runner.saw_cancellation.is_set()
    assert runner.finished.is_set()
    assert len(runner.specs) == 1
    account_block, incident = attempt_cleanup_incident_paths(runner.specs[0].paths)
    assert account_block.is_file() and incident.is_file()
    with database.session() as session:
        job = session.scalar(select(Job).where(Job.job_type == "sync.subscription"))
        run = session.scalar(select(SyncRun))
        assert job is not None and job.status == "running" and job.last_error_code is None
        assert run is not None and run.status == "running" and run.error_code is None


@pytest.mark.asyncio
async def test_repeated_task_cancellation_still_joins_runner_before_unwind(
    database: Database,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed(database)
    runner = _RepeatedCancelRunner()
    monkeypatch.setattr(
        mediacrawler_handler_module,
        "_cleanup_exact_attempt",
        lambda _paths: AttemptCleanupStatus.UNRESOLVED,
    )
    handler = _handler(database, tmp_path, runner=runner)
    task = asyncio.create_task(_run_worker(database, handler, worker_id="repeated-cancel-runner"))
    assert await asyncio.to_thread(runner.entered.wait, 5)

    task.cancel()
    assert await asyncio.to_thread(runner.saw_cancellation.wait, 5)
    task.cancel()
    await asyncio.sleep(0.05)
    outer_finished_before_release = task.done()
    runner_finished_before_release = runner.finished.is_set()

    runner.release.set()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, timeout=5)

    assert not outer_finished_before_release
    assert not runner_finished_before_release
    assert runner.finished.is_set()
    assert len(runner.specs) == 1
    account_block, incident = attempt_cleanup_incident_paths(runner.specs[0].paths)
    assert account_block.is_file() and incident.is_file()


@pytest.mark.asyncio
async def test_child_exit_pre_seal_cancellation_never_enters_normalization_or_ingestion(
    database: Database,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    subscription_id = _seed(database, platform=Platform.BILI)
    runtime_root = (tmp_path / "pre-seal-runtime").resolve()
    helper = _write_protocol_fixture_child(tmp_path / "pre-seal-protocol-child.py")
    monkeypatch.setattr(bridge_module, "RUNNER_SCRIPT", helper)
    tree_joined = Event()
    final_inspection_started = Event()
    release_final_inspection = Event()
    receipt_started = Event()
    original_close = runner_module._close_process_tree
    original_inspect = policies_module.inspect_output

    def observe_tree_join(
        process: subprocess.Popen[bytes],
        windows_job: runner_module._WindowsJob | None,
    ) -> bool:
        closed = original_close(process, windows_job)
        assert closed
        assert process.poll() == 0
        tree_joined.set()
        return closed

    def block_final_inspection(
        root: Path,
        limits: WatchdogLimits | None = None,
    ) -> policies_module.OutputStats:
        if tree_joined.is_set():
            final_inspection_started.set()
            assert release_final_inspection.wait(timeout=5)
        return original_inspect(root, limits)

    def forbid_receipt(*args: object, **kwargs: object) -> None:
        del args, kwargs
        receipt_started.set()
        raise AssertionError("receipt publication must not start after pre-seal cancellation")

    monkeypatch.setattr(runner_module, "_close_process_tree", observe_tree_join)
    monkeypatch.setattr(policies_module, "inspect_output", block_final_inspection)
    monkeypatch.setattr(receipt_module, "write_completion_receipt", forbid_receipt)

    clock = _Clock()
    scheduler = DurableSchedulerService(database, clock=clock)
    assert scheduler.tick(limit=1).materialized_count == 1
    runner = _ProtocolRecordingRunner()
    normalizer = _NoEntryNormalizer()
    ingestion = _IngestionSpy()
    handler = _protocol_handler(
        database,
        runtime_root,
        runner=runner,
        clock=clock,
        normalizer=normalizer,
        ingestion_factory=lambda _database: ingestion,
    )
    worker = SubscriptionWorker(
        database,
        SubscriptionHandlerRegistry({"mediacrawler": handler}),
        clock=clock,
        random_fraction=lambda: 0.0,
    )
    task = asyncio.create_task(worker.run_once(worker_id="pre-seal-cancel"))
    cancel_requested = False

    try:
        assert await asyncio.to_thread(final_inspection_started.wait, 5)
        assert tree_joined.is_set()
        assert len(runner.manifests) == 1
        manifest = runner.manifests[0]
        receipt_path = manifest.job_root / "completion-receipt.json"
        assert manifest.output_root.is_dir()
        assert not receipt_path.exists() and not receipt_path.is_symlink()
        assert normalizer.calls == 0 and ingestion.calls == 0

        task.cancel()
        cancel_requested = True
        await asyncio.sleep(0)

        assert not task.done()
        assert not receipt_started.is_set()
        assert normalizer.calls == 0 and ingestion.calls == 0
    finally:
        if not cancel_requested and not task.done():
            task.cancel()
        release_final_inspection.set()

    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, timeout=5)

    assert len(runner.results) == 1
    assert runner.results[0].status is MediaCrawlerProcessStatus.CANCELLED
    assert not receipt_started.is_set()
    assert normalizer.calls == 0 and ingestion.calls == 0
    assert not manifest.job_root.exists() and not manifest.job_root.is_symlink()
    assert not receipt_path.exists() and not receipt_path.is_symlink()
    account_lock = runner_module._AccountFileLock(manifest.account_root)
    assert account_lock.acquire()
    account_lock.release()
    with database.session() as session:
        subscription = session.get(Subscription, subscription_id)
        run = session.scalar(select(SyncRun).where(SyncRun.subscription_id == subscription_id))
        job = session.scalar(select(Job).where(Job.subscription_id == subscription_id))
        assert subscription is not None and subscription.checkpoint_revision == 0
        assert run is not None and run.status != "succeeded"
        assert job is not None and job.status != "succeeded"
        assert session.scalar(select(func.count()).select_from(Content)) == 0
        assert session.scalar(select(func.count()).select_from(Asset)) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "repeat_cancel",
    (False, True),
    ids=("single-cancel", "repeated-cancel"),
)
async def test_post_seal_pre_ingest_cancellation_joins_before_unwind(
    database: Database,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    repeat_cancel: bool,
) -> None:
    subscription_id = _seed(database, platform=Platform.BILI)
    runtime_root = (tmp_path / "post-seal-runtime").resolve()
    helper = _write_protocol_fixture_child(tmp_path / "post-seal-protocol-child.py")
    monkeypatch.setattr(bridge_module, "RUNNER_SCRIPT", helper)
    clock = _Clock()
    scheduler = DurableSchedulerService(database, clock=clock)
    assert scheduler.tick(limit=1).materialized_count == 1
    runner = _ProtocolRecordingRunner()
    normalizer = _BlockingPostSealNormalizer()
    ingestion = _IngestionSpy()
    handler = _protocol_handler(
        database,
        runtime_root,
        runner=runner,
        clock=clock,
        normalizer=normalizer,
        ingestion_factory=lambda _database: ingestion,
    )
    worker = SubscriptionWorker(
        database,
        SubscriptionHandlerRegistry({"mediacrawler": handler}),
        clock=clock,
        random_fraction=lambda: 0.0,
    )
    task = asyncio.create_task(
        worker.run_once(
            worker_id=f"post-seal-{'repeated' if repeat_cancel else 'single'}-cancel",
        )
    )
    cancel_requested = False

    try:
        assert await asyncio.to_thread(normalizer.entered.wait, 5)
        assert len(runner.manifests) == len(runner.results) == 1
        assert runner.results[0].status is MediaCrawlerProcessStatus.SUCCEEDED
        manifest = runner.manifests[0]
        receipt_path = manifest.job_root / "completion-receipt.json"
        assert manifest.job_root.is_dir() and receipt_path.is_file()
        snapshot = load_validated_output_snapshot(manifest)
        assert snapshot.receipt.schema_version == COMPLETION_RECEIPT_SCHEMA_VERSION
        assert normalizer.manifests == [manifest]
        assert normalizer.receipt_schema_versions == [COMPLETION_RECEIPT_SCHEMA_VERSION]
        assert not normalizer.finished.is_set()
        assert ingestion.calls == 0

        with database.session() as session:
            subscription = session.get(Subscription, subscription_id)
            runs = list(session.scalars(select(SyncRun)).all())
            job = session.scalar(select(Job).where(Job.subscription_id == subscription_id))
            assert subscription is not None and subscription.checkpoint_revision == 0
            state_before_cancel = (
                subscription.checkpoint_revision,
                session.scalar(select(func.count()).select_from(Content)),
                session.scalar(select(func.count()).select_from(Asset)),
            )
            assert state_before_cancel == (0, 0, 0)
            assert len(runs) == 1 and runs[0].status != "succeeded"
            assert job is not None and job.status != "succeeded"

        task.cancel()
        cancel_requested = True
        await asyncio.sleep(0)
        if repeat_cancel:
            task.cancel()
            await asyncio.sleep(0)

        assert not task.done()
        assert not normalizer.finished.is_set()
        assert ingestion.calls == 0
        assert manifest.job_root.is_dir() and receipt_path.is_file()
        assert load_validated_output_snapshot(manifest).receipt.schema_version == COMPLETION_RECEIPT_SCHEMA_VERSION
        with database.session() as session:
            subscription = session.get(Subscription, subscription_id)
            assert subscription is not None
            state_while_cancelled = (
                subscription.checkpoint_revision,
                session.scalar(select(func.count()).select_from(Content)),
                session.scalar(select(func.count()).select_from(Asset)),
            )
            assert state_while_cancelled == state_before_cancel
    finally:
        if not cancel_requested and not task.done():
            task.cancel()
        normalizer.release.set()

    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, timeout=5)

    assert normalizer.finished.is_set()
    assert ingestion.calls == 0
    assert not manifest.job_root.exists() and not manifest.job_root.is_symlink()
    assert not receipt_path.exists() and not receipt_path.is_symlink()
    with database.session() as session:
        subscription = session.get(Subscription, subscription_id)
        runs = list(session.scalars(select(SyncRun)).all())
        job = session.scalar(select(Job).where(Job.subscription_id == subscription_id))
        assert subscription is not None
        state_after_cancel = (
            subscription.checkpoint_revision,
            session.scalar(select(func.count()).select_from(Content)),
            session.scalar(select(func.count()).select_from(Asset)),
        )
        assert state_after_cancel == state_before_cancel
        assert len(runs) == 1 and runs[0].status != "succeeded"
        assert job is not None and job.status != "succeeded"


@pytest.mark.asyncio
async def test_repeated_cancellation_between_ingestion_batches_joins_before_unwind(
    database: Database,
    tmp_path: Path,
) -> None:
    subscription_id = _seed(database, platform=Platform.DY)
    entered = Event()
    release = Event()
    finished = Event()

    def ingestion_factory(active_database: Database) -> _BetweenBatchIngestionService:
        return _BetweenBatchIngestionService(
            active_database,
            entered=entered,
            release=release,
            finished=finished,
        )

    handler = _handler(database, tmp_path, ingestion_factory=ingestion_factory)
    task = asyncio.create_task(_run_worker(database, handler, worker_id="repeated-cancel-ingestion"))
    assert await asyncio.to_thread(entered.wait, 5)

    task.cancel()
    await asyncio.sleep(0)
    task.cancel()
    await asyncio.sleep(0.05)
    outer_finished_before_release = task.done()
    ingestion_finished_before_release = finished.is_set()

    release.set()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, timeout=5)

    assert not outer_finished_before_release
    assert not ingestion_finished_before_release
    assert finished.is_set()
    with database.session() as session:
        subscription = session.get(Subscription, subscription_id)
        run = session.scalar(select(SyncRun).where(SyncRun.subscription_id == subscription_id))
        assert subscription is not None and subscription.checkpoint_revision == 1
        assert session.scalar(select(func.count(Content.id))) == 1
        assert run is not None and run.status == "ingesting"


@pytest.mark.asyncio
async def test_repeated_cancellation_during_unresolved_cleanup_records_block_before_unwind(
    database: Database,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    subscription_id = _seed(database)
    clock = _Clock()
    resolver = _Resolver()
    bridge = _LateFailingBridge()
    cleanup_entered = Event()
    cleanup_release = Event()

    def blocking_unresolved_cleanup(_paths: object) -> AttemptCleanupStatus:
        cleanup_entered.set()
        assert cleanup_release.wait(timeout=5)
        return AttemptCleanupStatus.UNRESOLVED

    monkeypatch.setattr(
        mediacrawler_handler_module,
        "_cleanup_exact_attempt",
        blocking_unresolved_cleanup,
    )
    handler = _handler(database, tmp_path, resolver=resolver, bridge=bridge, clock=clock)
    worker = SubscriptionWorker(
        database,
        SubscriptionHandlerRegistry({"mediacrawler": handler}),
        clock=clock,
    )
    DurableSchedulerService(database, clock=clock).tick(limit=1)
    task = asyncio.create_task(worker.run_once(worker_id="cleanup-race-owner"))
    assert await asyncio.to_thread(cleanup_entered.wait, 5)

    task.cancel()
    task.cancel()
    cleanup_release.set()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, timeout=5)

    assert len(bridge.requests) == len(resolver.calls) == 1
    request = bridge.requests[0]
    assert request.execution_id is not None
    paths = build_run_paths(
        tmp_path / "runtime",
        request.platform,
        request.account_id,
        request.execution_id,
    )
    assert (paths.job_root / "private-sentinel.tmp").read_text(encoding="utf-8") == "attempt-secret"
    account_block, incident = attempt_cleanup_incident_paths(paths)
    assert account_block.is_file() and incident.is_file()
    with database.session() as session:
        job = session.scalar(select(Job).where(Job.subscription_id == subscription_id))
        run = session.scalar(select(SyncRun).where(SyncRun.subscription_id == subscription_id))
        assert job is not None and job.status == "running" and job.last_error_code is None
        assert run is not None and run.status == "running" and run.error_code is None

    clock.value += timedelta(seconds=61)
    replacement = await worker.run_once(worker_id="cleanup-race-recovery")

    assert (replacement.status, replacement.error_code) == ("fenced", None)
    assert len(bridge.requests) == len(resolver.calls) == 1
    with database.session() as session:
        runs = list(session.scalars(select(SyncRun).where(SyncRun.subscription_id == subscription_id)).all())
        job = session.scalar(select(Job).where(Job.subscription_id == subscription_id))
        assert len(runs) == 1
        assert job is not None and job.status == "running" and job.attempts == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("recovery_stage", ["missing_receipt", "rejected_manifest"])
async def test_repeated_cancellation_during_untrusted_recovery_records_block(
    database: Database,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    recovery_stage: str,
) -> None:
    account_id = uuid4()
    subscription_id = uuid4()
    job_id = uuid4()
    run_id = uuid4()
    execution_id = uuid5(job_id, "media-sync/mediacrawler/attempt/1")
    context = SubscriptionJobContext(
        job_id=job_id,
        subscription_id=subscription_id,
        account=AccountRef(
            account_id=account_id,
            platform=Platform.XHS,
            login_method=LoginMethod.COOKIE,
            adapter="mediacrawler",
            credential_ref="env:MEDIACRAWLER_TEST_COOKIE",
        ),
        creator_reference="creator-001",
        subscription_policy={
            "mediacrawler": MediaCrawlerSubscriptionPolicy(
                allow_full_history=True,
                request_delay_seconds=3.5,
                headless=True,
            ).to_payload()
        },
        schedule_revision=1,
        attempt=2,
        current_run_id=run_id,
        ownership_guard=lambda _session: None,
        run_attacher=lambda _session, _run_id, _expected: None,
    )
    scope = mediacrawler_handler_module._ScopeSnapshot(
        checkpoint_revision=0,
        cursor=None,
        creator_remote_id="creator-001",
        creator_display_name="Fixture creator xhs",
        current_run_status="running",
        current_run_manifest={
            "schema_version": 1,
            "adapter": "mediacrawler",
            "scheduler_job_id": str(job_id),
            "schedule_revision": 1,
            "attempt": 1,
            "execution_id": str(execution_id),
            "sync_run_id": str(run_id),
            "platform": "xhs",
            "mode": "forward",
            "crawl_revision_before": 0,
        },
        current_run_attempt=1,
        current_run_checkpoint_revision_before=0,
    )
    paths = build_run_paths(tmp_path / "runtime", Platform.XHS, account_id, execution_id)
    paths.integration_root.mkdir(parents=True)
    (paths.integration_root / "jobs").mkdir()
    paths.job_root.mkdir()
    paths.output_root.mkdir()
    (paths.output_root / "unsealed-private.tmp").write_text("recovery-secret", encoding="utf-8")
    receipt_path = paths.job_root / "completion-receipt.json"
    decision_entered = Event()
    decision_release = Event()
    original_is_file = Path.is_file
    manifest_loader: Callable[[Path], RunnerManifest] = RunnerManifest.load

    def blocking_missing_receipt(path: Path) -> bool:
        if path == receipt_path:
            decision_entered.set()
            assert decision_release.wait(timeout=5)
            return False
        return original_is_file(path)

    if recovery_stage == "missing_receipt":
        monkeypatch.setattr(Path, "is_file", blocking_missing_receipt)
    else:
        receipt_path.write_text('{"sealed":"fixture"}\n', encoding="utf-8")

        def blocking_rejected_manifest(_path: Path) -> RunnerManifest:
            decision_entered.set()
            assert decision_release.wait(timeout=5)
            raise ValueError("fixed rejected manifest")

        manifest_loader = blocking_rejected_manifest
    monkeypatch.setattr(
        mediacrawler_handler_module,
        "_cleanup_exact_attempt",
        lambda _paths: AttemptCleanupStatus.UNRESOLVED,
    )
    bridge = _Bridge(AssertionError("blocked recovery must not prepare a successor"))
    runner = _Runner()
    handler = _handler(
        database,
        tmp_path,
        bridge=bridge,
        runner=runner,
        manifest_loader=manifest_loader,
    )
    policy = MediaCrawlerSubscriptionPolicy(
        allow_full_history=True,
        request_delay_seconds=3.5,
        headless=True,
    )
    task = asyncio.create_task(
        handler._recover_sealed_output(
            context,
            scope,
            creator_reference="creator-001",
            policy=policy,
        )
    )
    assert await asyncio.to_thread(decision_entered.wait, 5)

    task.cancel()
    task.cancel()
    decision_release.set()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, timeout=5)

    assert (paths.output_root / "unsealed-private.tmp").read_text(encoding="utf-8") == "recovery-secret"
    account_block, incident = attempt_cleanup_incident_paths(paths)
    assert account_block.is_file() and incident.is_file()
    assert not bridge.requests and not runner.calls


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "recovery_case",
    ["valid", "policy_mismatch", "attempt_mismatch", "checkpoint_mismatch", "receipt_missing"],
)
async def test_prior_attempt_recovery_is_policy_bound_and_cleans_untrusted_roots(
    database: Database,
    tmp_path: Path,
    recovery_case: str,
) -> None:
    subscription_id = _seed(database, platform=Platform.XHS)
    previous_attempt = 2 if recovery_case == "attempt_mismatch" else 1
    checkpoint_before = 7 if recovery_case == "checkpoint_mismatch" else 0
    scheduler = DurableSchedulerService(database, clock=_Clock())
    scheduler.tick(limit=1)
    with database.session() as session:
        repository = SchedulerRepository(session)
        first = repository.claim_next(
            worker_id="crashed-worker",
            global_capacity=1,
            lease_seconds=1,
            now=NOW,
        )
        assert first is not None
        first = repository.start(
            first.job_id,
            worker_id="crashed-worker",
            lease_token=first.lease_token,
            now=NOW,
        )
        job = session.get(Job, first.job_id)
        subscription = session.get(Subscription, subscription_id)
        assert job is not None and subscription is not None
        job.attempts = previous_attempt
        subscription.checkpoint_revision = checkpoint_before
        session.flush()
        first_run_id = uuid4()
        first_execution_id = uuid5(
            UUID(first.job_id),
            f"media-sync/mediacrawler/attempt/{previous_attempt}",
        )
        runs = SyncRunRepository(session)
        run = runs.create(
            subscription_id=subscription_id,
            run_id=str(first_run_id),
            attempt=previous_attempt,
            checkpoint_revision_before=checkpoint_before,
            manifest={
                "schema_version": 1,
                "adapter": "mediacrawler",
                "scheduler_job_id": first.job_id,
                "schedule_revision": first.schedule_revision,
                "attempt": previous_attempt,
                "execution_id": str(first_execution_id),
                "sync_run_id": str(first_run_id),
                "platform": "xhs",
                "mode": "forward",
                "crawl_revision_before": checkpoint_before,
            },
        )
        runs.set_status(run.id, "claimed", expected_status="queued", at=NOW)
        runs.set_status(run.id, "running", expected_status="claimed", at=NOW)
        repository.attach_run(
            first.job_id,
            worker_id="crashed-worker",
            lease_token=first.lease_token,
            run_id=run.id,
            expected_current_run_id=None,
            now=NOW,
        )
        job_id = first.job_id

    replacement_time = NOW + timedelta(seconds=5)
    with database.session() as session:
        repository = SchedulerRepository(session)
        replacement = repository.claim_next(
            worker_id="recovery-worker",
            global_capacity=1,
            lease_seconds=60,
            now=replacement_time,
        )
        assert replacement is not None and replacement.attempt == previous_attempt + 1
        replacement = repository.start(
            replacement.job_id,
            worker_id="recovery-worker",
            lease_token=replacement.lease_token,
            now=replacement_time,
        )

    worker = SubscriptionWorker(
        database,
        SubscriptionHandlerRegistry({}),
        clock=_Clock(replacement_time),
    )
    context, handler_key = worker._load_context(replacement, worker_id="recovery-worker")
    assert context is not None and handler_key == "mediacrawler"

    runtime_root = (tmp_path / "runtime").resolve()
    receipt_path = runtime_root / "jobs" / str(first_execution_id) / "completion-receipt.json"
    receipt_path.parent.mkdir(parents=True)
    receipt_bytes = b'{"sealed":"unchanged"}\n'
    if recovery_case == "receipt_missing":
        (receipt_path.parent / "unsealed-private.tmp").write_text("attempt-secret", encoding="utf-8")
    else:
        receipt_path.write_bytes(receipt_bytes)
    creator_fingerprint = hashlib.sha256(b"creator-001").hexdigest()
    recovered_manifest = cast(
        RunnerManifest,
        SimpleNamespace(
            schema_version=MANIFEST_SCHEMA_VERSION,
            account_id=context.account.account_id,
            subscription_id=context.subscription_id,
            scheduler_job_id=context.job_id,
            schedule_revision=context.schedule_revision,
            attempt=1 if recovery_case == "attempt_mismatch" else previous_attempt,
            execution_id=first_execution_id,
            sync_run_id=first_run_id,
            checkpoint_revision_before=3 if recovery_case == "checkpoint_mismatch" else checkpoint_before,
            intended_mode=MediaCrawlerRunMode.FORWARD,
            platform=Platform.XHS,
            login_method=LoginMethod.COOKIE,
            max_items=30,
            allow_full_history=True,
            headless=True,
            request_delay_seconds=9.5 if recovery_case == "policy_mismatch" else 3.5,
            watchdogs=WatchdogLimits(),
            integration_root=runtime_root,
            lock_path=(tmp_path / "fixture-lock.json").resolve(),
            license_acknowledged=True,
            author_remote_id_fingerprint_sha256=creator_fingerprint,
            creator_fingerprint_sha256=creator_fingerprint,
            upstream_sha=PINNED_SHA,
        ),
    )
    loaded_paths: list[Path] = []

    def load_manifest(path: Path) -> RunnerManifest:
        loaded_paths.append(path)
        return recovered_manifest

    checkout_verifications: list[RunnerManifest] = []

    def verify_checkout(manifest: RunnerManifest) -> object:
        checkout_verifications.append(manifest)
        return object()

    bridge = (
        _Bridge()
        if recovery_case == "receipt_missing"
        else _Bridge(AssertionError("sealed recovery must not prepare a new child"))
    )
    runner = _Runner()
    handler = _handler(
        database,
        tmp_path,
        bridge=bridge,
        runner=runner,
        clock=_Clock(replacement_time),
        manifest_loader=load_manifest,
        checkout_verifier=verify_checkout,
    )
    result = await handler.run(context)

    assert result.run_id is not None and result.run_id != first_run_id
    if recovery_case == "valid":
        assert result.succeeded is True
        assert not bridge.requests and not runner.calls
        assert not receipt_path.parent.exists() and not receipt_path.parent.is_symlink()
        assert loaded_paths == [receipt_path.parent / "runner-manifest.json"]
        assert checkout_verifications == [recovered_manifest]
    elif recovery_case in {"policy_mismatch", "attempt_mismatch", "checkpoint_mismatch"}:
        assert (result.succeeded, result.error_code) == (False, "output_security_failed")
        assert not receipt_path.parent.exists()
        assert not bridge.requests and not runner.calls
        assert loaded_paths == [receipt_path.parent / "runner-manifest.json"]
        assert not checkout_verifications
    else:
        assert result.succeeded is True
        assert not receipt_path.parent.exists()
        assert len(bridge.requests) == 1 and len(runner.calls) == 1
        assert not loaded_paths and not checkout_verifications
    with database.session() as session:
        job = session.get(Job, job_id)
        old_run = session.get(SyncRun, str(first_run_id))
        new_run = session.get(SyncRun, str(result.run_id))
        assert job is not None and job.run_id == str(result.run_id)
        assert old_run is not None and old_run.status == "cancelled"
        assert old_run.error_code == "scheduler_lease_lost"
        assert new_run is not None
        if recovery_case == "valid":
            assert new_run.status == "succeeded"
            assert new_run.manifest["recovered_artifact"] == {
                "schema_version": MANIFEST_SCHEMA_VERSION,
                "attempt": 1,
                "execution_id": str(first_execution_id),
                "sync_run_id": str(first_run_id),
            }
            assert session.scalar(select(func.count()).select_from(Content)) >= 1
        elif recovery_case in {"policy_mismatch", "attempt_mismatch", "checkpoint_mismatch"}:
            assert new_run.status == "failed_terminal"
            assert new_run.error_code == "output_security_failed"
            assert session.scalar(select(func.count()).select_from(Content)) == 0
        else:
            assert new_run.status == "succeeded"
            assert "recovered_artifact" not in new_run.manifest
            assert session.scalar(select(func.count()).select_from(Content)) >= 1


def test_handler_context_fixture_remains_secret_free() -> None:
    context = SubscriptionJobContext(
        job_id=uuid4(),
        subscription_id=uuid4(),
        account=AccountRef(
            account_id=uuid4(),
            platform=Platform.BILI,
            login_method=LoginMethod.COOKIE,
            adapter="mediacrawler",
            credential_ref="env:MEDIACRAWLER_TEST_COOKIE",
        ),
        creator_reference="creator-001",
        subscription_policy={
            "mediacrawler": MediaCrawlerSubscriptionPolicy(
                allow_full_history=True,
                request_delay_seconds=3.5,
                headless=True,
            ).to_payload()
        },
        ownership_guard=lambda _session: None,
        run_attacher=lambda _session, _run_id, _expected: None,
    )

    assert "fixture-cookie-value" not in repr(context)
    assert "MEDIACRAWLER_TEST_COOKIE" not in repr(context)
