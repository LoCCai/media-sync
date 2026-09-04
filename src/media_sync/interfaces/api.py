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

import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from media_sync import __version__
from media_sync.application import MediaCrawlerLoginSessionReconciler
from media_sync.application.authentication import (
    AccountLoginError,
    AccountLoginRequest,
    MediaCrawlerQrLoginService,
)
from media_sync.application.emby import EmbyExportRequest, EmbyExportService
from media_sync.config import Settings, get_settings
from media_sync.domain import AssetStatus, JobStatus, LoginMethod, Platform
from media_sync.exporters.emby import EmbyExporter, ExportError
from media_sync.infrastructure.db import (
    AccountRepository,
    Asset,
    AuthorRepository,
    AuthorUpsert,
    Content,
    Database,
    LoginSessionRepository,
    NotFoundError,
    SubscriptionRepository,
    SyncRun,
)
from media_sync.integrations.mediacrawler.login_runner import (
    LOGIN_QR_IMAGE_NAME,
    MediaCrawlerLoginProcessRunner,
)
from media_sync.integrations.mediacrawler.subscription_policy import (
    MAX_REQUEST_DELAY_SECONDS,
    MediaCrawlerSubscriptionPolicy,
)
from media_sync.interfaces.cli import (
    _MEDIACRAWLER_LOGIN_METHODS,
    _account_login_outcome_payload,
    _account_login_status_payload,
    _account_payload,
    _asset_payload,
    _build_pipeline_worker,
    _build_subscription_worker,
    _credential_reference,
    _execute_asset_download,
    _pipeline_worker_payload,
    _scheduler_cycle_payload,
    _scheduler_job_payload,
    _scheduler_schedule_payload,
    _scheduler_worker_payload,
    _subscription_payload,
    _UnavailableMediaCrawlerLoginRunner,
    collect_deep_readiness_report,
)
from media_sync.scheduler import DurableSchedulerService, SchedulerRepository, StaleLaneError

_CONSOLE_PATH = Path(__file__).with_name("console.html")


# ------------------------------------------------------------------ operations


@dataclass
class _Operation:
    id: str
    kind: str
    state: str = "running"
    started_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    finished_at: str | None = None
    result: dict[str, Any] | None = None
    error_code: str | None = None


