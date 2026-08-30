"""Integration coverage for SQLite, Alembic, repositories, and job leases."""

from __future__ import annotations

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier
from types import MappingProxyType

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import func, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from media_sync.domain.enums import (
    AssetKind,
    AssetStatus,
    AuthStatus,
    ContentKind,
    JobStatus,
    LoginMethod,
    Platform,
    RunStatus,
)
from media_sync.domain.errors import InvalidStateTransitionError
from media_sync.infrastructure.db import (
    AccountRepository,
    AssetConflictError,
    AssetLeaseLostError,
    AssetRepository,
    AssetUpsert,
    AuthorRepository,
    AuthorUpsert,
    ContentUpsert,
    Database,
    ExportRecordRepository,
    JobRepository,
    LeaseLostError,
    NotFoundError,
    RepositoryError,
    SubscriptionRepository,
    SyncRunRepository,
)
from media_sync.infrastructure.db.models import (
    ASSET_KINDS,
    ASSET_STATUSES,
    AUTH_STATUSES,
    CONTENT_KINDS,
    JOB_STATUSES,
    LOGIN_METHODS,
    PLATFORMS,
    RUN_STATUSES,
    Account,
    Asset,
    Author,
    Content,
    Job,
    RunEvent,
    SchedulerLane,
    Subscription,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = REPOSITORY_ROOT / "alembic.ini"
DOMAIN_TABLES = {
    "accounts",
    "asset_refresh_sources",
    "assets",
    "authors",
    "contents",
    "export_records",
    "jobs",
    "login_sessions",
    "run_events",
    "scheduler_lanes",
    "subscriptions",
    "sync_runs",
}


def _database_url(path: Path) -> str:
    return f"sqlite+pysqlite:///{path.as_posix()}"


def _alembic_config(database_url: str | None = None) -> Config:
    configuration = Config(str(ALEMBIC_INI))
    if database_url is not None:
        configuration.set_main_option("sqlalchemy.url", database_url)
    return configuration


@pytest.fixture
def database(tmp_path: Path) -> Iterator[Database]:
    database_url = _database_url(tmp_path / "integration.sqlite3")
    command.upgrade(_alembic_config(database_url), "head")
    instance = Database(database_url)
    try:
        yield instance
    finally:
        instance.dispose()


def _seed_subscription(session: Session) -> tuple[Account, Author, str]:
    account = AccountRepository(session).create(
        platform="xhs",
        display_name="primary",
        login_method="qr",
        auth_status="authenticated",
    )
    author = AuthorRepository(session).upsert(
        AuthorUpsert(platform="xhs", remote_id="creator-1", display_name="Creator One")
    )
    subscription = SubscriptionRepository(session).create(account_id=account.id, author_id=author.id)
    return account, author, subscription.id


def test_alembic_upgrade_matches_metadata_and_downgrades(tmp_path: Path) -> None:
    database_url = _database_url(tmp_path / "migration.sqlite3")
    configuration = _alembic_config(database_url)

    command.upgrade(configuration, "head")
    migrated = Database(database_url)
    try:
        assert set(inspect(migrated.engine).get_table_names()) == DOMAIN_TABLES | {"alembic_version"}
    finally:
        migrated.dispose()
    command.check(configuration)

    command.downgrade(configuration, "base")
    downgraded = Database(database_url)
    try:
        assert DOMAIN_TABLES.isdisjoint(inspect(downgraded.engine).get_table_names())
    finally:
        downgraded.dispose()


def test_alembic_uses_runtime_database_setting(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "configured.sqlite3"
    monkeypatch.setenv("MEDIA_SYNC_DATABASE_URL", _database_url(target))

    command.upgrade(_alembic_config(), "head")

    assert target.is_file()
    configured = Database(_database_url(target))
    try:
        assert DOMAIN_TABLES.issubset(inspect(configured.engine).get_table_names())
    finally:
        configured.dispose()


def test_sqlite_pragmas_and_nested_work_rollback(database: Database) -> None:
    with database.engine.connect() as connection:
        assert connection.scalar(text("PRAGMA foreign_keys")) == 1
        assert str(connection.scalar(text("PRAGMA journal_mode"))).lower() == "wal"
        assert connection.scalar(text("PRAGMA busy_timeout")) == 5_000

    with pytest.raises(RuntimeError, match="outer rollback"), database.session() as session:
        AuthorRepository(session).upsert_with_contents(
            AuthorUpsert(platform="bili", remote_id="rollback-author", display_name="Rollback"),
            [ContentUpsert(remote_id="rollback-content", kind="video")],
        )
        raise RuntimeError("outer rollback")

    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(Author)) == 0
        assert session.scalar(select(func.count()).select_from(Content)) == 0


def test_persistence_vocabularies_match_domain_enums() -> None:
    assert frozenset(item.value for item in Platform) == PLATFORMS
    assert frozenset(item.value for item in LoginMethod) == LOGIN_METHODS
    assert frozenset(item.value for item in ContentKind) == CONTENT_KINDS
    assert frozenset(item.value for item in AssetKind) == ASSET_KINDS
    assert frozenset(item.value for item in AuthStatus) == AUTH_STATUSES
    assert frozenset(item.value for item in AssetStatus) == ASSET_STATUSES
    assert frozenset(item.value for item in RunStatus) == RUN_STATUSES
    assert frozenset(item.value for item in JobStatus) == JOB_STATUSES


def test_repository_upsert_dto_repr_redacts_secret_adjacent_fields() -> None:
    sentinel = "sentinel-secret"
    author = AuthorUpsert(
        platform="bili",
        remote_id="author-1",
        display_name="Author",
        profile_url=f"https://example.invalid/{sentinel}",
        avatar_url=f"https://example.invalid/avatar/{sentinel}",
        raw={"credential": sentinel},
    )
    content = ContentUpsert(
        remote_id="content-1",
        kind="video",
        body=sentinel,
        canonical_url=f"https://example.invalid/content?token={sentinel}",
        metrics={"private": sentinel},
        raw={"cookie": sentinel},
    )
    asset = AssetUpsert(
        platform="bili",
        kind="video",
        position=0,
        source_url=f"https://example.invalid/video?token={sentinel}",
        locator={"header": sentinel},
        raw={"cookie": sentinel},
    )

    assert sentinel not in repr((author, content, asset))
    assert author.raw["credential"] == sentinel
    assert content.body == sentinel
    assert asset.locator["header"] == sentinel


def test_foreign_keys_uniqueness_and_platform_checks(database: Database) -> None:
    inspector = inspect(database.engine)
    expected_unique_constraints = {
        "accounts": "uq_accounts_platform_display_name",
        "authors": "uq_authors_platform_remote_id",
        "subscriptions": "uq_subscriptions_account_id_author_id",
        "contents": "uq_contents_platform_remote_type_remote_id",
        "assets": "uq_assets_content_id_kind_position",
        "jobs": "uq_jobs_job_type_natural_key",
        "export_records": "uq_export_records_content_id_exporter_exporter_version_source_fingerprint",
    }
    for table_name, constraint_name in expected_unique_constraints.items():
        names = {constraint["name"] for constraint in inspector.get_unique_constraints(table_name)}
        assert constraint_name in names
    for table_name in ("accounts", "authors", "contents", "assets"):
        check_names = {constraint["name"] for constraint in inspector.get_check_constraints(table_name)}
        assert f"ck_{table_name}_platform" in check_names


def test_scheduler_control_plane_constraints_partial_uniqueness_and_cascades(database: Database) -> None:
    inspector = inspect(database.engine)
    job_indexes = {index["name"]: index for index in inspector.get_indexes("jobs")}
    assert {
        "ix_jobs_scheduler_claim",
        "ix_jobs_subscription_scope",
        "ix_jobs_account_scope",
        "ix_jobs_platform_scope",
        "uq_jobs_active_sync_subscription",
    } <= job_indexes.keys()
    assert job_indexes["uq_jobs_active_sync_subscription"]["unique"] == 1
    lane_indexes = {index["name"]: index for index in inspector.get_indexes("scheduler_lanes")}
    assert lane_indexes["uq_scheduler_lanes_platform"]["unique"] == 1
    assert lane_indexes["uq_scheduler_lanes_account"]["unique"] == 1
    assert "ix_scheduler_lanes_account_id" in lane_indexes
    assert {
        "ck_scheduler_lanes_scope_type",
        "ck_scheduler_lanes_scope_shape",
        "ck_scheduler_lanes_platform",
        "ck_scheduler_lanes_max_concurrency_positive",
        "ck_scheduler_lanes_min_start_interval_seconds_nonnegative",
        "ck_scheduler_lanes_failure_threshold_positive",
        "ck_scheduler_lanes_cooldown_seconds_positive",
        "ck_scheduler_lanes_consecutive_failures_nonnegative",
        "ck_scheduler_lanes_circuit_state",
        "ck_scheduler_lanes_revision_nonnegative",
    } <= {constraint["name"] for constraint in inspector.get_check_constraints("scheduler_lanes")}
    assert "ck_subscriptions_schedule_revision_nonnegative" in {
        constraint["name"] for constraint in inspector.get_check_constraints("subscriptions")
    }
    assert "ck_jobs_platform" in {constraint["name"] for constraint in inspector.get_check_constraints("jobs")}

    job_foreign_keys = {
        tuple(foreign_key["constrained_columns"]): foreign_key["options"].get("ondelete")
        for foreign_key in inspector.get_foreign_keys("jobs")
    }
    assert job_foreign_keys[("subscription_id",)] == "CASCADE"
    assert job_foreign_keys[("account_id",)] == "CASCADE"
    lane_foreign_keys = {
        tuple(foreign_key["constrained_columns"]): foreign_key["options"].get("ondelete")
        for foreign_key in inspector.get_foreign_keys("scheduler_lanes")
    }
    assert lane_foreign_keys[("account_id",)] == "CASCADE"
    assert lane_foreign_keys[("half_open_job_id",)] == "SET NULL"

    now = datetime(2026, 8, 30, 11, tzinfo=UTC)
    with database.session() as session:
        account, _author, subscription_id = _seed_subscription(session)
        subscription = session.get(Subscription, subscription_id)
        assert subscription is not None and subscription.schedule_revision == 0
        platform_lane = SchedulerLane(scope_type="platform", platform="xhs")
        account_lane = SchedulerLane(scope_type="account", platform="xhs", account_id=account.id)
        active_job = Job(
            subscription_id=subscription_id,
            account_id=account.id,
            platform="xhs",
            job_type="sync.subscription",
            natural_key=f"subscription:{subscription_id}:schedule:0",
            scheduled_for=now,
            available_at=now,
        )
        session.add_all((platform_lane, account_lane, active_job))
        session.flush()
        assert (
            platform_lane.max_concurrency,
            platform_lane.min_start_interval_seconds,
            platform_lane.failure_threshold,
            platform_lane.cooldown_seconds,
            platform_lane.consecutive_failures,
            platform_lane.circuit_state,
            platform_lane.revision,
        ) == (1, 5, 3, 900, 0, "closed", 0)
        account_id = account.id
        account_lane_id = account_lane.id
        platform_lane_id = platform_lane.id
        active_job_id = active_job.id

    for index, status in enumerate(
        ("queued", "claimed", "running", "retry_wait", "waiting_auth", "waiting_user", "failed_retryable"),
        start=1,
    ):
        with pytest.raises(IntegrityError), database.session() as session:
            session.add(
                Job(
                    subscription_id=subscription_id,
                    account_id=account_id,
                    platform="xhs",
                    job_type="sync.subscription",
                    natural_key=f"subscription:{subscription_id}:schedule:{index}",
                    status=status,
                    scheduled_for=now,
                    available_at=now,
                )
            )

    with database.session() as session:
        terminal_jobs = [
            Job(
                subscription_id=subscription_id,
                account_id=account_id,
                platform="xhs",
                job_type="sync.subscription",
                natural_key=f"subscription:{subscription_id}:schedule:{status}",
                status=status,
                scheduled_for=now,
                available_at=now,
            )
            for status in ("succeeded", "failed_terminal", "cancelled")
        ]
        unrelated_scoped_job = Job(
            subscription_id=subscription_id,
            account_id=account_id,
            platform="xhs",
            job_type="maintenance",
            natural_key=f"subscription:{subscription_id}:maintenance",
            scheduled_for=now,
            available_at=now,
        )
        session.add_all((*terminal_jobs, unrelated_scoped_job))
        session.flush()
        terminal_job_id = terminal_jobs[0].id
        unrelated_scoped_job_id = unrelated_scoped_job.id

    with pytest.raises(IntegrityError), database.session() as session:
        session.add(SchedulerLane(scope_type="platform", platform="xhs"))
    with pytest.raises(IntegrityError), database.session() as session:
        session.add(SchedulerLane(scope_type="account", platform="xhs", account_id=account_id))
    with pytest.raises(IntegrityError), database.session() as session:
        session.add(SchedulerLane(scope_type="platform", platform="bili", account_id=account_id))
    with pytest.raises(IntegrityError), database.session() as session:
        session.add(SchedulerLane(scope_type="account", platform="bili"))
    with pytest.raises(IntegrityError), database.session() as session:
        session.add(SchedulerLane(scope_type="platform", platform="not-a-platform"))
    for field, invalid in (
        ("max_concurrency", 0),
        ("min_start_interval_seconds", -1),
        ("failure_threshold", 0),
        ("cooldown_seconds", 0),
        ("consecutive_failures", -1),
        ("revision", -1),
        ("circuit_state", "invalid"),
    ):
        with pytest.raises(IntegrityError), database.session() as session:
            session.add(SchedulerLane(scope_type="platform", platform="bili", **{field: invalid}))
    with pytest.raises(IntegrityError), database.session() as session:
        subscription = session.get(Subscription, subscription_id)
        assert subscription is not None
        subscription.schedule_revision = -1
    with pytest.raises(IntegrityError), database.session() as session:
        session.add(
            Job(
                job_type="maintenance",
                natural_key="invalid-platform",
                platform="not-a-platform",
                available_at=now,
            )
        )

    with database.session() as session:
        lane = session.get(SchedulerLane, account_lane_id)
        terminal_job = session.get(Job, terminal_job_id)
        assert lane is not None and terminal_job is not None
        lane.half_open_job_id = terminal_job.id
        session.delete(terminal_job)
        session.flush()
        session.refresh(lane)
        assert lane.half_open_job_id is None

    with database.session() as session:
        subscription = session.get(Subscription, subscription_id)
        assert subscription is not None
        session.delete(subscription)

    with database.session() as session:
        assert session.get(Job, active_job_id) is None
        assert session.get(Job, unrelated_scoped_job_id) is None
        assert session.get(SchedulerLane, account_lane_id) is not None
        account_only_job = Job(
            account_id=account_id,
            platform="xhs",
            job_type="maintenance",
            natural_key="account-cascade",
            available_at=now,
        )
        session.add(account_only_job)
        session.flush()
        account_only_job_id = account_only_job.id

    with database.session() as session:
        account = session.get(Account, account_id)
        assert account is not None
        session.delete(account)

    with database.session() as session:
        assert session.get(Job, account_only_job_id) is None
        assert session.get(SchedulerLane, account_lane_id) is None
        assert session.get(SchedulerLane, platform_lane_id) is not None

    with pytest.raises(NotFoundError, match="account not found"), database.session() as session:
        SubscriptionRepository(session).create(account_id="missing", author_id="missing")

    with database.session() as session:
        AccountRepository(session).create(platform="bili", display_name="duplicate")
    with pytest.raises(IntegrityError), database.session() as session:
        AccountRepository(session).create(platform="bili", display_name="duplicate")
    with pytest.raises(IntegrityError), database.session() as session:
        AccountRepository(session).create(platform="not-a-platform", display_name="invalid")


def test_subscription_repository_rejects_missing_and_cross_platform_relations(database: Database) -> None:
    with database.session() as session:
        account = AccountRepository(session).create(platform="xhs", display_name="xhs-account")
        xhs_author = AuthorRepository(session).upsert(
            AuthorUpsert(platform="xhs", remote_id="xhs-author", display_name="XHS Author")
        )
        bili_author = AuthorRepository(session).upsert(
            AuthorUpsert(platform="bili", remote_id="bili-author", display_name="Bili Author")
        )

        repository = SubscriptionRepository(session)
        with pytest.raises(NotFoundError, match="account not found"):
            repository.create(account_id="missing-account", author_id=xhs_author.id)
        with pytest.raises(NotFoundError, match="author not found"):
            repository.create(account_id=account.id, author_id="missing-author")
        with pytest.raises(RepositoryError, match="platforms do not match"):
            repository.create(account_id=account.id, author_id=bili_author.id)

        assert session.scalar(select(func.count()).select_from(Subscription)) == 0


def test_account_and_subscription_get_list_eager_relationships(database: Database) -> None:
    with database.session() as session:
        account, author, subscription_id = _seed_subscription(session)
        account_id = account.id
        author_id = author.id

    with database.session() as session:
        account_repository = AccountRepository(session)
        loaded_account = account_repository.get(account_id)
        accounts = account_repository.list()
        subscription_repository = SubscriptionRepository(session)
        loaded_subscription = subscription_repository.get(subscription_id)
        subscriptions = subscription_repository.list(enabled=True)

    assert loaded_account is not None
    assert loaded_account.id == account_id
    assert [item.id for item in accounts] == [account_id]
    assert loaded_subscription is not None
    assert loaded_subscription.account.display_name == "primary"
    assert loaded_subscription.author.id == author_id
    assert subscriptions[0].account.id == account_id
    assert subscriptions[0].author.display_name == "Creator One"


def test_author_content_asset_and_export_upserts_are_idempotent(database: Database) -> None:
    first_seen = datetime(2026, 8, 30, 1, tzinfo=UTC)
    second_seen = first_seen + timedelta(minutes=5)
    nested_raw = MappingProxyType({"nested": MappingProxyType({"items": (MappingProxyType({"value": 1}),)})})

    with database.session() as session:
        repository = AuthorRepository(session)
        author, first_contents = repository.upsert_with_contents(
            AuthorUpsert(
                platform="bili",
                remote_id="author-1",
                display_name="First name",
                raw=nested_raw,
            ),
            [
                ContentUpsert(remote_id="dynamic-1", kind="dynamic", title="First title", raw=nested_raw),
                ContentUpsert(remote_id="audio-1", kind="audio"),
            ],
            seen_at=first_seen,
        )
        original_ids = [content.id for content in first_contents]
        author_id = author.id

        updated_author, updated_contents = repository.upsert_with_contents(
            AuthorUpsert(platform="bili", remote_id="author-1", display_name="Updated name", raw=nested_raw),
            [
                ContentUpsert(remote_id="dynamic-1", kind="dynamic", title="Updated title", raw=nested_raw),
                ContentUpsert(remote_id="audio-1", kind="audio"),
            ],
            seen_at=second_seen,
        )
        assert updated_author.id == author_id
        assert [content.id for content in updated_contents] == original_ids

        asset_repository = AssetRepository(session)
        avatar = asset_repository.upsert_for_content(
            updated_contents[0].id,
            AssetUpsert(platform="bili", kind="avatar", position=0, source_url="https://example.com/1.jpg"),
        )
        updated_avatar = asset_repository.upsert_for_content(
            updated_contents[0].id,
            AssetUpsert(platform="bili", kind="avatar", position=0, source_url="https://example.com/2.jpg"),
        )
        assert updated_avatar.id == avatar.id
        assert updated_avatar.source_url == "https://example.com/2.jpg"

        export_repository = ExportRecordRepository(session)
        export = export_repository.record(
            content_id=updated_contents[0].id,
            exporter="emby",
            exporter_version="1",
            source_fingerprint="a" * 64,
            output_path="library/item",
        )
        repeated_export = export_repository.record(
            content_id=updated_contents[0].id,
            exporter="emby",
            exporter_version="1",
            source_fingerprint="a" * 64,
            output_path="library/ignored",
        )
        assert repeated_export.id == export.id

    with database.session() as session:
        stored_author = AuthorRepository(session).get(author_id)
        assert stored_author is not None
        assert stored_author.first_seen_at == first_seen
        assert stored_author.last_seen_at == second_seen
        assert stored_author.raw == {"nested": {"items": [{"value": 1}]}}
        assert session.scalar(select(func.count()).select_from(Author)) == 1
        assert session.scalar(select(func.count()).select_from(Content)) == 2

    with database.session() as session:
        repository = AuthorRepository(session)
        with pytest.raises(IntegrityError):
            repository.upsert_with_contents(
                AuthorUpsert(platform="bili", remote_id="atomic-rollback", display_name="Atomic"),
                [
                    ContentUpsert(remote_id="valid-before-error", kind="video"),
                    ContentUpsert(remote_id="invalid-content", kind="unsupported"),
                ],
            )
        assert repository.get_by_remote("bili", "atomic-rollback") is None
        valid_content_count = session.scalar(
            select(func.count()).select_from(Content).where(Content.remote_id == "valid-before-error")
        )
        assert valid_content_count == 0


def test_asset_discovery_identity_and_download_lifecycle_are_fenced(database: Database) -> None:
    observed_at = datetime(2026, 8, 30, 2, tzinfo=UTC)
    with database.session() as session:
        author, contents = AuthorRepository(session).upsert_with_contents(
            AuthorUpsert(platform="bili", remote_id="asset-author", display_name="Asset Author"),
            [ContentUpsert(remote_id="asset-content", kind="video")],
        )
        del author
        repository = AssetRepository(session)
        discovered = repository.upsert_for_content(
            contents[0].id,
            AssetUpsert(
                platform="bili",
                remote_id="remote-video-1",
                kind="video",
                position=0,
                source_url="https://cdn.example.test/media/video.mp4?quality=720",
            ),
        )
        queued = repository.queue(
            discovered.id,
            expected_generation=1,
            expected_status="discovered",
            at=observed_at,
        )
        job = JobRepository(session).enqueue(
            job_type="asset_download",
            natural_key=f"{queued.id}:{queued.generation}",
            available_at=observed_at,
        )
        claimed = JobRepository(session).claim(job.id, worker_id="worker-a", now=observed_at)
        assert claimed is not None
        assert claimed.lease_token is not None
        running_job = JobRepository(session).start(
            claimed.id,
            worker_id="worker-a",
            lease_token=claimed.lease_token,
            now=observed_at,
        )
        downloading = repository.start(
            queued.id,
            expected_generation=1,
            expected_status="queued",
            job_id=running_job.id,
            worker_id="worker-a",
            lease_token=claimed.lease_token,
            at=observed_at,
        )
        verified = repository.verify(
            downloading.id,
            expected_generation=1,
            expected_status="downloading",
            job_id=running_job.id,
            worker_id="worker-a",
            lease_token=claimed.lease_token,
            mime_type="video/mp4",
            size_bytes=123,
            checksum_sha256="c" * 64,
            local_path="archive/sha256/cc/video.mp4",
            etag='"strong-etag"',
            last_modified="Sun, 30 Aug 2026 02:00:00 GMT",
            at=observed_at,
        )
        assert verified.status == "verified"
        assert verified.etag == '"strong-etag"'
        assert verified.last_modified == "Sun, 30 Aug 2026 02:00:00 GMT"

        query_rotation = repository.upsert_for_content(
            contents[0].id,
            AssetUpsert(
                platform="bili",
                remote_id="remote-video-1",
                kind="video",
                position=0,
                source_url="https://cdn.example.test/media/video.mp4?quality=1080",
            ),
        )
        assert query_rotation.generation == 1
        assert query_rotation.status == "verified"
        assert query_rotation.mime_type == "video/mp4"
        assert query_rotation.size_bytes == 123
        assert query_rotation.checksum_sha256 == "c" * 64
        assert query_rotation.local_path == "archive/sha256/cc/video.mp4"

        replacement = repository.upsert_for_content(
            contents[0].id,
            AssetUpsert(
                platform="bili",
                remote_id="remote-video-2",
                kind="video",
                position=0,
                source_url="https://cdn.example.test/media/replacement.mp4",
            ),
        )
        assert replacement.id == discovered.id
        assert replacement.generation == 2
        assert replacement.status == "discovered"
        assert replacement.mime_type is None
        assert replacement.size_bytes is None
        assert replacement.checksum_sha256 is None
        assert replacement.local_path is None
        assert replacement.etag is None
        assert replacement.last_modified is None
        assert replacement.download_job_id is None

        with pytest.raises(AssetConflictError):
            repository.queue(
                replacement.id,
                expected_generation=1,
                expected_status="discovered",
                at=observed_at,
            )
        with pytest.raises(AssetConflictError):
            repository.queue(
                replacement.id,
                expected_generation=2,
                expected_status="failed_retryable",
                at=observed_at,
            )

        explicitly_reset = repository.reset(
            replacement.id,
            expected_generation=2,
            expected_status="discovered",
            value=AssetUpsert(
                platform="bili",
                remote_id="remote-video-2",
                kind="video",
                position=0,
                source_url="https://cdn.example.test/media/replacement.mp4",
            ),
            at=observed_at,
        )
        assert explicitly_reset.generation == 3
        assert explicitly_reset.status == "discovered"


def test_expired_download_recovery_preserves_generation_and_fences_old_worker(database: Database) -> None:
    first_attempt = datetime(2026, 8, 30, 3, tzinfo=UTC)
    reclaimed_at = first_attempt + timedelta(seconds=2)
    with database.session() as session:
        _author, contents = AuthorRepository(session).upsert_with_contents(
            AuthorUpsert(platform="bili", remote_id="resume-author", display_name="Resume Author"),
            [ContentUpsert(remote_id="resume-content", kind="video")],
        )
        assets = AssetRepository(session)
        discovered = assets.upsert_for_content(
            contents[0].id,
            AssetUpsert(
                platform="bili",
                remote_id="resume-video",
                kind="video",
                position=0,
                source_url="https://cdn.example.test/media/resume.mp4",
            ),
        )
        original_locator_fingerprint = discovered.locator_fingerprint
        queued = assets.queue(
            discovered.id,
            expected_generation=1,
            expected_status="discovered",
            at=first_attempt,
        )
        jobs = JobRepository(session)
        job = jobs.enqueue(
            job_type="asset_download",
            natural_key=f"{queued.id}:{queued.generation}",
            available_at=first_attempt,
        )
        first_claim = jobs.claim(job.id, worker_id="worker-old", lease_seconds=1, now=first_attempt)
        assert first_claim is not None
        assert first_claim.lease_token is not None
        jobs.start(
            job.id,
            worker_id="worker-old",
            lease_token=first_claim.lease_token,
            now=first_attempt,
        )
        assets.start(
            queued.id,
            expected_generation=1,
            expected_status="queued",
            job_id=job.id,
            worker_id="worker-old",
            lease_token=first_claim.lease_token,
            at=first_attempt,
        )

        assert jobs.reclaim_expired(job_id=job.id, now=reclaimed_at) == 1
        recovered = assets.recover_expired_download(
            queued.id,
            expected_generation=1,
            expected_status="downloading",
            job_id=job.id,
            at=reclaimed_at,
        )
        assert recovered.status == "failed_retryable"
        assert recovered.generation == 1
        assert recovered.locator_fingerprint == original_locator_fingerprint

        requeued = assets.queue(
            recovered.id,
            expected_generation=1,
            expected_status="failed_retryable",
            at=reclaimed_at,
        )
        second_claim = jobs.claim(job.id, worker_id="worker-new", lease_seconds=60, now=reclaimed_at)
        assert second_claim is not None
        assert second_claim.lease_token is not None
        jobs.start(
            job.id,
            worker_id="worker-new",
            lease_token=second_claim.lease_token,
            now=reclaimed_at,
        )
        resumed = assets.start(
            requeued.id,
            expected_generation=1,
            expected_status="queued",
            job_id=job.id,
            worker_id="worker-new",
            lease_token=second_claim.lease_token,
            at=reclaimed_at,
        )
        assert resumed.generation == 1
        assert resumed.locator_fingerprint == original_locator_fingerprint

        with pytest.raises(AssetLeaseLostError):
            assets.verify(
                resumed.id,
                expected_generation=1,
                expected_status="downloading",
                job_id=job.id,
                worker_id="worker-old",
                lease_token=first_claim.lease_token,
                mime_type="video/mp4",
                size_bytes=1,
                checksum_sha256="e" * 64,
                local_path="archive/sha256/ee/stale.mp4",
                at=reclaimed_at,
            )
        with pytest.raises(AssetLeaseLostError):
            assets.fail(
                resumed.id,
                expected_generation=1,
                expected_status="downloading",
                job_id=job.id,
                worker_id="worker-old",
                lease_token=first_claim.lease_token,
                retryable=True,
                error_code="stale_worker",
                error_message="stale worker must not finalize",
                at=reclaimed_at,
            )
        assert assets.require(resumed.id).status == "downloading"

        failed = assets.fail(
            resumed.id,
            expected_generation=1,
            expected_status="downloading",
            job_id=job.id,
            worker_id="worker-new",
            lease_token=second_claim.lease_token,
            retryable=True,
            error_code="network_timeout",
            error_message="retry later",
            at=reclaimed_at,
        )
        assert failed.status == "failed_retryable"


def test_job_exact_claim_never_consumes_another_queue_item(database: Database) -> None:
    now = datetime(2026, 8, 30, 4, tzinfo=UTC)
    with database.session() as session:
        repository = JobRepository(session)
        untouched = repository.enqueue(job_type="asset_download", natural_key="untouched", available_at=now)
        requested = repository.enqueue(job_type="asset_download", natural_key="requested", available_at=now)

        claimed = repository.claim(requested.id, worker_id="exact-worker", now=now)
        assert claimed is not None
        assert claimed.id == requested.id
        assert claimed.status == "claimed"
        untouched_after = repository.get(untouched.id)
        assert untouched_after is not None
        assert untouched_after.status == "queued"


def test_concurrent_sqlite_author_content_upsert_is_idempotent(database: Database) -> None:
    start = Barrier(2)

    def ingest(label: str) -> tuple[str, str]:
        worker_database = Database(database.url)
        try:
            start.wait()
            with worker_database.session() as session:
                author, contents = AuthorRepository(session).upsert_with_contents(
                    AuthorUpsert(platform="dy", remote_id="shared-author", display_name=label),
                    [ContentUpsert(remote_id="shared-content", kind="video", title=label)],
                )
                return author.id, contents[0].id
        finally:
            worker_database.dispose()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(ingest, ("worker-a", "worker-b")))

    assert len({result[0] for result in results}) == 1
    assert len({result[1] for result in results}) == 1

    asset_start = Barrier(2)

    def ingest_asset(label: str) -> str:
        worker_database = Database(database.url)
        try:
            asset_start.wait()
            with worker_database.session() as session:
                asset = AssetRepository(session).upsert_for_content(
                    results[0][1],
                    AssetUpsert(
                        platform="dy",
                        content_remote_type="content",
                        content_remote_id="shared-content",
                        kind="cover",
                        position=0,
                        source_url=f"https://example.com/{label}.jpg",
                    ),
                )
                return asset.id
        finally:
            worker_database.dispose()

    with ThreadPoolExecutor(max_workers=2) as executor:
        asset_ids = list(executor.map(ingest_asset, ("worker-a", "worker-b")))

    assert len(set(asset_ids)) == 1
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(Author)) == 1
        assert session.scalar(select(func.count()).select_from(Content)) == 1
        assert session.scalar(select(func.count()).select_from(Asset)) == 1


