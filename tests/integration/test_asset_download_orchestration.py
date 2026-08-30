from __future__ import annotations

import hashlib
from collections.abc import Callable, Iterator, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Event
from uuid import UUID

import httpx
import pytest

from media_sync.application.downloads import (
    ASSET_DOWNLOAD_JOB_TYPE,
    AssetDownloadOrchestrationError,
    AssetDownloadRequest,
    AssetDownloadService,
    asset_download_natural_key,
)
from media_sync.domain import AssetStatus
from media_sync.infrastructure.db import (
    AssetRepository,
    AssetUpsert,
    AuthorRepository,
    AuthorUpsert,
    ContentUpsert,
    Database,
    JobRepository,
)
from media_sync.media import (
    ArchivePublisher,
    MediaDownloadError,
    MediaProbe,
    ProbeResult,
    SafeHttpClient,
    SecureMediaDownloader,
    ValidatedTarget,
)

PNG = b"\x89PNG\r\n\x1a\n" + b"offline-application-download"
MP4 = b"\x00\x00\x00\x18ftypisom" + b"offline-application-video"
ETAG = '"application-v1"'
STARTED_AT = datetime(2026, 8, 30, 6, tzinfo=UTC)


class _Resolver:
    def resolve(self, _hostname: str, _port: int) -> Sequence[str]:
        return ("8.8.8.8",)


class _BreakingStream(httpx.SyncByteStream):
    def __init__(self, prefix: bytes, detail: str = "offline transport failure") -> None:
        self.prefix = prefix
        self.detail = detail

    def __iter__(self) -> Iterator[bytes]:
        yield self.prefix
        raise httpx.ReadError(self.detail)


@dataclass
class _MutableClock:
    current: datetime

    def __call__(self) -> datetime:
        return self.current


@dataclass
class _SequenceClock:
    values: tuple[datetime, ...]
    index: int = 0

    def __call__(self) -> datetime:
        if self.index >= len(self.values):
            raise AssertionError("clock was called more times than expected")
        value = self.values[self.index]
        self.index += 1
        return value


@pytest.fixture
def database(tmp_path: Path) -> Iterator[Database]:
    path = tmp_path / "downloads.sqlite3"
    instance = Database(f"sqlite+pysqlite:///{path.as_posix()}")
    instance.create_schema()
    try:
        yield instance
    finally:
        instance.dispose()


def _seed_asset(
    database: Database,
    *,
    url: str = "https://media.test/original",
    kind: str = "image",
) -> UUID:
    with database.session() as session:
        _author, contents = AuthorRepository(session).upsert_with_contents(
            AuthorUpsert(platform="xhs", remote_id="download-author", display_name="Download Author"),
            [ContentUpsert(remote_id="download-content", kind=kind, title="Offline fixture")],
        )
        asset = AssetRepository(session).upsert_for_content(
            contents[0].id,
            AssetUpsert(
                platform="xhs",
                remote_id="download-image-v1",
                kind=kind,
                position=0,
                source_url=url,
            ),
        )
        return UUID(asset.id)


def _downloader(
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    probe: MediaProbe | None = None,
) -> SecureMediaDownloader:
    def factory(_target: ValidatedTarget) -> httpx.BaseTransport:
        return httpx.MockTransport(handler)

    return SecureMediaDownloader(SafeHttpClient(_Resolver(), transport_factory=factory), probe=probe)


class _VideoProbe:
    def probe(
        self,
        _path: Path,
        *,
        timeout_seconds: float,
        max_output_bytes: int,
    ) -> ProbeResult:
        assert timeout_seconds > 0
        assert max_output_bytes > 0
        return ProbeResult("video/mp4", "mp4")


def _request(
    tmp_path: Path,
    asset_id: UUID,
    *,
    worker_id: str = "download-worker",
    lease_seconds: int = 60,
    max_attempts: int = 5,
) -> AssetDownloadRequest:
    return AssetDownloadRequest(
        asset_id=asset_id,
        worker_id=worker_id,
        work_root=tmp_path / "work",
        archive_root=tmp_path / "archive",
        lease_seconds=lease_seconds,
        max_attempts=max_attempts,
    )


def _job_payload(request: AssetDownloadRequest, generation: int) -> dict[str, object]:
    return {
        "asset_id": str(request.asset_id),
        "generation": generation,
        "io_scope_fingerprint": request.io_scope_fingerprint,
    }


def _replace_expired_download_token(database: Database, asset_id: UUID, *, at: datetime) -> str:
    """Simulate a real reclaim/claim/start sequence outside orchestration locking."""

    with database.session() as session:
        assets = AssetRepository(session)
        jobs = JobRepository(session)
        asset = assets.require(str(asset_id))
        job = jobs.get_by_key(
            ASSET_DOWNLOAD_JOB_TYPE,
            asset_download_natural_key(asset_id, asset.generation),
        )
        assert job is not None
        assert jobs.reclaim_expired(job_id=job.id, now=at) == 1
        failed = assets.recover_expired_download(
            asset.id,
            expected_generation=asset.generation,
            expected_status=asset.status,
            job_id=job.id,
            at=at,
        )
        queued = assets.queue(
            failed.id,
            expected_generation=failed.generation,
            expected_status=failed.status,
            at=at,
        )
        claimed = jobs.claim(job.id, worker_id="replacement-worker", lease_seconds=60, now=at)
        assert claimed is not None and claimed.lease_token is not None
        running = jobs.start(
            job.id,
            worker_id="replacement-worker",
            lease_token=claimed.lease_token,
            now=at,
        )
        assets.start(
            queued.id,
            expected_generation=queued.generation,
            expected_status=queued.status,
            job_id=running.id,
            worker_id="replacement-worker",
            lease_token=claimed.lease_token,
            at=at,
        )
        return claimed.lease_token


def _ok_response(content: bytes = PNG) -> httpx.Response:
    return httpx.Response(
        200,
        headers={
            "Content-Length": str(len(content)),
            "Content-Type": "application/octet-stream",
            "ETag": ETAG,
        },
        content=content,
    )


