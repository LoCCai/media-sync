"""Relational persistence models for the platform-independent core."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
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
        CheckConstraint("size_bytes IS NULL OR size_bytes >= 0", name="size_bytes_nonnegative"),
        Index("ix_assets_status", "status"),
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
    mime_type: Mapped[str | None] = mapped_column(String(255))
    size_bytes: Mapped[int | None] = mapped_column(Integer)
    checksum_sha256: Mapped[str | None] = mapped_column(String(64))
    local_path: Mapped[str | None] = mapped_column(Text)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="discovered",
        server_default="discovered",
    )
    raw: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict, server_default=text("'{}'"))

    content: Mapped[Content] = relationship(back_populates="assets")


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
    __table_args__ = (
        UniqueConstraint("job_type", "natural_key"),
        CheckConstraint(f"status IN ({_quoted_values(JOB_STATUSES)})", name="status"),
        CheckConstraint("attempts >= 0", name="attempts_nonnegative"),
        CheckConstraint("max_attempts >= 1", name="max_attempts_positive"),
        Index("ix_jobs_claimable", "status", "available_at", "priority"),
        Index("ix_jobs_lease_expires_at", "lease_expires_at"),
        Index("ix_jobs_run_id", "run_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    run_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("sync_runs.id", ondelete="SET NULL"))
    job_type: Mapped[str] = mapped_column(String(128), nullable=False)
    natural_key: Mapped[str] = mapped_column(String(512), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict, server_default=text("'{}'"))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued", server_default="queued")
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=5, server_default="5")
    available_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utc_now)
    lease_owner: Mapped[str | None] = mapped_column(String(255))
    lease_token: Mapped[str | None] = mapped_column(String(36))
    lease_expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    last_error_code: Mapped[str | None] = mapped_column(String(128))
    last_error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime())

    run: Mapped[SyncRun | None] = relationship(back_populates="jobs")


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
    "ASSET_KINDS",
    "ASSET_STATUSES",
    "AUTH_STATUSES",
    "CONTENT_KINDS",
    "JOB_STATUSES",
    "LOGIN_METHODS",
    "LOGIN_SESSION_STATUSES",
    "PLATFORMS",
    "RUN_STATUSES",
    "TERMINAL_JOB_STATUSES",
    "TERMINAL_RUN_STATUSES",
    "Account",
    "Asset",
    "Author",
    "Content",
    "ExportRecord",
    "Job",
    "LoginSession",
    "RunEvent",
    "Subscription",
    "SyncRun",
]