def test_subscription_watermark_advances_monotonically(database: Database) -> None:
    first = datetime(2026, 8, 30, 1, tzinfo=UTC)
    later = first + timedelta(minutes=1)
    scheduled_at = later + timedelta(hours=6)
    with database.session() as session:
        _, _, subscription_id = _seed_subscription(session)
        repository = SubscriptionRepository(session)
        repository.update_cursor(
            subscription_id,
            {"cursor": "first"},
            next_run_at=scheduled_at,
            watermarked_at=first,
            watermark_remote_ids=("item-b", "item-a"),
        )
        repository.update_cursor(
            subscription_id,
            None,
            watermarked_at=first,
            watermark_remote_ids=("item-c", "item-a"),
        )
        subscription = repository.update_cursor(
            subscription_id,
            {"cursor": "later"},
            watermarked_at=later,
            watermark_remote_ids=("item-new",),
        )
        repository.update_cursor(
            subscription_id,
            {"cursor": "older-observation"},
            watermarked_at=first,
            watermark_remote_ids=("must-not-regress",),
        )

        assert subscription.watermarked_at == later
        assert subscription.watermark_remote_ids == ["item-new"]
        assert subscription.cursor == {"cursor": "older-observation"}
        assert subscription.next_run_at == scheduled_at

        cleared = repository.update_cursor(subscription_id, subscription.cursor, next_run_at=None)
        assert cleared.next_run_at is None


