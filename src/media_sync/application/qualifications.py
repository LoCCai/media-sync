"""Evidence-only qualification projection for the local control plane.

Automated rows describe durable facts already present in the local database.
They deliberately cannot promote a live, operator-observed qualification: the
current schema has no authenticated evidence ledger for that assertion.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Final, Literal, TypeAlias

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from media_sync.domain import Platform
from media_sync.infrastructure.db import (
    Account,
    Asset,
    Author,
    Content,
    Database,
    ExportRecord,
    OperationSnapshot,
    Subscription,
    SyncRun,
)

HumanQualificationStatus: TypeAlias = Literal["PASS", "FAIL", "NOT_RUN", "BLOCKED_EXTERNAL"]
ImplementationStatus: TypeAlias = Literal["IMPLEMENTED", "NOT_IMPLEMENTED"]

QUALIFICATION_SCHEMA_VERSION: Final = 2
HUMAN_QUALIFICATION_STATUSES: Final = frozenset({"PASS", "FAIL", "NOT_RUN", "BLOCKED_EXTERNAL"})
IMPLEMENTATION_STATUSES: Final = frozenset({"IMPLEMENTED", "NOT_IMPLEMENTED"})
_PLATFORM_ORDER: Final = tuple(platform.value for platform in Platform)

_PLATFORM_CAPABILITIES: Final = (
    "account_login",
    "creator_subscription",
    "content_capture",
    "media_download",
    "emby_export",
)
_MEDIA_SERVER_IMPLEMENTED: Final = (
    "connection_probe",
    "library_discovery",
    "targeted_scan_acceptance",
    "item_lookup",
    "post_refresh_item_observation",
)
_MEDIA_SERVER_NOT_IMPLEMENTED: Final = (
    "playback_evidence",
    "automatic_post_export_scan",
)


class QualificationError(RuntimeError):
    """A fixed-code qualification read failure safe for an API boundary."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _human_capability(
    name: str,
    implementation: ImplementationStatus,
    *,
    reason: Literal["provider_api_unsupported"] | None = None,
) -> dict[str, object]:
    capability: dict[str, object] = {
        "capability": name,
        "implementation_status": implementation,
        # An unimplemented capability cannot have a live qualification run.
        "human_status": "NOT_RUN" if implementation == "IMPLEMENTED" else None,
    }
    if reason is not None:
        capability["reason"] = reason
    return capability


def _counts_by_platform(rows: Sequence[tuple[str, int]]) -> dict[str, int]:
    counts = dict.fromkeys(_PLATFORM_ORDER, 0)
    for platform, value in rows:
        if platform in counts:
            counts[platform] = int(value)
    return counts


def _operation_evidence(operation: OperationSnapshot | None) -> dict[str, object] | None:
    if operation is None:
        return None
    return {
        "operation_id": operation.id,
        "state": operation.state,
        "finished_at": operation.finished_at.astimezone(UTC).isoformat() if operation.finished_at else None,
        "error_code": operation.error_code,
        "result": dict(operation.result_summary) if operation.result_summary else None,
    }


