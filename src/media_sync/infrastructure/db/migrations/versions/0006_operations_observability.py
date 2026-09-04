"""Add durable operations and a transactionally ordered event stream.

Revision ID: 0006_operations_observability
Revises: 0005_asset_refresh_sources
Create Date: 2026-09-04
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_operations_observability"
down_revision: str | None = "0005_asset_refresh_sources"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ACTIVE_EXCLUSIVE_PREDICATE = "exclusive_key IS NOT NULL AND state IN ('queued', 'running')"
_IDEMPOTENCY_PREDICATE = "idempotency_key_hash IS NOT NULL"
_FAILURE_STATES = "'failed_retryable', 'failed_terminal', 'interrupted'"
_TERMINAL_STATES = "'cancelled', 'failed_retryable', 'failed_terminal', 'interrupted', 'succeeded'"


def upgrade() -> None:
    stream_state = op.create_table(
        "operation_event_stream_state",
        sa.Column("id", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("last_sequence", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("pruned_through_sequence", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint("id = 1", name=op.f("ck_operation_event_stream_state_singleton")),
        sa.CheckConstraint(
            "last_sequence >= 0",
            name=op.f("ck_operation_event_stream_state_last_sequence_nonnegative"),
        ),
        sa.CheckConstraint(
            "pruned_through_sequence >= 0",
            name=op.f("ck_operation_event_stream_state_pruned_through_sequence_nonnegative"),
        ),
        sa.CheckConstraint(
            "pruned_through_sequence <= last_sequence",
            name=op.f("ck_operation_event_stream_state_pruned_through_not_after_last"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_operation_event_stream_state")),
    )
    op.bulk_insert(
        stream_state,
        [{"id": 1, "last_sequence": 0, "pruned_through_sequence": 0}],
    )

    op.create_table(
        "operations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("state", sa.String(length=32), server_default="queued", nullable=False),
        sa.Column("phase", sa.String(length=64), nullable=True),
        sa.Column("progress_current", sa.BigInteger(), nullable=True),
        sa.Column("progress_total", sa.BigInteger(), nullable=True),
        sa.Column("progress_unit", sa.String(length=32), nullable=True),
        sa.Column(
            "requested_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("requested_by", sa.String(length=128), server_default="local-api", nullable=False),
        sa.Column("idempotency_key_hash", sa.String(length=64), nullable=True),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("exclusive_key", sa.String(length=512), nullable=True),
        sa.Column("target_type", sa.String(length=32), nullable=True),
        sa.Column("target_id", sa.String(length=36), nullable=True),
        sa.Column("correlation_id", sa.String(length=36), nullable=False),
        sa.Column("cancel_requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(length=128), nullable=True),
        sa.Column("result_summary", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("event_sequence", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("revision", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("lease_owner", sa.String(length=255), nullable=True),
        sa.Column("lease_token", sa.String(length=36), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "kind IN ('account-login', 'asset-download', 'emby-export', 'pipeline-run', 'scheduler-run')",
            name=op.f("ck_operations_kind"),
        ),
        sa.CheckConstraint(
            "state IN ('cancelled', 'failed_retryable', 'failed_terminal', 'interrupted', "
            "'queued', 'running', 'succeeded')",
            name=op.f("ck_operations_state"),
        ),
        sa.CheckConstraint(
            "target_type IS NULL OR target_type IN ('account', 'asset', 'author', 'content', "
            "'export_record', 'job', 'login_session', 'subscription', 'sync_run')",
            name=op.f("ck_operations_target_type"),
        ),
        sa.CheckConstraint(
            "(target_type IS NULL AND target_id IS NULL) OR (target_type IS NOT NULL AND target_id IS NOT NULL)",
            name=op.f("ck_operations_target_shape"),
        ),
        sa.CheckConstraint(
            "idempotency_key_hash IS NULL OR "
            "(length(idempotency_key_hash) = 64 AND lower(idempotency_key_hash) = idempotency_key_hash)",
            name=op.f("ck_operations_idempotency_key_hash_shape"),
        ),
        sa.CheckConstraint(
            "length(request_fingerprint) = 64 AND lower(request_fingerprint) = request_fingerprint",
            name=op.f("ck_operations_request_fingerprint_shape"),
        ),
        sa.CheckConstraint(
            "event_sequence >= 0",
            name=op.f("ck_operations_event_sequence_nonnegative"),
        ),
        sa.CheckConstraint("revision >= 0", name=op.f("ck_operations_revision_nonnegative")),
        sa.CheckConstraint(
            "progress_current IS NULL OR progress_current >= 0",
            name=op.f("ck_operations_progress_current_nonnegative"),
        ),
        sa.CheckConstraint(
            "progress_total IS NULL OR progress_total >= 0",
            name=op.f("ck_operations_progress_total_nonnegative"),
        ),
        sa.CheckConstraint(
            "progress_current IS NULL OR progress_total IS NULL OR progress_current <= progress_total",
            name=op.f("ck_operations_progress_order"),
        ),
        sa.CheckConstraint(
            "progress_unit IS NULL OR progress_current IS NOT NULL OR progress_total IS NOT NULL",
            name=op.f("ck_operations_progress_unit_shape"),
        ),
        sa.CheckConstraint(
            "started_at IS NULL OR started_at >= requested_at",
            name=op.f("ck_operations_started_at_order"),
        ),
        sa.CheckConstraint(
            "finished_at IS NULL OR finished_at >= requested_at",
            name=op.f("ck_operations_finished_at_order"),
        ),
        sa.CheckConstraint(
            "cancel_requested_at IS NULL OR cancel_requested_at >= requested_at",
            name=op.f("ck_operations_cancel_requested_at_order"),
        ),
        sa.CheckConstraint(
            "(state = 'queued' AND started_at IS NULL AND finished_at IS NULL "
            "AND lease_owner IS NULL AND lease_token IS NULL AND lease_expires_at IS NULL) OR "
            "(state = 'running' AND started_at IS NOT NULL AND finished_at IS NULL "
            "AND lease_owner IS NOT NULL AND lease_token IS NOT NULL AND lease_expires_at IS NOT NULL) OR "
            f"(state IN ({_TERMINAL_STATES}) AND finished_at IS NOT NULL "
            "AND lease_owner IS NULL AND lease_token IS NULL AND lease_expires_at IS NULL)",
            name=op.f("ck_operations_lifecycle_shape"),
        ),
        sa.CheckConstraint(
            f"(state IN ({_FAILURE_STATES}) AND error_code IS NOT NULL) OR "
            f"(state NOT IN ({_FAILURE_STATES}) AND error_code IS NULL)",
            name=op.f("ck_operations_error_shape"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_operations")),
    )
    op.create_index(
        "ix_operations_state_requested_at",
        "operations",
        ["state", "requested_at", "id"],
        unique=False,
    )
    op.create_index(
        "ix_operations_lease_recovery",
        "operations",
        ["state", "lease_expires_at", "id"],
        unique=False,
    )
    op.create_index(
        "ix_operations_target",
        "operations",
        ["target_type", "target_id", "requested_at"],
        unique=False,
    )
    op.create_index(
        "ix_operations_correlation_id",
        "operations",
        ["correlation_id", "requested_at"],
        unique=False,
    )
    op.create_index(
        "uq_operations_active_exclusive_key",
        "operations",
        ["exclusive_key"],
        unique=True,
        sqlite_where=sa.text(_ACTIVE_EXCLUSIVE_PREDICATE),
        postgresql_where=sa.text(_ACTIVE_EXCLUSIVE_PREDICATE),
    )
    op.create_index(
        "uq_operations_kind_idempotency_key_hash",
        "operations",
        ["kind", "idempotency_key_hash"],
        unique=True,
        sqlite_where=sa.text(_IDEMPOTENCY_PREDICATE),
        postgresql_where=sa.text(_IDEMPOTENCY_PREDICATE),
    )

    op.create_table(
        "operation_events",
        sa.Column("stream_sequence", sa.BigInteger(), autoincrement=False, nullable=False),
        sa.Column("operation_id", sa.String(length=36), nullable=False),
        sa.Column("operation_sequence", sa.BigInteger(), nullable=False),
        sa.Column(
            "at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("level", sa.String(length=16), server_default="info", nullable=False),
        sa.Column("event_code", sa.String(length=128), nullable=False),
        sa.Column("from_state", sa.String(length=32), nullable=True),
        sa.Column("to_state", sa.String(length=32), nullable=True),
        sa.Column("phase", sa.String(length=64), nullable=True),
        sa.Column("message_key", sa.String(length=128), nullable=True),
        sa.Column("subject_type", sa.String(length=32), nullable=True),
        sa.Column("subject_id", sa.String(length=36), nullable=True),
        sa.Column("safe_context", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.CheckConstraint(
            "stream_sequence >= 1",
            name=op.f("ck_operation_events_stream_sequence_positive"),
        ),
        sa.CheckConstraint(
            "operation_sequence >= 1",
            name=op.f("ck_operation_events_operation_sequence_positive"),
        ),
        sa.CheckConstraint(
            "level IN ('error', 'info', 'warning')",
            name=op.f("ck_operation_events_level"),
        ),
        sa.CheckConstraint(
            "event_code IN ('operation_cancel_observed', 'operation_cancel_requested', "
            "'operation_cancelled', 'operation_entity_linked', 'operation_failed', "
            "'operation_interrupted', 'operation_phase_changed', 'operation_progressed', "
            "'operation_reconciled', 'operation_requested', 'operation_started', 'operation_succeeded')",
            name=op.f("ck_operation_events_event_code"),
        ),
        sa.CheckConstraint(
            "from_state IS NULL OR from_state IN ('cancelled', 'failed_retryable', 'failed_terminal', "
            "'interrupted', 'queued', 'running', 'succeeded')",
            name=op.f("ck_operation_events_from_state"),
        ),
        sa.CheckConstraint(
            "to_state IS NULL OR to_state IN ('cancelled', 'failed_retryable', 'failed_terminal', "
            "'interrupted', 'queued', 'running', 'succeeded')",
            name=op.f("ck_operation_events_to_state"),
        ),
        sa.CheckConstraint(
            "subject_type IS NULL OR subject_type IN ('account', 'asset', 'author', 'content', "
            "'export_record', 'job', 'login_session', 'subscription', 'sync_run')",
            name=op.f("ck_operation_events_subject_type"),
        ),
        sa.CheckConstraint(
            "(subject_type IS NULL AND subject_id IS NULL) OR (subject_type IS NOT NULL AND subject_id IS NOT NULL)",
            name=op.f("ck_operation_events_subject_shape"),
        ),
        sa.ForeignKeyConstraint(
            ["operation_id"],
            ["operations.id"],
            name=op.f("fk_operation_events_operation_id_operations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("stream_sequence", name=op.f("pk_operation_events")),
        sa.UniqueConstraint(
            "operation_id",
            "operation_sequence",
            name=op.f("uq_operation_events_operation_id_operation_sequence"),
        ),
    )
    op.create_index(
        "ix_operation_events_operation_sequence",
        "operation_events",
        ["operation_id", "operation_sequence"],
        unique=False,
    )
    op.create_index(
        "ix_operation_events_subject",
        "operation_events",
        ["subject_type", "subject_id", "stream_sequence"],
        unique=False,
    )
    op.create_index(
        "ix_operation_events_at",
        "operation_events",
        ["at", "stream_sequence"],
        unique=False,
    )

    op.create_table(
        "operation_subjects",
        sa.Column("operation_id", sa.String(length=36), nullable=False),
        sa.Column("subject_type", sa.String(length=32), nullable=False),
        sa.Column("subject_id", sa.String(length=36), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "subject_type IN ('account', 'asset', 'author', 'content', 'export_record', "
            "'job', 'login_session', 'subscription', 'sync_run')",
            name=op.f("ck_operation_subjects_subject_type"),
        ),
        sa.CheckConstraint(
            "role IN ('execution', 'related', 'result', 'target')",
            name=op.f("ck_operation_subjects_role"),
        ),
        sa.ForeignKeyConstraint(
            ["operation_id"],
            ["operations.id"],
            name=op.f("fk_operation_subjects_operation_id_operations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "operation_id",
            "subject_type",
            "subject_id",
            "role",
            name=op.f("pk_operation_subjects"),
        ),
    )
    op.create_index(
        "ix_operation_subjects_subject",
        "operation_subjects",
        ["subject_type", "subject_id", "operation_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_operation_subjects_subject", table_name="operation_subjects")
    op.drop_table("operation_subjects")

    op.drop_index("ix_operation_events_at", table_name="operation_events")
    op.drop_index("ix_operation_events_subject", table_name="operation_events")
    op.drop_index("ix_operation_events_operation_sequence", table_name="operation_events")
    op.drop_table("operation_events")

    op.drop_index("uq_operations_kind_idempotency_key_hash", table_name="operations")
    op.drop_index("uq_operations_active_exclusive_key", table_name="operations")
    op.drop_index("ix_operations_correlation_id", table_name="operations")
    op.drop_index("ix_operations_target", table_name="operations")
    op.drop_index("ix_operations_lease_recovery", table_name="operations")
    op.drop_index("ix_operations_state_requested_at", table_name="operations")
    op.drop_table("operations")

    op.drop_table("operation_event_stream_state")