def test_seed_to_download_is_atomic_and_already_verified_is_idempotent(
    database: Database,
    tmp_path: Path,
) -> None:
    asset_id = _seed_asset(database)
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return _ok_response()

    service = AssetDownloadService(database, _downloader(handler), clock=lambda: STARTED_AT)
    request = _request(tmp_path, asset_id)

    downloaded = service.run(request)
    repeated = service.run(request)
    with pytest.raises(AssetDownloadOrchestrationError) as mismatched_replay:
        service.run(_request(tmp_path / "other-scope", asset_id))

    assert downloaded.disposition == "downloaded"
    assert repeated.disposition == "already_verified"
    assert mismatched_replay.value.code == "asset_download_io_scope_mismatch"
    assert repeated == downloaded.__class__(
        asset_id=downloaded.asset_id,
        generation=downloaded.generation,
        job_id=downloaded.job_id,
        status=downloaded.status,
        disposition="already_verified",
        archive_path=downloaded.archive_path,
        checksum_sha256=downloaded.checksum_sha256,
        size_bytes=downloaded.size_bytes,
        mime_type=downloaded.mime_type,
    )
    assert calls == 1
    assert downloaded.archive_path.read_bytes() == PNG

    with database.session() as session:
        asset = AssetRepository(session).require(str(asset_id))
        job = JobRepository(session).get_by_key(
            ASSET_DOWNLOAD_JOB_TYPE,
            asset_download_natural_key(asset_id, 1),
        )
        assert asset.status == "verified"
        assert asset.download_job_id == (job.id if job is not None else None)
        assert asset.local_path == str(downloaded.archive_path.absolute())
        assert asset.checksum_sha256 == downloaded.checksum_sha256
        assert job is not None
        assert job.status == "succeeded"
        assert job.attempts == 1
        assert job.payload == _job_payload(request, 1)
        assert str(request.work_root) not in repr(job.payload)
        assert str(request.archive_root) not in repr(job.payload)


