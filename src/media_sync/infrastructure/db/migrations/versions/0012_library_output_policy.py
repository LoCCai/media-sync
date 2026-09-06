"""Persist shared output policy and immutable author locations.

Revision ID: 0012_library_output_policy
Revises: 0011_cookie_login
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012_library_output_policy"
down_revision: str | None = "0011_cookie_login"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
_PLATFORMS = ("bili", "dy", "ks", "tieba", "wb", "xhs", "zhihu")


def upgrade() -> None:
    # Machine-specific defaults belong to transactional application bootstrap,
    # never to migration execution or metadata creation.
    op.create_table(
        "library_output_policy",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=False),
        sa.Column("revision", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("shared_root", sa.Text(), nullable=False),
        sa.Column("layout", sa.String(32), nullable=False),
        *(sa.Column(f"{platform}_root", sa.Text(), nullable=True) for platform in _PLATFORMS),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")
        ),
        sa.CheckConstraint("id = 1", name="singleton"),
        sa.CheckConstraint("revision >= 0 AND revision <= 9007199254740991", name="revision_range"),
        sa.CheckConstraint("layout IN ('legacy_flat', 'platform_subdirectories')", name="layout"),
        sa.CheckConstraint("length(shared_root) BETWEEN 1 AND 4096", name="shared_root_length"),
        *(
            sa.CheckConstraint(
                f"{platform}_root IS NULL OR length({platform}_root) BETWEEN 1 AND 4096",
                name=f"{platform}_root_length",
            )
            for platform in _PLATFORMS
        ),
    )
    op.create_table(
        "author_output_bindings",
        sa.Column("author_id", sa.String(36), sa.ForeignKey("authors.id", ondelete="RESTRICT"), primary_key=True),
        sa.Column("platform", sa.String(32), nullable=False),
        sa.Column("canonical_root", sa.Text(), nullable=False),
        sa.Column("policy_revision", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")
        ),
        sa.CheckConstraint("platform IN ('bili', 'dy', 'ks', 'tieba', 'wb', 'xhs', 'zhihu')", name="platform"),
        sa.CheckConstraint("length(canonical_root) BETWEEN 1 AND 4096", name="root_length"),
        sa.CheckConstraint("policy_revision >= 0 AND policy_revision <= 9007199254740991", name="revision_range"),
    )
    op.create_index("ix_author_output_bindings_platform", "author_output_bindings", ["platform"])


def downgrade() -> None:
    if op.get_context().as_sql:
        raise RuntimeError("output_policy_downgrade_requires_online_audit")
    connection = op.get_bind()
    for table in ("author_output_bindings", "library_output_policy"):
        if connection.execute(sa.text(f"SELECT 1 FROM {table} LIMIT 1")).first() is not None:
            raise RuntimeError("output_policy_history_prevents_downgrade")
    op.drop_table("author_output_bindings")
    op.drop_table("library_output_policy")
