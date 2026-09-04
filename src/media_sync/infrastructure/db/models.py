"""Relational persistence models for the platform-independent core."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    event,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, UTCDateTime, new_uuid, utc_now

AUTH_STATUSES = frozenset({"unknown", "required", "authenticating", "authenticated", "expired", "failed"})
LOGIN_METHODS = frozenset({"qr", "cookie", "saved_session", "phone"})
LOGIN_SESSION_STATUSES = frozenset({"pending", "waiting_user", "succeeded", "expired", "failed", "cancelled"})
PLATFORMS = frozenset({"xhs", "dy", "ks", "bili", "wb", "tieba", "zhihu"})
CONTENT_KINDS = frozenset({"video", "image", "gallery", "text", "article", "audio", "dynamic", "mixed"})
ASSET_KINDS = frozenset({"image", "video", "audio", "subtitle", "cover", "avatar", "attachment"})
ASSET_STATUSES = frozenset(
    {
        "discovered",
        "queued",
        "downloading",
        "downloaded",
        "verified",
        "exported",
        "failed_retryable",
        "failed_terminal",
    }
)
RUN_STATUSES = frozenset(
    {
        "queued",
        "claimed",
        "awaiting_auth",
        "running",
        "ingesting",
        "succeeded",
        "failed_retryable",
        "failed_terminal",
        "cancelled",
    }
)
JOB_STATUSES = frozenset(
    {
        "queued",
        "claimed",
        "running",
        "retry_wait",
        "waiting_auth",
        "waiting_user",
        "succeeded",
        "failed_retryable",
        "failed_terminal",
        "cancelled",
    }
)
TERMINAL_RUN_STATUSES = frozenset({"succeeded", "failed_terminal", "cancelled"})
TERMINAL_JOB_STATUSES = frozenset({"succeeded", "failed_terminal", "cancelled"})
ACTIVE_SYNC_JOB_STATUSES = frozenset(
    {"queued", "claimed", "running", "retry_wait", "waiting_auth", "waiting_user", "failed_retryable"}
)
SCHEDULER_LANE_SCOPE_TYPES = frozenset({"platform", "account"})
CIRCUIT_STATES = frozenset({"closed", "open", "half_open"})
ASSET_REFRESH_OBSERVATION_KINDS = frozenset({"ingested", "legacy_unique_inferred"})
OPERATION_KINDS = frozenset(
    {
        "account-login",
        "asset-download",
        "emby-export",
        "pipeline-run",
        "scheduler-run",
    }
)
OPERATION_STATES = frozenset(
    {
        "queued",
        "running",
        "succeeded",
        "failed_retryable",
        "failed_terminal",
        "cancelled",
        "interrupted",
    }
)
ACTIVE_OPERATION_STATES = frozenset({"queued", "running"})
TERMINAL_OPERATION_STATES = frozenset(OPERATION_STATES - ACTIVE_OPERATION_STATES)
OPERATION_FAILURE_STATES = frozenset({"failed_retryable", "failed_terminal", "interrupted"})
OPERATION_EVENT_LEVELS = frozenset({"info", "warning", "error"})
OPERATION_EVENT_CODES = frozenset(
    {
        "operation_cancel_observed",
        "operation_cancel_requested",
        "operation_cancelled",
        "operation_entity_linked",
        "operation_failed",
        "operation_interrupted",
        "operation_phase_changed",
        "operation_progressed",
        "operation_reconciled",
        "operation_requested",
        "operation_started",
        "operation_succeeded",
    }
)
OPERATION_SUBJECT_TYPES = frozenset(
    {
        "account",
        "asset",
        "author",
        "content",
        "export_record",
        "job",
        "login_session",
        "subscription",
        "sync_run",
    }
)
OPERATION_SUBJECT_ROLES = frozenset({"target", "execution", "result", "related"})


def _quoted_values(values: frozenset[str]) -> str:
    return ", ".join(f"'{value}'" for value in sorted(values))


class TimestampMixin:
    """UTC creation and update timestamps shared by mutable records."""

    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        default=utc_now,
        server_default=text("CURRENT_TIMESTAMP"),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        default=utc_now,
        onupdate=utc_now,
        server_default=text("CURRENT_TIMESTAMP"),
        nullable=False,
    )


class Account(TimestampMixin, Base):
    __tablename__ = "accounts"
    __table_args__ = (
        UniqueConstraint("platform", "display_name"),
        CheckConstraint(f"platform IN ({_quoted_values(PLATFORMS)})", name="platform"),
        CheckConstraint(f"auth_status IN ({_quoted_values(AUTH_STATUSES)})", name="auth_status"),
        CheckConstraint(
            f"login_method IS NULL OR login_method IN ({_quoted_values(LOGIN_METHODS)})",
            name="login_method",
        ),
        Index("ix_accounts_platform_auth_status", "platform", "auth_status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    adapter: Mapped[str] = mapped_column(String(128), nullable=False, default="native", server_default="native")
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    login_method: Mapped[str | None] = mapped_column(String(32))
    credential_ref: Mapped[str | None] = mapped_column(String(512))
    profile_path: Mapped[str | None] = mapped_column(Text)
    auth_status: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown", server_default="unknown")
    auth_updated_at: Mapped[datetime | None] = mapped_column(UTCDateTime())

    login_sessions: Mapped[list[LoginSession]] = relationship(
        back_populates="account",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    subscriptions: Mapped[list[Subscription]] = relationship(
        back_populates="account",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class LoginSession(TimestampMixin, Base):
    __tablename__ = "login_sessions"
    __table_args__ = (
        CheckConstraint(f"method IN ({_quoted_values(LOGIN_METHODS)})", name="method"),
        CheckConstraint(f"status IN ({_quoted_values(LOGIN_SESSION_STATUSES)})", name="status"),
        Index("ix_login_sessions_account_status", "account_id", "status"),
        Index("ix_login_sessions_expires_at", "expires_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    account_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    method: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", server_default="pending")
    challenge_kind: Mapped[str | None] = mapped_column(String(64))
    public_payload: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        server_default=text("'{}'"),
    )
    expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())

    account: Mapped[Account] = relationship(back_populates="login_sessions")


class Author(TimestampMixin, Base):
    __tablename__ = "authors"
    __table_args__ = (
        UniqueConstraint("platform", "remote_id"),
        CheckConstraint(f"platform IN ({_quoted_values(PLATFORMS)})", name="platform"),
        Index("ix_authors_platform_handle", "platform", "handle"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    remote_id: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(512), nullable=False)
    handle: Mapped[str | None] = mapped_column(String(255))
    profile_url: Mapped[str | None] = mapped_column(Text)
    avatar_url: Mapped[str | None] = mapped_column(Text)
    raw: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict, server_default=text("'{}'"))
    first_seen_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utc_now)
    last_seen_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utc_now)

    subscriptions: Mapped[list[Subscription]] = relationship(
        back_populates="author",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    contents: Mapped[list[Content]] = relationship(
        back_populates="author",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class Subscription(TimestampMixin, Base):
    __tablename__ = "subscriptions"
    __table_args__ = (
        UniqueConstraint("account_id", "author_id"),
        CheckConstraint("interval_seconds >= 60", name="interval_seconds_minimum"),
        CheckConstraint("max_items >= 1", name="max_items_positive"),
        CheckConstraint("checkpoint_revision >= 0", name="checkpoint_revision_nonnegative"),
        CheckConstraint("schedule_revision >= 0", name="schedule_revision_nonnegative"),
        CheckConstraint("consecutive_failures >= 0", name="consecutive_failures_nonnegative"),
        Index("ix_subscriptions_due", "enabled", "next_run_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    account_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    author_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("authors.id", ondelete="CASCADE"),
        nullable=False,
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("1"))
    interval_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=21_600, server_default="21600")
    max_items: Mapped[int] = mapped_column(Integer, nullable=False, default=30, server_default="30")
    cursor: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    cursor_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    backfill_cursor: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    checkpoint_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    schedule_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    policy: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict, server_default=text("'{}'"))
    next_run_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    last_run_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    last_success_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    watermarked_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    watermark_remote_ids: Mapped[list[str]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
        server_default=text("'[]'"),
    )
    consecutive_failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

    account: Mapped[Account] = relationship(back_populates="subscriptions")
    author: Mapped[Author] = relationship(back_populates="subscriptions")
    sync_runs: Mapped[list[SyncRun]] = relationship(
        back_populates="subscription",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    asset_refresh_sources: Mapped[list[AssetRefreshSource]] = relationship(
        back_populates="subscription",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class Content(TimestampMixin, Base):
    __tablename__ = "contents"
    __table_args__ = (
        UniqueConstraint("platform", "remote_type", "remote_id"),
        CheckConstraint(f"platform IN ({_quoted_values(PLATFORMS)})", name="platform"),
        CheckConstraint(f"kind IN ({_quoted_values(CONTENT_KINDS)})", name="kind"),
        Index("ix_contents_author_published_at", "author_id", "published_at"),
        Index("ix_contents_platform_kind", "platform", "kind"),
        Index("ix_contents_last_seen_at", "last_seen_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    author_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("authors.id", ondelete="CASCADE"),
        nullable=False,
    )
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    remote_type: Mapped[str] = mapped_column(String(64), nullable=False, default="content", server_default="content")
    remote_id: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str | None] = mapped_column(Text)
    body: Mapped[str | None] = mapped_column(Text)
    canonical_url: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    remote_updated_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict, server_default=text("'{}'"))
    raw: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict, server_default=text("'{}'"))
    metadata_hash: Mapped[str | None] = mapped_column(String(64))
    first_seen_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utc_now)
    last_seen_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utc_now)
    tombstoned_at: Mapped[datetime | None] = mapped_column(UTCDateTime())

    author: Mapped[Author] = relationship(back_populates="contents")
    assets: Mapped[list[Asset]] = relationship(
        back_populates="content",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    export_records: Mapped[list[ExportRecord]] = relationship(
        back_populates="content",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class Asset(TimestampMixin, Base):
    __tablename__ = "assets"
    __table_args__ = (
        UniqueConstraint("content_id", "kind", "position"),
        CheckConstraint(f"platform IN ({_quoted_values(PLATFORMS)})", name="platform"),
        CheckConstraint(f"kind IN ({_quoted_values(ASSET_KINDS)})", name="kind"),
        CheckConstraint(f"status IN ({_quoted_values(ASSET_STATUSES)})", name="status"),
        CheckConstraint("position >= 0", name="position_nonnegative"),
        CheckConstraint("generation >= 1", name="generation_positive"),
        CheckConstraint("size_bytes IS NULL OR size_bytes >= 0", name="size_bytes_nonnegative"),
        Index("ix_assets_status", "status"),
        Index("ix_assets_download_job_id", "download_job_id"),
        Index("ix_assets_checksum_sha256", "checksum_sha256"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    content_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("contents.id", ondelete="CASCADE"),
        nullable=False,
    )
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    remote_id: Mapped[str | None] = mapped_column(String(512))
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    source_url: Mapped[str | None] = mapped_column(Text)
    locator: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict, server_default=text("'{}'"))
    semantic_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    locator_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    generation: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    mime_type: Mapped[str | None] = mapped_column(String(255))
    size_bytes: Mapped[int | None] = mapped_column(Integer)
    checksum_sha256: Mapped[str | None] = mapped_column(String(64))
    local_path: Mapped[str | None] = mapped_column(Text)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    download_job_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("jobs.id", ondelete="SET NULL"),
    )
    etag: Mapped[str | None] = mapped_column(String(512))
    last_modified: Mapped[str | None] = mapped_column(String(255))
    queued_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    download_started_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    downloaded_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    verified_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    last_error_code: Mapped[str | None] = mapped_column(String(128))
    last_error_message: Mapped[str | None] = mapped_column(Text)
    last_error_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="discovered",
        server_default="discovered",
    )
    raw: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict, server_default=text("'{}'"))

    content: Mapped[Content] = relationship(back_populates="assets")
    refresh_sources: Mapped[list[AssetRefreshSource]] = relationship(
        back_populates="asset",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class SyncRun(TimestampMixin, Base):
    __tablename__ = "sync_runs"
    __table_args__ = (
        CheckConstraint(f"status IN ({_quoted_values(RUN_STATUSES)})", name="status"),
        CheckConstraint("attempt >= 0", name="attempt_nonnegative"),
        CheckConstraint("discovered_count >= 0", name="discovered_count_nonnegative"),
        CheckConstraint("updated_count >= 0", name="updated_count_nonnegative"),
        CheckConstraint("asset_count >= 0", name="asset_count_nonnegative"),
        CheckConstraint("event_sequence >= 0", name="event_sequence_nonnegative"),
        CheckConstraint(
            "checkpoint_revision_before IS NULL OR checkpoint_revision_before >= 0",
            name="checkpoint_revision_before_nonnegative",
        ),
        CheckConstraint(
            "checkpoint_revision_after IS NULL OR checkpoint_revision_after >= 0",
            name="checkpoint_revision_after_nonnegative",
        ),
        Index("ix_sync_runs_subscription_status", "subscription_id", "status"),
        Index("ix_sync_runs_created_at", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    subscription_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("subscriptions.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued", server_default="queued")
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    cursor_before: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    cursor_after: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    checkpoint_revision_before: Mapped[int | None] = mapped_column(Integer)
    checkpoint_revision_after: Mapped[int | None] = mapped_column(Integer)
    manifest: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict, server_default=text("'{}'"))
    discovered_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    updated_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    asset_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    event_sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    error_code: Mapped[str | None] = mapped_column(String(128))
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime())

    subscription: Mapped[Subscription] = relationship(back_populates="sync_runs")
    events: Mapped[list[RunEvent]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="RunEvent.sequence",
    )
    jobs: Mapped[list[Job]] = relationship(back_populates="run", passive_deletes=True)
    asset_refresh_sources: Mapped[list[AssetRefreshSource]] = relationship(
        back_populates="last_run",
        passive_deletes=True,
    )


class AssetRefreshSource(Base):
    """One account subscription's durable observation of an asset identity."""

    __tablename__ = "asset_refresh_sources"
    __table_args__ = (
        CheckConstraint(
            f"observation_kind IN ({_quoted_values(ASSET_REFRESH_OBSERVATION_KINDS)})",
            name="observation_kind",
        ),
        CheckConstraint("observed_generation >= 1", name="observed_generation_positive"),
        CheckConstraint(
            "length(observed_semantic_fingerprint) = 64 "
            "AND lower(observed_semantic_fingerprint) = observed_semantic_fingerprint",
            name="observed_semantic_fingerprint_shape",
        ),
        CheckConstraint(
            "length(observed_locator_fingerprint) = 64 "
            "AND lower(observed_locator_fingerprint) = observed_locator_fingerprint",
            name="observed_locator_fingerprint_shape",
        ),
        CheckConstraint("last_seen_at >= first_seen_at", name="seen_at_order"),
        Index("ix_asset_refresh_sources_subscription_id", "subscription_id"),
        Index(
            "ix_asset_refresh_sources_asset_fingerprints",
            "asset_id",
            "observed_semantic_fingerprint",
            "observed_locator_fingerprint",
        ),
    )

    asset_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("assets.id", ondelete="CASCADE"),
        primary_key=True,
    )
    subscription_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("subscriptions.id", ondelete="CASCADE"),
        primary_key=True,
    )
    last_run_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("sync_runs.id", ondelete="SET NULL"),
    )
    observation_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    observed_generation: Mapped[int] = mapped_column(Integer, nullable=False)
    observed_semantic_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    observed_locator_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        default=utc_now,
        server_default=text("CURRENT_TIMESTAMP"),
        nullable=False,
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        default=utc_now,
        server_default=text("CURRENT_TIMESTAMP"),
        nullable=False,
    )

    asset: Mapped[Asset] = relationship(back_populates="refresh_sources")
    subscription: Mapped[Subscription] = relationship(back_populates="asset_refresh_sources")
    last_run: Mapped[SyncRun | None] = relationship(back_populates="asset_refresh_sources")


