"""Add the append-only playback-evidence ledger.

Revision ID: 0008_playback_evidence
Revises: 0007_media_server_operations
Create Date: 2026-09-05
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_playback_evidence"
down_revision: str | None = "0007_media_server_operations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _lower_hex_only(column: str) -> str:
    expression = column
    for character in "0123456789abcdef":
        expression = f"replace({expression}, '{character}', '')"
    return f"{expression} = ''"


def _canonical_uuid_check(column: str) -> str:
    compact = f"replace({column}, '-', '')"
    return (
        f"length({column}) = 36 AND lower({column}) = {column} "
        f"AND substr({column}, 9, 1) = '-' AND substr({column}, 14, 1) = '-' "
        f"AND substr({column}, 19, 1) = '-' AND substr({column}, 24, 1) = '-' "
        f"AND length({compact}) = 32 AND {_lower_hex_only(compact)}"
    )


def _sha256_check(column: str) -> str:
    return f"length({column}) = 64 AND lower({column}) = {column} AND {_lower_hex_only(column)}"


def upgrade() -> None:
    op.create_table(
        "playback_evidence",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("schema_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("author_id", sa.String(length=36), nullable=False),
        sa.Column("publication_job_id", sa.String(length=36), nullable=False),
        sa.Column("profile_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("publication_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("selector_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("item_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("observation_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("schema_version = 1", name=op.f("ck_playback_evidence_schema_version_supported")),
        sa.CheckConstraint(_canonical_uuid_check("id"), name=op.f("ck_playback_evidence_id_canonical_uuid")),
        sa.CheckConstraint(
            _canonical_uuid_check("author_id"),
            name=op.f("ck_playback_evidence_author_id_canonical_uuid"),
        ),
        sa.CheckConstraint(
            _canonical_uuid_check("publication_job_id"),
            name=op.f("ck_playback_evidence_publication_job_id_canonical_uuid"),
        ),
        sa.CheckConstraint(
            _sha256_check("profile_fingerprint"),
            name=op.f("ck_playback_evidence_profile_fingerprint_sha256"),
        ),
        sa.CheckConstraint(
            _sha256_check("publication_fingerprint"),
            name=op.f("ck_playback_evidence_publication_fingerprint_sha256"),
        ),
        sa.CheckConstraint(
            _sha256_check("selector_fingerprint"),
            name=op.f("ck_playback_evidence_selector_fingerprint_sha256"),
        ),
        sa.CheckConstraint(
            _sha256_check("item_fingerprint"),
            name=op.f("ck_playback_evidence_item_fingerprint_sha256"),
        ),
        sa.CheckConstraint(
            _sha256_check("observation_fingerprint"),
            name=op.f("ck_playback_evidence_observation_fingerprint_sha256"),
        ),
        sa.CheckConstraint(
            "observed_at <= confirmed_at",
            name=op.f("ck_playback_evidence_timestamps_ordered"),
        ),
        sa.ForeignKeyConstraint(
            ["author_id"],
            ["authors.id"],
            name=op.f("fk_playback_evidence_author_id_authors"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["publication_job_id"],
            ["jobs.id"],
            name=op.f("fk_playback_evidence_publication_job_id_jobs"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_playback_evidence")),
        sa.UniqueConstraint(
            "observation_fingerprint",
            name=op.f("uq_playback_evidence_observation_fingerprint"),
        ),
    )
    op.create_index(
        "ix_playback_evidence_author_confirmed",
        "playback_evidence",
        ["author_id", "confirmed_at", "id"],
        unique=False,
    )


def downgrade() -> None:
    context = op.get_context()
    if context.as_sql:
        raise RuntimeError("playback_evidence_downgrade_requires_online_audit")

    evidence = sa.table("playback_evidence", sa.column("id", sa.String(length=36)))
    contains_evidence = op.get_bind().execute(sa.select(sa.literal(1)).select_from(evidence).limit(1)).first()
    if contains_evidence is not None:
        raise RuntimeError("playback_evidence_rows_prevent_downgrade")

    op.drop_index("ix_playback_evidence_author_confirmed", table_name="playback_evidence")
    op.drop_table("playback_evidence")