class _OperationRegistry:
    """Track in-process background operations for the web console."""

    def __init__(self, *, history_limit: int = 200) -> None:
        self._lock = threading.Lock()
        self._operations: dict[str, _Operation] = {}
        self._order: list[str] = []
        self._history_limit = history_limit
        self._exclusive: dict[str, str] = {}

    def start(self, kind: str, *, exclusive_key: str | None = None) -> _Operation:
        with self._lock:
            if exclusive_key is not None and exclusive_key in self._exclusive:
                raise HTTPException(status_code=409, detail="operation already running")
            operation = _Operation(id=str(uuid4()), kind=kind)
            self._operations[operation.id] = operation
            self._order.append(operation.id)
            if exclusive_key is not None:
                self._exclusive[exclusive_key] = operation.id
            while len(self._order) > self._history_limit:
                self._operations.pop(self._order.pop(0), None)
            return operation

    def finish(
        self,
        operation: _Operation,
        *,
        result: dict[str, Any] | None = None,
        error_code: str | None = None,
        exclusive_key: str | None = None,
    ) -> None:
        with self._lock:
            operation.state = "succeeded" if error_code is None else "failed"
            operation.finished_at = datetime.now(UTC).isoformat()
            operation.result = result
            operation.error_code = error_code
            if exclusive_key is not None and self._exclusive.get(exclusive_key) == operation.id:
                self._exclusive.pop(exclusive_key, None)

    def payload(self, operation: _Operation) -> dict[str, Any]:
        return {
            "id": operation.id,
            "kind": operation.kind,
            "state": operation.state,
            "started_at": operation.started_at,
            "finished_at": operation.finished_at,
            "result": operation.result,
            "error_code": operation.error_code,
        }

    def get(self, operation_id: str) -> _Operation:
        with self._lock:
            operation = self._operations.get(operation_id)
        if operation is None:
            raise HTTPException(status_code=404, detail="operation not found")
        return operation

    def list(self, *, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            items = [self._operations[operation_id] for operation_id in reversed(self._order[-limit:])]
        return [self.payload(operation) for operation in items]


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
    creator_remote_id: str = Field(min_length=1, max_length=512)
    display_name: str = Field(min_length=1, max_length=200)
    creator_reference_ref: str | None = None
    interval_seconds: int = Field(default=21_600, ge=60)
    max_items: int = Field(default=30, ge=1, le=1_000)
    allow_full_history: bool = False
    request_delay_seconds: float = Field(default=5.0, gt=0, le=MAX_REQUEST_DELAY_SECONDS)
    headless: bool = True


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
    """Build the local FastAPI application; creating it never touches state."""

    resolved = settings or get_settings()
    operations = _OperationRegistry()

    app = FastAPI(title="media-sync", version=__version__, docs_url="/api/docs")
    app.state.settings = resolved
    app.state.operations = operations
    deep_readiness_cache: dict[bool, tuple[float, dict[str, object]]] = {}
    deep_readiness_lock = threading.Lock()

    def _database() -> Database:
        return Database(resolved.resolved_database_url)

    def _bad_request(code: str) -> HTTPException:
        return HTTPException(status_code=400, detail=code)

    def _safe_credential_reference(value: str | None) -> str | None:
        import typer

        try:
            return _credential_reference(value)
        except typer.BadParameter:
            raise _bad_request("invalid_credential_reference") from None

    @app.get("/api/v1/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

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

    @app.get("/", include_in_schema=False)
    def console() -> Response:
        return Response(content=_CONSOLE_PATH.read_text(encoding="utf-8"), media_type="text/html; charset=utf-8")

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
        normalized_credential_ref = _safe_credential_reference(body.credential_ref)
        if body.login_method not in _MEDIACRAWLER_LOGIN_METHODS:
            raise _bad_request("login_method_not_supported")
        if body.login_method is LoginMethod.COOKIE and normalized_credential_ref is None:
            raise _bad_request("cookie_login_requires_credential_ref")
        if body.login_method is not LoginMethod.COOKIE and normalized_credential_ref is not None:
            raise _bad_request("credential_ref_allowed_only_for_cookie_login")

        database = _database()
        try:
            with database.session() as session:
                repository = AccountRepository(session)
                existing = repository.get_by_platform_and_name(body.platform.value, body.display_name)
                if existing is not None:
                    if existing.login_method != body.login_method.value or (
                        existing.credential_ref != normalized_credential_ref
                    ):
                        raise _bad_request("account_exists_with_different_configuration")
                    return _account_payload(existing, created=False)
                account = repository.create(
                    platform=body.platform.value,
                    display_name=body.display_name,
                    adapter="mediacrawler",
                    login_method=body.login_method.value,
                    credential_ref=normalized_credential_ref,
                )
                return _account_payload(account, created=True)
        except SQLAlchemyError:
            raise _bad_request("database_operation_failed") from None
        finally:
            database.dispose()

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

    @app.get("/api/v1/accounts/{account_id}/login-qr.png")
    def login_qr(account_id: UUID) -> Response:
        database = _database()
        try:
            with database.session() as session:
                account = AccountRepository(session).get(str(account_id))
                if account is None:
                    raise HTTPException(status_code=404, detail="account not found")
                platform = account.platform
                sessions = LoginSessionRepository(session).list_for_account(account.id)
        except SQLAlchemyError:
            raise _bad_request("database_operation_failed") from None
        finally:
            database.dispose()
        qr_path = (
            resolved.resolved_mediacrawler_runtime_dir / "accounts" / platform / str(account_id) / LOGIN_QR_IMAGE_NAME
        )
        if not qr_path.is_file():
            latest = sessions[0] if sessions else None
            if latest is not None and latest.status in {"pending", "waiting_user"}:
                return JSONResponse(
                    status_code=202,
                    content={"code": "login_qr_pending", "login_session_id": latest.id},
                    headers={"Cache-Control": "no-store"},
                )
            if latest is not None and latest.status in {"succeeded", "expired", "failed", "cancelled"}:
                return JSONResponse(
                    status_code=410,
                    content={"code": "login_qr_gone", "login_session_id": latest.id},
                    headers={"Cache-Control": "no-store"},
                )
            raise HTTPException(status_code=404, detail="login_qr_not_available")
        return FileResponse(qr_path, media_type="image/png", headers={"Cache-Control": "no-store"})

    @app.post("/api/v1/accounts/{account_id}/login", status_code=202)
    def start_login(account_id: UUID, body: LoginStart) -> dict[str, object]:
        if not body.enable_mediacrawler:
            raise _bad_request("mediacrawler_not_enabled")
        if not body.accept_mediacrawler_license:
            raise _bad_request("license_acknowledgement_required")

        database = _database()
        try:
            with database.session() as session:
                account = AccountRepository(session).get(str(account_id))
                if account is None:
                    raise HTTPException(status_code=404, detail="account not found")
        except SQLAlchemyError:
            raise _bad_request("database_operation_failed") from None
        finally:
            database.dispose()

        operation = operations.start("account-login", exclusive_key=f"login:{account_id}")

        def run_login() -> None:
            login_database: Database | None = None
            try:
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
                    )
                )
                operations.finish(
                    operation,
                    result=_account_login_outcome_payload(outcome),
                    exclusive_key=f"login:{account_id}",
                )
            except AccountLoginError as error:
                operations.finish(operation, error_code=error.code, exclusive_key=f"login:{account_id}")
            except Exception:
                operations.finish(operation, error_code="account_login_unexpected", exclusive_key=f"login:{account_id}")
            finally:
                if login_database is not None:
                    login_database.dispose()

        threading.Thread(target=run_login, name=f"media-sync-login-{account_id}", daemon=True).start()
        return {"operation_id": operation.id, "state": "running"}

    # --------------------------------------------------------- subscriptions

    @app.get("/api/v1/subscriptions")
    def list_subscriptions() -> list[dict[str, object]]:
        database = _database()
        try:
            with database.session() as session:
                return [_subscription_payload(subscription) for subscription in SubscriptionRepository(session).list()]
        except SQLAlchemyError:
            raise _bad_request("database_operation_failed") from None
        finally:
            database.dispose()

    @app.post("/api/v1/subscriptions", status_code=201)
    def create_subscription(body: SubscriptionCreate) -> dict[str, object]:
        normalized_creator_reference = _safe_credential_reference(body.creator_reference_ref)
        database = _database()
        try:
            with database.session() as session:
                account = AccountRepository(session).get(str(body.account_id))
                if account is None:
                    raise HTTPException(status_code=404, detail="account not found")
                if account.platform != body.platform.value:
                    raise _bad_request("platform_conflict")
                if any(marker in body.creator_remote_id for marker in ("://", "?", "#", "&", "=", ";")):
                    raise _bad_request("creator_remote_id_must_be_stable_id")
                policy = {
                    "mediacrawler": MediaCrawlerSubscriptionPolicy(
                        allow_full_history=body.allow_full_history,
                        request_delay_seconds=body.request_delay_seconds,
                        headless=body.headless,
                        creator_secret_ref=normalized_creator_reference,
                    ).to_payload()
                }
                author = AuthorRepository(session).upsert(
                    AuthorUpsert(
                        platform=body.platform.value,
                        remote_id=body.creator_remote_id,
                        display_name=body.display_name,
                    )
                )
                repository = SubscriptionRepository(session)
                existing = repository.get_by_account_and_author(account.id, author.id)
                if existing is not None:
                    if (
                        existing.interval_seconds != body.interval_seconds
                        or existing.max_items != body.max_items
                        or existing.policy != policy
                    ):
                        raise _bad_request("subscription_exists_with_different_options")
                    return _subscription_payload(existing, created=False)
                subscription = repository.create(
                    account_id=account.id,
                    author_id=author.id,
                    interval_seconds=body.interval_seconds,
                    max_items=body.max_items,
                    policy=policy,
                )
                return _subscription_payload(subscription, created=True)
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
    def download_asset(asset_id: UUID, body: AssetDownload) -> dict[str, object]:
        if body.accept_mediacrawler_license and not body.enable_mediacrawler:
            raise _bad_request("license_requires_enable_mediacrawler")
        normalized_detail_reference = _safe_credential_reference(body.xhs_detail_reference_ref)
        if normalized_detail_reference is not None and not body.enable_mediacrawler:
            raise _bad_request("xhs_detail_reference_requires_mediacrawler")
        database = _database()
        try:
            with database.session() as session:
                if session.get(Asset, str(asset_id)) is None:
                    raise HTTPException(status_code=404, detail="asset not found")
        except SQLAlchemyError:
            raise _bad_request("database_operation_failed") from None
        finally:
            database.dispose()
        operation = operations.start("asset-download", exclusive_key=f"asset-download:{asset_id}")

        def run_download() -> None:
            download_database: Database | None = None
            try:
                download_database = Database(resolved.resolved_database_url)
                payload, ok = _execute_asset_download(
                    asset_id=asset_id,
                    worker_id=body.worker_id,
                    lease_seconds=body.lease_seconds,
                    max_attempts=body.max_attempts,
                    enable_mediacrawler=body.enable_mediacrawler,
                    accept_mediacrawler_license=body.accept_mediacrawler_license,
                    subscription_id=None,
                    xhs_detail_reference_ref=normalized_detail_reference,
                    settings=resolved,
                    database=download_database,
                )
                operations.finish(
                    operation,
                    result={"payload": payload, "ok": ok},
                    error_code=None if ok else str(payload.get("error_code") or "asset_download_failed"),
                    exclusive_key=f"asset-download:{asset_id}",
                )
            except ValueError as error:
                operations.finish(operation, error_code=str(error), exclusive_key=f"asset-download:{asset_id}")
            except Exception:
                operations.finish(
                    operation,
                    error_code="asset_download_failed",
                    exclusive_key=f"asset-download:{asset_id}",
                )
            finally:
                if download_database is not None:
                    download_database.dispose()

        threading.Thread(target=run_download, name=f"media-sync-asset-{asset_id}", daemon=True).start()
        return {"operation_id": operation.id, "state": "running"}

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
    def scheduler_run(body: SchedulerRun) -> dict[str, object]:
        if body.accept_mediacrawler_license and not body.enable_mediacrawler:
            raise _bad_request("license_requires_enable_mediacrawler")
        operation = operations.start("scheduler-run")

        def run_worker() -> None:
            import asyncio

            worker_database: Database | None = None
            try:
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
                        worker_id=f"api-{uuid4()}",
                        max_jobs=body.max_jobs,
                        global_capacity=body.global_capacity,
                        lease_seconds=body.lease_seconds,
                        scan_limit=body.scan_limit,
                    )
                )
                operations.finish(
                    operation,
                    result={"results": [_scheduler_worker_payload(item) for item in results]},
                )
            except Exception:
                operations.finish(operation, error_code="scheduler_run_failed")
            finally:
                if worker_database is not None:
                    worker_database.dispose()

        threading.Thread(target=run_worker, name="media-sync-scheduler-run", daemon=True).start()
        return {"operation_id": operation.id, "state": "running"}

    @app.post("/api/v1/pipeline/run", status_code=202)
    def pipeline_run(body: PipelineRun) -> dict[str, object]:
        if body.accept_mediacrawler_license and not body.enable_mediacrawler:
            raise _bad_request("license_requires_enable_mediacrawler")
        normalized_xhs_reference = _safe_credential_reference(body.xhs_detail_reference_ref)
        if normalized_xhs_reference is not None and not body.enable_mediacrawler:
            raise _bad_request("xhs_detail_reference_requires_mediacrawler")
        operation = operations.start("pipeline-run")

        def run_pipeline() -> None:
            import asyncio

            worker_database: Database | None = None
            try:
                run_settings = resolved
                worker_database = Database(run_settings.resolved_database_url)
                worker = _build_pipeline_worker(
                    worker_database,
                    run_settings,
                    worker_id=body.worker_id,
                    retry_delay_seconds=body.retry_delay_seconds,
                    enable_mediacrawler=body.enable_mediacrawler,
                    accept_mediacrawler_license=body.accept_mediacrawler_license,
                    xhs_detail_reference_ref=normalized_xhs_reference,
                )
                results = asyncio.run(
                    worker.run_bounded(
                        worker_id=body.worker_id,
                        max_jobs=body.max_jobs,
                        lease_seconds=body.lease_seconds,
                        scan_limit=body.scan_limit,
                    )
                )
                operations.finish(
                    operation,
                    result={"results": [_pipeline_worker_payload(item) for item in results]},
                )
            except Exception:
                operations.finish(operation, error_code="pipeline_run_failed")
            finally:
                if worker_database is not None:
                    worker_database.dispose()

        threading.Thread(target=run_pipeline, name="media-sync-pipeline-run", daemon=True).start()
        return {"operation_id": operation.id, "state": "running"}

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

    @app.post("/api/v1/emby/export", status_code=202)
    def emby_export(body: EmbyExport) -> dict[str, object]:
        operation = operations.start("emby-export", exclusive_key=f"emby-export:{body.author_id}")

        def run_export() -> None:
            export_database: Database | None = None
            try:
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
                        worker_id=body.worker_id,
                        lease_seconds=body.lease_seconds,
                        max_attempts=body.max_attempts,
                    )
                )
                operations.finish(
                    operation,
                    result={
                        "author_id": str(body.author_id),
                        "already_exported": outcome.already_exported,
                        "output_path": str(outcome.output_path),
                    },
                    exclusive_key=f"emby-export:{body.author_id}",
                )
            except ExportError as error:
                operations.finish(operation, error_code=error.code, exclusive_key=f"emby-export:{body.author_id}")
            except Exception:
                operations.finish(operation, error_code="export_failed", exclusive_key=f"emby-export:{body.author_id}")
            finally:
                if export_database is not None:
                    export_database.dispose()

        threading.Thread(target=run_export, name="media-sync-emby-export", daemon=True).start()
        return {"operation_id": operation.id, "state": "running"}

    # ------------------------------------------------------------ operations

    @app.get("/api/v1/operations")
    def list_operations(limit: int = 50) -> list[dict[str, object]]:
        return operations.list(limit=max(1, min(limit, 200)))

    @app.get("/api/v1/operations/{operation_id}")
    def get_operation(operation_id: str) -> dict[str, object]:
        return operations.payload(operations.get(operation_id))

    return app


__all__ = ["create_api_app"]