class RunEvent(Base):
    __tablename__ = "run_events"
    __table_args__ = (
        UniqueConstraint("run_id", "sequence"),
        Index("ix_run_events_run_created_at", "run_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    run_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("sync_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(32))
    to_status: Mapped[str | None] = mapped_column(String(32))
    message: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict, server_default=text("'{}'"))
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        default=utc_now,
        server_default=text("CURRENT_TIMESTAMP"),
        nullable=False,
    )

    run: Mapped[SyncRun] = relationship(back_populates="events")


class Job(TimestampMixin, Base):
    __tablename__ = "jobs"
    _active_sync_predicate = (
        "job_type = 'sync.subscription' AND subscription_id IS NOT NULL AND status IN ("
        f"{_quoted_values(ACTIVE_SYNC_JOB_STATUSES)})"
    )
    __table_args__ = (
        UniqueConstraint("job_type", "natural_key"),
        CheckConstraint(f"status IN ({_quoted_values(JOB_STATUSES)})", name="status"),
        CheckConstraint("attempts >= 0", name="attempts_nonnegative"),
        CheckConstraint("max_attempts >= 1", name="max_attempts_positive"),
        CheckConstraint(f"platform IS NULL OR platform IN ({_quoted_values(PLATFORMS)})", name="platform"),
        Index("ix_jobs_claimable", "status", "available_at", "priority"),
        Index("ix_jobs_scheduler_claim", "job_type", "status", "available_at", "priority", "scheduled_for"),
        Index("ix_jobs_subscription_scope", "subscription_id", "job_type", "status", "scheduled_for"),
        Index("ix_jobs_account_scope", "account_id", "job_type", "status", "lease_expires_at"),
        Index("ix_jobs_platform_scope", "platform", "job_type", "status", "lease_expires_at"),
        Index(
            "uq_jobs_active_sync_subscription",
            "subscription_id",
            unique=True,
            sqlite_where=text(_active_sync_predicate),
            postgresql_where=text(_active_sync_predicate),
        ),
        Index("ix_jobs_lease_expires_at", "lease_expires_at"),
        Index("ix_jobs_run_id", "run_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    run_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("sync_runs.id", ondelete="SET NULL"))
    subscription_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("subscriptions.id", ondelete="CASCADE"),
    )
    account_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("accounts.id", ondelete="CASCADE"),
    )
    platform: Mapped[str | None] = mapped_column(String(32))
    job_type: Mapped[str] = mapped_column(String(128), nullable=False)
    natural_key: Mapped[str] = mapped_column(String(512), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict, server_default=text("'{}'"))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued", server_default="queued")
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=5, server_default="5")
    available_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utc_now)
    scheduled_for: Mapped[datetime | None] = mapped_column(UTCDateTime())
    lease_owner: Mapped[str | None] = mapped_column(String(255))
    lease_token: Mapped[str | None] = mapped_column(String(36))
    lease_expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    last_error_code: Mapped[str | None] = mapped_column(String(128))
    last_error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime())

    run: Mapped[SyncRun | None] = relationship(back_populates="jobs")


