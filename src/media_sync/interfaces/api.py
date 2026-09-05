"""Authenticated REST API and embedded web console for media-sync administration.

The API mirrors the bounded CLI control surface: accounts (including the
blocking QR login with the QR-image relay for container displays),
subscriptions, durable scheduler/pipeline runs, scheduler Jobs, assets and
Emby export. Every endpoint is a thin projection over the same application
services the CLI uses; no new authority or credential surface is introduced.

The service is local-first and binds ``127.0.0.1`` by default.  A required
single-operator browser credential protects every non-public route; optional
Bearer automation remains separate from the HttpOnly browser session.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import stat
import threading
import time
from collections.abc import AsyncIterator, Mapping, Sequence
from contextlib import asynccontextmanager, suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.exception_handlers import http_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import Receive, Scope, Send

from media_sync import __version__
from media_sync.application import (
    AccountDraft,
    ArchivePreview,
    ArchivePreviewError,
    ArchivePreviewService,
    ArchivePreviewSource,
    MediaCrawlerLoginSessionReconciler,
    OperationCoordinator,
    OperationCoordinatorError,
    OperationExecution,
    OperationExecutionContext,
    OperationOutcome,
    OperationPayloadError,
    OperationSubmission,
    SubscriptionDraft,
    WorkbenchError,
    WorkbenchService,
    collect_account_login_preflight,
    operation_idempotency_key_digest,
    operation_request_fingerprint,
    parse_single_byte_range,
)
from media_sync.application.authentication import (
    AccountLoginError,
    AccountLoginRequest,
    MediaCrawlerQrLoginService,
)
from media_sync.application.cookie_login import CookieLoginService
from media_sync.application.creator_profiles import CreatorProfileService, lookup_error_code, profile_payload
from media_sync.application.emby import EmbyExportRequest, EmbyExportService, export_error_is_retryable
from media_sync.application.explorer import CatalogExplorerError, ContentAssetExplorer
from media_sync.application.job_diagnostics import JobDiagnosticError, JobDiagnosticService
from media_sync.application.library import LibraryInspection, LibraryInspectionError, LibraryInspectionService
from media_sync.application.login_diagnostics import latest_session_login_diagnostic, login_operation_error_code
from media_sync.application.media_server import MediaServerError, MediaServerService
from media_sync.application.media_server_observation import MediaServerObservationService
from media_sync.application.media_server_publication import MediaServerPublicationResolver
from media_sync.application.playback_evidence import (
    PlaybackEvidenceConfirmationError,
    PlaybackEvidenceService,
)
from media_sync.application.playback_evidence_query import (
    DEFAULT_EVIDENCE_HISTORY_LIMIT,
    PlaybackEvidenceQueryError,
    PlaybackEvidenceQueryService,
    validate_evidence_query,
)
from media_sync.application.qualifications import QualificationError, QualificationService
from media_sync.application.subscription_removal import SubscriptionRemovalError, SubscriptionRemovalService
from media_sync.application.support_bundle import SupportBundleError, SupportBundleService
from media_sync.config import Settings, get_settings
from media_sync.domain import AssetKind, AssetStatus, ContentKind, JobStatus, LoginMethod, Platform
from media_sync.exporters.emby import EmbyExporter, ExportError
from media_sync.infrastructure.db import (
    AccountLoginConflictError,
    AccountRepository,
    Asset,
    Database,
    LoginSession,
    LoginSessionRepository,
    NotFoundError,
    Operation,
    OperationConflictError,
    OperationEventCursorError,
    OperationEventSnapshot,
    OperationSnapshot,
    OperationStateConflictError,
    OperationSubjectInput,
    OperationSubjectSnapshot,
    RepositoryError,
    Subscription,
    SubscriptionRepository,
    SyncRun,
)
from media_sync.infrastructure.db.cookie_account_repository import CookieAccountError
from media_sync.infrastructure.db.creator_profile_repository import (
    CreatorProfileError,
    CreatorProfileRepository,
    ProfileSnapshot,
)
from media_sync.integrations.mediacrawler import platform_capabilities_payload
from media_sync.integrations.mediacrawler.checkout import load_mediacrawler_lock
from media_sync.integrations.mediacrawler.cookie_login_runner import CookieLoginProcessRunner
from media_sync.integrations.mediacrawler.creator_profile_runner import MediaCrawlerCreatorProfileProcessRunner
from media_sync.integrations.mediacrawler.login_runner import (
    LOGIN_QR_IMAGE_NAME,
    MediaCrawlerLoginProcessRunner,
)
from media_sync.integrations.mediacrawler.subscription_policy import (
    MAX_REQUEST_DELAY_SECONDS,
    SUBSCRIPTION_POLICY_SCHEMA_VERSION,
    MediaCrawlerSubscriptionPolicyError,
    from_subscription_policy,
)
from media_sync.interfaces.cli import (
    _EXPECTED_DATABASE_REVISION,
    _account_login_outcome_payload,
    _account_login_status_payload,
    _account_payload,
    _build_pipeline_worker,
    _build_subscription_worker,
    _credential_reference,
    _execute_asset_download,
    _scheduler_cycle_payload,
    _scheduler_job_payload,
    _scheduler_schedule_payload,
    _subscription_payload,
    _UnavailableMediaCrawlerLoginRunner,
    collect_deep_readiness_report,
)
from media_sync.interfaces.cookie_request import CookieRequestError, read_cookie_login_body
from media_sync.scheduler import DurableSchedulerService, SchedulerRepository, StaleLaneError
from media_sync.security import (
    OPERATOR_SESSION_COOKIE_NAME,
    OperatorAuthConfigurationError,
    OperatorAuthMethod,
    OperatorAuthMiddleware,
    OperatorAuthRuntime,
    OperatorLoginRejected,
    OperatorOriginPolicy,
    SecretResolver,
    derive_operator_origin_policy,
    operator_auth_method,
    resolve_operator_auth_runtime,
    session_cookie_from_headers,
)

_CONSOLE_PATH = Path(__file__).with_name("console.html")
_PACKAGED_WEB_ROOT = Path(__file__).with_name("static") / "console-v2"
_DEVELOPMENT_WEB_ROOT = Path(__file__).resolve().parents[3] / "web" / "build"
_MAX_LOGIN_QR_BYTES = 2 * 1024 * 1024
_MAX_OPERATION_LIST = 200
_MAX_OPERATION_EVENT_PAGE = 1_000
_OPERATION_STREAM_BATCH = 100
_OPERATION_STREAM_POLL_SECONDS = 0.25
_OPERATION_STREAM_KEEPALIVE_SECONDS = 10.0
_OPERATION_STREAM_MAX_SECONDS = 30.0
_OPERATION_RECONCILE_MIN_INTERVAL_SECONDS = 1.0
_OPERATION_RECONCILE_SHUTDOWN_SECONDS = 1.0
_MAX_OPERATOR_LOGIN_BODY_BYTES = 8 * 1024
_MAX_PLAYBACK_EVIDENCE_BODY_BYTES = 1_024
_LAST_EVENT_ID = re.compile(r"(?:0|[1-9][0-9]{0,18})\Z")
_JSON_CONTENT_TYPE = re.compile(r"application/json(?:\s*;\s*charset=utf-8)?\Z", re.IGNORECASE)
_OPERATOR_LOGIN_OPENAPI = {
    "requestBody": {
        "required": True,
        "content": {
            "application/json": {
                "schema": {
                    "type": "object",
                    "properties": {
                        "credential": {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": 1_024,
                            "writeOnly": True,
                        }
                    },
                    "required": ["credential"],
                    "additionalProperties": False,
                }
            }
        },
    }
}
_PLAYBACK_EVIDENCE_OPENAPI = {
    "requestBody": {
        "required": True,
        "content": {
            "application/json": {
                "schema": {
                    "type": "object",
                    "properties": {
                        "author_id": {
                            "type": "string",
                            "minLength": 36,
                            "maxLength": 36,
                            "format": "uuid",
                        },
                        "observation_fingerprint": {
                            "type": "string",
                            "minLength": 64,
                            "maxLength": 64,
                            "pattern": "^[0-9a-f]{64}$",
                            "writeOnly": True,
                        },
                    },
                    "required": ["author_id", "observation_fingerprint"],
                    "additionalProperties": False,
                }
            }
        },
    },
    "responses": {
        "201": {
            "description": "Playback evidence created or replayed",
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            "schema_version": {"type": "integer", "enum": [1]},
                            "id": {"type": "string", "format": "uuid"},
                            "author_id": {"type": "string", "format": "uuid"},
                            "observed_at": {"type": "string", "format": "date-time"},
                            "confirmed_at": {"type": "string", "format": "date-time"},
                            "replayed": {"type": "boolean"},
                        },
                        "required": [
                            "schema_version",
                            "id",
                            "author_id",
                            "observed_at",
                            "confirmed_at",
                            "replayed",
                        ],
                        "additionalProperties": False,
                    }
                }
            },
        }
    },
}
_ACCOUNT_LOGIN_RETRYABLE_CODES = frozenset(
    {
        "account_login_busy",
        "account_login_start_failed",
        "account_login_result_invalid",
        "account_login_conflict",
        "account_login_unexpected",
    }
)


def _resolve_web_root() -> Path | None:
    """Find a complete packaged or local-development Console v2 build."""

    for candidate in (_PACKAGED_WEB_ROOT, _DEVELOPMENT_WEB_ROOT):
        resolved = candidate.resolve()
        if (resolved / "index.html").is_file():
            return resolved
    return None


def _strict_json_object(payload: bytes) -> dict[str, object]:
    """Decode one finite JSON object while rejecting duplicate members."""

    def strict_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON member")
            result[key] = value
        return result

    def reject_constant(_value: str) -> object:
        raise ValueError("non-finite JSON value")

    decoded = json.loads(
        payload.decode("utf-8"),
        object_pairs_hook=strict_object,
        parse_constant=reject_constant,
    )
    if type(decoded) is not dict:
        raise ValueError("JSON value must be an object")
    return decoded


def _static_response(web_root: Path, relative_path: str = "index.html") -> FileResponse:
    """Serve one confined SPA file with appropriate cache semantics."""

    root = web_root.resolve()
    candidate = (root / relative_path).resolve()
    if not candidate.is_relative_to(root) or not candidate.is_file():
        candidate = root / "index.html"
    immutable = relative_path.startswith("_app/immutable/") and candidate.name != "index.html"
    return FileResponse(
        candidate,
        headers={
            "Cache-Control": "public, max-age=31536000, immutable" if immutable else "no-cache",
        },
    )


def _console_notice(*, missing_build: bool) -> Response:
    """Render fixed, inert migration guidance instead of the retired client."""

    if missing_build:
        title = "控制台构建缺失 / Console build missing"
        message_zh = "未找到 Console v2 构建。请安装包含前端构建的发行包。也可在源码的 web 目录完成构建后重启服务。"
        message_en = (
            "Console v2 is not built. Install a release containing the Web build, "
            "or build it from the web source directory and restart the server."
        )
    else:
        title = "旧控制台已停用 / Legacy console retired"
        message_zh = "旧版交互控制台已停用。请返回首页并使用操作者凭据登录 Console v2。此旧入口仍受认证保护。"
        message_en = (
            "The legacy interactive client is retired. Return to the home page and sign in to Console v2 "
            "with your operator credential. This legacy entry remains protected."
        )
    content = (
        _CONSOLE_PATH.read_text(encoding="utf-8")
        .replace("{{NOTICE_TITLE}}", title)
        .replace("{{NOTICE_ZH}}", message_zh)
        .replace("{{NOTICE_EN}}", message_en)
    )
    return Response(
        content=content,
        media_type="text/html; charset=utf-8",
        headers={
            "Cache-Control": "no-store",
            "Content-Security-Policy": (
                "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; "
                "frame-ancestors 'none'; form-action 'none'"
            ),
        },
    )


class _ArchiveStreamingResponse(StreamingResponse):
    """Close the archive descriptor even when ASGI send or disconnect fails."""

    def __init__(
        self,
        preview: ArchivePreview,
        *,
        status_code: int,
        headers: Mapping[str, str],
    ) -> None:
        self._archive_preview = preview
        try:
            super().__init__(
                preview.iter_bytes(),
                status_code=status_code,
                headers=headers,
                media_type=preview.media_type,
            )
        except BaseException:
            with suppress(ArchivePreviewError):
                preview.close()
            raise

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            with suppress(ArchivePreviewError):
                self._archive_preview.close()


# ------------------------------------------------------------------ operations


def _iso(value: datetime | None) -> str | None:
    return value.astimezone(UTC).isoformat() if value is not None else None


def _operation_payload(
    operation: OperationSnapshot,
    *,
    subjects: Sequence[OperationSubjectSnapshot] | None = None,
) -> dict[str, object]:
    """Project the version-one public shape without lease or revision data."""

    progress: dict[str, object] | None = None
    if any(
        value is not None for value in (operation.progress_current, operation.progress_total, operation.progress_unit)
    ):
        progress = {
            "current": operation.progress_current,
            "total": operation.progress_total,
            "unit": operation.progress_unit,
        }
    target = None
    if operation.target_type is not None and operation.target_id is not None:
        target = {"type": operation.target_type, "id": operation.target_id}
    payload: dict[str, object] = {
        "id": operation.id,
        "kind": operation.kind,
        "state": operation.state,
        "requested_at": _iso(operation.requested_at),
        "started_at": _iso(operation.started_at),
        "finished_at": _iso(operation.finished_at),
        "phase": operation.phase,
        "progress": progress,
        "target": target,
        "retryable": operation.retryable,
        "result": dict(operation.result_summary) if operation.result_summary else None,
        "error_code": operation.error_code,
        "correlation_id": operation.correlation_id,
        "cancel_requested_at": _iso(operation.cancel_requested_at),
        "allowed_actions": list(operation.allowed_actions),
        "event_sequence": operation.event_sequence,
    }
    if subjects is not None:
        payload["subjects"] = [
            {
                "type": subject.subject_type,
                "id": subject.subject_id,
                "role": subject.role,
                "created_at": _iso(subject.created_at),
            }
            for subject in subjects
        ]
    return payload


def _operation_event_payload(
    event: OperationEventSnapshot,
    *,
    operation: OperationSnapshot | None = None,
) -> dict[str, object]:
    subject = None
    if event.subject_type is not None and event.subject_id is not None:
        subject = {"type": event.subject_type, "id": event.subject_id}
    payload: dict[str, object] = {
        "stream_sequence": event.stream_sequence,
        "operation_id": event.operation_id,
        "operation_sequence": event.operation_sequence,
        "created_at": _iso(event.at),
        "level": event.level,
        "event_code": event.event_code,
        "phase": event.phase,
        "message_key": event.message_key,
        "from_state": event.from_state,
        "to_state": event.to_state,
        "subject": subject,
        "context": dict(event.safe_context),
    }
    if operation is not None:
        payload["operation"] = _operation_payload(operation)
    return payload


def _operation_start_payload(submission: OperationSubmission) -> dict[str, object]:
    return {
        "operation_id": submission.operation_id,
        "state": submission.operation.state,
        "replayed": submission.replayed,
        "correlation_id": submission.operation.correlation_id,
    }


def _private_reference_digest(value: str | None) -> str | None:
    if value is None:
        return None
    return hashlib.sha256(b"media-sync:operation-private-reference:v1\0" + value.encode("utf-8")).hexdigest()


def _sse_frame(
    event: str,
    payload: Mapping[str, object],
    *,
    event_id: int | None = None,
) -> bytes:
    encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    lines = []
    if event_id is not None:
        lines.append(f"id: {event_id}")
    lines.extend((f"event: {event}", f"data: {encoded}", ""))
    return ("\n".join(lines) + "\n").encode("utf-8")


class _OperationReconciliationTrigger:
    """Start at most one best-effort reconciliation without delaying reads."""

    def __init__(self, operations: OperationCoordinator, *, limit: int = 100) -> None:
        self._operations = operations
        self._limit = limit
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._last_started = float("-inf")
        self._closed = False

    def trigger(self) -> bool:
        now = time.monotonic()
        with self._lock:
            if self._closed or (self._thread is not None and self._thread.is_alive()):
                return False
            if now - self._last_started < _OPERATION_RECONCILE_MIN_INTERVAL_SECONDS:
                return False
            worker = threading.Thread(
                target=self._run,
                name="media-sync-operation-reconciliation",
                daemon=True,
            )
            self._thread = worker
            self._last_started = now
            try:
                worker.start()
            except RuntimeError:
                if self._thread is worker:
                    self._thread = None
                return False
        return True

    def close(self, *, timeout_seconds: float = 0.0) -> None:
        if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, int | float) or timeout_seconds < 0:
            raise ValueError("timeout_seconds must be non-negative")
        with self._lock:
            self._closed = True
            worker = self._thread
        if worker is not None and worker is not threading.current_thread() and worker.is_alive():
            worker.join(float(timeout_seconds))

    def _run(self) -> None:
        current = threading.current_thread()
        try:
            self._operations.reconcile_expired(limit=self._limit)
        except Exception:
            # Reads remain authoritative even when opportunistic recovery is
            # unavailable. A later trigger can retry without exposing details.
            pass
        finally:
            with self._lock:
                if self._thread is current:
                    self._thread = None


# ---------------------------------------------------------------------- models


class AccountCreate(BaseModel):
    platform: Platform
    display_name: str = Field(min_length=1, max_length=200)
    login_method: LoginMethod = LoginMethod.QR
    credential_ref: str | None = None


class LoginStart(BaseModel):
    enable_mediacrawler: bool = False
    accept_mediacrawler_license: bool = False
    timeout_seconds: float = Field(default=180.0, gt=0, le=3_600)


class SubscriptionCreate(BaseModel):
    account_id: UUID
    platform: Platform
    creator_remote_id: str = Field(min_length=1, max_length=255)
    display_name: str | None = Field(default=None, min_length=1, max_length=200)
    local_alias: str | None = Field(default=None, max_length=512)
    profile_lookup_id: UUID | None = None
    creator_reference_ref: str | None = None
    interval_seconds: int = Field(default=21_600, ge=60)
    max_items: int = Field(default=30, ge=1, le=1_000)
    allow_full_history: bool = False
    request_delay_seconds: float = Field(default=5.0, gt=0, le=MAX_REQUEST_DELAY_SECONDS)
    headless: bool = True


class CreatorLookupStart(BaseModel):
    model_config = ConfigDict(extra="forbid")

    platform: Platform
    creator_remote_id: str = Field(min_length=1, max_length=20, strict=True)
    frontend_generation: UUID
    enable_mediacrawler: bool = Field(default=False, strict=True)
    accept_mediacrawler_license: bool = Field(default=False, strict=True)


def _subscription_policy_summary_payload(subscription: Subscription) -> dict[str, object]:
    """Project durable policy controls without returning an opaque reference."""

    adapter = subscription.account.adapter
    if adapter != "mediacrawler":
        return {"adapter": adapter}
    try:
        policy = from_subscription_policy(subscription.policy)
    except MediaCrawlerSubscriptionPolicyError:
        return {
            "adapter": adapter,
            "schema_version": None,
            "allow_full_history": None,
            "request_delay_seconds": None,
            "headless": None,
            "creator_reference_configured": False,
        }
    return {
        "adapter": adapter,
        "schema_version": SUBSCRIPTION_POLICY_SCHEMA_VERSION,
        "allow_full_history": policy.allow_full_history,
        "request_delay_seconds": policy.request_delay_seconds,
        "headless": policy.headless,
        "creator_reference_configured": policy.creator_secret_ref is not None,
    }


def _bili_scan_summary_payload(subscription: Subscription, lock_path: Path) -> dict[str, object] | None:
    """Project only typed, exactly bound Bili state; never infer legacy coverage."""

    if subscription.account.adapter != "mediacrawler" or subscription.account.platform != Platform.BILI.value:
        return None
    payload: dict[str, object] = {
        "version": 1,
        "status": "not_started" if subscription.cursor is None else "unverified",
        "feed": "ordinary_uploads",
        "unit_item_limit": min(subscription.max_items, 30),
        "max_list_attempts": 2,
        "history_complete": False,
        "state": None,
    }
    if subscription.cursor is None:
        return payload
    try:
        from media_sync.integrations.mediacrawler.bilibili_scan import BiliScanState

        cursor = subscription.cursor
        if type(cursor) is not dict or set(cursor) != {"value"} or type(cursor["value"]) is not str:
            return payload
        if type(subscription.cursor_version) is not int or subscription.cursor_version != 1:
            return payload
        state = BiliScanState.from_cursor(cursor["value"])
        state.require_binding(
            account_id=UUID(subscription.account_id),
            author_fingerprint_sha256=hashlib.sha256(subscription.author.remote_id.encode("utf-8")).hexdigest(),
            upstream_sha=load_mediacrawler_lock(lock_path).commit,
        )
        payload["state"] = state.public_summary()
        payload["status"] = "verified"
    except (OSError, ValueError, TypeError, KeyError):
        # Unknown versions, mismatched identities or unavailable locked source
        # are not evidence. Do not expose their values or parser diagnostics.
        pass
    return payload


def _subscription_checkpoint_summary_payload(
    subscription: Subscription,
    *,
    lock_path: Path,
) -> dict[str, object]:
    """Return checkpoint presence and counters without serializing cursor data."""

    has_forward_cursor = subscription.cursor is not None
    has_backfill_cursor = subscription.backfill_cursor is not None
    payload: dict[str, object] = {
        "has_checkpoint": bool(
            subscription.checkpoint_revision
            or has_forward_cursor
            or has_backfill_cursor
            or subscription.watermarked_at is not None
            or subscription.last_success_at is not None
        ),
        "has_forward_cursor": has_forward_cursor,
        "has_backfill_cursor": has_backfill_cursor,
        "revision": subscription.checkpoint_revision,
        "cursor_version": subscription.cursor_version,
        "watermarked_at": subscription.watermarked_at.isoformat() if subscription.watermarked_at else None,
        "watermark_count": len(subscription.watermark_remote_ids),
        "last_success_at": subscription.last_success_at.isoformat() if subscription.last_success_at else None,
    }
    bili_scan = _bili_scan_summary_payload(subscription, lock_path)
    if bili_scan is not None:
        payload["bili_scan"] = bili_scan
    return payload


class SchedulerTick(BaseModel):
    limit: int = Field(default=100, ge=1, le=1_000)


class SchedulerRun(BaseModel):
    max_jobs: int = Field(default=1, ge=1, le=1_000)
    global_capacity: int = Field(default=1, ge=1, le=1_000)
    lease_seconds: int = Field(default=60, ge=1, le=86_400)
    scan_limit: int = Field(default=100, ge=1, le=1_000)
    enable_mediacrawler: bool = False
    accept_mediacrawler_license: bool = False


class PipelineRun(BaseModel):
    max_jobs: int = Field(default=1, ge=1, le=1_000)
    worker_id: str = Field(default="api-pipeline-worker", min_length=1, max_length=128)
    lease_seconds: int = Field(default=3_600, ge=1, le=86_400)
    scan_limit: int = Field(default=100, ge=1, le=1_000)
    retry_delay_seconds: int = Field(default=30, ge=1, le=86_400)
    enable_mediacrawler: bool = False
    accept_mediacrawler_license: bool = False
    xhs_detail_reference_ref: str | None = None


class EmbyExport(BaseModel):
    author_id: UUID
    worker_id: str = Field(default="api-worker", min_length=1, max_length=128)
    lease_seconds: int = Field(default=300, ge=1, le=86_400)
    max_attempts: int = Field(default=5, ge=1, le=100)


class AssetDownload(BaseModel):
    worker_id: str = Field(default="api-asset-worker", min_length=1, max_length=128)
    lease_seconds: int = Field(default=3_600, ge=1, le=86_400)
    max_attempts: int = Field(default=5, ge=1, le=100)
    enable_mediacrawler: bool = False
    accept_mediacrawler_license: bool = False
    xhs_detail_reference_ref: str | None = None


class MediaServerOperationRequest(BaseModel):
    """An intentionally empty body: callers cannot override remote authority."""

    model_config = ConfigDict(extra="forbid", strict=True)


class MediaServerAuthorOperationRequest(BaseModel):
    """The sole author-scoped scan request; every remote selector stays server-owned."""

    model_config = ConfigDict(extra="forbid", strict=True)

    author_id: str = Field(min_length=36, max_length=36)

    @field_validator("author_id")
    @classmethod
    def canonical_author_id(cls, value: str) -> str:
        try:
            canonical = str(UUID(value))
        except (AttributeError, TypeError, ValueError):
            raise ValueError("author_id must be a canonical UUID") from None
        if canonical != value:
            raise ValueError("author_id must be a canonical UUID")
        return value


# ------------------------------------------------------------------ app factory


def create_api_app(
    settings: Settings | None = None,
    *,
    operator_auth_runtime: OperatorAuthRuntime | None = None,
    operator_origin_policy: OperatorOriginPolicy | None = None,
) -> FastAPI:
    """Build the fail-closed FastAPI application without migrating durable state."""

    resolved = settings or get_settings()
    if (operator_auth_runtime is None) != (operator_origin_policy is None):
        raise OperatorAuthConfigurationError
    if operator_auth_runtime is None:
        resolver = SecretResolver.local(file_root=resolved.resolved_secret_file_dir)
        operator_auth_runtime = resolve_operator_auth_runtime(
            resolved.operator_credential_secret_reference,
            resolved.operator_api_token_secret_reference,
            resolver,
            resolved.operator_session_ttl_seconds,
        )
        operator_origin_policy = derive_operator_origin_policy(
            resolved.api_host,
            resolved.api_port,
            resolved.operator_allowed_origins,
        )
    assert operator_auth_runtime is not None
    assert operator_origin_policy is not None
    operation_database = Database(resolved.resolved_database_url)
    operations = OperationCoordinator(operation_database)
    operation_reconciliation = _OperationReconciliationTrigger(operations)
    support_bundle_service = SupportBundleService(
        operation_database,
        application_version=__version__,
        expected_revision=_EXPECTED_DATABASE_REVISION,
    )
    media_server_service = MediaServerService.from_settings(
        resolved,
        SecretResolver.local(file_root=resolved.resolved_secret_file_dir),
    )
    emby_exporter = EmbyExporter(
        resolved.export_dir,
        staging_root=resolved.job_dir / "emby-export",
    )
    library_inspection_service = LibraryInspectionService(operation_database, emby_exporter)
    creator_profile_service = CreatorProfileService(
        operation_database,
        MediaCrawlerCreatorProfileProcessRunner(
            lock_path=resolved.mediacrawler_lock_path,
            integration_root=resolved.resolved_mediacrawler_runtime_dir,
            python_executable=resolved.mediacrawler_python_executable,
            enabled=True,
            license_acknowledged=True,
        )
        if resolved.mediacrawler_python_executable is not None
        else None,
        secret_resolver=SecretResolver.local(
            file_root=resolved.resolved_secret_file_dir,
            managed_root=resolved.state_dir / "credentials",
        ),
    )
    cookie_login_service = CookieLoginService(
        operation_database,
        CookieLoginProcessRunner(
            lock_path=resolved.mediacrawler_lock_path,
            integration_root=resolved.resolved_mediacrawler_runtime_dir,
            python_executable=resolved.mediacrawler_python_executable,
            enabled=True,
            license_acknowledged=True,
        )
        if resolved.mediacrawler_python_executable is not None
        else None,
        integration_root=resolved.resolved_mediacrawler_runtime_dir,
        credential_root=resolved.state_dir / "credentials",
    )
    media_server_profile = resolved.media_server_profile
    media_server_observation_service = (
        MediaServerObservationService(
            MediaServerPublicationResolver(operation_database, emby_exporter, media_server_profile),
            media_server_service,
        )
        if media_server_profile is not None
        else None
    )
    playback_evidence_service = (
        PlaybackEvidenceService(operation_database, media_server_observation_service)
        if media_server_observation_service is not None
        else None
    )
    playback_evidence_query = PlaybackEvidenceQueryService(
        operation_database,
        media_server_observation_service if media_server_service.operations_enabled else None,
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        del _app
        try:
            operations.start()
            # Recovery is single-flight and best effort so a busy durable store
            # cannot hold liveness or the ASGI event loop hostage.
            operation_reconciliation.trigger()
            yield
        finally:
            operation_reconciliation.close()
            await asyncio.to_thread(operations.shutdown)
            await asyncio.to_thread(
                operation_reconciliation.close,
                timeout_seconds=_OPERATION_RECONCILE_SHUTDOWN_SECONDS,
            )
            operation_database.dispose()

    app = FastAPI(title="media-sync", version=__version__, docs_url="/api/docs", lifespan=lifespan)
    app.state.settings = resolved
    app.state.operator_auth_runtime = operator_auth_runtime
    app.state.operator_origin_policy = operator_origin_policy
    app.state.operations = operations
    app.state.media_server_service = media_server_service
    app.state.media_server_observation_service = media_server_observation_service
    app.state.playback_evidence_service = playback_evidence_service
    app.state.playback_evidence_query = playback_evidence_query
    app.state.library_inspection_service = library_inspection_service
    app.state.creator_profile_service = creator_profile_service
    app.state.cookie_login_service = cookie_login_service
    deep_readiness_cache: dict[bool, tuple[float, dict[str, object]]] = {}
    deep_readiness_lock = threading.Lock()
    web_root = _resolve_web_root()

    @app.exception_handler(StarletteHTTPException)
    async def head_safe_http_exception(request: Request, error: StarletteHTTPException) -> Response:
        """Preserve standard error headers while never emitting a HEAD body."""

        response = await http_exception_handler(request, error)
        if request.method == "HEAD":
            return Response(status_code=response.status_code, headers=dict(response.headers))
        return response

    @app.exception_handler(RequestValidationError)
    async def safe_request_validation_error(
        request: Request,
        error: RequestValidationError,
    ) -> Response:
        """Keep rejected request values out of FastAPI's default 422 body."""

        errors: list[dict[str, object]] = []
        for item in error.errors():
            location = [part for part in item.get("loc", ()) if isinstance(part, str | int)]
            error_type = item.get("type")
            errors.append(
                {
                    "location": location,
                    "code": error_type if isinstance(error_type, str) else "validation_error",
                }
            )
        response = JSONResponse(
            status_code=422,
            content={"detail": "request_validation_failed", "errors": errors},
            headers={"Cache-Control": "no-store"},
        )
        if request.method == "HEAD":
            return Response(status_code=response.status_code, headers=dict(response.headers))
        return response

    @app.middleware("http")
    async def security_headers(request: Request, call_next: Any) -> Response:
        response: Response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        if not request.url.path.startswith("/api/"):
            response.headers.setdefault(
                "Content-Security-Policy",
                "default-src 'self'; img-src 'self' blob: data:; style-src 'self' 'unsafe-inline'; "
                "script-src 'self' 'unsafe-inline'; connect-src 'self'; object-src 'none'; "
                "base-uri 'self'; frame-ancestors 'none'",
            )
        if request.url.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
        return response

    def _database() -> Database:
        return Database(resolved.resolved_database_url)

    def _bad_request(code: str) -> HTTPException:
        return HTTPException(status_code=400, detail=code)

    def _workbench_error(error: WorkbenchError) -> HTTPException:
        status_code = 404 if error.code == "account_not_found" else 400
        if error.code == "subscription_removed":
            status_code = 409
        return HTTPException(status_code=status_code, detail=error.code)

    def _catalog_error(error: CatalogExplorerError) -> HTTPException:
        status_code = 404 if error.code in {"catalog_content_not_found", "catalog_asset_not_found"} else 400
        return HTTPException(status_code=status_code, detail=error.code)

    def _archive_error_response(
        error: ArchivePreviewError,
        *,
        asset_id: str,
        request_method: str,
        size_bytes: object,
    ) -> Response:
        status_code = 416 if error.code == "asset_archive_range_unsatisfiable" else 409
        content: dict[str, object] = {"detail": error.code}
        if status_code != 416:
            content["recovery"] = {
                "operation_kind": "asset-download",
                "method": "POST",
                "url": f"/api/v1/assets/{asset_id}/download",
            }
        headers = {
            "Accept-Ranges": "bytes",
            "Cache-Control": "private, no-store",
        }
        if status_code == 416 and type(size_bytes) is int and size_bytes >= 0:
            headers["Content-Range"] = f"bytes */{size_bytes}"
        response = JSONResponse(status_code=status_code, content=content, headers=headers)
        if request_method == "HEAD":
            return Response(status_code=status_code, headers=dict(response.headers))
        return response

    def _safe_credential_reference(value: str | None) -> str | None:
        import typer

        try:
            return _credential_reference(value)
        except typer.BadParameter:
            raise _bad_request("invalid_credential_reference") from None

    def _operation_identity(
        request: Request,
        kind: str,
        *,
        target_id: str | None,
        parameters: Mapping[str, object],
    ) -> tuple[str, str | None]:
        header_values = request.headers.getlist("idempotency-key")
        if len(header_values) > 1:
            raise _bad_request("operation_idempotency_key_invalid")
        try:
            fingerprint = operation_request_fingerprint(kind, target_id=target_id, parameters=parameters)
            key_hash = operation_idempotency_key_digest(header_values[0]) if header_values else None
        except OperationPayloadError as error:
            raise _bad_request(error.code) from None
        return fingerprint, key_hash

    def _idempotent_replay(
        kind: str,
        *,
        key_hash: str | None,
        request_fingerprint: str,
    ) -> OperationSubmission | None:
        if key_hash is None:
            return None
        try:
            with operation_database.session() as session:
                existing = session.scalar(
                    select(Operation).where(
                        Operation.kind == kind,
                        Operation.idempotency_key_hash == key_hash,
                    )
                )
            if existing is None:
                return None
            if existing.request_fingerprint != request_fingerprint:
                raise HTTPException(status_code=409, detail="idempotency_key_reused")
            return OperationSubmission(operations.get(existing.id), replayed=True)
        except HTTPException:
            raise
        except (RepositoryError, SQLAlchemyError):
            raise HTTPException(status_code=503, detail="operation_store_unavailable") from None

    def _submit_operation(execution: OperationExecution) -> OperationSubmission:
        try:
            return operations.submit(execution)
        except OperationConflictError as error:
            raise HTTPException(status_code=409, detail=error.code) from None
        except OperationPayloadError as error:
            raise _bad_request(error.code) from None
        except OperationCoordinatorError as error:
            raise HTTPException(status_code=503, detail=error.code) from None
        except (RepositoryError, SQLAlchemyError):
            raise HTTPException(status_code=503, detail="operation_store_unavailable") from None
        except (TypeError, ValueError):
            raise _bad_request("operation_request_invalid") from None

    def _canonical_operation_id(value: str) -> str:
        try:
            canonical = str(UUID(value))
        except (AttributeError, TypeError, ValueError):
            raise HTTPException(status_code=404, detail="operation_not_found") from None
        if canonical != value:
            raise HTTPException(status_code=404, detail="operation_not_found")
        return canonical

    def _operation_detail(operation_id: str) -> dict[str, object]:
        canonical_id = _canonical_operation_id(operation_id)
        try:
            operation = operations.get(canonical_id)
            subjects = operations.list_subjects(canonical_id)
            return _operation_payload(operation, subjects=subjects)
        except NotFoundError:
            raise HTTPException(status_code=404, detail="operation_not_found") from None
        except (RepositoryError, SQLAlchemyError):
            raise HTTPException(status_code=503, detail="operation_store_unavailable") from None

    def _reconcile_operation_reads() -> None:
        operation_reconciliation.trigger()

    def _latest_media_server_operation(
        kind: str,
        *,
        profile_fingerprint: str | None,
    ) -> OperationSnapshot | None:
        if profile_fingerprint is None:
            return None
        snapshots = operations.list_operations(
            kind=kind,
            exclusive_key=f"media-server:{profile_fingerprint}",
            limit=1,
        )
        return snapshots[0] if snapshots else None

    def _media_server_status_payload() -> dict[str, object]:
        """Project configuration and durable evidence without doing network I/O."""

        summary = resolved.media_server_safe_summary
        profile_fingerprint = summary.profile_fingerprint if summary.configured else None
        latest_probe = _latest_media_server_operation(
            "media-server-probe",
            profile_fingerprint=profile_fingerprint,
        )
        latest_scan = _latest_media_server_operation(
            "media-server-scan",
            profile_fingerprint=profile_fingerprint,
        )
        busy = any(
            operation is not None and operation.state in {"queued", "running"}
            for operation in (latest_probe, latest_scan)
        )
        allowed_actions = ["probe", "scan"] if summary.configured and summary.operations_enabled and not busy else []
        return {
            "schema_version": 1,
            "configuration": summary.as_dict(),
            "latest_probe": _operation_payload(latest_probe) if latest_probe is not None else None,
            "latest_scan": _operation_payload(latest_scan) if latest_scan is not None else None,
            "allowed_actions": allowed_actions,
        }

    def _media_server_profile_identity() -> str:
        if not media_server_service.configured:
            raise HTTPException(
                status_code=409,
                detail="media_server_not_configured",
                headers={"Cache-Control": "no-store"},
            )
        if not media_server_service.operations_enabled:
            raise HTTPException(
                status_code=403,
                detail="media_server_operations_disabled",
                headers={"Cache-Control": "no-store"},
            )
        profile_fingerprint = media_server_service.profile_fingerprint
        if profile_fingerprint is None:
            raise HTTPException(
                status_code=409,
                detail="media_server_not_configured",
                headers={"Cache-Control": "no-store"},
            )
        return profile_fingerprint

    def _media_server_operation_identity(request: Request, kind: str) -> tuple[str, str | None, str]:
        profile_fingerprint = _media_server_profile_identity()
        request_fingerprint, key_hash = _operation_identity(
            request,
            kind,
            target_id=None,
            parameters={"profile_fingerprint": profile_fingerprint},
        )
        return request_fingerprint, key_hash, profile_fingerprint

    def _media_server_observation() -> MediaServerObservationService:
        _media_server_profile_identity()
        if media_server_observation_service is None:
            raise HTTPException(
                status_code=409,
                detail="media_server_not_configured",
                headers={"Cache-Control": "no-store"},
            )
        return media_server_observation_service

    def _playback_evidence_confirmation() -> PlaybackEvidenceService:
        _media_server_observation()
        if playback_evidence_service is None:
            raise HTTPException(
                status_code=409,
                detail="media_server_not_configured",
                headers={"Cache-Control": "no-store"},
            )
        return playback_evidence_service

    def _media_server_error(error: MediaServerError) -> HTTPException:
        if error.code == "media_server_operations_disabled":
            status_code = 403
        elif error.code in {
            "media_server_not_configured",
            "media_server_item_lookup_ambiguous",
            "media_server_provider_mismatch",
            "media_server_publication_changed",
            "media_server_publication_not_ready",
        }:
            status_code = 409
        else:
            status_code = 503
        return HTTPException(
            status_code=status_code,
            detail=error.code,
            headers={"Cache-Control": "no-store"},
        )

    def _canonical_media_server_author_id(author_id: str) -> str:
        try:
            canonical = str(UUID(author_id))
        except (AttributeError, TypeError, ValueError):
            raise HTTPException(
                status_code=409,
                detail="media_server_publication_not_ready",
                headers={"Cache-Control": "no-store"},
            ) from None
        if canonical != author_id:
            raise HTTPException(
                status_code=409,
                detail="media_server_publication_not_ready",
                headers={"Cache-Control": "no-store"},
            )
        return author_id

    def _library_inspection_payload(inspection: LibraryInspection) -> dict[str, object]:
        publication = inspection.publication
        return {
            "schema_version": 2,
            "author_id": inspection.author_id,
            "publication": (
                {
                    "layout_version": publication.layout_version,
                    "publication_scope": publication.publication_scope,
                    "job_id": publication.job_id,
                    "source_fingerprint": publication.source_fingerprint,
                    "tree_sha256": publication.tree_sha256,
                    "manifest_sha256": publication.manifest_sha256,
                    "managed_file_count": publication.managed_file_count,
                }
                if publication is not None
                else None
            ),
            "freshness": inspection.freshness,
            "freshness_reason_code": inspection.freshness_reason_code,
            "integrity": inspection.integrity,
            "integrity_reason_code": inspection.integrity_reason_code,
            "user_changes_protected": inspection.user_changes_protected,
            "files": [
                {
                    "relative_path": item.relative_path,
                    "sha256": item.sha256,
                    "size_bytes": item.size_bytes,
                }
                for item in inspection.files
            ],
            "page": {
                "start_index": inspection.page.start_index,
                "next_index": inspection.page.next_index,
                "limit": inspection.page.limit,
                "returned_count": inspection.page.returned_count,
                "bytes_read": inspection.page.bytes_read,
                "complete": inspection.page.complete,
                "budget_exhausted": inspection.page.budget_exhausted,
                "next_cursor": inspection.page.next_cursor,
            },
            "allowed_actions": list(inspection.allowed_actions),
        }

    @app.get("/api/v1/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.head("/api/v1/health", include_in_schema=False)
    def health_head() -> Response:
        return Response(status_code=200)

    @app.post("/api/v1/operator-auth/login", openapi_extra=_OPERATOR_LOGIN_OPENAPI)
    async def operator_login(request: Request) -> Response:
        raw_headers = request.scope.get("headers", ())
        content_types = [value for name, value in raw_headers if name.lower() == b"content-type"]
        if len(content_types) != 1 or len(content_types[0]) > 64:
            return JSONResponse(
                status_code=415,
                content={"detail": "operator_login_content_type_invalid"},
                headers={"Cache-Control": "no-store"},
            )
        try:
            content_type = content_types[0].decode("ascii")
        except UnicodeDecodeError:
            content_type = ""
        if _JSON_CONTENT_TYPE.fullmatch(content_type) is None:
            return JSONResponse(
                status_code=415,
                content={"detail": "operator_login_content_type_invalid"},
                headers={"Cache-Control": "no-store"},
            )
        content_lengths = [value for name, value in raw_headers if name.lower() == b"content-length"]
        if len(content_lengths) > 1:
            return JSONResponse(
                status_code=400,
                content={"detail": "operator_login_request_invalid"},
                headers={"Cache-Control": "no-store"},
            )
        if content_lengths:
            content_length_text = ""
            try:
                content_length_text = content_lengths[0].decode("ascii")
                content_length = int(content_length_text)
            except (UnicodeDecodeError, ValueError):
                content_length = -1
            if str(content_length) != content_length_text or not 0 <= content_length <= _MAX_OPERATOR_LOGIN_BODY_BYTES:
                return JSONResponse(
                    status_code=413 if content_length > _MAX_OPERATOR_LOGIN_BODY_BYTES else 400,
                    content={
                        "detail": (
                            "operator_login_body_too_large"
                            if content_length > _MAX_OPERATOR_LOGIN_BODY_BYTES
                            else "operator_login_request_invalid"
                        )
                    },
                    headers={"Cache-Control": "no-store"},
                )
        payload = bytearray()
        try:
            async for chunk in request.stream():
                payload.extend(chunk)
                if len(payload) > _MAX_OPERATOR_LOGIN_BODY_BYTES:
                    return JSONResponse(
                        status_code=413,
                        content={"detail": "operator_login_body_too_large"},
                        headers={"Cache-Control": "no-store"},
                    )

            def strict_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
                result: dict[str, object] = {}
                for key, value in pairs:
                    if key in result:
                        raise ValueError("duplicate JSON member")
                    result[key] = value
                return result

            def reject_constant(_value: str) -> object:
                raise ValueError("non-finite JSON value")

            decoded = json.loads(
                bytes(payload).decode("utf-8"),
                object_pairs_hook=strict_object,
                parse_constant=reject_constant,
            )
            credential = decoded.get("credential") if type(decoded) is dict and set(decoded) == {"credential"} else None
            if type(credential) is not str or not credential or len(credential.encode("utf-8")) > 1_024:
                raise ValueError("invalid credential shape")
        except (RecursionError, UnicodeError, ValueError):
            return JSONResponse(
                status_code=400,
                content={"detail": "operator_login_request_invalid"},
                headers={"Cache-Control": "no-store"},
            )
        try:
            issued = await asyncio.to_thread(operator_auth_runtime.login, credential)
        except OperatorLoginRejected as error:
            headers = {"Cache-Control": "no-store"}
            if error.retry_after_seconds is not None:
                headers["Retry-After"] = str(error.retry_after_seconds)
            return JSONResponse(
                status_code=error.status_code,
                content={"detail": error.code.value},
                headers=headers,
            )
        response = JSONResponse(
            content={"authenticated": True, "expires_in_seconds": issued.max_age_seconds},
            headers={"Cache-Control": "no-store"},
        )
        response.set_cookie(
            key=OPERATOR_SESSION_COOKIE_NAME,
            value=issued.cookie_value,
            max_age=issued.max_age_seconds,
            path="/",
            secure=operator_origin_policy.secure_cookie,
            httponly=True,
            samesite="strict",
        )
        return response

    @app.get("/api/v1/operator-auth/session")
    def operator_session(request: Request) -> Response:
        cookie = session_cookie_from_headers(request.scope.get("headers", ()))
        session = operator_auth_runtime.session(cookie)
        if session is None:
            response = JSONResponse(
                content={"authenticated": False},
                headers={"Cache-Control": "no-store"},
            )
            response.delete_cookie(
                OPERATOR_SESSION_COOKIE_NAME,
                path="/",
                secure=operator_origin_policy.secure_cookie,
                httponly=True,
                samesite="strict",
            )
            return response
        return JSONResponse(
            content={
                "authenticated": True,
                "csrf_token": session.csrf_token,
                "expires_in_seconds": session.expires_in_seconds,
            },
            headers={"Cache-Control": "no-store"},
        )

    @app.post("/api/v1/operator-auth/logout", status_code=204)
    def operator_logout(request: Request) -> Response:
        cookie = session_cookie_from_headers(request.scope.get("headers", ()))
        operator_auth_runtime.logout(cookie)
        response = Response(status_code=204, headers={"Cache-Control": "no-store"})
        response.delete_cookie(
            OPERATOR_SESSION_COOKIE_NAME,
            path="/",
            secure=operator_origin_policy.secure_cookie,
            httponly=True,
            samesite="strict",
        )
        return response

    @app.get("/api/v1/support-bundle")
    def support_bundle() -> Response:
        try:
            content = support_bundle_service.build()
        except SupportBundleError as error:
            return JSONResponse(
                status_code=503,
                content={"detail": error.code},
                headers={"Cache-Control": "no-store"},
            )
        return Response(
            content=content,
            media_type="application/json",
            headers={"Cache-Control": "no-store"},
        )

    def _ready_payload() -> dict[str, object]:
        database = _database()
        try:
            with database.session() as session:
                from sqlalchemy import func
                from sqlalchemy import select as sa_select

                session.execute(sa_select(func.now())).scalar_one()
        except Exception:
            raise HTTPException(status_code=503, detail="database_not_ready") from None
        finally:
            database.dispose()
        return {"status": "ready", "database": "ok"}

    @app.get("/api/v1/ready")
    def ready() -> dict[str, object]:
        return _ready_payload()

    @app.head("/api/v1/ready", include_in_schema=False)
    def ready_head() -> Response:
        _ready_payload()
        return Response(status_code=200)

    @app.get("/api/v1/readiness/deep")
    def deep_readiness(
        accept_mediacrawler_license: bool = False,
        refresh: bool = False,
    ) -> dict[str, object]:
        """Run the explicit runtime qualification and cache it briefly."""

        cache_key = bool(accept_mediacrawler_license)
        now = time.monotonic()
        with deep_readiness_lock:
            cached = deep_readiness_cache.get(cache_key)
        if cached is not None and not refresh and now - cached[0] < 60:
            return {**cached[1], "cached": True}

        report = collect_deep_readiness_report(
            resolved,
            license_acknowledged=cache_key,
        )
        with deep_readiness_lock:
            deep_readiness_cache[cache_key] = (time.monotonic(), report)
        return {**report, "cached": False}

    @app.get("/api/v1/settings")
    def settings_view() -> dict[str, object]:
        return {
            "version": __version__,
            "state_dir": str(resolved.state_dir),
            "archive_dir": str(resolved.archive_dir),
            "export_dir": str(resolved.export_dir),
            "job_dir": str(resolved.job_dir),
            "api_bind": f"{resolved.api_host}:{resolved.api_port}",
            "mediacrawler_python_executable": (
                str(resolved.mediacrawler_python_executable)
                if resolved.mediacrawler_python_executable is not None
                else None
            ),
            "media_server": resolved.media_server_safe_summary.as_dict(),
        }

    @app.get("/api/v1/platform-capabilities")
    def platform_capabilities() -> dict[str, object]:
        return platform_capabilities_payload()

    @app.get("/api/v1/media-server")
    def media_server_status() -> dict[str, object]:
        """Return only the redacted immutable profile and durable evidence."""

        _reconcile_operation_reads()
        try:
            return _media_server_status_payload()
        except (RepositoryError, SQLAlchemyError):
            raise HTTPException(status_code=503, detail="operation_store_unavailable") from None

    @app.get("/api/v1/media-server/items/by-author/{author_id}")
    def media_server_item_by_author(author_id: str, response: Response) -> dict[str, object]:
        """Return one bounded complete item observation without exposing selectors."""

        response.headers["Cache-Control"] = "no-store"
        canonical_author_id = _canonical_media_server_author_id(author_id)
        service = _media_server_observation()
        try:
            return service.lookup_author(canonical_author_id).as_dict()
        except MediaServerError as error:
            raise _media_server_error(error) from None

    @app.post(
        "/api/v1/media-server/playback-evidence",
        status_code=201,
        openapi_extra=_PLAYBACK_EVIDENCE_OPENAPI,
    )
    async def confirm_media_server_playback(request: Request) -> Response:
        """Revalidate and append one explicit browser-only playback attestation."""

        if operator_auth_method(request.scope) is not OperatorAuthMethod.BROWSER:
            return JSONResponse(
                status_code=403,
                content={"detail": "operator_browser_session_required"},
                headers={"Cache-Control": "no-store"},
            )
        raw_headers = request.scope.get("headers", ())
        if any(name.lower() == b"idempotency-key" for name, _value in raw_headers):
            return JSONResponse(
                status_code=400,
                content={"detail": "playback_evidence_idempotency_key_unsupported"},
                headers={"Cache-Control": "no-store"},
            )

        content_types = [value for name, value in raw_headers if name.lower() == b"content-type"]
        if len(content_types) != 1 or len(content_types[0]) > 64:
            return JSONResponse(
                status_code=415,
                content={"detail": "playback_evidence_content_type_invalid"},
                headers={"Cache-Control": "no-store"},
            )
        try:
            content_type = content_types[0].decode("ascii")
        except UnicodeDecodeError:
            content_type = ""
        if _JSON_CONTENT_TYPE.fullmatch(content_type) is None:
            return JSONResponse(
                status_code=415,
                content={"detail": "playback_evidence_content_type_invalid"},
                headers={"Cache-Control": "no-store"},
            )

        content_lengths = [value for name, value in raw_headers if name.lower() == b"content-length"]
        if len(content_lengths) > 1:
            return JSONResponse(
                status_code=400,
                content={"detail": "playback_evidence_request_invalid"},
                headers={"Cache-Control": "no-store"},
            )
        if content_lengths:
            content_length_text = ""
            try:
                content_length_text = content_lengths[0].decode("ascii")
                content_length = int(content_length_text)
            except (UnicodeDecodeError, ValueError):
                content_length = -1
            if (
                str(content_length) != content_length_text
                or not 0 <= content_length <= _MAX_PLAYBACK_EVIDENCE_BODY_BYTES
            ):
                too_large = content_length > _MAX_PLAYBACK_EVIDENCE_BODY_BYTES
                return JSONResponse(
                    status_code=413 if too_large else 400,
                    content={
                        "detail": (
                            "playback_evidence_body_too_large" if too_large else "playback_evidence_request_invalid"
                        )
                    },
                    headers={"Cache-Control": "no-store"},
                )

        payload = bytearray()
        try:
            async for chunk in request.stream():
                payload.extend(chunk)
                if len(payload) > _MAX_PLAYBACK_EVIDENCE_BODY_BYTES:
                    return JSONResponse(
                        status_code=413,
                        content={"detail": "playback_evidence_body_too_large"},
                        headers={"Cache-Control": "no-store"},
                    )
            decoded = _strict_json_object(bytes(payload))
            if set(decoded) != {"author_id", "observation_fingerprint"}:
                raise ValueError("invalid playback-evidence fields")
            author_id = decoded["author_id"]
            observation_fingerprint = decoded["observation_fingerprint"]
            if type(author_id) is not str or type(observation_fingerprint) is not str:
                raise ValueError("invalid playback-evidence field types")
            if str(UUID(author_id)) != author_id or re.fullmatch(r"[0-9a-f]{64}", observation_fingerprint) is None:
                raise ValueError("invalid playback-evidence identity")
        except (AttributeError, RecursionError, UnicodeError, ValueError):
            return JSONResponse(
                status_code=400,
                content={"detail": "playback_evidence_request_invalid"},
                headers={"Cache-Control": "no-store"},
            )

        service = _playback_evidence_confirmation()
        try:
            result = await asyncio.to_thread(service.confirm, author_id, observation_fingerprint)
        except MediaServerError as error:
            raise _media_server_error(error) from None
        except PlaybackEvidenceConfirmationError as error:
            if error.code in {"playback_evidence_identity_conflict", "playback_evidence_not_confirmable"}:
                status = 409
            elif error.code == "playback_evidence_request_invalid":
                status = 400
            else:
                status = 503
            return JSONResponse(
                status_code=status,
                content={"detail": error.code},
                headers={"Cache-Control": "no-store"},
            )

        return JSONResponse(
            status_code=201,
            content={
                "schema_version": result.schema_version,
                "id": result.id,
                "author_id": result.author_id,
                "observed_at": result.observed_at.astimezone(UTC).isoformat(),
                "confirmed_at": result.confirmed_at.astimezone(UTC).isoformat(),
                "replayed": result.replayed,
            },
            headers={"Cache-Control": "no-store"},
        )

    @app.post("/api/v1/media-server/probe", status_code=202)
    def media_server_probe(_body: MediaServerOperationRequest, request: Request) -> dict[str, object]:
        """Persist and start one bounded read-only connection probe."""

        request_fingerprint, key_hash, profile_fingerprint = _media_server_operation_identity(
            request,
            "media-server-probe",
        )
        replay = _idempotent_replay(
            "media-server-probe",
            key_hash=key_hash,
            request_fingerprint=request_fingerprint,
        )
        if replay is not None:
            return _operation_start_payload(replay)

        def run_probe(context: OperationExecutionContext) -> OperationOutcome:
            phase = context.phase("probing")
            if phase.cancel_requested_at is not None or context.cancel_requested:
                return OperationOutcome.cancelled()
            try:
                result = media_server_service.probe()
            except MediaServerError as error:
                return OperationOutcome.failed(error.code, retryable=error.retryable)
            return OperationOutcome.success(
                {
                    "provider": result.provider,
                    "server_version": result.server_version,
                    "library_id_digest": result.library_id_digest,
                    "library_present": result.library_present,
                }
            )

        submission = _submit_operation(
            OperationExecution(
                kind="media-server-probe",
                request_fingerprint=request_fingerprint,
                idempotency_key_hash=key_hash,
                exclusive_key=f"media-server:{profile_fingerprint}",
                target_type=None,
                target_id=None,
                phase="preparing",
                execute=run_probe,
            )
        )
        return _operation_start_payload(submission)

    @app.post("/api/v1/media-server/scan", status_code=202)
    def media_server_scan(
        body: MediaServerOperationRequest | MediaServerAuthorOperationRequest,
        request: Request,
    ) -> dict[str, object]:
        """Persist and dispatch only the configured targeted library refresh."""

        if isinstance(body, MediaServerAuthorOperationRequest):
            profile_fingerprint = _media_server_profile_identity()
            observation = _media_server_observation()
            try:
                target = observation.resolve_target(body.author_id)
            except MediaServerError as error:
                raise _media_server_error(error) from None
            request_fingerprint, key_hash = _operation_identity(
                request,
                "media-server-scan",
                target_id=target.author_id,
                parameters={
                    "profile_fingerprint": profile_fingerprint,
                    "mode": "post_refresh_item_observation",
                    "publication_fingerprint": target.publication_fingerprint,
                },
            )
            replay = _idempotent_replay(
                "media-server-scan",
                key_hash=key_hash,
                request_fingerprint=request_fingerprint,
            )
            if replay is not None:
                return _operation_start_payload(replay)

            def run_observation(context: OperationExecutionContext) -> OperationOutcome:
                try:
                    return observation.observe_author(target, context)
                except MediaServerError as error:
                    if error.code == "media_server_scan_cancelled":
                        return OperationOutcome.cancelled()
                    return OperationOutcome.failed(error.code, retryable=error.retryable)

            submission = _submit_operation(
                OperationExecution(
                    kind="media-server-scan",
                    request_fingerprint=request_fingerprint,
                    idempotency_key_hash=key_hash,
                    exclusive_key=f"media-server:{profile_fingerprint}",
                    target_type="author",
                    target_id=target.author_id,
                    phase="preparing",
                    subjects=(
                        OperationSubjectInput(
                            "job",
                            target.publication_job_id,
                            "related",
                        ),
                    ),
                    execute=run_observation,
                )
            )
            return _operation_start_payload(submission)

        request_fingerprint, key_hash, profile_fingerprint = _media_server_operation_identity(
            request,
            "media-server-scan",
        )
        replay = _idempotent_replay(
            "media-server-scan",
            key_hash=key_hash,
            request_fingerprint=request_fingerprint,
        )
        if replay is not None:
            return _operation_start_payload(replay)

        def run_scan(context: OperationExecutionContext) -> OperationOutcome:
            phase = context.phase("discovering")
            if phase.cancel_requested_at is not None or context.cancel_requested:
                return OperationOutcome.cancelled()
            try:
                result = media_server_service.scan(lambda: context.cancel_requested)
            except MediaServerError as error:
                if error.code == "media_server_scan_cancelled":
                    return OperationOutcome.cancelled()
                return OperationOutcome.failed(error.code, retryable=error.retryable)
            return OperationOutcome.success(
                {
                    "provider": result.provider,
                    "server_version": result.server_version,
                    "library_id_digest": result.library_id_digest,
                    "scan_state": result.scan_state,
                }
            )

        submission = _submit_operation(
            OperationExecution(
                kind="media-server-scan",
                request_fingerprint=request_fingerprint,
                idempotency_key_hash=key_hash,
                exclusive_key=f"media-server:{profile_fingerprint}",
                target_type=None,
                target_id=None,
                phase="preparing",
                execute=run_scan,
            )
        )
        return _operation_start_payload(submission)

    def _validate_evidence_read(request: Request, author_id: str | None, *, history: bool) -> int:
        allowed = {"limit"} if history else {"author_id"}
        entries = list(request.query_params.multi_items())
        names = [name for name, _value in entries]
        raw_limit = request.query_params.get("limit", str(DEFAULT_EVIDENCE_HISTORY_LIMIT))
        if (
            not set(names).issubset(allowed)
            or len(names) != len(set(names))
            or re.fullmatch(r"[1-9][0-9]?", raw_limit) is None
        ):
            raise HTTPException(status_code=400, detail="playback_evidence_request_invalid")
        limit = int(raw_limit)
        if author_id is not None:
            try:
                validate_evidence_query(author_id, limit)
            except PlaybackEvidenceQueryError:
                raise HTTPException(status_code=400, detail="playback_evidence_request_invalid") from None
        return limit

    @app.get("/api/v1/media-server/playback-evidence/by-author/{author_id}")
    def author_playback_evidence(
        request: Request, author_id: str, limit: int = DEFAULT_EVIDENCE_HISTORY_LIMIT
    ) -> dict[str, object]:
        """Read current and bounded historical attestations for one author."""

        limit = _validate_evidence_read(request, author_id, history=True)
        try:
            return playback_evidence_query.snapshot(author_id, limit=limit).as_dict()
        except PlaybackEvidenceQueryError as error:
            raise HTTPException(status_code=503, detail=error.code) from None

    @app.get("/api/v1/qualifications")
    def qualifications(request: Request, author_id: str | None = None) -> dict[str, object]:
        """Keep local automated evidence separate from live qualifications."""

        _validate_evidence_read(request, author_id, history=False)
        _reconcile_operation_reads()
        try:
            profile_fingerprint = resolved.media_server_profile_fingerprint
            evidence = {
                "media-server-probe": _latest_media_server_operation(
                    "media-server-probe",
                    profile_fingerprint=profile_fingerprint,
                ),
                "media-server-scan": _latest_media_server_operation(
                    "media-server-scan",
                    profile_fingerprint=profile_fingerprint,
                ),
            }
            return QualificationService(operation_database, playback_evidence=playback_evidence_query).snapshot(
                media_server_configured=resolved.media_server_profile is not None,
                media_server_operations=evidence,
                author_id=author_id,
            )
        except QualificationError as error:
            raise HTTPException(status_code=503, detail=error.code) from None
        except (RepositoryError, SQLAlchemyError):
            raise HTTPException(status_code=503, detail="operation_store_unavailable") from None

    @app.api_route("/", methods=["GET", "HEAD"], include_in_schema=False)
    def console() -> Response:
        if web_root is not None:
            return _static_response(web_root)
        return _console_notice(missing_build=True)

    @app.api_route("/legacy", methods=["GET", "HEAD"], include_in_schema=False)
    def legacy_console() -> Response:
        return _console_notice(missing_build=False)

    # ------------------------------------------------------------- accounts

    @app.get("/api/v1/accounts")
    def list_accounts() -> list[dict[str, object]]:
        database = _database()
        try:
            with database.session() as session:
                return [_account_payload(account) for account in AccountRepository(session).list()]
        except SQLAlchemyError:
            raise _bad_request("database_operation_failed") from None
        finally:
            database.dispose()

    @app.post("/api/v1/accounts", status_code=201)
    def create_account(body: AccountCreate) -> dict[str, object]:
        database = _database()
        try:
            with database.session() as session:
                result = WorkbenchService(session).create_account(
                    AccountDraft(
                        platform=body.platform,
                        display_name=body.display_name,
                        login_method=body.login_method,
                        adapter="mediacrawler",
                        credential_ref=body.credential_ref,
                    )
                )
                return result.to_payload()
        except WorkbenchError as error:
            raise _workbench_error(error) from None
        except SQLAlchemyError:
            raise _bad_request("database_operation_failed") from None
        finally:
            database.dispose()

    @app.get("/api/v1/accounts/{account_id}/login-preflight")
    def login_preflight(
        account_id: UUID,
        accept_mediacrawler_license: bool = False,
    ) -> dict[str, object]:
        return collect_account_login_preflight(
            resolved,
            account_id,
            license_acknowledged=accept_mediacrawler_license,
        ).to_payload()

    @app.get("/api/v1/accounts/{account_id}/login-status")
    def login_status(account_id: UUID) -> dict[str, object]:
        database = _database()
        try:
            MediaCrawlerLoginSessionReconciler(
                database,
                integration_root=resolved.resolved_mediacrawler_runtime_dir,
            ).reconcile_account(account_id)
            with database.session() as session:
                account = AccountRepository(session).get(str(account_id))
                if account is None:
                    raise HTTPException(status_code=404, detail="account not found")
                sessions = LoginSessionRepository(session).list_for_account(account.id)
                latest = sessions[0] if sessions else None
                return _account_login_status_payload(
                    account,
                    latest,
                    diagnostic=latest_session_login_diagnostic(session, account.id, latest),
                )
        except HTTPException:
            raise
        except SQLAlchemyError:
            raise _bad_request("database_operation_failed") from None
        finally:
            database.dispose()

    def _login_qr_response(
        login_session_id: UUID,
        *,
        expected_account_id: UUID | None = None,
    ) -> Response:
        database = _database()
        try:
            with database.session() as session:
                repository = LoginSessionRepository(session)
                login_session = repository.get(str(login_session_id))
                if login_session is None:
                    raise HTTPException(status_code=404, detail="login_session_not_found")
                if expected_account_id is not None and login_session.account_id != str(expected_account_id):
                    raise HTTPException(status_code=404, detail="login_session_not_found")
                account = AccountRepository(session).get(login_session.account_id)
                if account is None:  # pragma: no cover - guarded by the database foreign key
                    raise HTTPException(status_code=404, detail="login_session_not_found")
                if (
                    account.adapter != "mediacrawler"
                    or login_session.method != "qr"
                    or login_session.challenge_kind != "qr"
                ):
                    raise HTTPException(status_code=404, detail="login_qr_not_available")
                try:
                    account_id = UUID(account.id)
                    platform = Platform(account.platform)
                except ValueError:
                    raise HTTPException(status_code=404, detail="login_qr_not_available") from None
                if str(account_id) != account.id:
                    raise HTTPException(status_code=404, detail="login_qr_not_available")
                status = login_session.status
                if status in {"pending", "waiting_user"}:
                    try:
                        current = repository.get_active_for_account(account.id)
                    except AccountLoginConflictError:
                        raise HTTPException(status_code=409, detail="account_login_conflict") from None
                    if current is None or current.id != str(login_session_id):
                        raise HTTPException(status_code=404, detail="login_qr_not_available")
        except HTTPException:
            raise
        except SQLAlchemyError:
            raise _bad_request("database_operation_failed") from None
        finally:
            database.dispose()

        if status in {"pending", "waiting_user"}:
            reconcile_database = _database()
            try:
                MediaCrawlerLoginSessionReconciler(
                    reconcile_database,
                    integration_root=resolved.resolved_mediacrawler_runtime_dir,
                ).reconcile_account(account_id)
                with reconcile_database.session() as session:
                    repository = LoginSessionRepository(session)
                    refreshed = repository.get(str(login_session_id))
                    if refreshed is None:
                        raise HTTPException(status_code=404, detail="login_session_not_found")
                    status = refreshed.status
                    if status in {"pending", "waiting_user"}:
                        try:
                            current = repository.get_active_for_account(str(account_id))
                        except AccountLoginConflictError:
                            raise HTTPException(status_code=409, detail="account_login_conflict") from None
                        if current is None or current.id != str(login_session_id):
                            raise HTTPException(status_code=404, detail="login_qr_not_available")
            except HTTPException:
                raise
            except SQLAlchemyError:
                raise _bad_request("database_operation_failed") from None
            finally:
                reconcile_database.dispose()

        if status in {"succeeded", "expired", "failed", "cancelled"}:
            return JSONResponse(
                status_code=410,
                content={"code": "login_qr_gone", "login_session_id": str(login_session_id)},
                headers={"Cache-Control": "no-store"},
            )
        if status not in {"pending", "waiting_user"}:  # pragma: no cover - closed database constraint
            raise HTTPException(status_code=404, detail="login_qr_not_available")

        qr_path = (
            resolved.resolved_mediacrawler_runtime_dir
            / "accounts"
            / platform.value
            / str(account_id)
            / LOGIN_QR_IMAGE_NAME
        )
        try:
            metadata = qr_path.lstat()
        except FileNotFoundError:
            metadata = None
        except OSError:
            raise HTTPException(status_code=404, detail="login_qr_not_available") from None
        if metadata is None:
            return JSONResponse(
                status_code=202,
                content={"code": "login_qr_pending", "login_session_id": str(login_session_id)},
                headers={"Cache-Control": "no-store"},
            )
        if not stat.S_ISREG(metadata.st_mode) or not 0 < metadata.st_size <= _MAX_LOGIN_QR_BYTES:
            raise HTTPException(status_code=404, detail="login_qr_not_available")
        try:
            with qr_path.open("rb") as stream:
                opened = os.fstat(stream.fileno())
                if (
                    not stat.S_ISREG(opened.st_mode)
                    or opened.st_dev != metadata.st_dev
                    or opened.st_ino != metadata.st_ino
                    or opened.st_size != metadata.st_size
                ):
                    raise HTTPException(status_code=404, detail="login_qr_not_available")
                qr_bytes = stream.read(_MAX_LOGIN_QR_BYTES + 1)
        except HTTPException:
            raise
        except OSError:
            raise HTTPException(status_code=404, detail="login_qr_not_available") from None
        if not 0 < len(qr_bytes) <= _MAX_LOGIN_QR_BYTES:
            raise HTTPException(status_code=404, detail="login_qr_not_available")

        # The relay filename is account-scoped. Revalidate after reading the
        # immutable bytes so a terminal transition followed by a new attempt
        # cannot pair the requested session identity with the next QR image.
        database = _database()
        try:
            with database.session() as session:
                repository = LoginSessionRepository(session)
                revalidated = repository.get(str(login_session_id))
                if revalidated is None:
                    raise HTTPException(status_code=404, detail="login_session_not_found")
                if revalidated.status in {"succeeded", "expired", "failed", "cancelled"}:
                    return JSONResponse(
                        status_code=410,
                        content={"code": "login_qr_gone", "login_session_id": str(login_session_id)},
                        headers={"Cache-Control": "no-store"},
                    )
                try:
                    current = repository.get_active_for_account(str(account_id))
                except AccountLoginConflictError:
                    raise HTTPException(status_code=409, detail="account_login_conflict") from None
                if current is None or current.id != str(login_session_id):
                    raise HTTPException(status_code=404, detail="login_qr_not_available")
        except HTTPException:
            raise
        except SQLAlchemyError:
            raise _bad_request("database_operation_failed") from None
        finally:
            database.dispose()
        return Response(
            content=qr_bytes,
            media_type="image/png",
            headers={
                "Cache-Control": "no-store",
                "X-Login-Session-Id": str(login_session_id),
            },
        )

    @app.get("/api/v1/login-sessions/{login_session_id}/qr.png")
    def login_session_qr(login_session_id: UUID) -> Response:
        return _login_qr_response(login_session_id)

    @app.get("/api/v1/accounts/{account_id}/login-qr.png")
    def login_qr(account_id: UUID) -> Response:
        database = _database()
        try:
            with database.session() as session:
                account = AccountRepository(session).get(str(account_id))
                if account is None:
                    raise HTTPException(status_code=404, detail="account not found")
                latest_id = session.scalar(
                    select(LoginSession.id)
                    .where(
                        LoginSession.account_id == account.id,
                        LoginSession.method == "qr",
                        LoginSession.challenge_kind == "qr",
                    )
                    .order_by(LoginSession.created_at.desc(), LoginSession.id.desc())
                    .limit(1)
                )
        except HTTPException:
            raise
        except SQLAlchemyError:
            raise _bad_request("database_operation_failed") from None
        finally:
            database.dispose()
        if latest_id is None:
            raise HTTPException(status_code=404, detail="login_qr_not_available")
        return _login_qr_response(UUID(latest_id), expected_account_id=account_id)

    @app.post("/api/v1/accounts/{account_id}/login", status_code=202)
    def start_login(account_id: UUID, body: LoginStart, request: Request) -> dict[str, object]:
        if not body.enable_mediacrawler:
            raise _bad_request("mediacrawler_not_enabled")
        request_fingerprint, key_hash = _operation_identity(
            request,
            "account-login",
            target_id=str(account_id),
            parameters={
                "timeout_microseconds": round(body.timeout_seconds * 1_000_000),
                "enable_mediacrawler": body.enable_mediacrawler,
                "accept_mediacrawler_license": body.accept_mediacrawler_license,
            },
        )
        replay = _idempotent_replay(
            "account-login",
            key_hash=key_hash,
            request_fingerprint=request_fingerprint,
        )
        if replay is not None:
            return _operation_start_payload(replay)
        preflight = collect_account_login_preflight(
            resolved,
            account_id,
            license_acknowledged=body.accept_mediacrawler_license,
        )
        if not preflight.ok:
            replay = _idempotent_replay(
                "account-login",
                key_hash=key_hash,
                request_fingerprint=request_fingerprint,
            )
            if replay is not None:
                return _operation_start_payload(replay)
            status_code = 404 if preflight.code == "account_login_not_found" else 400
            if preflight.code == "account_login_busy":
                status_code = 409
            raise HTTPException(status_code=status_code, detail=preflight.code)

        def run_login(context: OperationExecutionContext) -> OperationOutcome:
            login_database: Database | None = None
            try:
                phase = context.phase("authenticating")
                if phase.cancel_requested_at is not None or context.cancel_requested:
                    return OperationOutcome.cancelled()
                login_database = Database(resolved.resolved_database_url)
                if resolved.mediacrawler_python_executable is None:
                    runner: Any = _UnavailableMediaCrawlerLoginRunner()
                else:
                    runner = MediaCrawlerLoginProcessRunner(
                        lock_path=resolved.mediacrawler_lock_path,
                        integration_root=resolved.resolved_mediacrawler_runtime_dir,
                        python_executable=resolved.mediacrawler_python_executable,
                        enabled=True,
                        license_acknowledged=True,
                    )
                reconciler = MediaCrawlerLoginSessionReconciler(
                    login_database,
                    integration_root=resolved.resolved_mediacrawler_runtime_dir,
                )
                outcome = MediaCrawlerQrLoginService(login_database, runner, reconciler=reconciler).run(
                    AccountLoginRequest(
                        account_id=account_id,
                        timeout_seconds=body.timeout_seconds,
                        poll_seconds=min(0.05, body.timeout_seconds / 2),
                    ),
                    cancellation=context.cancellation,
                    subject_hook=context.subject_hook,
                )
                raw_result = _account_login_outcome_payload(outcome)
                result = {
                    key: raw_result[key]
                    for key in (
                        "account_id",
                        "login_session_id",
                        "runner_status",
                        "login_session_status",
                        "auth_status",
                        "expires_at",
                        "completed_at",
                    )
                }
                if outcome.authenticated:
                    return OperationOutcome.success(result)
                if outcome.runner_status.value == "cancelled" or outcome.session_status == "cancelled":
                    return OperationOutcome.cancelled(result)
                error_code = login_operation_error_code(outcome.runner_status.value)
                return OperationOutcome.failed(error_code, retryable=False, payload=result)
            except AccountLoginError as error:
                return OperationOutcome.failed(
                    error.code,
                    retryable=error.code in _ACCOUNT_LOGIN_RETRYABLE_CODES,
                )
            finally:
                if login_database is not None:
                    login_database.dispose()

        submission = _submit_operation(
            OperationExecution(
                kind="account-login",
                request_fingerprint=request_fingerprint,
                idempotency_key_hash=key_hash,
                exclusive_key=f"account-login:{account_id}",
                target_type="account",
                target_id=str(account_id),
                phase="preparing",
                execute=run_login,
            )
        )
        return _operation_start_payload(submission)

    @app.post("/api/v1/accounts/{account_id}/cookie-login", status_code=202)
    async def start_cookie_login(account_id: UUID, request: Request) -> dict[str, object]:
        try:
            body = await read_cookie_login_body(request)
        except CookieRequestError as error:
            raise HTTPException(status_code=error.status, detail=error.code) from None
        if not body.enable_mediacrawler:
            raise _bad_request("mediacrawler_not_enabled")
        if not body.accept_mediacrawler_license:
            raise _bad_request("license_acknowledgement_required")
        fingerprint, key_hash = _operation_identity(
            request,
            "account-cookie-login",
            target_id=str(account_id),
            parameters={
                "identity_digest": hashlib.sha256(
                    (body.platform.value + "\0" + body.cookie.reveal()).encode("ascii")
                ).hexdigest(),
                "expected_auth_revision": body.expected_auth_revision,
                "frontend_generation": str(body.frontend_generation),
                "enable_mediacrawler": body.enable_mediacrawler,
                "accept_mediacrawler_license": body.accept_mediacrawler_license,
            },
        )
        replay = await asyncio.to_thread(
            _idempotent_replay,
            "account-cookie-login",
            key_hash=key_hash,
            request_fingerprint=fingerprint,
        )
        if replay is not None:
            return _operation_start_payload(replay)
        try:
            await asyncio.to_thread(
                cookie_login_service.preflight, str(account_id), body.platform, body.expected_auth_revision
            )
        except CookieAccountError as error:
            status = (
                404
                if error.code == "cookie_login_account_not_found"
                else 409
                if error.code in {"cookie_login_conflict", "cookie_login_busy"}
                else 400
            )
            raise HTTPException(status_code=status, detail=error.code) from None
        except SQLAlchemyError:
            raise HTTPException(status_code=503, detail="cookie_login_unavailable") from None
        submission = await asyncio.to_thread(
            _submit_operation,
            OperationExecution(
                kind="account-cookie-login",
                request_fingerprint=fingerprint,
                idempotency_key_hash=key_hash,
                exclusive_key=f"account-login:{account_id}",
                target_type="account",
                target_id=str(account_id),
                phase="preparing",
                execute=lambda context: cookie_login_service.execute(
                    context,
                    account_id=str(account_id),
                    platform=body.platform,
                    expected_auth_revision=body.expected_auth_revision,
                    candidate=body.cookie,
                ),
            ),
        )
        return _operation_start_payload(submission)

    # ----------------------------------------------- creator profile lookup

    @app.post("/api/v1/accounts/{account_id}/creator-lookups", status_code=202)
    def start_creator_lookup(account_id: UUID, body: CreatorLookupStart, request: Request) -> dict[str, object]:
        if not body.enable_mediacrawler:
            raise _bad_request("mediacrawler_not_enabled")
        if not body.accept_mediacrawler_license:
            raise _bad_request("license_acknowledgement_required")
        fingerprint, key_hash = _operation_identity(
            request,
            "creator-profile",
            target_id=str(account_id),
            parameters={
                "identity_digest": hashlib.sha256(
                    f"{body.platform.value}\0{body.creator_remote_id}".encode()
                ).hexdigest(),
                "frontend_generation": str(body.frontend_generation),
                "enable_mediacrawler": body.enable_mediacrawler,
                "accept_mediacrawler_license": body.accept_mediacrawler_license,
            },
        )
        replay = _idempotent_replay("creator-profile", key_hash=key_hash, request_fingerprint=fingerprint)
        if replay is not None:
            return _operation_start_payload(replay)
        try:
            digest = creator_profile_service.preflight(str(account_id), body.platform.value, body.creator_remote_id)
        except CreatorProfileError as error:
            raise _bad_request(error.code) from None
        except SQLAlchemyError:
            raise HTTPException(status_code=503, detail="creator_profile_unavailable") from None
        return _operation_start_payload(
            _submit_operation(
                OperationExecution(
                    kind="creator-profile",
                    request_fingerprint=fingerprint,
                    idempotency_key_hash=key_hash,
                    exclusive_key=f"creator-profile:{account_id}",
                    target_type="account",
                    target_id=str(account_id),
                    phase="preparing",
                    execute=lambda context: creator_profile_service.execute(
                        context,
                        account_id=str(account_id),
                        platform=body.platform.value,
                        creator_remote_id=body.creator_remote_id,
                        frontend_generation=str(body.frontend_generation),
                        credential_digest=digest,
                    ),
                )
            )
        )

    def _verified_profile_payload(session: Any, profile: ProfileSnapshot | None) -> dict[str, object] | None:
        if profile is None:
            return None
        observed = session.get(Operation, profile.last_success_operation_id)
        if (
            observed is None
            or observed.kind != "creator-profile"
            or observed.state != "succeeded"
            or observed.target_type != "account"
            or observed.target_id != profile.account_id
            or observed.result_summary.get("profile_id") != profile.profile_id
            or observed.result_summary.get("revision") != profile.revision
        ):
            return None
        return profile_payload(profile)

    @app.get("/api/v1/creator-lookups/{operation_id}")
    def creator_lookup(operation_id: UUID) -> dict[str, object]:
        try:
            with operation_database.session() as session:
                operation = session.get(Operation, str(operation_id))
                if operation is None or operation.kind != "creator-profile" or operation.target_type != "account":
                    raise HTTPException(status_code=404, detail="creator_profile_not_found")
                lookup = CreatorProfileRepository(session).read_lookup(str(operation_id))
                identity: dict[str, object] | None = None
                profile = None
                source = None
                if lookup is not None:
                    ticket = lookup.ticket
                    if ticket.account_id != operation.target_id or ticket.operation_id != operation.id:
                        raise _bad_request("creator_profile_identity_mismatch")
                    identity = {
                        "account_id": ticket.account_id,
                        "platform": ticket.platform,
                        "creator_remote_id": ticket.creator_remote_id,
                        "frontend_generation": ticket.frontend_generation,
                        "generation": ticket.generation,
                        "operation_id": ticket.operation_id,
                        "result_profile_revision": lookup.result_revision,
                    }
                    profile = _verified_profile_payload(session, lookup.profile)
                    if profile is not None:
                        source = (
                            "lookup_result"
                            if (
                                operation.state == "succeeded"
                                and lookup.state == "succeeded"
                                and lookup.result_revision == profile["revision"]
                                and lookup.profile is not None
                                and lookup.profile.last_success_operation_id == operation.id
                            )
                            else "previous_success"
                        )
                return {
                    "operation_id": operation.id,
                    "state": operation.state,
                    "error_code": lookup_error_code(operation.error_code),
                    "lookup": identity,
                    "profile": profile,
                    "profile_source": source,
                }
        except CreatorProfileError as error:
            raise _bad_request(error.code) from None
        except SQLAlchemyError:
            raise HTTPException(status_code=503, detail="creator_profile_unavailable") from None

    @app.get("/api/v1/creator-profiles/{profile_id}/avatar/{revision}")
    def creator_avatar(profile_id: UUID, revision: int) -> Response:
        try:
            with operation_database.session() as session:
                payload = CreatorProfileRepository(session).get_avatar(str(profile_id), revision)
            if payload is None:
                raise HTTPException(status_code=404, detail="creator_avatar_not_found")
            return Response(
                payload,
                media_type="image/png",
                headers={
                    "Cache-Control": "private, no-store",
                    "X-Content-Type-Options": "nosniff",
                    "Cross-Origin-Resource-Policy": "same-origin",
                },
            )
        except CreatorProfileError as error:
            raise _bad_request(error.code) from None
        except SQLAlchemyError:
            raise HTTPException(status_code=503, detail="creator_profile_unavailable") from None

    # --------------------------------------------------------- subscriptions

    def _add_creator_profile(session: Any, subscription: Subscription, payload: dict[str, object]) -> None:
        payload["creator_profile"] = _verified_profile_payload(
            session,
            CreatorProfileRepository(session).get_profile(
                subscription.account_id,
                subscription.account.platform,
                subscription.author.remote_id,
            ),
        )

    @app.get("/api/v1/subscriptions")
    def list_subscriptions(deleted: bool = False) -> list[dict[str, object]]:
        database = _database()
        try:
            with database.session() as session:
                payloads: list[dict[str, object]] = []
                for subscription in SubscriptionRepository(session).list(deleted=deleted):
                    payload = _subscription_payload(subscription)
                    payload["policy_summary"] = _subscription_policy_summary_payload(subscription)
                    _add_creator_profile(session, subscription, payload)
                    payloads.append(payload)
                return payloads
        except SQLAlchemyError:
            raise _bad_request("database_operation_failed") from None
        finally:
            database.dispose()

    def _subscription_draft(body: SubscriptionCreate) -> SubscriptionDraft:
        return SubscriptionDraft(
            account_id=body.account_id,
            platform=body.platform,
            creator_remote_id=body.creator_remote_id,
            display_name=body.display_name or "",
            local_alias=body.local_alias,
            profile_lookup_id=body.profile_lookup_id,
            creator_secret_ref=body.creator_reference_ref,
            interval_seconds=body.interval_seconds,
            max_items=body.max_items,
            allow_full_history=body.allow_full_history,
            request_delay_seconds=body.request_delay_seconds,
            headless=body.headless,
        )

    @app.post("/api/v1/subscriptions/preview")
    def preview_subscription(body: SubscriptionCreate) -> dict[str, object]:
        database = _database()
        try:
            with database.session() as session:
                return WorkbenchService(session).validate_subscription(_subscription_draft(body)).to_payload()
        except WorkbenchError as error:
            raise _workbench_error(error) from None
        except SQLAlchemyError:
            raise _bad_request("database_operation_failed") from None
        finally:
            database.dispose()

    @app.post("/api/v1/subscriptions", status_code=201)
    def create_subscription(body: SubscriptionCreate) -> dict[str, object]:
        database = _database()
        try:
            with database.session() as session:
                return WorkbenchService(session).create_subscription(_subscription_draft(body)).to_payload()
        except WorkbenchError as error:
            raise _workbench_error(error) from None
        except SQLAlchemyError:
            raise _bad_request("database_operation_failed") from None
        finally:
            database.dispose()

    def _subscription_schedule_action(subscription_id: UUID, action: str) -> dict[str, object]:
        database = _database()
        try:
            service = DurableSchedulerService(database)
            schedule = {
                "pause": service.pause_subscription,
                "resume": service.resume_subscription,
                "run-now": service.run_now,
            }[action](str(subscription_id))
            return _scheduler_schedule_payload(schedule)
        except SubscriptionRemovalError as error:
            raise HTTPException(status_code=409, detail=error.code) from None
        except NotFoundError:
            raise HTTPException(status_code=404, detail="subscription not found") from None
        except (StaleLaneError, SQLAlchemyError, ValueError, TypeError):
            raise _bad_request("scheduler_operation_rejected") from None
        finally:
            database.dispose()

    @app.get("/api/v1/subscriptions/{subscription_id}")
    def subscription_detail(subscription_id: UUID) -> dict[str, object]:
        database = _database()
        try:
            with database.session() as session:
                subscription = SubscriptionRepository(session).get(str(subscription_id))
                if subscription is None:
                    raise HTTPException(status_code=404, detail="subscription not found")
                payload = _subscription_payload(subscription)
                _add_creator_profile(session, subscription, payload)
                payload["policy_summary"] = _subscription_policy_summary_payload(subscription)
                payload["checkpoint_summary"] = _subscription_checkpoint_summary_payload(
                    subscription,
                    lock_path=resolved.mediacrawler_lock_path,
                )
                payload["schedule"] = _scheduler_schedule_payload(
                    SchedulerRepository(session).get_subscription_schedule(str(subscription_id))
                )
                runs = (
                    session.execute(
                        select(SyncRun)
                        .where(SyncRun.subscription_id == str(subscription_id))
                        .order_by(SyncRun.created_at.desc(), SyncRun.id.desc())
                        .limit(5)
                    )
                    .scalars()
                    .all()
                )
                payload["recent_runs"] = [
                    {
                        "run_id": run.id,
                        "status": run.status,
                        "attempt": run.attempt,
                        "discovered_count": run.discovered_count,
                        "asset_count": run.asset_count,
                        "error_code": run.error_code,
                        "started_at": run.started_at.isoformat() if run.started_at else None,
                        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
                    }
                    for run in runs
                ]
            payload["recent_jobs"] = [
                _scheduler_job_payload(job)
                for job in DurableSchedulerService(database).list_jobs(subscription_id=str(subscription_id), limit=5)
            ]
            return payload
        except HTTPException:
            raise
        except NotFoundError:
            raise HTTPException(status_code=404, detail="subscription not found") from None
        except (SQLAlchemyError, ValueError, TypeError):
            raise _bad_request("scheduler_operation_rejected") from None
        finally:
            database.dispose()

    @app.get("/api/v1/scheduler/jobs/{job_id}")
    def scheduler_job_detail(job_id: UUID) -> dict[str, object]:
        database = _database()
        try:
            with database.session() as session:
                return _scheduler_job_payload(SchedulerRepository(session).get_job(str(job_id)))
        except NotFoundError:
            raise HTTPException(status_code=404, detail="job not found") from None
        except (SQLAlchemyError, ValueError, TypeError):
            raise _bad_request("scheduler_operation_rejected") from None
        finally:
            database.dispose()

    @app.get("/api/v1/scheduler/jobs/{job_id}/diagnostics")
    def scheduler_job_diagnostics(job_id: UUID) -> dict[str, object]:
        database = _database()
        try:
            return JobDiagnosticService(database, expected_revision=_EXPECTED_DATABASE_REVISION).build(str(job_id))
        except JobDiagnosticError as error:
            status_code = 404 if error.code == "job_diagnostic_not_found" else 503
            raise HTTPException(status_code=status_code, detail=error.code) from None
        finally:
            database.dispose()

    def _subscription_lifecycle(subscription_id: UUID, *, restore: bool) -> dict[str, object]:
        database = _database()
        try:
            service = SubscriptionRemovalService(database)
            result = service.restore(str(subscription_id)) if restore else service.remove(str(subscription_id))
            return result.to_payload()
        except SubscriptionRemovalError as error:
            status_code = 404 if error.code == "subscription_not_found" else 409
            raise HTTPException(status_code=status_code, detail=error.code) from None
        except (SQLAlchemyError, ValueError, TypeError):
            raise _bad_request("subscription_operation_rejected") from None
        finally:
            database.dispose()

    @app.delete("/api/v1/subscriptions/{subscription_id}")
    def delete_subscription(subscription_id: UUID) -> dict[str, object]:
        return _subscription_lifecycle(subscription_id, restore=False)

    @app.post("/api/v1/subscriptions/{subscription_id}/restore")
    def restore_subscription(subscription_id: UUID) -> dict[str, object]:
        return _subscription_lifecycle(subscription_id, restore=True)

    @app.post("/api/v1/assets/{asset_id}/download", status_code=202)
    def download_asset(asset_id: UUID, body: AssetDownload, request: Request) -> dict[str, object]:
        if body.accept_mediacrawler_license and not body.enable_mediacrawler:
            raise _bad_request("license_requires_enable_mediacrawler")
        normalized_detail_reference = _safe_credential_reference(body.xhs_detail_reference_ref)
        if normalized_detail_reference is not None and not body.enable_mediacrawler:
            raise _bad_request("xhs_detail_reference_requires_mediacrawler")
        request_fingerprint, key_hash = _operation_identity(
            request,
            "asset-download",
            target_id=str(asset_id),
            parameters={
                "lease_seconds": body.lease_seconds,
                "max_attempts": body.max_attempts,
                "enable_mediacrawler": body.enable_mediacrawler,
                "accept_mediacrawler_license": body.accept_mediacrawler_license,
                "xhs_detail_reference_digest": _private_reference_digest(normalized_detail_reference),
            },
        )
        replay = _idempotent_replay(
            "asset-download",
            key_hash=key_hash,
            request_fingerprint=request_fingerprint,
        )
        if replay is not None:
            return _operation_start_payload(replay)
        database = _database()
        try:
            with database.session() as session:
                if session.get(Asset, str(asset_id)) is None:
                    replay = _idempotent_replay(
                        "asset-download",
                        key_hash=key_hash,
                        request_fingerprint=request_fingerprint,
                    )
                    if replay is not None:
                        return _operation_start_payload(replay)
                    raise HTTPException(status_code=404, detail="asset not found")
        except SQLAlchemyError:
            raise _bad_request("database_operation_failed") from None
        finally:
            database.dispose()

        def run_download(context: OperationExecutionContext) -> OperationOutcome:
            download_database: Database | None = None
            try:
                phase = context.phase("downloading")
                if phase.cancel_requested_at is not None or context.cancel_requested:
                    return OperationOutcome.cancelled()
                download_database = Database(resolved.resolved_database_url)
                payload, ok = _execute_asset_download(
                    asset_id=asset_id,
                    worker_id=context.worker_id,
                    lease_seconds=body.lease_seconds,
                    max_attempts=body.max_attempts,
                    enable_mediacrawler=body.enable_mediacrawler,
                    accept_mediacrawler_license=body.accept_mediacrawler_license,
                    subscription_id=None,
                    xhs_detail_reference_ref=normalized_detail_reference,
                    settings=resolved,
                    database=download_database,
                    subject_hook=context.subject_hook,
                )
                result = {
                    "asset_id": str(asset_id),
                    "job_id": payload.get("job_id"),
                    "ok": ok,
                    "status": payload.get("status", "failed"),
                    "disposition": payload.get("disposition"),
                    "generation": payload.get("generation"),
                    "size_bytes": payload.get("size_bytes"),
                }
                if ok:
                    return OperationOutcome.success(result)
                error_code = payload.get("error_code")
                if not isinstance(error_code, str):
                    error_code = "asset_download_failed"
                return OperationOutcome.failed(
                    error_code,
                    retryable=payload.get("retryable") is True,
                    payload=result,
                )
            except ValueError:
                return OperationOutcome.failed("asset_download_request_invalid", retryable=False)
            finally:
                if download_database is not None:
                    download_database.dispose()

        submission = _submit_operation(
            OperationExecution(
                kind="asset-download",
                request_fingerprint=request_fingerprint,
                idempotency_key_hash=key_hash,
                exclusive_key=f"asset-download:{asset_id}",
                target_type="asset",
                target_id=str(asset_id),
                phase="preparing",
                execute=run_download,
            )
        )
        return _operation_start_payload(submission)

    @app.post("/api/v1/subscriptions/{subscription_id}/pause")
    def pause_subscription(subscription_id: UUID) -> dict[str, object]:
        return _subscription_schedule_action(subscription_id, "pause")

    @app.post("/api/v1/subscriptions/{subscription_id}/resume")
    def resume_subscription(subscription_id: UUID) -> dict[str, object]:
        return _subscription_schedule_action(subscription_id, "resume")

    @app.post("/api/v1/subscriptions/{subscription_id}/run-now")
    def run_subscription_now(subscription_id: UUID) -> dict[str, object]:
        return _subscription_schedule_action(subscription_id, "run-now")

    # ------------------------------------------------------------ scheduler

    @app.post("/api/v1/scheduler/tick")
    def scheduler_tick(body: SchedulerTick) -> dict[str, object]:
        database = _database()
        try:
            result = DurableSchedulerService(database).tick(limit=body.limit)
            return {
                "materialized_count": result.materialized_count,
                "cycles": [_scheduler_cycle_payload(cycle) for cycle in result.cycles],
            }
        except (SQLAlchemyError, ValueError, TypeError):
            raise _bad_request("scheduler_operation_rejected") from None
        finally:
            database.dispose()

    @app.post("/api/v1/scheduler/run", status_code=202)
    def scheduler_run(body: SchedulerRun, request: Request) -> dict[str, object]:
        if body.accept_mediacrawler_license and not body.enable_mediacrawler:
            raise _bad_request("license_requires_enable_mediacrawler")
        request_fingerprint, key_hash = _operation_identity(
            request,
            "scheduler-run",
            target_id=None,
            parameters={
                "max_jobs": body.max_jobs,
                "global_capacity": body.global_capacity,
                "lease_seconds": body.lease_seconds,
                "scan_limit": body.scan_limit,
                "enable_mediacrawler": body.enable_mediacrawler,
                "accept_mediacrawler_license": body.accept_mediacrawler_license,
            },
        )

        def run_worker(context: OperationExecutionContext) -> OperationOutcome:
            worker_database: Database | None = None
            try:
                phase = context.phase("claiming_jobs")
                if phase.cancel_requested_at is not None or context.cancel_requested:
                    return OperationOutcome.cancelled({"statuses": []})
                run_settings = resolved
                worker_database = Database(run_settings.resolved_database_url)
                worker = _build_subscription_worker(
                    worker_database,
                    run_settings,
                    enable_mediacrawler=body.enable_mediacrawler,
                    accept_mediacrawler_license=body.accept_mediacrawler_license,
                )
                results = asyncio.run(
                    worker.run_bounded(
                        worker_id=context.worker_id,
                        max_jobs=body.max_jobs,
                        global_capacity=body.global_capacity,
                        lease_seconds=body.lease_seconds,
                        scan_limit=body.scan_limit,
                        cancellation=context.cancellation,
                        subject_hook=context.subject_hook,
                    )
                )
                statuses = [item.status for item in results]
                context.progress(
                    phase="jobs_processed",
                    current=len(statuses),
                    total=body.max_jobs,
                    unit="jobs",
                )
                result = {"statuses": statuses}
                if context.cancel_requested and len(statuses) < body.max_jobs:
                    return OperationOutcome.cancelled(result)
                return OperationOutcome.success(result)
            except Exception:
                return OperationOutcome.failed("scheduler_run_failed", retryable=True)
            finally:
                if worker_database is not None:
                    worker_database.dispose()

        submission = _submit_operation(
            OperationExecution(
                kind="scheduler-run",
                request_fingerprint=request_fingerprint,
                idempotency_key_hash=key_hash,
                exclusive_key="scheduler-run:global",
                phase="preparing",
                execute=run_worker,
            )
        )
        return _operation_start_payload(submission)

    @app.post("/api/v1/pipeline/run", status_code=202)
    def pipeline_run(body: PipelineRun, request: Request) -> dict[str, object]:
        if body.accept_mediacrawler_license and not body.enable_mediacrawler:
            raise _bad_request("license_requires_enable_mediacrawler")
        normalized_xhs_reference = _safe_credential_reference(body.xhs_detail_reference_ref)
        if normalized_xhs_reference is not None and not body.enable_mediacrawler:
            raise _bad_request("xhs_detail_reference_requires_mediacrawler")
        request_fingerprint, key_hash = _operation_identity(
            request,
            "pipeline-run",
            target_id=None,
            parameters={
                "max_jobs": body.max_jobs,
                "lease_seconds": body.lease_seconds,
                "scan_limit": body.scan_limit,
                "retry_delay_seconds": body.retry_delay_seconds,
                "enable_mediacrawler": body.enable_mediacrawler,
                "accept_mediacrawler_license": body.accept_mediacrawler_license,
                "xhs_detail_reference_digest": _private_reference_digest(normalized_xhs_reference),
            },
        )

        def run_pipeline(context: OperationExecutionContext) -> OperationOutcome:
            worker_database: Database | None = None
            try:
                phase = context.phase("claiming_jobs")
                if phase.cancel_requested_at is not None or context.cancel_requested:
                    return OperationOutcome.cancelled({"statuses": []})
                run_settings = resolved
                worker_database = Database(run_settings.resolved_database_url)
                worker = _build_pipeline_worker(
                    worker_database,
                    run_settings,
                    worker_id=context.worker_id,
                    retry_delay_seconds=body.retry_delay_seconds,
                    enable_mediacrawler=body.enable_mediacrawler,
                    accept_mediacrawler_license=body.accept_mediacrawler_license,
                    xhs_detail_reference_ref=normalized_xhs_reference,
                )
                results = asyncio.run(
                    worker.run_bounded(
                        worker_id=context.worker_id,
                        max_jobs=body.max_jobs,
                        lease_seconds=body.lease_seconds,
                        scan_limit=body.scan_limit,
                        cancellation=context.cancellation,
                        subject_hook=context.subject_hook,
                    )
                )
                statuses = [item.status for item in results]
                context.progress(
                    phase="jobs_processed",
                    current=len(statuses),
                    total=body.max_jobs,
                    unit="jobs",
                )
                result = {"statuses": statuses}
                if context.cancel_requested and len(statuses) < body.max_jobs:
                    return OperationOutcome.cancelled(result)
                return OperationOutcome.success(result)
            except Exception:
                return OperationOutcome.failed("pipeline_run_failed", retryable=True)
            finally:
                if worker_database is not None:
                    worker_database.dispose()

        submission = _submit_operation(
            OperationExecution(
                kind="pipeline-run",
                request_fingerprint=request_fingerprint,
                idempotency_key_hash=key_hash,
                exclusive_key="pipeline-run:global",
                phase="preparing",
                execute=run_pipeline,
            )
        )
        return _operation_start_payload(submission)

    @app.get("/api/v1/scheduler/jobs")
    def list_scheduler_jobs(
        status: JobStatus | None = None,
        subscription_id: UUID | None = None,
        limit: int = 100,
    ) -> list[dict[str, object]]:
        database = _database()
        try:
            jobs = DurableSchedulerService(database).list_jobs(
                status=status.value if status is not None else None,
                subscription_id=str(subscription_id) if subscription_id is not None else None,
                limit=max(1, min(limit, 1_000)),
            )
            return [_scheduler_job_payload(job) for job in jobs]
        except (SQLAlchemyError, ValueError, TypeError):
            raise _bad_request("scheduler_operation_rejected") from None
        finally:
            database.dispose()

    # ---------------------------------------------------------- assets/export

    @app.get("/api/v1/assets")
    def list_assets(
        author_id: UUID | None = None,
        content_id: UUID | None = None,
        platform: Platform | None = None,
        kind: AssetKind | None = None,
        status: AssetStatus | None = None,
        archived: bool | None = None,
        q: str | None = Query(default=None, max_length=200),
        limit: int = 200,
    ) -> list[dict[str, object]]:
        database = _database()
        try:
            return ContentAssetExplorer(database).list_assets(
                author_id=str(author_id) if author_id is not None else None,
                content_id=str(content_id) if content_id is not None else None,
                platform=platform.value if platform is not None else None,
                kind=kind.value if kind is not None else None,
                status=status.value if status is not None else None,
                archived=archived,
                query=q,
                limit=max(1, min(limit, 1_000)),
            )
        except CatalogExplorerError as error:
            raise _catalog_error(error) from None
        except SQLAlchemyError:
            raise _bad_request("database_operation_failed") from None
        finally:
            database.dispose()

    @app.get("/api/v1/assets/{asset_id}")
    def get_asset(asset_id: UUID) -> dict[str, object]:
        database = _database()
        try:
            return ContentAssetExplorer(database).get_asset(str(asset_id))
        except CatalogExplorerError as error:
            raise _catalog_error(error) from None
        except SQLAlchemyError:
            raise _bad_request("database_operation_failed") from None
        finally:
            database.dispose()

    def _preview_asset_archive(asset_id: UUID, request: Request) -> Response:
        """Serve one verified archive blob without exposing or reopening its path."""

        canonical_asset_id = str(asset_id)
        database = _database()
        try:
            with database.session() as session:
                asset = session.get(Asset, canonical_asset_id)
                if asset is None:
                    raise HTTPException(status_code=404, detail="catalog_asset_not_found")
                source = ArchivePreviewSource(
                    status=asset.status,
                    local_path=asset.local_path,
                    checksum_sha256=asset.checksum_sha256,
                    size_bytes=asset.size_bytes,
                    mime_type=asset.mime_type,
                )
        except HTTPException:
            raise
        except SQLAlchemyError:
            raise _bad_request("database_operation_failed") from None
        finally:
            database.dispose()

        try:
            # A Range is meaningful only after the representation has passed
            # every status, path, size and digest gate that would yield 200.
            preview = ArchivePreviewService(resolved.archive_dir).open(source)
        except ArchivePreviewError as error:
            return _archive_error_response(
                error,
                asset_id=canonical_asset_id,
                request_method=request.method,
                size_bytes=source.size_bytes,
            )

        representation_size = preview.content_length
        range_values = request.headers.getlist("range")
        if_range_values = request.headers.getlist("if-range")
        if (
            request.method == "GET"
            and range_values
            and (not if_range_values or (len(if_range_values) == 1 and if_range_values[0] == preview.etag))
        ):
            try:
                if len(range_values) != 1:
                    raise ArchivePreviewError("asset_archive_range_unsatisfiable")
                start, end = parse_single_byte_range(range_values[0], representation_size)
                preview.select_range(start, end)
            except ArchivePreviewError as error:
                with suppress(ArchivePreviewError):
                    preview.close()
                return _archive_error_response(
                    error,
                    asset_id=canonical_asset_id,
                    request_method=request.method,
                    size_bytes=representation_size,
                )

        status_code = 206 if preview.partial else 200
        headers = {
            "Accept-Ranges": "bytes",
            "Cache-Control": "private, no-store",
            "Content-Disposition": f'inline; filename="asset-{canonical_asset_id}"',
            "Content-Length": str(preview.content_length),
            "Content-Security-Policy": "sandbox; default-src 'none'",
            "Cross-Origin-Resource-Policy": "same-origin",
            "ETag": preview.etag,
        }
        if preview.partial:
            headers["Content-Range"] = f"bytes {preview.start}-{preview.end}/{representation_size}"
        if request.method == "HEAD":
            try:
                preview.close()
            except ArchivePreviewError as error:
                return _archive_error_response(
                    error,
                    asset_id=canonical_asset_id,
                    request_method=request.method,
                    size_bytes=source.size_bytes,
                )
            return Response(
                status_code=status_code,
                headers=headers,
                media_type=preview.media_type,
            )

        try:
            return _ArchiveStreamingResponse(
                preview,
                status_code=status_code,
                headers=headers,
            )
        except Exception:
            with suppress(ArchivePreviewError):
                preview.close()
            raise

    @app.get("/api/v1/assets/{asset_id}/archive")
    def preview_asset_archive(asset_id: UUID, request: Request) -> Response:
        return _preview_asset_archive(asset_id, request)

    @app.head("/api/v1/assets/{asset_id}/archive", include_in_schema=False)
    def preview_asset_archive_head(asset_id: UUID, request: Request) -> Response:
        return _preview_asset_archive(asset_id, request)

    @app.get("/api/v1/contents")
    def list_contents(
        platform: Platform | None = None,
        kind: ContentKind | None = None,
        author_id: UUID | None = None,
        archived: bool | None = None,
        exported: bool | None = None,
        q: str | None = Query(default=None, max_length=200),
        limit: int = 200,
    ) -> list[dict[str, object]]:
        """Return a bounded, redaction-safe content catalogue projection."""

        database = _database()
        try:
            return ContentAssetExplorer(database).list_contents(
                platform=platform.value if platform is not None else None,
                kind=kind.value if kind is not None else None,
                author_id=str(author_id) if author_id is not None else None,
                archived=archived,
                exported=exported,
                query=q,
                limit=max(1, min(limit, 1_000)),
            )
        except CatalogExplorerError as error:
            raise _catalog_error(error) from None
        except SQLAlchemyError:
            raise _bad_request("database_operation_failed") from None
        finally:
            database.dispose()

    @app.get("/api/v1/contents/{content_id}")
    def get_content(content_id: UUID) -> dict[str, object]:
        database = _database()
        try:
            return ContentAssetExplorer(database).get_content(str(content_id))
        except CatalogExplorerError as error:
            raise _catalog_error(error) from None
        except SQLAlchemyError:
            raise _bad_request("database_operation_failed") from None
        finally:
            database.dispose()

    @app.get("/api/v1/library")
    def list_library(
        platform: Platform | None = None,
        q: str | None = Query(default=None, max_length=200),
        limit: int = 200,
    ) -> list[dict[str, object]]:
        """Summarize the media library per author without exposing host paths."""

        database = _database()
        try:
            return ContentAssetExplorer(database).list_library(
                platform=platform.value if platform is not None else None,
                query=q,
                limit=max(1, min(limit, 1_000)),
            )
        except CatalogExplorerError as error:
            raise _catalog_error(error) from None
        except SQLAlchemyError:
            raise _bad_request("database_operation_failed") from None
        finally:
            database.dispose()

    @app.get("/api/v1/library/{author_id}")
    def inspect_library_author(
        author_id: str,
        request: Request,
        cursor: str | None = Query(default=None, max_length=4_096),
        limit: int = Query(default=128, ge=1, le=128),
    ) -> dict[str, object]:
        """Verify one bounded manifest page without accepting a host path."""

        query_keys = [key for key, _value in request.query_params.multi_items()]
        if any(key not in {"cursor", "limit"} for key in query_keys) or any(
            query_keys.count(key) > 1 for key in {"cursor", "limit"}
        ):
            raise _bad_request("library_inspection_invalid")
        try:
            inspection = library_inspection_service.inspect(
                author_id,
                cursor=cursor,
                limit=limit,
                max_bytes=resolved.library_inspection_max_bytes,
                deadline_seconds=resolved.library_inspection_deadline_seconds,
            )
            return _library_inspection_payload(inspection)
        except LibraryInspectionError as error:
            if error.code in {"library_author_invalid", "library_author_not_found"}:
                status_code = 404
            elif error.code in {"library_cursor_stale", "library_publication_inconsistent"}:
                status_code = 409
            elif error.code == "library_inspection_busy":
                raise HTTPException(
                    status_code=429,
                    detail=error.code,
                    headers={"Retry-After": "1"},
                ) from None
            elif error.code == "library_inspection_failed":
                status_code = 503
            else:
                status_code = 400
            raise HTTPException(status_code=status_code, detail=error.code) from None

    @app.post("/api/v1/emby/export", status_code=202)
    def emby_export(body: EmbyExport, request: Request) -> dict[str, object]:
        request_fingerprint, key_hash = _operation_identity(
            request,
            "emby-export",
            target_id=str(body.author_id),
            parameters={
                "lease_seconds": body.lease_seconds,
                "max_attempts": body.max_attempts,
            },
        )

        def run_export(context: OperationExecutionContext) -> OperationOutcome:
            export_database: Database | None = None
            try:
                phase = context.phase("exporting")
                if phase.cancel_requested_at is not None or context.cancel_requested:
                    return OperationOutcome.cancelled()
                run_settings = resolved
                export_database = Database(run_settings.resolved_database_url)
                outcome = EmbyExportService(
                    export_database,
                    EmbyExporter(
                        run_settings.export_dir,
                        staging_root=run_settings.job_dir / "emby-export",
                    ),
                ).export_author(
                    EmbyExportRequest(
                        author_id=str(body.author_id),
                        worker_id=context.worker_id,
                        lease_seconds=body.lease_seconds,
                        max_attempts=body.max_attempts,
                    ),
                    subject_hook=context.subject_hook,
                )
                return OperationOutcome.success(
                    {
                        "author_id": str(body.author_id),
                        "job_id": outcome.job_id,
                        "already_exported": outcome.already_exported,
                        "managed_file_count": outcome.managed_file_count,
                    }
                )
            except ExportError as error:
                return OperationOutcome.failed(
                    error.code,
                    retryable=export_error_is_retryable(error.code),
                )
            finally:
                if export_database is not None:
                    export_database.dispose()

        submission = _submit_operation(
            OperationExecution(
                kind="emby-export",
                request_fingerprint=request_fingerprint,
                idempotency_key_hash=key_hash,
                exclusive_key=f"emby-export:{body.author_id}",
                target_type="author",
                target_id=str(body.author_id),
                phase="preparing",
                execute=run_export,
            )
        )
        return _operation_start_payload(submission)

    # ------------------------------------------------------------ operations

    @app.get("/api/v1/operations")
    def list_operations(
        kind: str | None = None,
        state: str | None = None,
        target_type: str | None = None,
        target_id: UUID | None = None,
        correlation_id: UUID | None = None,
        before_requested_at: datetime | None = None,
        before_id: UUID | None = None,
        limit: int = 100,
    ) -> list[dict[str, object]]:
        if not 1 <= limit <= _MAX_OPERATION_LIST:
            raise _bad_request("operation_query_invalid")
        if (target_type is None) != (target_id is None):
            raise _bad_request("operation_query_invalid")
        if (before_requested_at is None) != (before_id is None):
            raise _bad_request("operation_query_invalid")
        before = None
        if before_requested_at is not None and before_id is not None:
            if before_requested_at.tzinfo is None or before_requested_at.utcoffset() is None:
                raise _bad_request("operation_query_invalid")
            before = (before_requested_at, str(before_id))
        _reconcile_operation_reads()
        try:
            snapshots = operations.list_operations(
                kind=kind,
                state=state,
                target_type=target_type,
                target_id=str(target_id) if target_id is not None else None,
                correlation_id=str(correlation_id) if correlation_id is not None else None,
                before=before,
                limit=limit,
            )
            return [_operation_payload(operation) for operation in snapshots]
        except ValueError:
            raise _bad_request("operation_query_invalid") from None
        except (RepositoryError, SQLAlchemyError):
            raise HTTPException(status_code=503, detail="operation_store_unavailable") from None

    # This fixed route must precede the dynamic operation-id route. EventSource
    # reconnects with the last committed global stream cursor in this header.
    @app.get("/api/v1/operations/events")
    async def operation_event_stream(request: Request) -> StreamingResponse:
        cursor_headers = request.headers.getlist("last-event-id")
        if len(cursor_headers) > 1:
            raise _bad_request("operation_event_cursor_invalid")
        cursor: int | None = None
        if cursor_headers:
            raw_cursor = cursor_headers[0]
            if _LAST_EVENT_ID.fullmatch(raw_cursor) is None:
                raise _bad_request("operation_event_cursor_invalid")
            cursor = int(raw_cursor)

        _reconcile_operation_reads()
        try:
            _pruned_through, high_water = await asyncio.to_thread(operations.stream_bounds)
            if cursor is not None:
                await asyncio.to_thread(operations.events_after, cursor, limit=1)
        except OperationEventCursorError as error:
            status_code = 410 if error.code == "operation_event_cursor_expired" else 400
            raise HTTPException(status_code=status_code, detail=error.code) from None
        except (RepositoryError, SQLAlchemyError):
            raise HTTPException(status_code=503, detail="operation_store_unavailable") from None

        initial_cursor = high_water if cursor is None else cursor

        async def stream(after_sequence: int) -> AsyncIterator[bytes]:
            yield _sse_frame(
                "ready",
                {"type": "ready", "high_water": high_water},
                event_id=after_sequence,
            )
            deadline = time.monotonic() + _OPERATION_STREAM_MAX_SECONDS
            last_write = time.monotonic()
            current = after_sequence
            while time.monotonic() < deadline:
                if await request.is_disconnected():
                    break
                try:
                    events = await asyncio.to_thread(
                        operations.events_after,
                        current,
                        limit=_OPERATION_STREAM_BATCH,
                    )
                except (OperationEventCursorError, RepositoryError, SQLAlchemyError):
                    break
                if events:
                    for event in events:
                        try:
                            snapshot = await asyncio.to_thread(operations.get, event.operation_id)
                        except (NotFoundError, RepositoryError, SQLAlchemyError):
                            snapshot = None
                        event_payload = _operation_event_payload(event, operation=snapshot)
                        yield _sse_frame(
                            "operation",
                            {"type": "operation", "event": event_payload},
                            event_id=event.stream_sequence,
                        )
                        current = event.stream_sequence
                    last_write = time.monotonic()
                    continue
                now = time.monotonic()
                if now - last_write >= _OPERATION_STREAM_KEEPALIVE_SECONDS:
                    yield b": keepalive\n\n"
                    last_write = now
                await asyncio.sleep(_OPERATION_STREAM_POLL_SECONDS)

        return StreamingResponse(
            stream(initial_cursor),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-store",
                "X-Accel-Buffering": "no",
            },
        )

    @app.get("/api/v1/operations/{operation_id}/events")
    def operation_events(
        operation_id: str,
        after: int = 0,
        limit: int = 100,
    ) -> list[dict[str, object]]:
        canonical_id = _canonical_operation_id(operation_id)
        if after < 0 or not 1 <= limit <= _MAX_OPERATION_EVENT_PAGE:
            raise _bad_request("operation_event_cursor_invalid")
        try:
            events = operations.events_for_operation(
                canonical_id,
                after_operation_sequence=after,
                limit=limit,
            )
            return [_operation_event_payload(event) for event in events]
        except NotFoundError:
            raise HTTPException(status_code=404, detail="operation_not_found") from None
        except OperationEventCursorError as error:
            raise _bad_request(error.code) from None
        except (RepositoryError, SQLAlchemyError):
            raise HTTPException(status_code=503, detail="operation_store_unavailable") from None

    @app.post("/api/v1/operations/{operation_id}/cancel")
    def cancel_operation(operation_id: str) -> dict[str, object]:
        canonical_id = _canonical_operation_id(operation_id)
        try:
            operation = operations.request_cancel(canonical_id)
        except NotFoundError:
            raise HTTPException(status_code=404, detail="operation_not_found") from None
        except OperationStateConflictError:
            try:
                observed = operations.get(canonical_id)
                operation = (
                    operations.request_cancel(canonical_id) if observed.state in {"queued", "running"} else observed
                )
            except OperationStateConflictError:
                raise HTTPException(status_code=409, detail="operation_state_conflict") from None
            except NotFoundError:
                raise HTTPException(status_code=404, detail="operation_not_found") from None
            except (RepositoryError, SQLAlchemyError):
                raise HTTPException(status_code=503, detail="operation_store_unavailable") from None
        except (RepositoryError, SQLAlchemyError):
            raise HTTPException(status_code=503, detail="operation_store_unavailable") from None
        try:
            subjects = operations.list_subjects(canonical_id)
        except (RepositoryError, SQLAlchemyError):
            raise HTTPException(status_code=503, detail="operation_store_unavailable") from None
        return _operation_payload(operation, subjects=subjects)

    @app.get("/api/v1/operations/{operation_id}")
    def get_operation(operation_id: str) -> dict[str, object]:
        _reconcile_operation_reads()
        return _operation_detail(operation_id)

    @app.api_route("/{frontend_path:path}", methods=["GET", "HEAD"], include_in_schema=False)
    def console_spa(frontend_path: str) -> Response:
        if frontend_path.startswith("api/") or web_root is None:
            raise HTTPException(status_code=404, detail="not found")
        return _static_response(web_root, frontend_path or "index.html")

    app.add_middleware(
        OperatorAuthMiddleware,
        runtime=operator_auth_runtime,
        origin_policy=operator_origin_policy,
        web_root=web_root,
    )
    return app


__all__ = ["create_api_app"]
