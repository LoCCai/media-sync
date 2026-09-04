"""Local REST API and embedded web console for media-sync administration.

The API mirrors the bounded CLI control surface: accounts (including the
blocking QR login with the QR-image relay for container displays),
subscriptions, durable scheduler/pipeline runs, scheduler Jobs, assets and
Emby export. Every endpoint is a thin projection over the same application
services the CLI uses; no new authority or credential surface is introduced.

The service is local-first: it binds ``127.0.0.1`` by default and carries no
authentication. Container deployments bind ``0.0.0.0`` inside the network
namespace but must publish the port to a trusted network only.
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
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from media_sync import __version__
from media_sync.application import (
    AccountDraft,
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
)
from media_sync.application.authentication import (
    AccountLoginError,
    AccountLoginRequest,
    MediaCrawlerQrLoginService,
)
from media_sync.application.emby import EmbyExportRequest, EmbyExportService, export_error_is_retryable
from media_sync.application.support_bundle import SupportBundleError, SupportBundleService
from media_sync.config import Settings, get_settings
from media_sync.domain import AssetStatus, ContentKind, JobStatus, LoginMethod, Platform
from media_sync.exporters.emby import EmbyExporter, ExportError
from media_sync.infrastructure.db import (
    AccountLoginConflictError,
    AccountRepository,
    Asset,
    Author,
    Content,
    Database,
    ExportRecord,
    LoginSession,
    LoginSessionRepository,
    NotFoundError,
    Operation,
    OperationConflictError,
    OperationEventCursorError,
    OperationEventSnapshot,
    OperationSnapshot,
    OperationStateConflictError,
    OperationSubjectSnapshot,
    RepositoryError,
    Subscription,
    SubscriptionRepository,
    SyncRun,
)
from media_sync.integrations.mediacrawler import platform_capabilities_payload
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
    _asset_payload,
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
from media_sync.scheduler import DurableSchedulerService, SchedulerRepository, StaleLaneError

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
_LAST_EVENT_ID = re.compile(r"(?:0|[1-9][0-9]{0,18})\Z")
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
    display_name: str = Field(min_length=1, max_length=200)
    creator_reference_ref: str | None = None
    interval_seconds: int = Field(default=21_600, ge=60)
    max_items: int = Field(default=30, ge=1, le=1_000)
    allow_full_history: bool = False
    request_delay_seconds: float = Field(default=5.0, gt=0, le=MAX_REQUEST_DELAY_SECONDS)
    headless: bool = True


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


def _subscription_checkpoint_summary_payload(subscription: Subscription) -> dict[str, object]:
    """Return checkpoint presence and counters without serializing cursor data."""

    has_forward_cursor = subscription.cursor is not None
    has_backfill_cursor = subscription.backfill_cursor is not None
    return {
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


# ------------------------------------------------------------------ app factory


def create_api_app(settings: Settings | None = None) -> FastAPI:
    """Build the local FastAPI application without migrating durable state."""

    resolved = settings or get_settings()
    operation_database = Database(resolved.resolved_database_url)
    operations = OperationCoordinator(operation_database)
    operation_reconciliation = _OperationReconciliationTrigger(operations)
    support_bundle_service = SupportBundleService(
        operation_database,
        application_version=__version__,
        expected_revision=_EXPECTED_DATABASE_REVISION,
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
    app.state.operations = operations
    deep_readiness_cache: dict[bool, tuple[float, dict[str, object]]] = {}
    deep_readiness_lock = threading.Lock()
    web_root = _resolve_web_root()

    @app.exception_handler(RequestValidationError)
    async def safe_request_validation_error(
        request: Request,
        error: RequestValidationError,
    ) -> JSONResponse:
        """Keep rejected request values out of FastAPI's default 422 body."""

        del request
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
        return JSONResponse(
            status_code=422,
            content={"detail": "request_validation_failed", "errors": errors},
            headers={"Cache-Control": "no-store"},
        )

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
        return HTTPException(status_code=status_code, detail=error.code)

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

    @app.get("/api/v1/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

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

    @app.get("/api/v1/ready")
    def ready() -> dict[str, object]:
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
        }

    @app.get("/api/v1/platform-capabilities")
    def platform_capabilities() -> dict[str, object]:
        return platform_capabilities_payload()

    @app.get("/", include_in_schema=False)
    def console() -> Response:
        if web_root is not None:
            return _static_response(web_root)
        return Response(content=_CONSOLE_PATH.read_text(encoding="utf-8"), media_type="text/html; charset=utf-8")

    @app.get("/legacy", include_in_schema=False)
    def legacy_console() -> Response:
        return Response(
            content=_CONSOLE_PATH.read_text(encoding="utf-8"),
            media_type="text/html; charset=utf-8",
            headers={"Cache-Control": "no-cache"},
        )

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
                return _account_login_status_payload(account, sessions[0] if sessions else None)
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
                error_code = (
                    "operation_login_expired"
                    if outcome.runner_status.value in {"expired", "timed_out"}
                    else "operation_login_failed"
                )
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

    # --------------------------------------------------------- subscriptions

    @app.get("/api/v1/subscriptions")
    def list_subscriptions() -> list[dict[str, object]]:
        database = _database()
        try:
            with database.session() as session:
                payloads: list[dict[str, object]] = []
                for subscription in SubscriptionRepository(session).list():
                    payload = _subscription_payload(subscription)
                    payload["policy_summary"] = _subscription_policy_summary_payload(subscription)
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
            display_name=body.display_name,
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
                payload["policy_summary"] = _subscription_policy_summary_payload(subscription)
                payload["checkpoint_summary"] = _subscription_checkpoint_summary_payload(subscription)
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
        status: AssetStatus | None = None,
        limit: int = 200,
    ) -> list[dict[str, object]]:
        database = _database()
        try:
            with database.session() as session:
                statement = select(Asset, Content.author_id).join(Content, Asset.content_id == Content.id)
                if author_id is not None:
                    statement = statement.where(Content.author_id == str(author_id))
                if status is not None:
                    statement = statement.where(Asset.status == status.value)
                statement = statement.order_by(
                    Content.author_id,
                    Asset.content_id,
                    Asset.kind,
                    Asset.position,
                    Asset.id,
                ).limit(max(1, min(limit, 1_000)))
                return [
                    _asset_payload(asset, author_id=row_author_id)
                    for asset, row_author_id in session.execute(statement).all()
                ]
        except SQLAlchemyError:
            raise _bad_request("database_operation_failed") from None
        finally:
            database.dispose()

    @app.get("/api/v1/contents")
    def list_contents(
        platform: Platform | None = None,
        kind: ContentKind | None = None,
        limit: int = 200,
    ) -> list[dict[str, object]]:
        """Return a bounded, redaction-safe content catalogue projection."""

        asset_count = (
            select(func.count(Asset.id)).where(Asset.content_id == Content.id).correlate(Content).scalar_subquery()
        )
        archived_count = (
            select(func.count(Asset.id))
            .where(Asset.content_id == Content.id, Asset.status.in_(("verified", "exported")))
            .correlate(Content)
            .scalar_subquery()
        )
        export_count = (
            select(func.count(ExportRecord.id))
            .where(ExportRecord.content_id == Content.id, ExportRecord.status == "succeeded")
            .correlate(Content)
            .scalar_subquery()
        )
        database = _database()
        try:
            with database.session() as session:
                statement = (
                    select(
                        Content,
                        Author.display_name,
                        asset_count.label("asset_count"),
                        archived_count.label("archived_count"),
                        export_count.label("export_count"),
                    )
                    .join(Author, Content.author_id == Author.id)
                    .order_by(Content.published_at.desc(), Content.created_at.desc(), Content.id.desc())
                    .limit(max(1, min(limit, 1_000)))
                )
                if platform is not None:
                    statement = statement.where(Content.platform == platform.value)
                if kind is not None:
                    statement = statement.where(Content.kind == kind.value)
                rows = session.execute(statement).all()
                return [
                    {
                        "id": content.id,
                        "author_id": content.author_id,
                        "author_display_name": author_display_name,
                        "platform": content.platform,
                        "remote_type": content.remote_type,
                        "remote_id": content.remote_id,
                        "kind": content.kind,
                        "title": content.title,
                        "body_excerpt": content.body[:280] if content.body else None,
                        "canonical_url": content.canonical_url,
                        "published_at": content.published_at.isoformat() if content.published_at else None,
                        "asset_count": row_asset_count,
                        "archived_count": row_archived_count,
                        "export_count": row_export_count,
                    }
                    for content, author_display_name, row_asset_count, row_archived_count, row_export_count in rows
                ]
        except SQLAlchemyError:
            raise _bad_request("database_operation_failed") from None
        finally:
            database.dispose()

    @app.get("/api/v1/library")
    def list_library(limit: int = 200) -> list[dict[str, object]]:
        """Summarize the media library per author without exposing host paths."""

        content_count = (
            select(func.count(Content.id)).where(Content.author_id == Author.id).correlate(Author).scalar_subquery()
        )
        asset_count = (
            select(func.count(Asset.id))
            .select_from(Asset)
            .join(Content, Asset.content_id == Content.id)
            .where(Content.author_id == Author.id)
            .correlate(Author)
            .scalar_subquery()
        )
        archived_count = (
            select(func.count(Asset.id))
            .select_from(Asset)
            .join(Content, Asset.content_id == Content.id)
            .where(Content.author_id == Author.id, Asset.status.in_(("verified", "exported")))
            .correlate(Author)
            .scalar_subquery()
        )
        exported_count = (
            select(func.count(ExportRecord.id))
            .select_from(ExportRecord)
            .join(Content, ExportRecord.content_id == Content.id)
            .where(Content.author_id == Author.id, ExportRecord.status == "succeeded")
            .correlate(Author)
            .scalar_subquery()
        )
        last_published_at = (
            select(func.max(Content.published_at))
            .where(Content.author_id == Author.id)
            .correlate(Author)
            .scalar_subquery()
        )
        database = _database()
        try:
            with database.session() as session:
                rows = session.execute(
                    select(
                        Author,
                        content_count.label("content_count"),
                        asset_count.label("asset_count"),
                        archived_count.label("archived_count"),
                        exported_count.label("exported_count"),
                        last_published_at.label("last_published_at"),
                    )
                    .order_by(Author.display_name, Author.id)
                    .limit(max(1, min(limit, 1_000)))
                ).all()
                return [
                    {
                        "author_id": author.id,
                        "platform": author.platform,
                        "display_name": author.display_name,
                        "remote_id": author.remote_id,
                        "content_count": row_content_count,
                        "asset_count": row_asset_count,
                        "archived_count": row_archived_count,
                        "exported_count": row_exported_count,
                        "last_published_at": last_published.isoformat() if last_published else None,
                    }
                    for (
                        author,
                        row_content_count,
                        row_asset_count,
                        row_archived_count,
                        row_exported_count,
                        last_published,
                    ) in rows
                ]
        except SQLAlchemyError:
            raise _bad_request("database_operation_failed") from None
        finally:
            database.dispose()

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

    @app.get("/{frontend_path:path}", include_in_schema=False)
    def console_spa(frontend_path: str) -> Response:
        if frontend_path.startswith("api/") or web_root is None:
            raise HTTPException(status_code=404, detail="not found")
        return _static_response(web_root, frontend_path or "index.html")

    return app


__all__ = ["create_api_app"]