class SchedulerLane(TimestampMixin, Base):
    __tablename__ = "scheduler_lanes"
    __table_args__ = (
        CheckConstraint(f"scope_type IN ({_quoted_values(SCHEDULER_LANE_SCOPE_TYPES)})", name="scope_type"),
        CheckConstraint(
            "(scope_type = 'platform' AND account_id IS NULL) OR (scope_type = 'account' AND account_id IS NOT NULL)",
            name="scope_shape",
        ),
        CheckConstraint(f"platform IN ({_quoted_values(PLATFORMS)})", name="platform"),
        CheckConstraint("max_concurrency >= 1", name="max_concurrency_positive"),
        CheckConstraint(
            "min_start_interval_seconds >= 0",
            name="min_start_interval_seconds_nonnegative",
        ),
        CheckConstraint("failure_threshold >= 1", name="failure_threshold_positive"),
        CheckConstraint("cooldown_seconds >= 1", name="cooldown_seconds_positive"),
        CheckConstraint("consecutive_failures >= 0", name="consecutive_failures_nonnegative"),
        CheckConstraint(f"circuit_state IN ({_quoted_values(CIRCUIT_STATES)})", name="circuit_state"),
        CheckConstraint("revision >= 0", name="revision_nonnegative"),
        Index(
            "uq_scheduler_lanes_platform",
            "platform",
            unique=True,
            sqlite_where=text("scope_type = 'platform'"),
            postgresql_where=text("scope_type = 'platform'"),
        ),
        Index(
            "uq_scheduler_lanes_account",
            "account_id",
            unique=True,
            sqlite_where=text("scope_type = 'account'"),
            postgresql_where=text("scope_type = 'account'"),
        ),
        Index("ix_scheduler_lanes_account_id", "account_id"),
        Index("ix_scheduler_lanes_half_open_job_id", "half_open_job_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    scope_type: Mapped[str] = mapped_column(String(32), nullable=False)
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    account_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("accounts.id", ondelete="CASCADE"),
    )
    max_concurrency: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    min_start_interval_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=5, server_default="5")
    failure_threshold: Mapped[int] = mapped_column(Integer, nullable=False, default=3, server_default="3")
    cooldown_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=900, server_default="900")
    next_start_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    consecutive_failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    circuit_state: Mapped[str] = mapped_column(String(32), nullable=False, default="closed", server_default="closed")
    circuit_open_until: Mapped[datetime | None] = mapped_column(UTCDateTime())
    half_open_job_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("jobs.id", ondelete="SET NULL"),
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")