def test_sync_run_status_cas_and_events(database: Database) -> None:
    with database.session() as session:
        _, _, subscription_id = _seed_subscription(session)
        run = SyncRunRepository(session).create(subscription_id=subscription_id)
        run_id = run.id

    stale_session = database.session_factory()
    try:
        stale_repository = SyncRunRepository(stale_session)
        stale = stale_repository.require(run_id)
        assert stale.status == "queued"
        stale_session.commit()

        with database.session() as session:
            repository = SyncRunRepository(session)
            with pytest.raises(InvalidStateTransitionError):
                repository.set_status(run_id, "succeeded", expected_status="queued")
            repository.set_status(run_id, "claimed", expected_status="queued")
            repository.set_status(run_id, "running", expected_status="claimed")

        with pytest.raises(RepositoryError, match="no longer"):
            stale_repository.set_status(run_id, "cancelled", expected_status="queued")
        stale_session.rollback()
    finally:
        stale_session.close()

    with database.session() as session:
        repository = SyncRunRepository(session)
        repository.set_status(run_id, "ingesting", expected_status="running")
        completed = repository.set_status(run_id, "succeeded", expected_status="ingesting")
        events = list(session.scalars(select(RunEvent).where(RunEvent.run_id == run_id).order_by(RunEvent.sequence)))
        assert completed.finished_at is not None
        assert [event.sequence for event in events] == [1, 2, 3, 4, 5]
        assert [event.to_status for event in events] == ["queued", "claimed", "running", "ingesting", "succeeded"]