def test_cleanup_failure_keeps_verified_commit_and_replay_retries_cleanup(
    database: Database,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asset_id = _seed_asset(database)
    network_calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal network_calls
        network_calls += 1
        return _ok_response()

    downloader = _downloader(handler)
    real_cleanup = downloader.cleanup_partial
    cleanup_calls = 0

    def flaky_cleanup(cleanup_asset_id: UUID, generation: int, work_root: Path) -> None:
        nonlocal cleanup_calls
        cleanup_calls += 1
        if cleanup_calls == 1:
            raise MediaDownloadError("filesystem_write_failed")
        real_cleanup(cleanup_asset_id, generation, work_root)

    monkeypatch.setattr(downloader, "cleanup_partial", flaky_cleanup)
    service = AssetDownloadService(database, downloader, clock=lambda: STARTED_AT)
    request = _request(tmp_path, asset_id)

    downloaded = service.run(request)
    part = tmp_path / "work" / "parts" / f"{asset_id}.1.part"
    assert downloaded.disposition == "downloaded"
    assert part.read_bytes() == PNG
    with database.session() as session:
        assert AssetRepository(session).require(str(asset_id)).status == "verified"

    replayed = service.run(request)

    assert replayed.disposition == "already_verified"
    assert cleanup_calls == 2
    assert network_calls == 1
    assert not tuple((tmp_path / "work" / "parts").iterdir())


def test_final_attempt_commits_read_only_blob_without_post_link_chmod(
    database: Database,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asset_id = _seed_asset(database)
    real_chmod = Path.chmod
    canonical_chmod_calls = 0

    def reject_canonical_chmod(path: Path, mode: int, *args: object, **kwargs: object) -> None:
        nonlocal canonical_chmod_calls
        if path.parent.parent.name == "sha256" and not path.name.startswith("."):
            canonical_chmod_calls += 1
            raise OSError("post-link chmod must never be required")
        real_chmod(path, mode, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Path, "chmod", reject_canonical_chmod)
    outcome = AssetDownloadService(
        database,
        _downloader(lambda _request: _ok_response()),
        clock=lambda: STARTED_AT,
    ).run(_request(tmp_path, asset_id, max_attempts=1))

    assert outcome.archive_path.read_bytes() == PNG
    assert outcome.archive_path.stat().st_mode & 0o222 == 0
    assert canonical_chmod_calls == 0
    with database.session() as session:
        job = JobRepository(session).get_by_key(
            ASSET_DOWNLOAD_JOB_TYPE,
            asset_download_natural_key(asset_id, 1),
        )
        assert AssetRepository(session).require(str(asset_id)).status == "verified"
        assert job is not None
        assert job.status == "succeeded"
        assert job.attempts == job.max_attempts == 1


@pytest.mark.parametrize("cleanup_failure", ["chmod", "unlink"])
def test_existing_winner_cleanup_failure_cannot_reverse_final_attempt_success(
    database: Database,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    cleanup_failure: str,
) -> None:
    asset_id = _seed_asset(database)
    digest = hashlib.sha256(PNG).hexdigest()
    canonical = tmp_path / "archive" / "sha256" / digest[:2] / f"{digest}.png"
    real_make_read_only = ArchivePublisher._make_read_only
    real_chmod = Path.chmod
    real_unlink = Path.unlink
    winner_installed = False
    cleanup_failures = 0
    network_calls = 0

    def install_winner_after_temporary_is_ready(publisher: ArchivePublisher, path: Path) -> None:
        nonlocal winner_installed
        real_make_read_only(publisher, path)
        if not winner_installed and path.name.startswith(".") and path.name.endswith(".tmp"):
            canonical.write_bytes(PNG)
            real_chmod(canonical, 0o444)
            winner_installed = True

    def fail_orphan_chmod(path: Path, mode: int, *args: object, **kwargs: object) -> None:
        nonlocal cleanup_failures
        if cleanup_failure == "chmod" and _is_orphan(path) and mode == 0o600 and cleanup_failures == 0:
            cleanup_failures += 1
            raise OSError("injected Windows read-only cleanup chmod failure")
        real_chmod(path, mode, *args, **kwargs)  # type: ignore[arg-type]

    def fail_orphan_unlink(path: Path, *args: object, **kwargs: object) -> None:
        nonlocal cleanup_failures
        if cleanup_failure == "unlink" and _is_orphan(path) and cleanup_failures == 0:
            cleanup_failures += 1
            raise OSError("injected Windows temporary unlink failure")
        real_unlink(path, *args, **kwargs)  # type: ignore[arg-type]

    def _is_orphan(path: Path) -> bool:
        return (
            path.parent == canonical.parent
            and path.name.startswith(f".{canonical.name}.")
            and path.name.endswith(".tmp")
        )

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal network_calls
        network_calls += 1
        return _ok_response()

    monkeypatch.setattr(ArchivePublisher, "_make_read_only", install_winner_after_temporary_is_ready)
    monkeypatch.setattr(Path, "chmod", fail_orphan_chmod)
    monkeypatch.setattr(Path, "unlink", fail_orphan_unlink)
    request = _request(tmp_path, asset_id, max_attempts=1)
    service = AssetDownloadService(database, _downloader(handler), clock=lambda: STARTED_AT)

    downloaded = service.run(request)
    replayed = service.run(request)

    assert downloaded.disposition == "downloaded"
    assert replayed.disposition == "already_verified"
    assert downloaded.archive_path == replayed.archive_path == canonical
    assert canonical.read_bytes() == PNG
    assert canonical.stat().st_mode & 0o222 == 0
    assert cleanup_failures == 1
    assert network_calls == 1
    orphans = tuple(
        path
        for path in canonical.parent.iterdir()
        if path.name.startswith(f".{canonical.name}.") and path.name.endswith(".tmp")
    )
    assert len(orphans) == 1
    with database.session() as session:
        asset = AssetRepository(session).require(str(asset_id))
        job = JobRepository(session).get_by_key(
            ASSET_DOWNLOAD_JOB_TYPE,
            asset_download_natural_key(asset_id, 1),
        )
        assert asset.status == "verified"
        assert asset.local_path == str(canonical.absolute())
        assert asset.checksum_sha256 == digest
        assert job is not None
        assert job.status == "succeeded"
        assert job.attempts == job.max_attempts == 1

    for orphan in orphans:
        real_chmod(orphan, 0o600)
        real_unlink(orphan)


@pytest.mark.parametrize(
    ("mutation", "expected_code", "expected_retryable"),
    [
        ("delete", "archive_blob_missing", True),
        ("replace", "archive_blob_invalid", False),
    ],
)
def test_already_verified_shortcut_revalidates_and_fences_invalid_archive_generation(
    database: Database,
    tmp_path: Path,
    mutation: str,
    expected_code: str,
    expected_retryable: bool,
) -> None:
    asset_id = _seed_asset(database)
    first = AssetDownloadService(
        database,
        _downloader(lambda _request: _ok_response()),
        clock=lambda: STARTED_AT,
    ).run(_request(tmp_path, asset_id))
    if mutation == "delete":
        first.archive_path.chmod(0o600)
        first.archive_path.unlink()
    else:
        first.archive_path.chmod(0o600)
        first.archive_path.write_bytes(b"X" * first.size_bytes)

    network_calls = 0

    def forbidden_network(_request: httpx.Request) -> httpx.Response:
        nonlocal network_calls
        network_calls += 1
        raise AssertionError("verified archive revalidation must not contact the network")

    with pytest.raises(AssetDownloadOrchestrationError) as invalid:
        AssetDownloadService(
            database,
            _downloader(forbidden_network),
            clock=lambda: STARTED_AT,
        ).run(_request(tmp_path, asset_id))

    assert invalid.value.code == expected_code
    assert invalid.value.retryable is expected_retryable
    assert network_calls == 0
    with database.session() as session:
        asset = AssetRepository(session).require(str(asset_id))
        job = JobRepository(session).get_by_key(
            ASSET_DOWNLOAD_JOB_TYPE,
            asset_download_natural_key(asset_id, 1),
        )
        assert asset.status == "discovered"
        assert asset.generation == 2
        assert asset.local_path is None
        assert asset.checksum_sha256 is None
        assert asset.last_error_code == expected_code
        assert job is not None and job.status == "succeeded" and job.attempts == 1


def test_corrupt_archive_is_quarantined_then_same_hash_redownload_recovers(
    database: Database,
    tmp_path: Path,
) -> None:
    asset_id = _seed_asset(database)
    network_calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal network_calls
        network_calls += 1
        return _ok_response()

    request = _request(tmp_path, asset_id)
    service = AssetDownloadService(database, _downloader(handler), clock=lambda: STARTED_AT)
    first = service.run(request)
    first.archive_path.chmod(0o600)
    corrupt_bytes = b"X" * first.size_bytes
    first.archive_path.write_bytes(corrupt_bytes)

    with pytest.raises(AssetDownloadOrchestrationError) as invalid:
        service.run(request)

    assert invalid.value.code == "archive_blob_invalid"
    assert not first.archive_path.exists()
    quarantined = tuple(
        path for path in (tmp_path / "archive" / ".quarantine" / "sha256").rglob("*.corrupt") if path.is_file()
    )
    assert len(quarantined) == 1
    assert quarantined[0].read_bytes() == corrupt_bytes

    recovered = service.run(request)

    assert recovered.generation == 2
    assert recovered.archive_path == first.archive_path
    assert recovered.archive_path.read_bytes() == PNG
    assert quarantined[0].read_bytes() == corrupt_bytes
    assert network_calls == 2
    with database.session() as session:
        asset = AssetRepository(session).require(str(asset_id))
        second_job = JobRepository(session).get_by_key(
            ASSET_DOWNLOAD_JOB_TYPE,
            asset_download_natural_key(asset_id, 2),
        )
        assert asset.status == "verified"
        assert asset.generation == 2
        assert second_job is not None
        assert second_job.status == "succeeded"
        assert second_job.attempts == 1


def test_missing_structural_probe_is_retryable_and_can_recover_without_generation_reset(
    database: Database,
    tmp_path: Path,
) -> None:
    asset_id = _seed_asset(database, kind="video")
    request = _request(tmp_path, asset_id, max_attempts=2)

    with pytest.raises(AssetDownloadOrchestrationError) as unavailable:
        AssetDownloadService(
            database,
            _downloader(lambda _request: _ok_response(MP4)),
            clock=lambda: STARTED_AT,
        ).run(request)

    assert unavailable.value.code == "media_probe_unavailable"
    assert unavailable.value.retryable is True
    with database.session() as session:
        asset = AssetRepository(session).require(str(asset_id))
        job = JobRepository(session).get_by_key(
            ASSET_DOWNLOAD_JOB_TYPE,
            asset_download_natural_key(asset_id, 1),
        )
        assert asset.status == "failed_retryable"
        assert asset.generation == 1
        assert job is not None and job.status == "failed_retryable"

    recovered = AssetDownloadService(
        database,
        _downloader(lambda _request: _ok_response(MP4), probe=_VideoProbe()),
        clock=lambda: STARTED_AT,
    ).run(request)

    assert recovered.status is AssetStatus.VERIFIED
    assert recovered.generation == 1
    assert recovered.mime_type == "video/mp4"


def test_network_phase_holds_no_database_transaction(database: Database, tmp_path: Path) -> None:
    asset_id = _seed_asset(database)

    def handler(_request: httpx.Request) -> httpx.Response:
        with database.session() as session:
            unrelated = JobRepository(session).enqueue(
                job_type="offline_probe",
                natural_key="network-phase-independent-write",
                available_at=STARTED_AT,
            )
            assert unrelated.status == "queued"
        return _ok_response()

    outcome = AssetDownloadService(database, _downloader(handler), clock=lambda: STARTED_AT).run(
        _request(tmp_path, asset_id)
    )

    assert outcome.disposition == "downloaded"
    with database.session() as session:
        assert JobRepository(session).get_by_key("offline_probe", "network-phase-independent-write") is not None


def test_active_lease_is_not_stolen_or_sent_to_network(database: Database, tmp_path: Path) -> None:
    asset_id = _seed_asset(database)
    original_request = _request(tmp_path, asset_id)
    with database.session() as session:
        assets = AssetRepository(session)
        asset = assets.require(str(asset_id))
        queued = assets.queue(
            asset.id,
            expected_generation=asset.generation,
            expected_status=asset.status,
            at=STARTED_AT,
        )
        jobs = JobRepository(session)
        job = jobs.enqueue(
            job_type=ASSET_DOWNLOAD_JOB_TYPE,
            natural_key=asset_download_natural_key(asset_id, queued.generation),
            payload=_job_payload(original_request, queued.generation),
            max_attempts=3,
            available_at=STARTED_AT,
        )
        claimed = jobs.claim(job.id, worker_id="active-worker", lease_seconds=60, now=STARTED_AT)
        assert claimed is not None and claimed.lease_token is not None
        jobs.start(job.id, worker_id="active-worker", lease_token=claimed.lease_token, now=STARTED_AT)
        assets.start(
            queued.id,
            expected_generation=queued.generation,
            expected_status=queued.status,
            job_id=job.id,
            worker_id="active-worker",
            lease_token=claimed.lease_token,
            at=STARTED_AT,
        )

    def forbidden_network(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("active leases must not reach the network")

    service = AssetDownloadService(
        database,
        _downloader(forbidden_network),
        clock=lambda: STARTED_AT + timedelta(seconds=1),
    )
    with pytest.raises(AssetDownloadOrchestrationError) as caught:
        service.run(_request(tmp_path, asset_id, worker_id="contender"))

    assert caught.value.code == "asset_download_busy"
    assert caught.value.retryable is True
    with database.session() as session:
        asset = AssetRepository(session).require(str(asset_id))
        job = JobRepository(session).get_by_key(
            ASSET_DOWNLOAD_JOB_TYPE,
            asset_download_natural_key(asset_id, 1),
        )
        assert asset.status == "downloading"
        assert job is not None
        assert job.status == "running"
        assert job.lease_owner == "active-worker"
        assert job.attempts == 1


def test_expired_lease_recovers_asset_and_reuses_generation_bound_job(
    database: Database,
    tmp_path: Path,
) -> None:
    asset_id = _seed_asset(database)
    original_request = _request(tmp_path, asset_id)
    with database.session() as session:
        assets = AssetRepository(session)
        asset = assets.require(str(asset_id))
        queued = assets.queue(
            asset.id,
            expected_generation=asset.generation,
            expected_status=asset.status,
            at=STARTED_AT,
        )
        jobs = JobRepository(session)
        job = jobs.enqueue(
            job_type=ASSET_DOWNLOAD_JOB_TYPE,
            natural_key=asset_download_natural_key(asset_id, queued.generation),
            payload=_job_payload(original_request, queued.generation),
            max_attempts=3,
            available_at=STARTED_AT,
        )
        claimed = jobs.claim(job.id, worker_id="crashed-worker", lease_seconds=1, now=STARTED_AT)
        assert claimed is not None and claimed.lease_token is not None
        jobs.start(job.id, worker_id="crashed-worker", lease_token=claimed.lease_token, now=STARTED_AT)
        assets.start(
            queued.id,
            expected_generation=queued.generation,
            expected_status=queued.status,
            job_id=job.id,
            worker_id="crashed-worker",
            lease_token=claimed.lease_token,
            at=STARTED_AT,
        )
        original_job_id = job.id

    recovered_at = STARTED_AT + timedelta(seconds=2)
    service = AssetDownloadService(
        database,
        _downloader(lambda _request: _ok_response()),
        clock=lambda: recovered_at,
    )
    outcome = service.run(_request(tmp_path, asset_id, worker_id="recovery-worker"))

    assert outcome.disposition == "downloaded"
    assert outcome.generation == 1
    assert outcome.job_id == UUID(original_job_id)
    with database.session() as session:
        asset = AssetRepository(session).require(str(asset_id))
        job = JobRepository(session).get_by_key(
            ASSET_DOWNLOAD_JOB_TYPE,
            asset_download_natural_key(asset_id, 1),
        )
        assert asset.status == "verified"
        assert asset.last_error_code is None
        assert job is not None
        assert job.id == original_job_id
        assert job.status == "succeeded"
        assert job.attempts == 2
        assert job.lease_owner is None


def test_orchestration_lock_and_publish_guard_protect_expired_live_worker(
    database: Database,
    tmp_path: Path,
) -> None:
    asset_id = _seed_asset(database)
    stale_entered_network = Event()
    release_stale_worker = Event()
    stale_clock = _MutableClock(STARTED_AT)

    def stale_handler(_request: httpx.Request) -> httpx.Response:
        stale_entered_network.set()
        if not release_stale_worker.wait(timeout=10):
            raise AssertionError("test did not release stale worker")
        return _ok_response()

    stale_service = AssetDownloadService(database, _downloader(stale_handler), clock=stale_clock)
    stale_request = _request(
        tmp_path,
        asset_id,
        worker_id="stale-worker",
        lease_seconds=1,
        max_attempts=2,
    )

    with ThreadPoolExecutor(max_workers=1) as pool:
        stale_future = pool.submit(stale_service.run, stale_request)
        assert stale_entered_network.wait(timeout=10)
        replacement_at = STARTED_AT + timedelta(seconds=2)

        def forbidden_replacement_network(_request: httpx.Request) -> httpx.Response:
            raise AssertionError("orchestration-lock contention must not reach the network")

        replacement = AssetDownloadService(
            database,
            _downloader(forbidden_replacement_network),
            clock=lambda: replacement_at,
        )
        try:
            with pytest.raises(AssetDownloadOrchestrationError) as busy:
                replacement.run(
                    _request(
                        tmp_path,
                        asset_id,
                        worker_id="replacement-worker",
                        lease_seconds=60,
                        max_attempts=2,
                    )
                )
            assert busy.value.code == "asset_download_busy"
            assert busy.value.retryable is True
            with database.session() as session:
                asset = AssetRepository(session).require(str(asset_id))
                job = JobRepository(session).get_by_key(
                    ASSET_DOWNLOAD_JOB_TYPE,
                    asset_download_natural_key(asset_id, 1),
                )
                assert asset.status == "downloading"
                assert asset.last_error_code is None
                assert job is not None
                assert job.status == "running"
                assert job.attempts == 1
                assert job.max_attempts == 2
                assert job.lease_owner == "stale-worker"
                assert job.last_error_code is None
        finally:
            stale_clock.current = replacement_at
            release_stale_worker.set()

        completed = stale_future.result(timeout=10)

    assert completed.disposition == "downloaded"
    assert completed.generation == 1
    assert completed.archive_path.read_bytes() == PNG
    assert not tuple((tmp_path / "work" / "parts").iterdir())
    with database.session() as session:
        asset = AssetRepository(session).require(str(asset_id))
        job = JobRepository(session).get_by_key(
            ASSET_DOWNLOAD_JOB_TYPE,
            asset_download_natural_key(asset_id, 1),
        )
        assert asset.status == "verified"
        assert asset.generation == 1
        assert job is not None
        assert job.status == "succeeded"
        assert job.attempts == 1
        assert job.max_attempts == 2


def test_different_io_scope_is_rejected_before_reclaim_or_attempt_mutation(
    database: Database,
    tmp_path: Path,
) -> None:
    asset_id = _seed_asset(database)
    stale_entered_network = Event()
    release_stale_worker = Event()
    stale_clock = _MutableClock(STARTED_AT)
    stale_root = tmp_path / "stale"
    replacement_root = tmp_path / "replacement"

    def stale_handler(_request: httpx.Request) -> httpx.Response:
        stale_entered_network.set()
        if not release_stale_worker.wait(timeout=10):
            raise AssertionError("test did not release stale worker")
        return _ok_response()

    stale_request = _request(
        stale_root,
        asset_id,
        worker_id="stale-worker",
        lease_seconds=1,
        max_attempts=2,
    )
    stale_service = AssetDownloadService(database, _downloader(stale_handler), clock=stale_clock)
    with ThreadPoolExecutor(max_workers=1) as pool:
        stale_future = pool.submit(stale_service.run, stale_request)
        assert stale_entered_network.wait(timeout=10)
        replacement_at = STARTED_AT + timedelta(seconds=2)
        replacement_network_calls = 0

        def forbidden_replacement_network(_request: httpx.Request) -> httpx.Response:
            nonlocal replacement_network_calls
            replacement_network_calls += 1
            raise AssertionError("scope mismatch must not reach the network")

        with database.session() as session:
            asset = AssetRepository(session).require(str(asset_id))
            job = JobRepository(session).get_by_key(
                ASSET_DOWNLOAD_JOB_TYPE,
                asset_download_natural_key(asset_id, 1),
            )
            assert job is not None
            asset_before = (asset.status, asset.generation, asset.download_job_id, asset.updated_at)
            job_before = (
                job.status,
                job.attempts,
                job.lease_owner,
                job.lease_token,
                job.lease_expires_at,
                job.updated_at,
            )
        try:
            with pytest.raises(AssetDownloadOrchestrationError) as mismatch:
                AssetDownloadService(
                    database,
                    _downloader(forbidden_replacement_network),
                    clock=lambda: replacement_at,
                ).run(
                    _request(
                        replacement_root,
                        asset_id,
                        worker_id="replacement-worker",
                        lease_seconds=60,
                        max_attempts=2,
                    )
                )
            assert mismatch.value.code == "asset_download_io_scope_mismatch"
            assert mismatch.value.retryable is False
            assert replacement_network_calls == 0
            with database.session() as session:
                asset = AssetRepository(session).require(str(asset_id))
                job = JobRepository(session).get_by_key(
                    ASSET_DOWNLOAD_JOB_TYPE,
                    asset_download_natural_key(asset_id, 1),
                )
                assert job is not None
                assert (asset.status, asset.generation, asset.download_job_id, asset.updated_at) == asset_before
                assert (
                    job.status,
                    job.attempts,
                    job.lease_owner,
                    job.lease_token,
                    job.lease_expires_at,
                    job.updated_at,
                ) == job_before
        finally:
            stale_clock.current = replacement_at
            release_stale_worker.set()

        completed = stale_future.result(timeout=10)

    assert completed.disposition == "downloaded"
    assert completed.archive_path.read_bytes() == PNG
    assert tuple((stale_root / "archive" / "sha256").glob("*/*"))
    assert not tuple((replacement_root / "archive").rglob("*"))
    with database.session() as session:
        asset = AssetRepository(session).require(str(asset_id))
        job = JobRepository(session).get_by_key(
            ASSET_DOWNLOAD_JOB_TYPE,
            asset_download_natural_key(asset_id, 1),
        )
        assert asset.status == "verified"
        assert asset.local_path == str(completed.archive_path.absolute())
        assert job is not None
        assert job.status == "succeeded"
        assert job.attempts == 1
        assert job.lease_owner is None
        assert job.payload == _job_payload(stale_request, 1)


def test_retryable_media_error_on_last_attempt_atomically_terminalizes_asset_and_job(
    database: Database,
    tmp_path: Path,
) -> None:
    asset_id = _seed_asset(database)
    service = AssetDownloadService(
        database,
        _downloader(lambda _request: httpx.Response(503)),
        clock=lambda: STARTED_AT,
    )

    with pytest.raises(AssetDownloadOrchestrationError) as caught:
        service.run(_request(tmp_path, asset_id, max_attempts=1))

    assert caught.value.code == "download_http_retryable"
    assert caught.value.retryable is False
    with database.session() as session:
        asset = AssetRepository(session).require(str(asset_id))
        job = JobRepository(session).get_by_key(
            ASSET_DOWNLOAD_JOB_TYPE,
            asset_download_natural_key(asset_id, 1),
        )
        assert asset.status == "failed_terminal"
        assert asset.last_error_code == "download_http_retryable"
        assert job is not None
        assert job.status == "failed_terminal"
        assert job.attempts == job.max_attempts == 1
        assert job.last_error_code == "download_http_retryable"


def test_unexpected_worker_error_on_last_attempt_is_fixed_and_terminal(
    database: Database,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asset_id = _seed_asset(database)
    sentinel = "sentinel-raw-worker-detail"
    downloader = _downloader(lambda _request: _ok_response())

    def explode(_request: object) -> object:
        raise RuntimeError(sentinel)

    monkeypatch.setattr(downloader, "download", explode)
    service = AssetDownloadService(database, downloader, clock=lambda: STARTED_AT)

    with pytest.raises(AssetDownloadOrchestrationError) as caught:
        service.run(_request(tmp_path, asset_id, max_attempts=1))

    assert caught.value.code == "asset_download_worker_failed"
    assert caught.value.retryable is False
    assert sentinel not in str(caught.value)
    with database.session() as session:
        asset = AssetRepository(session).require(str(asset_id))
        job = JobRepository(session).get_by_key(
            ASSET_DOWNLOAD_JOB_TYPE,
            asset_download_natural_key(asset_id, 1),
        )
        assert asset.status == "failed_terminal"
        assert asset.last_error_code == "asset_download_worker_failed"
        assert asset.last_error_message == "asset download worker failed unexpectedly"
        assert job is not None
        assert job.status == "failed_terminal"
        assert sentinel not in repr((asset.last_error_message, job.last_error_message, job.payload))


def test_interrupted_attempt_resumes_same_generation_and_part(database: Database, tmp_path: Path) -> None:
    asset_id = _seed_asset(database)
    split = 12
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(
                200,
                headers={"Content-Length": str(len(PNG)), "ETag": ETAG},
                stream=_BreakingStream(PNG[:split]),
            )
        assert request.headers["range"] == f"bytes={split}-"
        assert request.headers["if-range"] == ETAG
        remainder = PNG[split:]
        return httpx.Response(
            206,
            headers={
                "Content-Length": str(len(remainder)),
                "Content-Range": f"bytes {split}-{len(PNG) - 1}/{len(PNG)}",
                "ETag": ETAG,
            },
            content=remainder,
        )

    service = AssetDownloadService(database, _downloader(handler), clock=lambda: STARTED_AT)
    request = _request(tmp_path, asset_id, max_attempts=2)

    with pytest.raises(AssetDownloadOrchestrationError) as first:
        service.run(request)
    assert first.value.code == "download_interrupted"
    assert first.value.retryable is True
    parts = tmp_path / "work" / "parts"
    assert (parts / f"{asset_id}.1.part").read_bytes() == PNG[:split]

    result = service.run(request)

    assert result.disposition == "downloaded"
    assert result.generation == 1
    assert result.archive_path.read_bytes() == PNG
    assert not tuple(parts.iterdir())
    with database.session() as session:
        asset = AssetRepository(session).require(str(asset_id))
        job = JobRepository(session).get_by_key(
            ASSET_DOWNLOAD_JOB_TYPE,
            asset_download_natural_key(asset_id, 1),
        )
        assert asset.status == "verified"
        assert asset.generation == 1
        assert job is not None
        assert job.status == "succeeded"
        assert job.attempts == 2


def test_expired_unreclaimed_token_renews_during_finalize_on_last_attempt(
    database: Database,
    tmp_path: Path,
) -> None:
    asset_id = _seed_asset(database)
    finalized_at = STARTED_AT + timedelta(seconds=2)
    clock = _SequenceClock((STARTED_AT, STARTED_AT, finalized_at))
    outcome = AssetDownloadService(
        database,
        _downloader(lambda _request: _ok_response()),
        clock=clock,
    ).run(_request(tmp_path, asset_id, lease_seconds=1, max_attempts=1))

    assert clock.index == 3
    assert outcome.disposition == "downloaded"
    assert outcome.archive_path.read_bytes() == PNG
    assert not tuple((tmp_path / "work" / "parts").iterdir())
    with database.session() as session:
        asset = AssetRepository(session).require(str(asset_id))
        job = JobRepository(session).get_by_key(
            ASSET_DOWNLOAD_JOB_TYPE,
            asset_download_natural_key(asset_id, 1),
        )
        assert asset.status == "verified"
        assert asset.local_path == str(outcome.archive_path.absolute())
        assert asset.verified_at == finalized_at
        assert job is not None
        assert job.status == "succeeded"
        assert job.attempts == job.max_attempts == 1
        assert job.finished_at == finalized_at


def test_token_reclaimed_during_existing_blob_validation_fences_stale_worker(
    database: Database,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asset_id = _seed_asset(database)
    source_root = tmp_path / "seed-source"
    source_root.mkdir()
    source = source_root / "fixture.png"
    source.write_bytes(PNG)
    digest = hashlib.sha256(PNG).hexdigest()
    existing = ArchivePublisher(tmp_path / "archive").publish(
        source,
        source_root=source_root,
        sha256=digest,
        size_bytes=len(PNG),
        extension="png",
    )
    original_validate = ArchivePublisher._validate_existing
    replacement_token: str | None = None

    def validate_then_reclaim(
        publisher: ArchivePublisher,
        path: Path,
        *,
        sha256: str,
        size_bytes: int,
    ) -> object:
        nonlocal replacement_token
        archived = original_validate(publisher, path, sha256=sha256, size_bytes=size_bytes)
        assert replacement_token is None
        replacement_token = _replace_expired_download_token(
            database,
            asset_id,
            at=STARTED_AT + timedelta(seconds=2),
        )
        return archived

    monkeypatch.setattr(ArchivePublisher, "_validate_existing", validate_then_reclaim)
    service = AssetDownloadService(
        database,
        _downloader(lambda _request: _ok_response()),
        clock=lambda: STARTED_AT,
    )

    with pytest.raises(AssetDownloadOrchestrationError) as stale:
        service.run(_request(tmp_path, asset_id, worker_id="stale-worker", lease_seconds=1, max_attempts=2))

    assert stale.value.code == "asset_download_lease_lost"
    assert replacement_token is not None
    assert existing.path.read_bytes() == PNG
    assert tuple(path for path in (tmp_path / "archive" / "sha256").rglob("*") if path.is_file()) == (existing.path,)
    assert (tmp_path / "work" / "parts" / f"{asset_id}.1.part").read_bytes() == PNG
    with database.session() as session:
        asset = AssetRepository(session).require(str(asset_id))
        job = JobRepository(session).get_by_key(
            ASSET_DOWNLOAD_JOB_TYPE,
            asset_download_natural_key(asset_id, 1),
        )
        assert asset.status == "downloading"
        assert asset.local_path is None
        assert job is not None
        assert job.status == "running"
        assert job.attempts == job.max_attempts == 2
        assert job.lease_owner == "replacement-worker"
        assert job.lease_token == replacement_token


def test_job_completion_failure_rolls_back_asset_verification(
    database: Database,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asset_id = _seed_asset(database)

    def fail_completion(self: JobRepository, *args: object, **kwargs: object) -> object:
        del self, args, kwargs
        raise RuntimeError("sentinel-finalize-detail")

    monkeypatch.setattr(JobRepository, "complete", fail_completion)
    service = AssetDownloadService(database, _downloader(lambda _request: _ok_response()), clock=lambda: STARTED_AT)

    with pytest.raises(AssetDownloadOrchestrationError) as caught:
        service.run(_request(tmp_path, asset_id))

    assert caught.value.code == "asset_download_finalize_failed"
    assert "sentinel" not in str(caught.value)
    with database.session() as session:
        asset = AssetRepository(session).require(str(asset_id))
        job = JobRepository(session).get_by_key(
            ASSET_DOWNLOAD_JOB_TYPE,
            asset_download_natural_key(asset_id, 1),
        )
        assert asset.status == "downloading"
        assert asset.local_path is None
        assert asset.checksum_sha256 is None
        assert asset.verified_at is None
        assert job is not None
        assert job.status == "running"
        assert job.finished_at is None


def test_reclaimed_retryable_attempt_recovers_prepared_result_before_next_claim(
    database: Database,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asset_id = _seed_asset(database)
    clock = _MutableClock(STARTED_AT)
    initial_network_calls = 0

    def initial_handler(_request: httpx.Request) -> httpx.Response:
        nonlocal initial_network_calls
        initial_network_calls += 1
        return _ok_response()

    original_complete = JobRepository.complete

    def crash_after_blob_commit(self: JobRepository, *args: object, **kwargs: object) -> object:
        del self, args, kwargs
        raise RuntimeError("simulated process loss before database completion")

    monkeypatch.setattr(JobRepository, "complete", crash_after_blob_commit)
    initial_request = _request(
        tmp_path,
        asset_id,
        worker_id="original-worker",
        lease_seconds=1,
        max_attempts=5,
    )
    with pytest.raises(AssetDownloadOrchestrationError) as crashed:
        AssetDownloadService(database, _downloader(initial_handler), clock=clock).run(initial_request)

    assert crashed.value.code == "asset_download_finalize_failed"
    assert initial_network_calls == 1
    part = tmp_path / "work" / "parts" / f"{asset_id}.1.part"
    assert part.read_bytes() == PNG
    blobs = tuple(path for path in (tmp_path / "archive" / "sha256").rglob("*") if path.is_file())
    assert len(blobs) == 1 and blobs[0].read_bytes() == PNG

    expired_at = STARTED_AT + timedelta(seconds=2)
    with database.session() as session:
        assets = AssetRepository(session)
        jobs = JobRepository(session)
        asset = assets.require(str(asset_id))
        job = jobs.get_by_key(
            ASSET_DOWNLOAD_JOB_TYPE,
            asset_download_natural_key(asset_id, 1),
        )
        assert job is not None
        assert job.status == "running"
        assert job.attempts == 1
        assert jobs.reclaim_expired(job_id=job.id, now=expired_at) == 1
        reclaimed_asset = assets.recover_expired_download(
            asset.id,
            expected_generation=asset.generation,
            expected_status=asset.status,
            job_id=job.id,
            at=expired_at,
        )
        reclaimed_job = jobs.get(job.id)
        assert reclaimed_asset.status == "failed_retryable"
        assert reclaimed_asset.last_error_code == "download_lease_expired"
        assert reclaimed_job is not None
        assert reclaimed_job.status == "failed_retryable"
        assert reclaimed_job.last_error_code == "lease_expired"
        assert reclaimed_job.attempts == 1

    monkeypatch.setattr(JobRepository, "complete", original_complete)
    clock.current = expired_at
    recovery_network_calls = 0

    def forbidden_network(_request: httpx.Request) -> httpx.Response:
        nonlocal recovery_network_calls
        recovery_network_calls += 1
        raise AssertionError("prepared retryable recovery must run before another network attempt")

    recovery_request = _request(
        tmp_path,
        asset_id,
        worker_id="recovery-worker",
        lease_seconds=60,
        max_attempts=5,
    )
    recovery_service = AssetDownloadService(database, _downloader(forbidden_network), clock=clock)

    recovered = recovery_service.run(recovery_request)
    replayed = recovery_service.run(recovery_request)

    assert recovered.disposition == "downloaded"
    assert replayed.disposition == "already_verified"
    assert recovered.archive_path == replayed.archive_path == blobs[0]
    assert recovered.archive_path.read_bytes() == PNG
    assert recovery_network_calls == 0
    assert not tuple((tmp_path / "work" / "parts").iterdir())
    with database.session() as session:
        asset = AssetRepository(session).require(str(asset_id))
        job = JobRepository(session).get_by_key(
            ASSET_DOWNLOAD_JOB_TYPE,
            asset_download_natural_key(asset_id, 1),
        )
        assert asset.status == "verified"
        assert asset.last_error_code is None
        assert job is not None
        assert job.status == "succeeded"
        assert job.attempts == 1
        assert job.max_attempts == 5
        assert job.lease_token is None


def test_expired_final_attempt_recovers_published_result_without_network_or_new_attempt(
    database: Database,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asset_id = _seed_asset(database)
    clock = _MutableClock(STARTED_AT)
    network_calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal network_calls
        network_calls += 1
        return _ok_response()

    original_complete = JobRepository.complete

    def crash_after_blob_commit(self: JobRepository, *args: object, **kwargs: object) -> object:
        del self, args, kwargs
        raise RuntimeError("simulated process loss before database completion")

    monkeypatch.setattr(JobRepository, "complete", crash_after_blob_commit)
    request = _request(
        tmp_path,
        asset_id,
        worker_id="original-worker",
        lease_seconds=1,
        max_attempts=1,
    )
    with pytest.raises(AssetDownloadOrchestrationError) as crashed:
        AssetDownloadService(database, _downloader(handler), clock=clock).run(request)

    assert crashed.value.code == "asset_download_finalize_failed"
    part = tmp_path / "work" / "parts" / f"{asset_id}.1.part"
    assert part.read_bytes() == PNG
    blobs = tuple(path for path in (tmp_path / "archive" / "sha256").rglob("*") if path.is_file())
    assert len(blobs) == 1 and blobs[0].read_bytes() == PNG
    with database.session() as session:
        job = JobRepository(session).get_by_key(
            ASSET_DOWNLOAD_JOB_TYPE,
            asset_download_natural_key(asset_id, 1),
        )
        assert AssetRepository(session).require(str(asset_id)).status == "downloading"
        assert job is not None
        assert job.status == "running"
        assert job.attempts == job.max_attempts == 1
        original_token = job.lease_token

    expired_at = STARTED_AT + timedelta(seconds=2)
    with database.session() as session:
        assets = AssetRepository(session)
        jobs = JobRepository(session)
        asset = assets.require(str(asset_id))
        job = jobs.get_by_key(
            ASSET_DOWNLOAD_JOB_TYPE,
            asset_download_natural_key(asset_id, 1),
        )
        assert job is not None
        assert jobs.reclaim_expired(job_id=job.id, now=expired_at) == 1
        terminal_asset = assets.recover_expired_download(
            asset.id,
            expected_generation=asset.generation,
            expected_status=asset.status,
            job_id=job.id,
            at=expired_at,
        )
        assert terminal_asset.status == "failed_terminal"
        terminal_job = jobs.get(job.id)
        assert terminal_job is not None
        assert terminal_job.status == "failed_terminal"

    monkeypatch.setattr(JobRepository, "complete", original_complete)
    clock.current = expired_at
    recovery_network_calls = 0

    def forbidden_network(_request: httpx.Request) -> httpx.Response:
        nonlocal recovery_network_calls
        recovery_network_calls += 1
        raise AssertionError("prepared-result recovery must not contact the network")

    recovered = AssetDownloadService(database, _downloader(forbidden_network), clock=clock).run(
        _request(
            tmp_path,
            asset_id,
            worker_id="recovery-worker",
            lease_seconds=60,
            max_attempts=1,
        )
    )

    assert recovered.disposition == "downloaded"
    assert recovered.archive_path.read_bytes() == PNG
    assert network_calls == 1
    assert recovery_network_calls == 0
    assert not tuple((tmp_path / "work" / "parts").iterdir())
    with database.session() as session:
        asset = AssetRepository(session).require(str(asset_id))
        job = JobRepository(session).get_by_key(
            ASSET_DOWNLOAD_JOB_TYPE,
            asset_download_natural_key(asset_id, 1),
        )
        assert asset.status == "verified"
        assert job is not None
        assert job.status == "succeeded"
        assert job.attempts == job.max_attempts == 1
        assert job.lease_token is None
        assert original_token is not None


def test_job_failure_write_error_rolls_back_asset_failure(
    database: Database,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asset_id = _seed_asset(database)

    def fail_failure_write(self: JobRepository, *args: object, **kwargs: object) -> object:
        del self, args, kwargs
        raise RuntimeError("sentinel-failure-finalize-detail")

    monkeypatch.setattr(JobRepository, "fail", fail_failure_write)
    service = AssetDownloadService(
        database,
        _downloader(lambda _request: httpx.Response(503)),
        clock=lambda: STARTED_AT,
    )

    with pytest.raises(AssetDownloadOrchestrationError) as caught:
        service.run(_request(tmp_path, asset_id))

    assert caught.value.code == "asset_download_failure_finalize_failed"
    assert "sentinel" not in str(caught.value)
    with database.session() as session:
        asset = AssetRepository(session).require(str(asset_id))
        job = JobRepository(session).get_by_key(
            ASSET_DOWNLOAD_JOB_TYPE,
            asset_download_natural_key(asset_id, 1),
        )
        assert asset.status == "downloading"
        assert asset.last_error_code is None
        assert asset.last_error_message is None
        assert job is not None
        assert job.status == "running"
        assert job.last_error_code is None
        assert job.last_error_message is None


def test_transport_exception_sentinel_never_reaches_error_or_persistence(
    database: Database,
    tmp_path: Path,
) -> None:
    asset_id = _seed_asset(database)
    sentinel = "sentinel-signed-url-and-cookie"

    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(sentinel)

    service = AssetDownloadService(database, _downloader(handler), clock=lambda: STARTED_AT)
    with pytest.raises(AssetDownloadOrchestrationError) as caught:
        service.run(_request(tmp_path, asset_id, max_attempts=2))

    assert caught.value.code == "download_transport"
    assert caught.value.retryable is True
    assert sentinel not in str(caught.value)
    with database.session() as session:
        asset = AssetRepository(session).require(str(asset_id))
        job = JobRepository(session).get_by_key(
            ASSET_DOWNLOAD_JOB_TYPE,
            asset_download_natural_key(asset_id, 1),
        )
        assert asset.status == "failed_retryable"
        assert asset.last_error_code == "download_transport"
        assert asset.last_error_message == "download transport failed"
        assert job is not None
        assert job.status == "failed_retryable"
        persisted = repr(
            (
                asset.locator,
                asset.raw,
                asset.last_error_code,
                asset.last_error_message,
                job.payload,
                job.last_error_code,
                job.last_error_message,
            )
        )
        assert sentinel not in persisted

    database.dispose()
    for path in tmp_path.rglob("*"):
        if path.is_file():
            assert sentinel.encode() not in path.read_bytes()