class OperationEventStreamState(Base):
    """Singleton transactional clock used by the resumable operation stream."""

    __tablename__ = "operation_event_stream_state"
    __table_args__ = (
        CheckConstraint("id = 1", name="singleton"),
        CheckConstraint("last_sequence >= 0", name="last_sequence_nonnegative"),
        CheckConstraint("pruned_through_sequence >= 0", name="pruned_through_sequence_nonnegative"),
        CheckConstraint(
            "pruned_through_sequence <= last_sequence",
            name="pruned_through_not_after_last",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    last_sequence: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default="0")
    pruned_through_sequence: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=0,
        server_default="0",
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        default=utc_now,
        server_default=text("CURRENT_TIMESTAMP"),
        nullable=False,
    )


class Operation(Base):
    """One durable operator request, distinct from Jobs and domain runs."""

    __tablename__ = "operations"
    _active_exclusive_predicate = f"exclusive_key IS NOT NULL AND state IN ({_quoted_values(ACTIVE_OPERATION_STATES)})"
    _idempotency_predicate = "idempotency_key_hash IS NOT NULL"
    _terminal_values = _quoted_values(TERMINAL_OPERATION_STATES)
    _failure_values = _quoted_values(OPERATION_FAILURE_STATES)
    __table_args__ = (
        CheckConstraint(f"kind IN ({_quoted_values(OPERATION_KINDS)})", name="kind"),
        CheckConstraint(f"state IN ({_quoted_values(OPERATION_STATES)})", name="state"),
        CheckConstraint(
            f"target_type IS NULL OR target_type IN ({_quoted_values(OPERATION_SUBJECT_TYPES)})",
            name="target_type",
        ),
        CheckConstraint(
            "(target_type IS NULL AND target_id IS NULL) OR (target_type IS NOT NULL AND target_id IS NOT NULL)",
            name="target_shape",
        ),
        CheckConstraint(
            "idempotency_key_hash IS NULL OR "
            "(length(idempotency_key_hash) = 64 AND lower(idempotency_key_hash) = idempotency_key_hash)",
            name="idempotency_key_hash_shape",
        ),
        CheckConstraint(
            "length(request_fingerprint) = 64 AND lower(request_fingerprint) = request_fingerprint",
            name="request_fingerprint_shape",
        ),
        CheckConstraint("event_sequence >= 0", name="event_sequence_nonnegative"),
        CheckConstraint("revision >= 0", name="revision_nonnegative"),
        CheckConstraint(
            "progress_current IS NULL OR progress_current >= 0",
            name="progress_current_nonnegative",
        ),
        CheckConstraint(
            "progress_total IS NULL OR progress_total >= 0",
            name="progress_total_nonnegative",
        ),
        CheckConstraint(
            "progress_current IS NULL OR progress_total IS NULL OR progress_current <= progress_total",
            name="progress_order",
        ),
        CheckConstraint(
            "progress_unit IS NULL OR progress_current IS NOT NULL OR progress_total IS NOT NULL",
            name="progress_unit_shape",
        ),
        CheckConstraint("started_at IS NULL OR started_at >= requested_at", name="started_at_order"),
        CheckConstraint("finished_at IS NULL OR finished_at >= requested_at", name="finished_at_order"),
        CheckConstraint(
            "cancel_requested_at IS NULL OR cancel_requested_at >= requested_at",
            name="cancel_requested_at_order",
        ),
        CheckConstraint(
            "(state = 'queued' AND started_at IS NULL AND finished_at IS NULL "
            "AND lease_owner IS NULL AND lease_token IS NULL AND lease_expires_at IS NULL) OR "
            "(state = 'running' AND started_at IS NOT NULL AND finished_at IS NULL "
            "AND lease_owner IS NOT NULL AND lease_token IS NOT NULL AND lease_expires_at IS NOT NULL) OR "
            f"(state IN ({_terminal_values}) AND finished_at IS NOT NULL "
            "AND lease_owner IS NULL AND lease_token IS NULL AND lease_expires_at IS NULL)",
            name="lifecycle_shape",
        ),
        CheckConstraint(
            f"(state IN ({_failure_values}) AND error_code IS NOT NULL) OR "
            f"(state NOT IN ({_failure_values}) AND error_code IS NULL)",
            name="error_shape",
        ),
        Index("ix_operations_state_requested_at", "state", "requested_at", "id"),
        Index("ix_operations_lease_recovery", "state", "lease_expires_at", "id"),
        Index("ix_operations_target", "target_type", "target_id", "requested_at"),
        Index("ix_operations_correlation_id", "correlation_id", "requested_at"),
        Index(
            "uq_operations_active_exclusive_key",
            "exclusive_key",
            unique=True,
            sqlite_where=text(_active_exclusive_predicate),
            postgresql_where=text(_active_exclusive_predicate),
        ),
        Index(
            "uq_operations_kind_idempotency_key_hash",
            "kind",
            "idempotency_key_hash",
            unique=True,
            sqlite_where=text(_idempotency_predicate),
            postgresql_where=text(_idempotency_predicate),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="queued", server_default="queued")
    phase: Mapped[str | None] = mapped_column(String(64))
    progress_current: Mapped[int | None] = mapped_column(BigInteger)
    progress_total: Mapped[int | None] = mapped_column(BigInteger)
    progress_unit: Mapped[str | None] = mapped_column(String(32))
    requested_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        default=utc_now,
        server_default=text("CURRENT_TIMESTAMP"),
        nullable=False,
    )
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    requested_by: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        default="local-api",
        server_default="local-api",
    )
    idempotency_key_hash: Mapped[str | None] = mapped_column(String(64))
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    exclusive_key: Mapped[str | None] = mapped_column(String(512))
    target_type: Mapped[str | None] = mapped_column(String(32))
    target_id: Mapped[str | None] = mapped_column(String(36))
    correlation_id: Mapped[str] = mapped_column(String(36), nullable=False, default=new_uuid)
    cancel_requested_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    error_code: Mapped[str | None] = mapped_column(String(128))
    result_summary: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        server_default=text("'{}'"),
    )
    event_sequence: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default="0")
    revision: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default="0")
    lease_owner: Mapped[str | None] = mapped_column(String(255))
    lease_token: Mapped[str | None] = mapped_column(String(36))
    lease_expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        default=utc_now,
        server_default=text("CURRENT_TIMESTAMP"),
        nullable=False,
    )

    events: Mapped[list[OperationEvent]] = relationship(
        back_populates="operation",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="OperationEvent.operation_sequence",
    )
    subjects: Mapped[list[OperationSubject]] = relationship(
        back_populates="operation",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class OperationEvent(Base):
    """Immutable, globally replayable event for one durable Operation."""

    __tablename__ = "operation_events"
    __table_args__ = (
        UniqueConstraint("operation_id", "operation_sequence"),
        CheckConstraint("stream_sequence >= 1", name="stream_sequence_positive"),
        CheckConstraint("operation_sequence >= 1", name="operation_sequence_positive"),
        CheckConstraint(f"level IN ({_quoted_values(OPERATION_EVENT_LEVELS)})", name="level"),
        CheckConstraint(f"event_code IN ({_quoted_values(OPERATION_EVENT_CODES)})", name="event_code"),
        CheckConstraint(
            f"from_state IS NULL OR from_state IN ({_quoted_values(OPERATION_STATES)})",
            name="from_state",
        ),
        CheckConstraint(
            f"to_state IS NULL OR to_state IN ({_quoted_values(OPERATION_STATES)})",
            name="to_state",
        ),
        CheckConstraint(
            f"subject_type IS NULL OR subject_type IN ({_quoted_values(OPERATION_SUBJECT_TYPES)})",
            name="subject_type",
        ),
        CheckConstraint(
            "(subject_type IS NULL AND subject_id IS NULL) OR (subject_type IS NOT NULL AND subject_id IS NOT NULL)",
            name="subject_shape",
        ),
        Index("ix_operation_events_operation_sequence", "operation_id", "operation_sequence"),
        Index("ix_operation_events_subject", "subject_type", "subject_id", "stream_sequence"),
        Index("ix_operation_events_at", "at", "stream_sequence"),
    )

    stream_sequence: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    operation_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("operations.id", ondelete="CASCADE"),
        nullable=False,
    )
    operation_sequence: Mapped[int] = mapped_column(BigInteger, nullable=False)
    at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        default=utc_now,
        server_default=text("CURRENT_TIMESTAMP"),
        nullable=False,
    )
    level: Mapped[str] = mapped_column(String(16), nullable=False, default="info", server_default="info")
    event_code: Mapped[str] = mapped_column(String(128), nullable=False)
    from_state: Mapped[str | None] = mapped_column(String(32))
    to_state: Mapped[str | None] = mapped_column(String(32))
    phase: Mapped[str | None] = mapped_column(String(64))
    message_key: Mapped[str | None] = mapped_column(String(128))
    subject_type: Mapped[str | None] = mapped_column(String(32))
    subject_id: Mapped[str | None] = mapped_column(String(36))
    safe_context: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        server_default=text("'{}'"),
    )

    operation: Mapped[Operation] = relationship(back_populates="events")