def test_job_enqueue_and_concurrent_claim_are_exclusive(database: Database) -> None:
    now = datetime(2026, 8, 30, 1, tzinfo=UTC)
    with database.session() as session:
        repository = JobRepository(session)
        first = repository.enqueue(
            job_type="sync",
            natural_key="subscription:1",
            payload={"nested": MappingProxyType({"value": 1})},
            available_at=now,
        )
        repeated = repository.enqueue(
            job_type="sync",
            natural_key="subscription:1",
            payload={"ignored": True},
            available_at=now,
        )
        assert repeated.id == first.id

    start = Barrier(2)

    def claim(worker_id: str) -> str | None:
        worker_database = Database(database.url)
        try:
            start.wait()
            with worker_database.session() as session:
                job = JobRepository(session).claim_next(worker_id=worker_id, lease_seconds=30, now=now)
                return job.id if job is not None else None
        finally:
            worker_database.dispose()

    with ThreadPoolExecutor(max_workers=2) as executor:
        claimed_ids = list(executor.map(claim, ("worker-a", "worker-b")))

    assert len([job_id for job_id in claimed_ids if job_id is not None]) == 1
    with database.session() as session:
        jobs = JobRepository(session).list()
        assert len(jobs) == 1
        assert jobs[0].status == "claimed"
        assert jobs[0].attempts == 1
        assert jobs[0].lease_token is not None