class QualificationService:
    """Build schema-v2 evidence without inferring live qualification PASS."""

    def __init__(self, database: Database) -> None:
        if not isinstance(database, Database):
            raise TypeError("database must be a Database")
        self._database = database

    def snapshot(
        self,
        *,
        media_server_configured: bool,
        media_server_operations: Mapping[str, OperationSnapshot | None] | None = None,
        generated_at: datetime | None = None,
    ) -> dict[str, object]:
        """Return bounded counts and explicit human/implementation states."""

        if type(media_server_configured) is not bool:
            raise TypeError("media_server_configured must be a bool")
        current = generated_at or datetime.now(UTC)
        if current.tzinfo is None or current.utcoffset() is None:
            raise ValueError("generated_at must be timezone-aware")

        try:
            counts = self._platform_counts()
        except SQLAlchemyError:
            raise QualificationError("qualification_store_unavailable") from None

        platforms = [
            {
                "platform": platform,
                "automated_evidence": {name: values[platform] for name, values in counts.items()},
                "human_qualification": [
                    _human_capability(capability, "IMPLEMENTED") for capability in _PLATFORM_CAPABILITIES
                ],
            }
            for platform in _PLATFORM_ORDER
        ]

        operations = media_server_operations or {}
        probe = operations.get("media-server-probe")
        scan = operations.get("media-server-scan")
        media_server = {
            "configured": media_server_configured,
            "automated_evidence": {
                "latest_probe": _operation_evidence(probe),
                "latest_targeted_scan": _operation_evidence(scan),
            },
            "human_qualification": [
                *(_human_capability(capability, "IMPLEMENTED") for capability in _MEDIA_SERVER_IMPLEMENTED),
                _human_capability(
                    "provider_task_completion",
                    "NOT_IMPLEMENTED",
                    reason="provider_api_unsupported",
                ),
                *(_human_capability(capability, "NOT_IMPLEMENTED") for capability in _MEDIA_SERVER_NOT_IMPLEMENTED),
            ],
        }
        return {
            "schema_version": QUALIFICATION_SCHEMA_VERSION,
            "generated_at": current.astimezone(UTC).isoformat(),
            "policy": {
                "automated_evidence_confers_human_pass": False,
                "human_statuses": sorted(HUMAN_QUALIFICATION_STATUSES),
                "implementation_statuses": sorted(IMPLEMENTATION_STATUSES),
            },
            "platforms": platforms,
            "media_server": media_server,
        }

    def _platform_counts(self) -> dict[str, dict[str, int]]:
        with self._database.session() as session:
            accounts = _counts_by_platform(
                session.execute(select(Account.platform, func.count(Account.id)).group_by(Account.platform))
                .tuples()
                .all()
            )
            authenticated_accounts = _counts_by_platform(
                session.execute(
                    select(Account.platform, func.count(Account.id))
                    .where(Account.auth_status == "authenticated")
                    .group_by(Account.platform)
                )
                .tuples()
                .all()
            )
            subscriptions = _counts_by_platform(
                session.execute(
                    select(Author.platform, func.count(Subscription.id))
                    .join(Subscription, Subscription.author_id == Author.id)
                    .group_by(Author.platform)
                )
                .tuples()
                .all()
            )
            successful_sync_runs = _counts_by_platform(
                session.execute(
                    select(Author.platform, func.count(SyncRun.id))
                    .join(Subscription, SyncRun.subscription_id == Subscription.id)
                    .join(Author, Subscription.author_id == Author.id)
                    .where(SyncRun.status == "succeeded")
                    .group_by(Author.platform)
                )
                .tuples()
                .all()
            )
            contents = _counts_by_platform(
                session.execute(select(Content.platform, func.count(Content.id)).group_by(Content.platform))
                .tuples()
                .all()
            )
            verified_assets = _counts_by_platform(
                session.execute(
                    select(Asset.platform, func.count(Asset.id))
                    .where(Asset.status.in_(("verified", "exported")))
                    .group_by(Asset.platform)
                )
                .tuples()
                .all()
            )
            succeeded_exports = _counts_by_platform(
                session.execute(
                    select(Content.platform, func.count(ExportRecord.id))
                    .join(ExportRecord, ExportRecord.content_id == Content.id)
                    .where(ExportRecord.status == "succeeded")
                    .group_by(Content.platform)
                )
                .tuples()
                .all()
            )
        return {
            "account_count": accounts,
            "authenticated_account_count": authenticated_accounts,
            "subscription_count": subscriptions,
            "successful_sync_run_count": successful_sync_runs,
            "content_count": contents,
            "verified_asset_count": verified_assets,
            "successful_export_count": succeeded_exports,
        }


__all__ = [
    "HUMAN_QUALIFICATION_STATUSES",
    "IMPLEMENTATION_STATUSES",
    "QUALIFICATION_SCHEMA_VERSION",
    "HumanQualificationStatus",
    "ImplementationStatus",
    "QualificationError",
    "QualificationService",
]
