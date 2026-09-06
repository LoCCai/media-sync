"""Bounded operation diagnostics over safe segments and durable control events."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from media_sync import __version__
from media_sync.config import Settings
from media_sync.infrastructure.db import Database
from media_sync.infrastructure.db.models import (
    OPERATION_EVENT_CODES,
    OPERATION_EVENT_LEVELS,
    OPERATION_KINDS,
    OPERATION_STATES,
    Operation,
    OperationEvent,
    OperationSubject,
)
from media_sync.infrastructure.observability.events import PHASES, canonical_uuid, format_time
from media_sync.infrastructure.observability.store import LogStore
from media_sync.integrations.mediacrawler.login import MediaCrawlerLoginStatus

MAX_DIAGNOSTIC_BYTES = 1_048_576
_SUBJECTS = frozenset({"login_session", "job", "sync_run"})
_ROLES = frozenset({"execution", "result", "related"})
_TARGETS = frozenset({"account", "asset", "author"})
_LOGIN_STATUSES = frozenset(status.value for status in MediaCrawlerLoginStatus)


class LogCenterError(RuntimeError):
    """Fixed public failure; rejected values and exceptions never cross the API."""

    def __init__(self, code: str) -> None:
        self.code = (
            code
            if code
            in {"log_operation_not_found", "log_query_invalid", "log_database_unavailable", "log_diagnostic_too_large"}
            else "log_database_unavailable"
        )
        super().__init__(self.code)


def create_log_store(settings: Settings) -> LogStore:
    return LogStore(
        settings.state_dir / "logs",
        segment_max_bytes=settings.log_segment_max_bytes,
        total_max_bytes=settings.log_total_max_bytes,
        retention_days=settings.log_retention_days,
    )


def _uuid_or_none(value: object) -> str | None:
    try:
        return canonical_uuid(value)
    except ValueError:
        return None


def _time(value: object) -> str | None:
    return format_time(value) if isinstance(value, datetime) and value.tzinfo is not None else None


def _count(value: object) -> int | None:
    return value if type(value) is int and 0 <= value <= 9_007_199_254_740_991 else None


def _upstream_versions(path: Path) -> dict[str, str | None]:
    result: dict[str, str | None] = {"MediaCrawler": None, "bili-sync-up": None}
    try:
        with path.open("rb") as stream:
            data = stream.read(65_537)
        if len(data) > 65_536:
            return result
        payload = json.loads(data)
        if not isinstance(payload, dict) or not isinstance(payload.get("upstreams"), list):
            return result
        for item in payload["upstreams"][:8]:
            if not isinstance(item, dict):
                continue
            name, commit = item.get("name"), item.get("commit")
            if type(name) is str and name in result and type(commit) is str and re.fullmatch(r"[0-9a-f]{40}", commit):
                result[name] = commit
    except (OSError, ValueError, TypeError):
        pass
    return result


class LogCenterService:
    def __init__(self, database: Database, store: LogStore, settings: Settings) -> None:
        self._database = database
        self._store = store
        self._settings = settings

    def operation_trace(self, operation_id: str) -> dict[str, object]:
        """Snapshot fixed columns only; no payload, free phase/error strings or credentials."""
        if _uuid_or_none(operation_id) is None:
            raise LogCenterError("log_query_invalid")
        try:
            with self._database.session() as session:
                row = session.execute(
                    select(
                        Operation.id,
                        Operation.kind,
                        Operation.state,
                        Operation.revision,
                        Operation.correlation_id,
                        Operation.target_type,
                        Operation.target_id,
                        Operation.phase,
                        Operation.requested_at,
                        Operation.started_at,
                        Operation.finished_at,
                        Operation.result_summary["runner_status"].as_string(),
                    ).where(Operation.id == operation_id)
                ).first()
                if row is None:
                    raise LogCenterError("log_operation_not_found")
                control_rows = session.execute(
                    select(
                        OperationEvent.operation_sequence,
                        OperationEvent.at,
                        OperationEvent.event_code,
                        OperationEvent.level,
                        OperationEvent.phase,
                        OperationEvent.from_state,
                        OperationEvent.to_state,
                    )
                    .where(OperationEvent.operation_id == operation_id)
                    .order_by(OperationEvent.operation_sequence)
                    .limit(201)
                ).all()
                subjects = session.execute(
                    select(
                        OperationSubject.subject_type,
                        OperationSubject.subject_id,
                        OperationSubject.role,
                    )
                    .where(OperationSubject.operation_id == operation_id)
                    .limit(65)
                ).all()
        except SQLAlchemyError:
            raise LogCenterError("log_database_unavailable") from None

        operation = {
            "id": operation_id,
            "kind": row.kind if row.kind in OPERATION_KINDS else "unknown",
            "state": row.state if row.state in OPERATION_STATES else "unknown",
            "revision": _count(row.revision),
            "correlation_id": _uuid_or_none(row.correlation_id),
            "target_type": row.target_type if row.target_type in _TARGETS else None,
            "target_id": _uuid_or_none(row.target_id),
            "phase": row.phase if row.phase in PHASES else "unknown",
            "requested_at": _time(row.requested_at),
            "started_at": _time(row.started_at),
            "finished_at": _time(row.finished_at),
            "runner_status": row[11] if row[11] in _LOGIN_STATUSES else None,
        }
        controls = [
            {
                "sequence": _count(event.operation_sequence),
                "at": _time(event.at),
                "event_code": event.event_code if event.event_code in OPERATION_EVENT_CODES else "unknown",
                "level": event.level if event.level in OPERATION_EVENT_LEVELS else "info",
                "phase": event.phase if event.phase in PHASES else "unknown",
                "from_state": event.from_state if event.from_state in OPERATION_STATES else None,
                "to_state": event.to_state if event.to_state in OPERATION_STATES else None,
            }
            for event in control_rows[:200]
        ]
        safe_subjects = [
            {"type": subject.subject_type, "id": identifier, "role": subject.role}
            for subject in subjects[:64]
            if subject.subject_type in _SUBJECTS
            and subject.role in _ROLES
            and (identifier := _uuid_or_none(subject.subject_id)) is not None
        ]
        page = self._store.query(operation_id=operation_id, limit=200)
        events = page.get("events", [])
        stage_seen = isinstance(events, list) and any(
            isinstance(event, dict) and event.get("event_code") == "login_stage" for event in events
        )
        return {
            "schema_version": 1,
            "generated_at": format_time(datetime.now(UTC)),
            "operation": operation,
            "subjects": safe_subjects,
            "subjects_truncated": len(subjects) > 64,
            "control_events": controls,
            "control_events_truncated": len(control_rows) > 200,
            "logs": page,
            "login_stage_evidence": "available_in_page" if stage_seen else "not_recorded_or_not_in_retained_page",
            "consistency": "bounded_observation_not_atomic",
            "authentication_authority": "durable_account_state_only",
        }

    def diagnostic_bytes(self, operation_id: str) -> bytes:
        document = {
            "diagnostic_schema_version": 1,
            "project": {"name": "media-sync", "version": __version__},
            "upstreams": _upstream_versions(self._settings.mediacrawler_lock_path),
            "trace": self.operation_trace(operation_id),
            "logging": self._store.status(),
            "limitations": ["bounded_retained_page", "no_raw_output_or_credentials", "not_live_qualification"],
        }
        encoded = json.dumps(document, ensure_ascii=True, separators=(",", ":"), allow_nan=False).encode("ascii")
        if len(encoded) > MAX_DIAGNOSTIC_BYTES:
            raise LogCenterError("log_diagnostic_too_large")
        return encoded


__all__ = ["MAX_DIAGNOSTIC_BYTES", "LogCenterError", "LogCenterService", "create_log_store"]