class OperationSubject(Base):
    """Bounded polymorphic association retained independently of domain rows."""

    __tablename__ = "operation_subjects"
    __table_args__ = (
        CheckConstraint(f"subject_type IN ({_quoted_values(OPERATION_SUBJECT_TYPES)})", name="subject_type"),
        CheckConstraint(f"role IN ({_quoted_values(OPERATION_SUBJECT_ROLES)})", name="role"),
        Index("ix_operation_subjects_subject", "subject_type", "subject_id", "operation_id"),
    )

    operation_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("operations.id", ondelete="CASCADE"),
        primary_key=True,
    )
    subject_type: Mapped[str] = mapped_column(String(32), primary_key=True)
    subject_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    role: Mapped[str] = mapped_column(String(32), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        default=utc_now,
        server_default=text("CURRENT_TIMESTAMP"),
        nullable=False,
    )

    operation: Mapped[Operation] = relationship(back_populates="subjects")


@event.listens_for(OperationEventStreamState.__table__, "after_create")
def _seed_operation_event_stream_state(target: Any, connection: Any, **_: Any) -> None:
    """Make ``Base.metadata.create_all`` as usable as the packaged migration."""

    connection.execute(
        target.insert().values(
            id=1,
            last_sequence=0,
            pruned_through_sequence=0,
            updated_at=utc_now(),
        )
    )