def test_job_expiry_fencing_and_terminal_recovery(database: Database) -> None:
    claimed_at = datetime(2026, 8, 30, 1, tzinfo=UTC)
    with database.session() as session:
        repository = JobRepository(session)
        repository.enqueue(
            job_type="sync",
            natural_key="reclaimable",
            max_attempts=2,
            available_at=claimed_at,
        )
        first_claim = repository.claim_next(
            worker_id="stable-worker",
            lease_seconds=1,
            now=claimed_at,
        )
        assert first_claim is not None
        assert first_claim.lease_token is not None
        job_id = first_claim.id
        stale_token = first_claim.lease_token

    reclaimed_at = claimed_at + timedelta(seconds=2)
    with database.session() as session:
        repository = JobRepository(session)
        second_claim = repository.claim_next(
            worker_id="stable-worker",
            lease_seconds=30,
            now=reclaimed_at,
        )
        assert second_claim is not None
        assert second_claim.id == job_id
        assert second_claim.lease_token is not None
        assert second_claim.lease_token != stale_token
        current_token = second_claim.lease_token

        with pytest.raises(LeaseLostError):
            repository.complete(
                job_id,
                worker_id="stable-worker",
                lease_token=current_token,
                now=reclaimed_at,
            )
        still_claimed = repository.get(job_id)
        assert still_claimed is not None
        assert still_claimed.status == JobStatus.CLAIMED.value

        repository.start(
            job_id,
            worker_id="stable-worker",
            lease_token=current_token,
            now=reclaimed_at,
        )

        with pytest.raises(LeaseLostError):
            repository.complete(
                job_id,
                worker_id="stable-worker",
                lease_token=stale_token,
                now=reclaimed_at,
            )
        with pytest.raises(LeaseLostError):
            repository.renew_lease(
                job_id,
                worker_id="stable-worker",
                lease_token=stale_token,
                now=reclaimed_at,
            )
        with pytest.raises(LeaseLostError):
            repository.renew_unreclaimed_lease(
                job_id,
                worker_id="stable-worker",
                lease_token=stale_token,
                now=reclaimed_at,
            )
        completed = repository.complete(
            job_id,
            worker_id="stable-worker",
            lease_token=current_token,
            now=reclaimed_at,
        )
        assert completed.status == "succeeded"
        assert completed.lease_token is None

    with database.session() as session:
        repository = JobRepository(session)
        terminal = repository.enqueue(
            job_type="sync",
            natural_key="terminal-after-expiry",
            max_attempts=1,
            available_at=claimed_at,
        )
        claimed = repository.claim_next(worker_id="worker", lease_seconds=1, now=claimed_at)
        assert claimed is not None
        assert claimed.id == terminal.id

    with database.session() as session:
        repository = JobRepository(session)
        assert repository.claim_next(worker_id="next-worker", now=reclaimed_at) is None
        recovered = repository.get(terminal.id)
        assert recovered is not None
        assert recovered.status == "failed_terminal"
        assert recovered.finished_at == reclaimed_at
        assert recovered.lease_owner is None
        assert recovered.lease_token is None


