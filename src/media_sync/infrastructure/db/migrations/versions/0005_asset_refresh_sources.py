"""Add exact subscription provenance for refreshable assets.

Revision ID: 0005_asset_refresh_sources
Revises: 0004_scheduler_control_plane
Create Date: 2026-08-30
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from alembic import op

revision: str = "0005_asset_refresh_sources"
down_revision: str | None = "0004_scheduler_control_plane"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_STABLE_NAME = re.compile(r"[a-z][a-z0-9_.-]{0,63}\Z")
_STABLE_KEY = re.compile(r"[A-Za-z0-9._:/-]{1,255}\Z")
_SECRET_WORDS = frozenset(
    {
        "auth",
        "authorization",
        "cookie",
        "credential",
        "key",
        "password",
        "secret",
        "signature",
        "token",
    }
)


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate locator key")
        result[key] = value
    return result


def _mapping(value: object) -> Mapping[str, Any] | None:
    if isinstance(value, Mapping):
        return value
    if not isinstance(value, str):
        return None
    try:
        decoded = json.loads(value, object_pairs_hook=_reject_duplicate_keys)
    except (TypeError, ValueError):
        return None
    return decoded if isinstance(decoded, Mapping) else None


def _plain_locator_value(value: object, *, name: bool = False) -> str | None:
    if not isinstance(value, str) or value != value.strip():
        return None
    pattern = _STABLE_NAME if name else _STABLE_KEY
    if pattern.fullmatch(value) is None:
        return None
    if frozenset(re.split(r"[._:/-]+", value.lower())) & _SECRET_WORDS:
        return None
    return value


def _mediacrawler_asset_key(value: object) -> str | None:
    locator = _mapping(value)
    if locator is None or set(locator) != {"version", "type", "adapter", "asset_key"}:
        return None
    if type(locator.get("version")) is not int or locator.get("version") != 1:
        return None
    if locator.get("type") != "adapter_refresh":
        return None
    adapter = _plain_locator_value(locator.get("adapter"), name=True)
    asset_key = _plain_locator_value(locator.get("asset_key"))
    if adapter != "mediacrawler":
        return None
    return asset_key


def _stable_asset_key(
    *,
    platform: str,
    content_remote_type: str,
    content_remote_id: str,
    kind: str,
    position: int,
    remote_id: str | None,
) -> str:
    payload = json.dumps(
        {
            "version": 1,
            "platform": platform,
            "content_remote_type": content_remote_type,
            "content_remote_id": content_remote_id,
            "kind": kind,
            "position": position,
            "remote_id": remote_id,
        },
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _legacy_rows(connection: sa.engine.Connection) -> list[dict[str, object]]:
    assets = sa.table(
        "assets",
        sa.column("id", sa.String(36)),
        sa.column("content_id", sa.String(36)),
        sa.column("platform", sa.String(32)),
        sa.column("remote_id", sa.String(512)),
        sa.column("kind", sa.String(32)),
        sa.column("position", sa.Integer()),
        # Read through Text so malformed legacy SQLite JSON is data to reject,
        # not a result-processor exception that aborts the whole migration.
        sa.column("locator", sa.Text()),
        sa.column("semantic_fingerprint", sa.String(64)),
        sa.column("locator_fingerprint", sa.String(64)),
        sa.column("generation", sa.Integer()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    contents = sa.table(
        "contents",
        sa.column("id", sa.String(36)),
        sa.column("author_id", sa.String(36)),
        sa.column("platform", sa.String(32)),
        sa.column("remote_type", sa.String(64)),
        sa.column("remote_id", sa.String(255)),
    )
    authors = sa.table(
        "authors",
        sa.column("id", sa.String(36)),
        sa.column("platform", sa.String(32)),
    )
    subscriptions = sa.table(
        "subscriptions",
        sa.column("id", sa.String(36)),
        sa.column("account_id", sa.String(36)),
        sa.column("author_id", sa.String(36)),
    )
    accounts = sa.table(
        "accounts",
        sa.column("id", sa.String(36)),
        sa.column("platform", sa.String(32)),
        sa.column("adapter", sa.String(128)),
    )

    asset_rows = connection.execute(
        sa.select(
            assets.c.id.label("asset_id"),
            assets.c.platform.label("asset_platform"),
            assets.c.remote_id.label("asset_remote_id"),
            assets.c.kind.label("asset_kind"),
            assets.c.position.label("asset_position"),
            assets.c.locator,
            assets.c.semantic_fingerprint,
            assets.c.locator_fingerprint,
            assets.c.generation,
            assets.c.created_at,
            assets.c.updated_at,
            contents.c.author_id,
            contents.c.platform.label("content_platform"),
            contents.c.remote_type.label("content_remote_type"),
            contents.c.remote_id.label("content_remote_id"),
            authors.c.platform.label("author_platform"),
        )
        .select_from(
            assets.join(contents, contents.c.id == assets.c.content_id).join(
                authors, authors.c.id == contents.c.author_id
            )
        )
        .order_by(assets.c.id)
    ).mappings()

    inferred: list[dict[str, object]] = []
    for row in asset_rows:
        asset_key = _mediacrawler_asset_key(row["locator"])
        generation = row["generation"]
        position = row["asset_position"]
        created_at = row["created_at"]
        updated_at = row["updated_at"]
        if (
            asset_key is None
            or not isinstance(generation, int)
            or isinstance(generation, bool)
            or generation < 1
            or not isinstance(position, int)
            or isinstance(position, bool)
            or position < 0
            or not _is_sha256(row["semantic_fingerprint"])
            or not _is_sha256(row["locator_fingerprint"])
            or not isinstance(created_at, datetime)
            or not isinstance(updated_at, datetime)
        ):
            continue
        asset_platform = row["asset_platform"]
        if (
            not isinstance(asset_platform, str)
            or asset_platform != row["content_platform"]
            or asset_platform != row["author_platform"]
            or not isinstance(row["content_remote_type"], str)
            or not isinstance(row["content_remote_id"], str)
            or not isinstance(row["asset_kind"], str)
            or (row["asset_remote_id"] is not None and not isinstance(row["asset_remote_id"], str))
        ):
            continue
        expected_key = _stable_asset_key(
            platform=asset_platform,
            content_remote_type=row["content_remote_type"],
            content_remote_id=row["content_remote_id"],
            kind=row["asset_kind"],
            position=position,
            remote_id=row["asset_remote_id"],
        )
        if asset_key != expected_key:
            continue

        candidates = list(
            connection.execute(
                sa.select(subscriptions.c.id)
                .select_from(subscriptions.join(accounts, accounts.c.id == subscriptions.c.account_id))
                .where(
                    subscriptions.c.author_id == row["author_id"],
                    accounts.c.platform == asset_platform,
                    accounts.c.adapter == "mediacrawler",
                )
                .order_by(subscriptions.c.id)
            ).scalars()
        )
        if len(candidates) != 1:
            continue
        first_seen_at = created_at
        last_seen_at = updated_at if updated_at >= created_at else created_at
        inferred.append(
            {
                "asset_id": row["asset_id"],
                "subscription_id": candidates[0],
                "last_run_id": None,
                "observation_kind": "legacy_unique_inferred",
                "observed_generation": generation,
                "observed_semantic_fingerprint": row["semantic_fingerprint"],
                "observed_locator_fingerprint": row["locator_fingerprint"],
                "first_seen_at": first_seen_at,
                "last_seen_at": last_seen_at,
            }
        )
    return inferred


def upgrade() -> None:
    refresh_sources = op.create_table(
        "asset_refresh_sources",
        sa.Column("asset_id", sa.String(length=36), nullable=False),
        sa.Column("subscription_id", sa.String(length=36), nullable=False),
        sa.Column("last_run_id", sa.String(length=36), nullable=True),
        sa.Column("observation_kind", sa.String(length=32), nullable=False),
        sa.Column("observed_generation", sa.Integer(), nullable=False),
        sa.Column("observed_semantic_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("observed_locator_fingerprint", sa.String(length=64), nullable=False),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "observation_kind IN ('ingested', 'legacy_unique_inferred')",
            name=op.f("ck_asset_refresh_sources_observation_kind"),
        ),
        sa.CheckConstraint(
            "observed_generation >= 1",
            name=op.f("ck_asset_refresh_sources_observed_generation_positive"),
        ),
        sa.CheckConstraint(
            "length(observed_semantic_fingerprint) = 64 "
            "AND lower(observed_semantic_fingerprint) = observed_semantic_fingerprint",
            name=op.f("ck_asset_refresh_sources_observed_semantic_fingerprint_shape"),
        ),
        sa.CheckConstraint(
            "length(observed_locator_fingerprint) = 64 "
            "AND lower(observed_locator_fingerprint) = observed_locator_fingerprint",
            name=op.f("ck_asset_refresh_sources_observed_locator_fingerprint_shape"),
        ),
        sa.CheckConstraint(
            "last_seen_at >= first_seen_at",
            name=op.f("ck_asset_refresh_sources_seen_at_order"),
        ),
        sa.ForeignKeyConstraint(
            ["asset_id"],
            ["assets.id"],
            name=op.f("fk_asset_refresh_sources_asset_id_assets"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["subscription_id"],
            ["subscriptions.id"],
            name=op.f("fk_asset_refresh_sources_subscription_id_subscriptions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["last_run_id"],
            ["sync_runs.id"],
            name=op.f("fk_asset_refresh_sources_last_run_id_sync_runs"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint(
            "asset_id",
            "subscription_id",
            name=op.f("pk_asset_refresh_sources"),
        ),
    )
    op.create_index(
        "ix_asset_refresh_sources_subscription_id",
        "asset_refresh_sources",
        ["subscription_id"],
        unique=False,
    )
    op.create_index(
        "ix_asset_refresh_sources_asset_fingerprints",
        "asset_refresh_sources",
        ["asset_id", "observed_semantic_fingerprint", "observed_locator_fingerprint"],
        unique=False,
    )

    inferred = _legacy_rows(op.get_bind())
    if inferred:
        op.bulk_insert(refresh_sources, inferred)


def downgrade() -> None:
    op.drop_index(
        "ix_asset_refresh_sources_asset_fingerprints",
        table_name="asset_refresh_sources",
    )
    op.drop_index(
        "ix_asset_refresh_sources_subscription_id",
        table_name="asset_refresh_sources",
    )
    op.drop_table("asset_refresh_sources")