class ExportRecord(TimestampMixin, Base):
    __tablename__ = "export_records"
    __table_args__ = (
        UniqueConstraint("content_id", "exporter", "exporter_version", "source_fingerprint"),
        Index("ix_export_records_content_exporter", "content_id", "exporter"),
        Index("ix_export_records_status", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    content_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("contents.id", ondelete="CASCADE"),
        nullable=False,
    )
    exporter: Mapped[str] = mapped_column(String(64), nullable=False, default="emby", server_default="emby")
    exporter_version: Mapped[str] = mapped_column(String(32), nullable=False)
    source_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    output_path: Mapped[str] = mapped_column(Text, nullable=False)
    rendered_fingerprint: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", server_default="pending")
    error_message: Mapped[str | None] = mapped_column(Text)
    exported_at: Mapped[datetime | None] = mapped_column(UTCDateTime())

    content: Mapped[Content] = relationship(back_populates="export_records")


__all__ = [
    "ACTIVE_OPERATION_STATES",
    "ACTIVE_SYNC_JOB_STATUSES",
    "ASSET_KINDS",
    "ASSET_REFRESH_OBSERVATION_KINDS",
    "ASSET_STATUSES",
    "AUTH_STATUSES",
    "CIRCUIT_STATES",
    "CONTENT_KINDS",
    "JOB_STATUSES",
    "LOGIN_METHODS",
    "LOGIN_SESSION_STATUSES",
    "OPERATION_EVENT_CODES",
    "OPERATION_EVENT_LEVELS",
    "OPERATION_FAILURE_STATES",
    "OPERATION_KINDS",
    "OPERATION_STATES",
    "OPERATION_SUBJECT_ROLES",
    "OPERATION_SUBJECT_TYPES",
    "PLATFORMS",
    "RUN_STATUSES",
    "SCHEDULER_LANE_SCOPE_TYPES",
    "TERMINAL_JOB_STATUSES",
    "TERMINAL_OPERATION_STATES",
    "TERMINAL_RUN_STATUSES",
    "Account",
    "Asset",
    "AssetRefreshSource",
    "Author",
    "Content",
    "ExportRecord",
    "Job",
    "LoginSession",
    "Operation",
    "OperationEvent",
    "OperationEventStreamState",
    "OperationSubject",
    "RunEvent",
    "SchedulerLane",
    "Subscription",
    "SyncRun",
]