def test_expired_running_token_can_renew_only_before_reclaim(database: Database) -> None:
    claimed_at = datetime(2026, 8, 30, 1, tzinfo=UTC)
    expired_at = claimed_at + timedelta(seconds=2)
    with database.session() as session:
        repository = JobRepository(session)
        job = repository.enqueue(
            job_type="sync",
            natural_key="unreclaimed-renewal",
            max_attempts=1,
            available_at=claimed_at,
        )
        claimed = repository.claim(job.id, worker_id="live-worker", lease_seconds=1, now=claimed_at)
        assert claimed is not None and claimed.lease_token is not None
        token = claimed.lease_token
        repository.start(job.id, worker_id="live-worker", lease_token=token, now=claimed_at)

    with database.session() as session:
        repository = JobRepository(session)
        renewed = repository.renew_unreclaimed_lease(
            job.id,
            worker_id="live-worker",
            lease_token=token,
            lease_seconds=30,
            now=expired_at,
        )
        assert renewed.status == "running"
        assert renewed.lease_token == token
        assert renewed.lease_expires_at == expired_at + timedelta(seconds=30)
        assert repository.reclaim_expired(job_id=job.id, now=expired_at) == 0
        completed = repository.complete(
            job.id,
            worker_id="live-worker",
            lease_token=token,
            now=expired_at,
        )
        assert completed.status == "succeeded"
