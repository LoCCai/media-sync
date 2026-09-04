"""Command-line interface for local media-sync administration."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import hmac
import json
import math
import os
import platform as runtime_platform
import shutil
import signal
import sys
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Annotated, Any
from uuid import UUID, uuid4

import typer
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError
from sqlalchemy.orm import Session

from media_sync import __version__
from media_sync.adapters.fake import FakePlatformAdapter
from media_sync.application import (
    AccountDraft,
    LocalPipelineRuntimeConfig,
    MediaCrawlerLoginSessionReconciler,
    SubscriptionDraft,
    SubscriptionPipelineError,
    SubscriptionPipelineExecutor,
    SyncRequest,
    SyncService,
    WorkbenchError,
    WorkbenchService,
)
from media_sync.application.authentication import (
    AccountLoginError,
    AccountLoginOutcome,
    AccountLoginRequest,
    MediaCrawlerQrLoginService,
)
from media_sync.application.downloads import (
    AssetDownloadOrchestrationError,
    AssetDownloadRequest,
    AssetDownloadService,
)
from media_sync.application.emby import (
    EmbyExportRequest,
    EmbyExportService,
    export_error_is_retryable,
)
from media_sync.application.mediacrawler import load_normalized_output
from media_sync.application.mediacrawler_download import LazyMediaCrawlerLocatorRefresher
from media_sync.application.operations import DurableSubjectHook
from media_sync.config import Settings, get_settings
from media_sync.domain import AccountRef, AssetStatus, Cursor, DomainError, JobStatus, LoginMethod, Platform, RunStatus
from media_sync.exporters.emby import EmbyExporter, ExportError
from media_sync.infrastructure.db import (
    Account,
    AccountRepository,
    Asset,
    Base,
    Content,
    Database,
    IngestionMode,
    LoginSessionRepository,
    LoginSessionState,
    MediaCrawlerIngestionService,
    NotFoundError,
    RepositoryError,
    SQLAlchemySyncRepository,
    StaleCheckpointError,
    Subscription,
    SubscriptionRepository,
    SyncRunRepository,
    upgrade_database,
)
from media_sync.integrations.mediacrawler.bridge import (
    BridgeRequest,
    MediaCrawlerBridge,
    MediaCrawlerRunMode,
    RunnerManifest,
    verify_manifest_checkout,
)
from media_sync.integrations.mediacrawler.capabilities import (
    MediaCrawlerCapabilityError,
    normalize_creator_stable_id,
)
from media_sync.integrations.mediacrawler.checkout import (
    MEDIACRAWLER_LICENSE,
    CheckoutValidationError,
    LicenseAcknowledgementRequired,
    verify_mediacrawler_browser,
    verify_mediacrawler_checkout,
    verify_mediacrawler_python,
)
from media_sync.integrations.mediacrawler.login import (
    MediaCrawlerLoginRequest,
    MediaCrawlerLoginResult,
    MediaCrawlerLoginStatus,
)
from media_sync.integrations.mediacrawler.login_runner import MediaCrawlerLoginProcessRunner
from media_sync.integrations.mediacrawler.policies import (
    MediaCrawlerPolicyError,
    build_run_paths,
    normalize_creator_reference,
)
from media_sync.integrations.mediacrawler.subscription_policy import MAX_REQUEST_DELAY_SECONDS
from media_sync.media import (
    DownloadLimits,
    FFmpegStreamCopyMuxer,
    FFprobeMediaProbe,
    MediaDownloadError,
    NetworkLimits,
    SafeHttpClient,
    SecureMediaDownloader,
    SocketAddressResolver,
)
from media_sync.scheduler import (
    DurableSchedulerService,
    FakeSubscriptionHandler,
    LanePolicy,
    LaneScope,
    LaneSnapshot,
    MaterializedCycle,
    MediaCrawlerScheduledHandler,
    PipelineHandlerResult,
    PipelineSubscriptionClaim,
    PipelineSubscriptionWorker,
    PipelineWorkerResult,
    ResidentSchedulerSupervisor,
    ResidentSupervisorConfig,
    ResidentSupervisorResult,
    SchedulerJobSummary,
    SchedulerRepositoryError,
    SchedulerWorkerResult,
    StaleLaneError,
    SubscriptionHandler,
    SubscriptionHandlerRegistry,
    SubscriptionSchedule,
    SubscriptionWorker,
)
from media_sync.security import (
    InvalidSecretReferenceError,
    SecretError,
    SecretReference,
    SecretResolver,
)

app = typer.Typer(
    name="media-sync",
    help="Local-first creator subscriptions and Emby/Jellyfin export.",
    no_args_is_help=True,
)
db_app = typer.Typer(help="Database schema and diagnostic commands.")
account_app = typer.Typer(help="Platform account commands.")
subscription_app = typer.Typer(help="Creator subscription commands.")
sync_app = typer.Typer(help="Subscription synchronization commands.")
scheduler_app = typer.Typer(help="Durable scheduler controls and foreground supervision.")
scheduler_job_app = typer.Typer(help="Redaction-safe scheduler Job controls.")
scheduler_lane_app = typer.Typer(help="Persistent scheduler lane controls.")
mediacrawler_app = typer.Typer(help="License-gated external MediaCrawler bridge commands.")
asset_app = typer.Typer(help="Verified media asset download commands.")
emby_app = typer.Typer(help="Emby/Jellyfin library export commands.")
pipeline_app = typer.Typer(help="Durable subscription download-to-Emby pipeline commands.")
app.add_typer(db_app, name="db")
app.add_typer(account_app, name="account")
app.add_typer(subscription_app, name="subscription")
app.add_typer(sync_app, name="sync")
app.add_typer(scheduler_app, name="scheduler")
scheduler_app.add_typer(scheduler_job_app, name="job")
scheduler_app.add_typer(scheduler_lane_app, name="lane")
app.add_typer(mediacrawler_app, name="mediacrawler")
app.add_typer(asset_app, name="asset")
app.add_typer(emby_app, name="emby")
app.add_typer(pipeline_app, name="pipeline")

_EXPECTED_DATABASE_REVISION = "0007_media_server_operations"
_REQUIRED_DATABASE_TABLES = frozenset(str(name) for name in Base.metadata.tables)


class AdapterName(StrEnum):
    """Account adapter identifiers exposed as a closed CLI choice."""

    FAKE = "fake"
    MEDIACRAWLER = "mediacrawler"


class SchedulerLaneScope(StrEnum):
    """Closed lane scopes exposed by the local scheduler CLI."""

    PLATFORM = "platform"
    ACCOUNT = "account"


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"media-sync {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option("--version", callback=_version_callback, is_eager=True, help="Show version and exit."),
    ] = False,
) -> None:
    """Manage media-sync locally."""


def collect_doctor_report(settings: Settings) -> dict[str, Any]:
    """Collect a secret-free, read-only environment report."""

    tools = {
        "ffmpeg": shutil.which("ffmpeg"),
        "ffprobe": shutil.which("ffprobe"),
        "git": shutil.which("git"),
    }
    runtime_roots = {
        "state": settings.state_dir,
        "archive": settings.archive_dir,
        "export": settings.export_dir,
        "jobs": settings.job_dir,
    }
    return {
        "ok": True,
        "version": __version__,
        "python": sys.version.split()[0],
        "system": runtime_platform.system(),
        "database_driver": settings.resolved_database_url.split(":", 1)[0],
        "api_bind": f"{settings.api_host}:{settings.api_port}",
        "tools": tools,
        "requirements": {
            "asset_download": {
                "ffprobe_required_for": ["video", "audio"],
                "ready": tools["ffprobe"] is not None,
            },
            "bilibili_dash_mux": {
                "ffmpeg_required": True,
                "ready": tools["ffmpeg"] is not None,
            },
        },
        "paths": {name: str(path.resolve()) for name, path in runtime_roots.items()},
        "path_exists": {name: path.exists() for name, path in runtime_roots.items()},
    }


def describe_database_target(database_url: str) -> str:
    """Return a useful target label without URL credentials or query values."""

    url = make_url(database_url)
    if url.drivername.startswith("sqlite"):
        if not url.database or url.database == ":memory:":
            return f"driver={url.drivername}, target=memory"
        database_path = Path(url.database).expanduser().resolve()
        return f"driver={url.drivername}, file={database_path}"

    host = url.host or "local"
    if url.port is not None:
        host = f"{host}:{url.port}"
    return f"driver={url.drivername}, host={host}"


def collect_database_status(database_url: str) -> dict[str, object]:
    """Inspect schema readiness without migrating or exposing the database target."""

    url = make_url(database_url)
    base_status: dict[str, object] = {
        "ok": False,
        "database_driver": url.drivername,
        "reachable": False,
        "revision": None,
        "expected_revision": _EXPECTED_DATABASE_REVISION,
        "revision_current": False,
        "required_table_count": len(_REQUIRED_DATABASE_TABLES),
        "present_table_count": 0,
        "missing_tables": sorted(_REQUIRED_DATABASE_TABLES),
    }

    if url.drivername.startswith("sqlite") and url.database is not None and url.database not in {"", ":memory:"}:
        database_path = Path(url.database).expanduser().resolve()
        if not database_path.is_file():
            return {**base_status, "reason": "database file does not exist"}

    engine = create_engine(database_url, future=True)
    try:
        with engine.connect() as connection:
            table_names = set(inspect(connection).get_table_names())
            present_tables = _REQUIRED_DATABASE_TABLES.intersection(table_names)
            missing_tables = sorted(_REQUIRED_DATABASE_TABLES.difference(table_names))
            revisions: tuple[str, ...] = ()
            if "alembic_version" in table_names:
                revisions = tuple(connection.scalars(text("SELECT version_num FROM alembic_version")))
    except SQLAlchemyError:
        return {**base_status, "reason": "database connection failed"}
    finally:
        engine.dispose()

    revision_current = revisions == (_EXPECTED_DATABASE_REVISION,)
    status = {
        **base_status,
        "reachable": True,
        "revision": _EXPECTED_DATABASE_REVISION if revision_current else None,
        "revision_current": revision_current,
        "present_table_count": len(present_tables),
        "missing_tables": missing_tables,
    }
    if "alembic_version" not in table_names:
        return {**status, "reason": "database schema is not initialized"}
    if not revision_current:
        return {**status, "reason": "database schema revision is not current"}
    if missing_tables:
        return {**status, "reason": "database schema is incomplete"}
    return {**status, "ok": True, "reason": None}


def collect_mediacrawler_doctor_report(
    settings: Settings,
    *,
    license_acknowledged: bool,
) -> dict[str, object]:
    """Inspect the pinned checkout/runtime without creating jobs or resolving secrets."""

    checkout_check_names = (
        "license_acknowledgement",
        "lock",
        "checkout_path",
        "repository_root",
        "required_files",
        "license",
        "revision",
        "tracked_files",
        "worktree_clean",
    )
    checkout_failure_check = {
        "lock_missing": "lock",
        "lock_invalid": "lock",
        "lock_repository_mismatch": "lock",
        "lock_license_mismatch": "lock",
        "lock_commit_invalid": "lock",
        "lock_path_invalid": "checkout_path",
        "checkout_missing": "checkout_path",
        "not_repository_root": "repository_root",
        "required_file_missing": "required_files",
        "license_unavailable": "license",
        "license_header_mismatch": "license",
        "license_digest_mismatch": "license",
        "revision_mismatch": "revision",
        "required_file_not_tracked": "tracked_files",
        "tracked_blob_mismatch": "tracked_files",
        "worktree_dirty": "worktree_clean",
        "git_inspection_failed": "repository_root",
    }

    def checkout_checks(detail_code: str | None) -> dict[str, str]:
        checks = {name: "not_run" for name in checkout_check_names}
        if not license_acknowledged:
            checks["license_acknowledgement"] = "fail"
            return checks
        if detail_code is None:
            return {name: "pass" for name in checkout_check_names}
        checks["license_acknowledgement"] = "pass"
        failed_check = checkout_failure_check.get(detail_code)
        if failed_check is None:
            return checks
        failed_index = checkout_check_names.index(failed_check)
        for name in checkout_check_names[:failed_index]:
            checks[name] = "pass"
        checks[failed_check] = "fail"
        return checks

    report: dict[str, object] = {
        "ok": False,
        "code": None,
        "detail_code": None,
        "upstream_sha": None,
        "license": MEDIACRAWLER_LICENSE,
        "checkout_ready": False,
        "runtime_configured": settings.mediacrawler_python_executable is not None,
        "runtime_ready": False,
        "checks": checkout_checks(None),
        "live_qualification": "NOT_RUN",
    }
    try:
        checkout = verify_mediacrawler_checkout(
            settings.mediacrawler_lock_path,
            license_acknowledged=license_acknowledged,
        )
    except LicenseAcknowledgementRequired as error:
        return {
            **report,
            "code": "license_acknowledgement_required",
            "detail_code": error.code,
            "checks": checkout_checks(error.code),
        }
    except CheckoutValidationError as error:
        return {
            **report,
            "code": "checkout_invalid",
            "detail_code": error.code,
            "checks": checkout_checks(error.code),
        }

    report.update(
        {
            "checkout_ready": True,
            "upstream_sha": checkout.commit,
            "checks": checkout_checks(None),
        }
    )
    if settings.mediacrawler_python_executable is None:
        return {
            **report,
            "code": "runtime_unconfigured",
            "detail_code": "runtime_unconfigured",
            "checks": {**checkout_checks(None), "runtime": "fail"},
        }
    try:
        verify_mediacrawler_python(settings.mediacrawler_python_executable)
    except CheckoutValidationError as error:
        return {
            **report,
            "code": "runtime_invalid",
            "detail_code": error.code,
            "checks": {**checkout_checks(None), "runtime": "fail"},
        }
    return {
        **report,
        "ok": True,
        "code": "ready",
        "detail_code": None,
        "runtime_ready": True,
        "checks": {**checkout_checks(None), "runtime": "pass"},
    }


def _readiness_path_status(path: Path) -> dict[str, object]:
    """Return path facts without returning the configured absolute path."""

    try:
        resolved = path.expanduser().resolve()
        exists = resolved.is_dir()
        writable = exists and os.access(resolved, os.W_OK)
    except OSError:
        exists = False
        writable = False
    return {
        "status": "pass" if exists and writable else "fail",
        "exists": exists,
        "writable": writable,
    }


def _read_build_manifest() -> dict[str, object]:
    """Read only small, non-secret toolchain facts from the image manifest."""

    manifest_path = Path("/opt/BUILD-MANIFEST.txt")
    if not manifest_path.is_file():
        return {"status": "not_run", "present": False, "facts": {}}
    allowed = {
        "python",
        "uv",
        "ffmpeg",
        "playwright",
        "chromium",
        "base_image",
        "node",
        "pnpm",
        "web_lock_sha256",
    }
    facts: dict[str, str] = {}
    try:
        for line in manifest_path.read_text(encoding="utf-8", errors="replace")[:1_048_576].splitlines():
            name, separator, value = line.partition(":")
            if separator and name in allowed and value.strip():
                facts[name] = value.strip()[:256]
    except (OSError, UnicodeError):
        return {"status": "fail", "present": True, "facts": {}}
    return {"status": "pass", "present": True, "facts": facts}


def collect_deep_readiness_report(
    settings: Settings,
    *,
    license_acknowledged: bool,
) -> dict[str, object]:
    """Run the explicit, read-only runtime qualification used by the console."""

    database: dict[str, object]
    try:
        database = collect_database_status(settings.resolved_database_url)
    except (OSError, SQLAlchemyError, ValueError):
        database = {
            "ok": False,
            "database_driver": "unknown",
            "reachable": False,
            "revision": None,
            "expected_revision": _EXPECTED_DATABASE_REVISION,
            "missing_tables": [],
            "reason": "database check failed",
        }

    tool_ready = {name: shutil.which(name) is not None for name in ("git", "ffmpeg", "ffprobe", "Xvfb")}
    tools: dict[str, object] = {
        name: {"status": "pass" if ready else "fail", "ready": ready} for name, ready in tool_ready.items()
    }
    paths: dict[str, object] = {
        "state": _readiness_path_status(settings.state_dir),
        "archive": _readiness_path_status(settings.archive_dir),
        "export": _readiness_path_status(settings.export_dir),
        "jobs": _readiness_path_status(settings.job_dir),
        "mediacrawler_runtime": _readiness_path_status(settings.resolved_mediacrawler_runtime_dir),
    }
    mediacrawler = collect_mediacrawler_doctor_report(
        settings,
        license_acknowledged=license_acknowledged,
    )
    browser: dict[str, object] = {
        "status": "not_run",
        "version": None,
        "detail_code": None,
    }
    if mediacrawler.get("runtime_ready") is True and settings.mediacrawler_python_executable is not None:
        try:
            browser["version"] = verify_mediacrawler_browser(settings.mediacrawler_python_executable)
            browser["status"] = "pass"
        except CheckoutValidationError as error:
            browser["status"] = "fail"
            browser["detail_code"] = error.code

    bind_host = settings.api_host.strip().lower()
    loopback_only = bind_host in {"127.0.0.1", "::1", "localhost"}
    security = {
        "status": "pass" if loopback_only else "warn",
        "code": None if loopback_only else "api_not_loopback",
        "safe": loopback_only,
        "requires_operator_review": not loopback_only,
        "api_host": settings.api_host,
        "api_port": settings.api_port,
        "note": "loopback_only" if loopback_only else "verify_host_port_is_trusted",
    }

    path_ready = all(isinstance(item, dict) and item.get("status") == "pass" for item in paths.values())
    database_ready = database.get("ok") is True
    mediacrawler_ready = mediacrawler.get("ok") is True
    browser_ready = browser.get("status") == "pass"
    if not database_ready:
        code = "database_not_ready"
    elif not mediacrawler_ready:
        code = str(mediacrawler.get("detail_code") or mediacrawler.get("code") or "mediacrawler_not_ready")
    elif not browser_ready:
        code = str(browser.get("detail_code") or "browser_not_ready")
    elif not tool_ready["git"]:
        code = "git_unavailable"
    elif not tool_ready["ffprobe"]:
        code = "ffprobe_unavailable"
    elif not tool_ready["ffmpeg"]:
        code = "ffmpeg_unavailable"
    elif not path_ready:
        code = "runtime_paths_not_ready"
    else:
        code = "ready"
    ok = code == "ready"
    return {
        "ok": ok,
        "status": "ready" if ok else "blocked",
        "code": code,
        "checked_at": datetime.now(UTC).isoformat(),
        "database": database,
        "tools": tools,
        "paths": paths,
        "mediacrawler": mediacrawler,
        "browser": browser,
        "build_manifest": _read_build_manifest(),
        "security": security,
        "live_qualification": "NOT_RUN",
    }


def _iso_datetime(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _account_payload(account: Account, *, created: bool | None = None) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": account.id,
        "platform": account.platform,
        "adapter": account.adapter,
        "display_name": account.display_name,
        "login_method": account.login_method,
        "auth_status": account.auth_status,
        "created_at": _iso_datetime(account.created_at),
    }
    if created is not None:
        payload["created"] = created
    return payload


def _account_login_outcome_payload(outcome: AccountLoginOutcome) -> dict[str, object]:
    """Project a completed login without profile, challenge, or child-process data."""

    return {
        "account_id": str(outcome.account_id),
        "login_session_id": str(outcome.login_session_id),
        "runner_status": outcome.runner_status.value,
        "login_session_status": outcome.session_status,
        "auth_status": outcome.auth_status.value,
        "expires_at": _iso_datetime(outcome.expires_at),
        "completed_at": _iso_datetime(outcome.completed_at),
        "created_at": _iso_datetime(outcome.created_at),
        "updated_at": _iso_datetime(outcome.updated_at),
    }


def _account_login_status_payload(
    account: Account,
    latest: LoginSessionState | None,
) -> dict[str, object]:
    """Project current Account auth plus the latest redaction-safe session state."""

    return {
        "account_id": account.id,
        "auth_status": account.auth_status,
        "auth_updated_at": _iso_datetime(account.auth_updated_at),
        "login_session_id": latest.id if latest is not None else None,
        "login_session_status": latest.status if latest is not None else None,
        "expires_at": _iso_datetime(latest.expires_at) if latest is not None else None,
        "completed_at": _iso_datetime(latest.completed_at) if latest is not None else None,
        "created_at": _iso_datetime(latest.created_at) if latest is not None else None,
        "updated_at": _iso_datetime(latest.updated_at) if latest is not None else None,
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


def _account_login_error_payload(account_id: UUID, code: str) -> dict[str, object]:
    """Return one fixed failure record without exception or upstream-controlled text."""

    return {
        "account_id": str(account_id),
        "status": "failed",
        "error_code": code,
        "retryable": code in _ACCOUNT_LOGIN_RETRYABLE_CODES,
    }


class _UnavailableMediaCrawlerLoginRunner:
    """Fail closed after account eligibility checks when no Python is configured."""

    def run(
        self,
        request: MediaCrawlerLoginRequest,
        *,
        on_account_locked: Any = None,
        cancellation: Any = None,
    ) -> MediaCrawlerLoginResult:
        del request, on_account_locked, cancellation
        return MediaCrawlerLoginResult(MediaCrawlerLoginStatus.CONFIGURATION_INVALID)


class _DeferredMediaCrawlerLoginRunner:
    """Construct the filesystem/process integration only after application preflight."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def run(
        self,
        request: MediaCrawlerLoginRequest,
        *,
        on_account_locked: Any = None,
        cancellation: Any = None,
    ) -> MediaCrawlerLoginResult:
        python_executable = self._settings.mediacrawler_python_executable
        if python_executable is None:  # pragma: no cover - caller selects the unavailable boundary
            return MediaCrawlerLoginResult(MediaCrawlerLoginStatus.CONFIGURATION_INVALID)
        return MediaCrawlerLoginProcessRunner(
            lock_path=self._settings.mediacrawler_lock_path,
            integration_root=self._settings.resolved_mediacrawler_runtime_dir,
            python_executable=python_executable,
            enabled=True,
            license_acknowledged=True,
        ).run(
            request,
            on_account_locked=on_account_locked,
            cancellation=cancellation,
        )


def _subscription_payload(
    subscription: Subscription,
    *,
    created: bool | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": subscription.id,
        "account_id": subscription.account_id,
        "platform": subscription.account.platform,
        "account_display_name": subscription.account.display_name,
        "author_id": subscription.author_id,
        "creator_remote_id": subscription.author.remote_id,
        "creator_display_name": subscription.author.display_name,
        "enabled": subscription.enabled,
        "interval_seconds": subscription.interval_seconds,
        "max_items": subscription.max_items,
        "watermarked_at": _iso_datetime(subscription.watermarked_at),
        "last_success_at": _iso_datetime(subscription.last_success_at),
        "next_run_at": _iso_datetime(subscription.next_run_at),
    }
    if created is not None:
        payload["created"] = created
    return payload


def _scheduler_schedule_payload(schedule: SubscriptionSchedule) -> dict[str, object]:
    """Project subscription scheduling state without creator/account secrets."""

    return {
        "subscription_id": schedule.subscription_id,
        "status": "enabled" if schedule.enabled else "paused",
        "interval_seconds": schedule.interval_seconds,
        "next_run_at": _iso_datetime(schedule.next_run_at),
        "last_run_at": _iso_datetime(schedule.last_run_at),
        "last_success_at": _iso_datetime(schedule.last_success_at),
        "schedule_revision": schedule.schedule_revision,
        "consecutive_failures": schedule.consecutive_failures,
    }


def _scheduler_cycle_payload(cycle: MaterializedCycle) -> dict[str, object]:
    return {
        "job_id": cycle.job_id,
        "subscription_id": cycle.subscription_id,
        "schedule_revision": cycle.schedule_revision,
        "scheduled_for": _iso_datetime(cycle.scheduled_for),
    }


def _scheduler_job_payload(job: SchedulerJobSummary) -> dict[str, object]:
    """Return the closed scheduler Job projection; never serialize Job payloads or leases."""

    return {
        "job_id": job.job_id,
        "subscription_id": job.subscription_id,
        "account_id": job.account_id,
        "platform": job.platform,
        "status": job.status,
        "attempt": job.attempts,
        "max_attempts": job.max_attempts,
        "available_at": _iso_datetime(job.available_at),
        "scheduled_for": _iso_datetime(job.scheduled_for),
        "run_id": job.run_id,
        "created_at": _iso_datetime(job.created_at),
        "updated_at": _iso_datetime(job.updated_at),
        "started_at": _iso_datetime(job.started_at),
        "finished_at": _iso_datetime(job.finished_at),
    }


def _scheduler_worker_payload(result: SchedulerWorkerResult) -> dict[str, object]:
    return {
        "job_id": result.job_id,
        "subscription_id": result.subscription_id,
        "status": result.status,
        "attempt": result.attempt,
        "run_id": result.run_id,
    }


def _pipeline_worker_payload(result: PipelineWorkerResult) -> dict[str, object]:
    return {
        "job_id": result.job_id,
        "subscription_id": result.subscription_id,
        "status": result.status,
        "attempt": result.attempt,
        "error_code": result.error_code,
    }


def _resident_supervisor_payload(result: ResidentSupervisorResult) -> dict[str, object]:
    """Return one fixed final summary without Job, lease, path or handler data."""

    return {
        "status": "stopped" if result.stopped else "completed",
        "outcome": result.outcome,
        "cycles": result.cycles,
        "login_scanned": result.login_scanned,
        "login_recovered": result.login_recovered,
        "login_busy": result.login_busy,
        "login_conflicted": result.login_conflicted,
        "materialized": result.materialized,
        "subscription_attempts": result.subscription_attempts,
        "pipeline_attempts": result.pipeline_attempts,
    }


def _scheduler_lane_payload(lane: LaneSnapshot) -> dict[str, object]:
    policy = lane.policy
    return {
        "lane_id": lane.lane_id,
        "scope": policy.scope_type,
        "platform": policy.platform,
        "account_id": policy.account_id,
        "max_concurrency": policy.max_concurrency,
        "min_start_interval_seconds": policy.min_start_interval_seconds,
        "failure_threshold": policy.failure_threshold,
        "cooldown_seconds": policy.cooldown_seconds,
        "next_start_at": _iso_datetime(lane.next_start_at),
        "consecutive_failures": lane.consecutive_failures,
        "circuit_state": lane.circuit_state,
        "circuit_open_until": _iso_datetime(lane.circuit_open_until),
        "half_open_job_id": lane.half_open_job_id,
        "revision": lane.revision,
        "created_at": _iso_datetime(lane.created_at),
        "updated_at": _iso_datetime(lane.updated_at),
    }


def _asset_payload(asset: Asset, *, author_id: str) -> dict[str, object]:
    """Return only stable asset discovery and lifecycle fields."""

    return {
        "id": asset.id,
        "author_id": author_id,
        "content_id": asset.content_id,
        "platform": asset.platform,
        "kind": asset.kind,
        "position": asset.position,
        "generation": asset.generation,
        "status": asset.status,
        "mime_type": asset.mime_type,
        "size_bytes": asset.size_bytes,
        "verified_at": _iso_datetime(asset.verified_at),
    }


def _emit_record(payload: dict[str, object], *, json_output: bool, label: str) -> None:
    if json_output:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    fields = " ".join(f"{key}={value}" for key, value in payload.items() if value is not None)
    typer.echo(f"{label}: {fields}")


def _emit_list(records: list[dict[str, object]], *, json_output: bool, label: str) -> None:
    if json_output:
        typer.echo(json.dumps(records, ensure_ascii=False, indent=2))
        return
    if not records:
        typer.echo(f"No {label} found.")
        return
    for record in records:
        fields = " ".join(f"{key}={value}" for key, value in record.items() if value is not None)
        typer.echo(fields)


@contextmanager
def _database_session() -> Iterator[Session]:
    """Open one transaction and translate persistence errors into safe CLI errors."""

    database: Database | None = None
    try:
        database = Database(get_settings().resolved_database_url)
        with database.session() as session:
            yield session
    except IntegrityError:
        raise typer.BadParameter("database conflict: a record already exists or violates a constraint") from None
    except OperationalError:
        raise typer.BadParameter(
            "database operation failed; run `media-sync db init` and verify the database is not busy"
        ) from None
    except DomainError as error:
        raise typer.BadParameter(f"{error.code}: domain operation rejected") from None
    except RepositoryError:
        raise typer.BadParameter("repository operation rejected; no changes were committed") from None
    except SQLAlchemyError:
        raise typer.BadParameter("database operation failed; no changes were committed") from None
    finally:
        if database is not None:
            database.dispose()


@contextmanager
def _scheduler_runtime() -> Iterator[tuple[Database, DurableSchedulerService]]:
    """Own one local scheduler Database while translating failures to fixed CLI messages."""

    database: Database | None = None
    try:
        database = Database(get_settings().resolved_database_url)
        yield database, DurableSchedulerService(database)
    except StaleLaneError:
        raise typer.BadParameter("scheduler lane revision conflict; list lanes and retry") from None
    except NotFoundError:
        raise typer.BadParameter("scheduler record was not found") from None
    except IntegrityError:
        raise typer.BadParameter("scheduler database conflict; retry the bounded operation") from None
    except OperationalError:
        raise typer.BadParameter(
            "scheduler database operation failed; run `media-sync db init` and verify the database is not busy"
        ) from None
    except (SchedulerRepositoryError, RepositoryError):
        raise typer.BadParameter("scheduler operation was rejected; no unsafe details were emitted") from None
    except SQLAlchemyError:
        raise typer.BadParameter("scheduler database operation failed; no changes were committed") from None
    except (TypeError, ValueError):
        raise typer.BadParameter("scheduler arguments or durable state were rejected") from None
    finally:
        if database is not None:
            database.dispose()


def _build_subscription_worker(
    database: Database,
    settings: Settings,
    *,
    enable_mediacrawler: bool,
    accept_mediacrawler_license: bool,
) -> SubscriptionWorker:
    """Compose the same closed handler registry for bounded and resident workers."""

    handlers: dict[str, SubscriptionHandler] = {"fake": FakeSubscriptionHandler(database)}
    if enable_mediacrawler:
        handlers[AdapterName.MEDIACRAWLER.value] = MediaCrawlerScheduledHandler(
            database,
            lock_path=settings.mediacrawler_lock_path,
            integration_root=settings.resolved_mediacrawler_runtime_dir,
            python_executable=settings.mediacrawler_python_executable,
            secret_resolver=SecretResolver.local(file_root=settings.resolved_secret_file_dir),
            enabled=True,
            license_acknowledged=accept_mediacrawler_license,
        )
    return SubscriptionWorker(
        database,
        SubscriptionHandlerRegistry(handlers),
        claim_registered_only=True,
    )


def _build_pipeline_worker(
    database: Database,
    settings: Settings,
    *,
    worker_id: str,
    retry_delay_seconds: int,
    enable_mediacrawler: bool,
    accept_mediacrawler_license: bool,
    xhs_detail_reference_ref: str | None,
) -> PipelineSubscriptionWorker:
    """Compose one durable pipeline worker with a fixed, scope-validating handler."""

    executor = SubscriptionPipelineExecutor(
        database,
        LocalPipelineRuntimeConfig(
            work_root=settings.job_dir / "downloads",
            archive_root=settings.archive_dir,
            export_root=settings.export_dir,
            export_staging_root=settings.job_dir / "emby-export",
            mediacrawler_lock_path=settings.mediacrawler_lock_path,
            mediacrawler_runtime_root=settings.resolved_mediacrawler_runtime_dir,
            mediacrawler_python_executable=settings.mediacrawler_python_executable,
            secret_resolver=SecretResolver.local(file_root=settings.resolved_secret_file_dir),
            enable_mediacrawler=enable_mediacrawler,
            accept_mediacrawler_license=accept_mediacrawler_license,
            xhs_detail_reference_ref=xhs_detail_reference_ref,
            ffprobe_executable=shutil.which("ffprobe"),
            ffmpeg_executable=shutil.which("ffmpeg"),
        ),
    )

    def handle(claim: PipelineSubscriptionClaim) -> PipelineHandlerResult:
        try:
            with database.session() as session:
                subscription = session.get(Subscription, claim.subscription_id)
                if (
                    subscription is None
                    or subscription.account_id != claim.account_id
                    or subscription.account.platform != claim.platform
                ):
                    return PipelineHandlerResult.failure("pipeline_subscription_invalid")
            outcome = executor.run(
                UUID(claim.subscription_id),
                expected_account_id=UUID(claim.account_id),
                expected_platform=claim.platform,
                worker_id=f"{worker_id}:{claim.job_id}",
            )
            if (
                str(outcome.selection.subscription_id) != claim.subscription_id
                or str(outcome.selection.account_id) != claim.account_id
                or outcome.selection.platform != claim.platform
            ):
                return PipelineHandlerResult.failure("pipeline_subscription_invalid")
        except SubscriptionPipelineError as error:
            return PipelineHandlerResult.failure(error.code)
        except AssetDownloadOrchestrationError as error:
            return PipelineHandlerResult.failure(
                "pipeline_download_retryable" if error.retryable else "pipeline_download_terminal"
            )
        except ExportError as error:
            return PipelineHandlerResult.failure(
                "pipeline_export_retryable" if export_error_is_retryable(error.code) else "pipeline_export_terminal"
            )
        except (TypeError, ValueError):
            return PipelineHandlerResult.failure("pipeline_handler_invalid")
        return PipelineHandlerResult.success()

    return PipelineSubscriptionWorker(
        database,
        handle,
        retry_delay_seconds=retry_delay_seconds,
    )


@contextmanager
def _resident_stop_signals(supervisor: ResidentSchedulerSupervisor) -> Iterator[None]:
    """Cooperate on the first signal and hard-exit on a repeated request."""

    previous: dict[signal.Signals, Any] = {}
    stop_requested = False

    def request_stop(number: int, _frame: Any) -> None:
        nonlocal stop_requested
        if stop_requested:
            # The first signal starts phase-correct drain. A repeated operator
            # request is deliberately forceful: durable leases and child
            # parent-liveness fencing own recovery after this process exits.
            os._exit(128 + int(number))
        stop_requested = True
        supervisor.request_stop()

    candidates = (signal.SIGINT, getattr(signal, "SIGTERM", signal.SIGINT))
    try:
        for candidate in dict.fromkeys(candidates):
            try:
                previous[candidate] = signal.getsignal(candidate)
                signal.signal(candidate, request_stop)
            except (OSError, RuntimeError, ValueError):
                previous.pop(candidate, None)
        yield
    finally:
        for candidate, handler in previous.items():
            with contextlib.suppress(OSError, RuntimeError, ValueError):
                signal.signal(candidate, handler)


async def _run_resident_supervisor(supervisor: ResidentSchedulerSupervisor) -> ResidentSupervisorResult:
    """Own temporary signal handlers for one foreground supervisor run."""

    with _resident_stop_signals(supervisor):
        return await supervisor.run()


def _lane_scope(value: SchedulerLaneScope) -> LaneScope:
    return "platform" if value is SchedulerLaneScope.PLATFORM else "account"


def _required_option(value: str, name: str) -> str:
    normalized = value.strip()
    if not normalized or len(normalized) > 255:
        raise typer.BadParameter(f"{name} must contain between 1 and 255 characters")
    if any(not character.isprintable() for character in normalized):
        raise typer.BadParameter(f"{name} must not contain control characters")
    return normalized


def _credential_reference(value: str | None) -> str | None:
    """Validate an opaque lookup reference and reject secret-like inline data."""

    if value is None:
        return None
    normalized = value.strip()
    if any(marker in normalized for marker in ("\r", "\n", "\0", ";", "=")):
        raise typer.BadParameter("credential_ref must not contain inline credential data")
    try:
        return SecretReference.parse(normalized).serialize()
    except InvalidSecretReferenceError:
        raise typer.BadParameter(
            "credential_ref must use env:<VAR>, keyring:<service/account>, or a confined file:<relative-path>"
        ) from None


def _account_workbench_error_message(error: WorkbenchError, *, adapter: AdapterName) -> str:
    """Map shared fixed codes to the established CLI vocabulary."""

    if error.code == "login_method_not_supported":
        if adapter is AdapterName.FAKE:
            return "selected login method is not supported by the fake adapter"
        return "MediaCrawler accounts support only QR, Cookie, or saved-session login"
    messages = {
        "display_name_invalid": "display_name must contain between 1 and 255 printable characters",
        "cookie_login_requires_credential_ref": "MediaCrawler Cookie login requires credential_ref",
        "credential_ref_allowed_only_for_cookie_login": (
            "credential_ref is allowed only for MediaCrawler Cookie login"
        ),
        "account_exists_with_different_configuration": ("account already exists with different login configuration"),
    }
    return messages.get(error.code, error.message)


def _subscription_workbench_error_message(error: WorkbenchError, *, account_id: UUID) -> str:
    """Map shared fixed codes without copying rejected creator or secret input."""

    messages = {
        "account_not_found": f"account not found: {account_id}",
        "platform_conflict": "platform conflict: account and creator platforms differ",
        "creator_remote_id_must_be_stable_id": (
            "MediaCrawler creator_remote_id must be a stable ID; use creator_reference_ref for signed URLs"
        ),
        "creator_secret_ref_only_for_mediacrawler": (
            "creator_reference_ref is available only for MediaCrawler accounts"
        ),
        "creator_secret_ref_not_supported": (
            "creator_reference_ref is supported only for the XHS creator-authority flow"
        ),
        "invalid_creator_secret_reference": (
            "creator_reference_ref must be an opaque env, keyring, or confined file reference"
        ),
        "full_history_acknowledgement_required": (
            "allow_full_history acknowledgement is required for this MediaCrawler platform"
        ),
        "mediacrawler_policy_options_require_mediacrawler": (
            "MediaCrawler scheduling policy options require a MediaCrawler account"
        ),
        "subscription_exists_with_different_options": ("subscription already exists with different scheduling options"),
    }
    return messages.get(error.code, error.message)


def _expected_mediacrawler_creator_fingerprint(
    settings: Settings,
    *,
    platform: Platform,
    creator_remote_id: str,
    policy: Mapping[str, object],
) -> str:
    """Hash the creator input authorized by the current subscription policy."""

    raw_reference: object | None = None
    mediacrawler_policy = policy.get("mediacrawler")
    if mediacrawler_policy is not None:
        if not isinstance(mediacrawler_policy, Mapping):
            raise MediaCrawlerPolicyError("stored MediaCrawler creator policy is invalid")
        creator_input = mediacrawler_policy.get("creator_input")
        if creator_input is not None:
            if not isinstance(creator_input, Mapping) or set(creator_input) != {"secret_ref"}:
                raise MediaCrawlerPolicyError("stored MediaCrawler creator policy is invalid")
            raw_reference = creator_input.get("secret_ref")

    if raw_reference is None:
        creator_reference = creator_remote_id
    else:
        if not isinstance(raw_reference, str):
            raise MediaCrawlerPolicyError("stored MediaCrawler creator policy is invalid")
        try:
            reference = SecretReference.parse(raw_reference)
            resolved = SecretResolver.local(file_root=settings.resolved_secret_file_dir).resolve(reference)
            creator_reference = resolved.reveal()
        except SecretError:
            raise MediaCrawlerPolicyError("stored MediaCrawler creator reference could not be resolved") from None

    normalized = normalize_creator_reference(platform, creator_reference)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _stored_cursor(subscription: Subscription) -> Cursor | None:
    if subscription.cursor is None:
        return None
    value = subscription.cursor.get("value")
    if not isinstance(value, str) or not value.strip():
        raise RepositoryError("subscription has a malformed cursor")
    return Cursor(value)


@app.command()
def doctor(
    json_output: Annotated[bool, typer.Option("--json", help="Emit machine-readable JSON.")] = False,
) -> None:
    """Inspect local prerequisites without displaying credentials."""

    report = collect_doctor_report(get_settings())
    if json_output:
        typer.echo(json.dumps(report, ensure_ascii=False, indent=2))
        return

    typer.echo(f"media-sync {report['version']} on Python {report['python']} ({report['system']})")
    typer.echo(f"API default: {report['api_bind']}")
    for name, executable in report["tools"].items():
        typer.echo(f"{name}: {executable or 'NOT FOUND'}")
    asset_download_ready = report["requirements"]["asset_download"]["ready"]
    typer.echo(
        "video/audio asset download prerequisite: "
        f"ffprobe is required ({'ready' if asset_download_ready else 'NOT READY'})"
    )
    dash_mux_ready = report["requirements"]["bilibili_dash_mux"]["ready"]
    typer.echo(
        f"Bilibili DASH video download prerequisite: ffmpeg is required ({'ready' if dash_mux_ready else 'NOT READY'})"
    )
    for name, path in report["paths"].items():
        marker = "exists" if report["path_exists"][name] else "will be created"
        typer.echo(f"{name}: {path} ({marker})")


@mediacrawler_app.command("doctor")
def mediacrawler_doctor(
    accept_license: Annotated[
        bool,
        typer.Option(
            "--accept-license",
            help="Acknowledge the pinned non-commercial learning license for this check.",
        ),
    ] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Emit machine-readable JSON.")] = False,
) -> None:
    """Read-only validation of the external checkout and explicit Python runtime."""

    report = collect_mediacrawler_doctor_report(
        get_settings(),
        license_acknowledged=accept_license,
    )
    if json_output:
        typer.echo(json.dumps(report, ensure_ascii=False, indent=2))
    elif report["ok"]:
        typer.echo(f"MediaCrawler bridge ready: upstream_sha={report['upstream_sha']} live_qualification=NOT_RUN")
    else:
        typer.echo(f"MediaCrawler bridge not ready: code={report['code']} live_qualification=NOT_RUN")
    if not report["ok"]:
        raise typer.Exit(code=1)


@mediacrawler_app.command("dry-run")
def mediacrawler_dry_run(
    platform: Annotated[Platform, typer.Option(help="Platform code.")],
    creator_id: Annotated[str, typer.Option(help="Stable non-secret creator ID/token.")],
    accept_license: Annotated[
        bool,
        typer.Option(
            "--accept-license",
            help="Acknowledge the pinned non-commercial learning license for this preparation.",
        ),
    ] = False,
    allow_full_history: Annotated[
        bool,
        typer.Option(help="Acknowledge platforms whose upstream creator path ignores item caps."),
    ] = False,
    max_items: Annotated[int, typer.Option(min=1, max=1_000)] = 30,
    json_output: Annotated[bool, typer.Option("--json", help="Emit machine-readable JSON.")] = False,
) -> None:
    """Prepare, inspect, and discard a secret-free bridge job without spawning it."""

    try:
        normalized_creator_id = normalize_creator_stable_id(creator_id)
    except MediaCrawlerCapabilityError:
        raise typer.BadParameter(
            "creator_id must be a stable non-secret ID; token-bearing URLs require a secret reference"
        ) from None
    settings = get_settings()
    if settings.mediacrawler_python_executable is None:
        raise typer.BadParameter("MediaCrawler Python runtime is not configured")

    account_id = uuid4()
    subscription_id = uuid4()
    job_id = uuid4()
    try:
        with TemporaryDirectory(prefix="media-sync-mediacrawler-dry-run-") as temporary_root:
            spec = MediaCrawlerBridge().prepare(
                BridgeRequest(
                    lock_path=settings.mediacrawler_lock_path,
                    integration_root=Path(temporary_root),
                    python_executable=settings.mediacrawler_python_executable,
                    account_id=account_id,
                    subscription_id=subscription_id,
                    job_id=job_id,
                    checkpoint_revision_before=0,
                    intended_mode=MediaCrawlerRunMode.FORWARD,
                    platform=platform,
                    login_method=LoginMethod.QR,
                    author_remote_id=normalized_creator_id,
                    creator_reference=normalized_creator_id,
                    license_acknowledged=accept_license,
                    allow_full_history=allow_full_history,
                    headless=True,
                    max_items=max_items,
                )
            )
            payload: dict[str, object] = {
                "ok": True,
                "platform": platform.value,
                "login_method": LoginMethod.QR.value,
                "upstream_sha": spec.manifest.upstream_sha,
                "allow_full_history": allow_full_history,
                "max_items": max_items,
                "command_shape": [
                    "<verified-python>",
                    "-I",
                    "-u",
                    "-B",
                    "<isolated-runner>",
                    "--manifest",
                    "<unique-job-manifest>",
                ],
                "spawned": False,
                "live_qualification": "NOT_RUN",
            }
    except (CheckoutValidationError, MediaCrawlerPolicyError):
        raise typer.BadParameter("MediaCrawler dry-run preparation was rejected") from None

    _emit_record(payload, json_output=json_output, label="MediaCrawler dry-run")


@db_app.command("init")
def init_database() -> None:
    """Create runtime roots and upgrade the database schema."""

    try:
        settings = get_settings()
        settings.ensure_directories()
        upgrade_database(settings.resolved_database_url)
        target = describe_database_target(settings.resolved_database_url)
    except Exception:
        raise typer.BadParameter("database initialization failed; verify configuration and permissions") from None
    typer.echo(f"Database schema upgraded ({target})")


@db_app.command("status")
def database_status(
    json_output: Annotated[bool, typer.Option("--json", help="Emit machine-readable JSON.")] = False,
) -> None:
    """Check database connectivity, migration revision, and required tables."""

    try:
        status = collect_database_status(get_settings().resolved_database_url)
    except Exception:
        raise typer.BadParameter("database status check failed; verify configuration") from None

    if json_output:
        typer.echo(json.dumps(status, ensure_ascii=False, indent=2))
    elif status["ok"]:
        typer.echo(
            "Database ready: "
            f"driver={status['database_driver']} "
            f"revision={status['revision']} "
            f"tables={status['present_table_count']}/{status['required_table_count']}"
        )
    else:
        typer.echo(
            "Database not ready: "
            f"{status['reason']}; "
            f"driver={status['database_driver']} "
            f"tables={status['present_table_count']}/{status['required_table_count']}; "
            "run `media-sync db init`"
        )

    if not status["ok"]:
        raise typer.Exit(code=1)


@account_app.command("add")
def add_account(
    platform: Annotated[Platform, typer.Option(help="Platform code.")],
    display_name: Annotated[str, typer.Option(help="Local account display name.")],
    adapter: Annotated[AdapterName, typer.Option(help="Platform adapter implementation.")] = AdapterName.FAKE,
    login_method: Annotated[LoginMethod, typer.Option(help="Authentication method.")] = LoginMethod.COOKIE,
    credential_ref: Annotated[
        str | None,
        typer.Option(help="Opaque credential-store reference; never a raw cookie or password."),
    ] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Emit machine-readable JSON.")] = False,
) -> None:
    """Add an account without resolving or displaying its credential reference."""

    normalized_name = _required_option(display_name, "display_name")
    normalized_credential_ref = _credential_reference(credential_ref)
    try:
        with _database_session() as session:
            result = WorkbenchService(session).create_account(
                AccountDraft(
                    platform=platform,
                    display_name=normalized_name,
                    adapter=adapter.value,
                    login_method=login_method,
                    credential_ref=normalized_credential_ref,
                )
            )
    except WorkbenchError as error:
        raise typer.BadParameter(_account_workbench_error_message(error, adapter=adapter)) from None

    _emit_record(result.to_payload(), json_output=json_output, label="Account")


@account_app.command("list")
def list_accounts(
    json_output: Annotated[bool, typer.Option("--json", help="Emit machine-readable JSON.")] = False,
) -> None:
    """List accounts without credential references or profile paths."""

    with _database_session() as session:
        records = [_account_payload(account) for account in AccountRepository(session).list()]
    _emit_list(records, json_output=json_output, label="accounts")


@account_app.command("login")
def login_account(
    account_id: Annotated[
        UUID,
        typer.Option(help="Exact local QR or expired saved-session account UUID."),
    ],
    enable_mediacrawler: Annotated[
        bool,
        typer.Option(
            "--enable-mediacrawler",
            help="Explicitly enable one headed MediaCrawler login attempt.",
        ),
    ] = False,
    accept_mediacrawler_license: Annotated[
        bool,
        typer.Option(
            "--accept-mediacrawler-license",
            help="Acknowledge the pinned non-commercial learning license for this login attempt.",
        ),
    ] = False,
    timeout_seconds: Annotated[
        float,
        typer.Option(min=0.001, max=3_600.0, help="Hard timeout before the login child is cancelled and joined."),
    ] = 180.0,
    json_output: Annotated[bool, typer.Option("--json", help="Emit machine-readable JSON.")] = False,
) -> None:
    """Run one blocking, host-assisted MediaCrawler QR login."""

    if not enable_mediacrawler:
        _emit_record(
            _account_login_error_payload(account_id, "mediacrawler_not_enabled"),
            json_output=json_output,
            label="Account login",
        )
        raise typer.Exit(code=1)
    if not accept_mediacrawler_license:
        _emit_record(
            _account_login_error_payload(account_id, "license_acknowledgement_required"),
            json_output=json_output,
            label="Account login",
        )
        raise typer.Exit(code=1)
    if not math.isfinite(timeout_seconds) or timeout_seconds <= 0 or timeout_seconds > 3_600:
        raise typer.BadParameter("timeout_seconds must be finite and between zero and 3600")

    database: Database | None = None
    try:
        settings = get_settings()
        database = Database(settings.resolved_database_url)
        if settings.mediacrawler_python_executable is None:
            login_runner: Any = _UnavailableMediaCrawlerLoginRunner()
        else:
            login_runner = _DeferredMediaCrawlerLoginRunner(settings)
        reconciler = MediaCrawlerLoginSessionReconciler(
            database,
            integration_root=settings.resolved_mediacrawler_runtime_dir,
        )
        outcome = MediaCrawlerQrLoginService(database, login_runner, reconciler=reconciler).run(
            AccountLoginRequest(
                account_id=account_id,
                timeout_seconds=timeout_seconds,
                poll_seconds=min(0.05, timeout_seconds / 2),
            )
        )
    except AccountLoginError as error:
        _emit_record(
            _account_login_error_payload(account_id, error.code),
            json_output=json_output,
            label="Account login",
        )
        raise typer.Exit(code=1) from None
    except Exception:
        _emit_record(
            _account_login_error_payload(account_id, "account_login_unexpected"),
            json_output=json_output,
            label="Account login",
        )
        raise typer.Exit(code=1) from None
    finally:
        if database is not None:
            database.dispose()

    _emit_record(
        _account_login_outcome_payload(outcome),
        json_output=json_output,
        label="Account login",
    )
    if not outcome.authenticated:
        raise typer.Exit(code=1)


@account_app.command("login-status")
def account_login_status(
    account_id: Annotated[UUID, typer.Option(help="Exact local account UUID.")],
    json_output: Annotated[bool, typer.Option("--json", help="Emit machine-readable JSON.")] = False,
) -> None:
    """Show Account auth and latest login-session state without challenge data."""

    database: Database | None = None
    try:
        settings = get_settings()
        database = Database(settings.resolved_database_url)
        MediaCrawlerLoginSessionReconciler(
            database,
            integration_root=settings.resolved_mediacrawler_runtime_dir,
        ).reconcile_account(account_id)
        with database.session() as session:
            account = AccountRepository(session).get(str(account_id))
            if account is None:
                payload = None
            else:
                sessions = LoginSessionRepository(session).list_for_account(account.id)
                payload = _account_login_status_payload(account, sessions[0] if sessions else None)
    except (RepositoryError, SQLAlchemyError):
        raise typer.BadParameter("account login status database operation failed safely") from None
    except Exception:
        raise typer.BadParameter("account login status failed safely; no unsafe details were emitted") from None
    finally:
        if database is not None:
            database.dispose()
    if payload is None:
        _emit_record(
            _account_login_error_payload(account_id, "account_login_not_found"),
            json_output=json_output,
            label="Account login status",
        )
        raise typer.Exit(code=1)
    _emit_record(payload, json_output=json_output, label="Account login status")


@subscription_app.command("add")
def add_subscription(
    account_id: Annotated[UUID, typer.Option(help="Local account UUID.")],
    platform: Annotated[Platform, typer.Option(help="Creator platform code.")],
    creator_remote_id: Annotated[str, typer.Option(help="Stable creator ID on the platform.")],
    display_name: Annotated[str, typer.Option(help="Creator display name.")],
    creator_reference_ref: Annotated[
        str | None,
        typer.Option(help="Optional secret-provider reference for a token-bearing MediaCrawler creator URL."),
    ] = None,
    interval_seconds: Annotated[int, typer.Option(min=60, help="Polling interval in seconds.")] = 21_600,
    max_items: Annotated[int, typer.Option(min=1, max=1_000, help="Maximum items per run.")] = 30,
    allow_full_history: Annotated[
        bool,
        typer.Option(help="Acknowledge MediaCrawler creator modes that can scan full history."),
    ] = False,
    request_delay_seconds: Annotated[
        float,
        typer.Option(
            min=0.001,
            max=MAX_REQUEST_DELAY_SECONDS,
            help="Positive MediaCrawler upstream crawl-delay setting; not a per-request guarantee.",
        ),
    ] = 5.0,
    headless: Annotated[
        bool,
        typer.Option("--headless/--headed", help="Run a scheduled MediaCrawler browser without visible UI."),
    ] = True,
    json_output: Annotated[bool, typer.Option("--json", help="Emit machine-readable JSON.")] = False,
) -> None:
    """Idempotently subscribe an account to one platform creator."""

    normalized_remote_id = _required_option(creator_remote_id, "creator_remote_id")
    normalized_display_name = _required_option(display_name, "display_name")
    normalized_creator_reference_ref = _credential_reference(creator_reference_ref)
    try:
        with _database_session() as session:
            result = WorkbenchService(session).create_subscription(
                SubscriptionDraft(
                    account_id=account_id,
                    platform=platform,
                    creator_remote_id=normalized_remote_id,
                    display_name=normalized_display_name,
                    creator_secret_ref=normalized_creator_reference_ref,
                    interval_seconds=interval_seconds,
                    max_items=max_items,
                    allow_full_history=allow_full_history,
                    request_delay_seconds=request_delay_seconds,
                    headless=headless,
                )
            )
    except WorkbenchError as error:
        raise typer.BadParameter(_subscription_workbench_error_message(error, account_id=account_id)) from None

    payload = result.to_payload()
    payload.pop("policy_summary", None)

    _emit_record(payload, json_output=json_output, label="Subscription")


@subscription_app.command("list")
def list_subscriptions(
    json_output: Annotated[bool, typer.Option("--json", help="Emit machine-readable JSON.")] = False,
) -> None:
    """List creator subscriptions using redaction-safe fields."""

    with _database_session() as session:
        records = [_subscription_payload(subscription) for subscription in SubscriptionRepository(session).list()]
    _emit_list(records, json_output=json_output, label="subscriptions")


@subscription_app.command("pause")
def pause_subscription(
    subscription_id: Annotated[UUID, typer.Option(help="Subscription UUID to pause.")],
    json_output: Annotated[bool, typer.Option("--json", help="Emit machine-readable JSON.")] = False,
) -> None:
    """Pause future cycle materialization without exposing subscription payload data."""

    with _scheduler_runtime() as (_database, service):
        schedule = service.pause_subscription(str(subscription_id))
    _emit_record(_scheduler_schedule_payload(schedule), json_output=json_output, label="Subscription schedule")


@subscription_app.command("resume")
def resume_subscription(
    subscription_id: Annotated[UUID, typer.Option(help="Subscription UUID to resume.")],
    json_output: Annotated[bool, typer.Option("--json", help="Emit machine-readable JSON.")] = False,
) -> None:
    """Resume future cycle materialization."""

    with _scheduler_runtime() as (_database, service):
        schedule = service.resume_subscription(str(subscription_id))
    _emit_record(_scheduler_schedule_payload(schedule), json_output=json_output, label="Subscription schedule")


@subscription_app.command("run-now")
def run_subscription_now(
    subscription_id: Annotated[UUID, typer.Option(help="Subscription UUID to make immediately due.")],
    json_output: Annotated[bool, typer.Option("--json", help="Emit machine-readable JSON.")] = False,
) -> None:
    """Make a subscription due now; this does not implicitly resume a paused subscription."""

    with _scheduler_runtime() as (_database, service):
        schedule = service.run_now(str(subscription_id))
    _emit_record(_scheduler_schedule_payload(schedule), json_output=json_output, label="Subscription schedule")


@scheduler_app.command("tick")
def scheduler_tick(
    limit: Annotated[int, typer.Option(min=1, max=1_000, help="Maximum due subscriptions to materialize.")] = 100,
    json_output: Annotated[bool, typer.Option("--json", help="Emit machine-readable JSON.")] = False,
) -> None:
    """Materialize a bounded batch of due subscription cycles."""

    with _scheduler_runtime() as (_database, service):
        result = service.tick(limit=limit)
    payload: dict[str, object] = {
        "materialized_count": result.materialized_count,
        "cycles": [_scheduler_cycle_payload(cycle) for cycle in result.cycles],
    }
    _emit_record(payload, json_output=json_output, label="Scheduler tick")


@scheduler_app.command("run")
def scheduler_run(
    max_jobs: Annotated[int, typer.Option(min=1, max=1_000, help="Maximum Jobs to execute without sleeping.")] = 1,
    global_capacity: Annotated[
        int,
        typer.Option(min=1, max=1_000, help="Maximum concurrent sync Jobs across workers."),
    ] = 1,
    lease_seconds: Annotated[
        int,
        typer.Option(min=1, max=86_400, help="Lease duration for each claimed Job."),
    ] = 60,
    scan_limit: Annotated[
        int,
        typer.Option(min=1, max=1_000, help="Maximum queued candidates scanned per claim."),
    ] = 100,
    enable_mediacrawler: Annotated[
        bool,
        typer.Option(
            "--enable-mediacrawler",
            help="Explicitly enable the external MediaCrawler handler for this bounded worker run.",
        ),
    ] = False,
    accept_mediacrawler_license: Annotated[
        bool,
        typer.Option(
            "--accept-mediacrawler-license",
            help="Acknowledge the pinned non-commercial learning license for this worker run.",
        ),
    ] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Emit machine-readable JSON.")] = False,
) -> None:
    """Run a bounded worker batch; the MediaCrawler handler remains default-off."""

    if accept_mediacrawler_license and not enable_mediacrawler:
        raise typer.BadParameter("MediaCrawler license acknowledgement requires --enable-mediacrawler")
    settings = get_settings()
    with _scheduler_runtime() as (database, _service):
        worker = _build_subscription_worker(
            database,
            settings,
            enable_mediacrawler=enable_mediacrawler,
            accept_mediacrawler_license=accept_mediacrawler_license,
        )
        results = asyncio.run(
            worker.run_bounded(
                worker_id=f"cli-{uuid4()}",
                max_jobs=max_jobs,
                global_capacity=global_capacity,
                lease_seconds=lease_seconds,
                scan_limit=scan_limit,
            )
        )
    _emit_list(
        [_scheduler_worker_payload(result) for result in results],
        json_output=json_output,
        label="scheduler worker results",
    )


@scheduler_app.command("supervise")
def scheduler_supervise(
    idle_interval_seconds: Annotated[
        float,
        typer.Option(min=0.001, max=3_600.0, help="Idle wait before the next fair resident cycle."),
    ] = 1.0,
    login_sweep_limit: Annotated[
        int,
        typer.Option(min=1, max=1_000, help="Maximum expired login candidates inspected per cycle."),
    ] = 100,
    materialize_limit: Annotated[
        int,
        typer.Option(min=1, max=1_000, help="Maximum due subscriptions materialized per cycle."),
    ] = 100,
    subscription_jobs_per_cycle: Annotated[
        int,
        typer.Option(min=1, max=1_000, help="Maximum sync attempts before yielding to pipeline work."),
    ] = 1,
    pipeline_jobs_per_cycle: Annotated[
        int,
        typer.Option(min=1, max=1_000, help="Maximum pipeline attempts before the next scheduler cycle."),
    ] = 1,
    global_capacity: Annotated[
        int,
        typer.Option(min=1, max=1_000, help="Maximum concurrent sync Jobs across local workers."),
    ] = 1,
    subscription_lease_seconds: Annotated[
        int,
        typer.Option(min=1, max=86_400, help="Lease duration for each subscription sync attempt."),
    ] = 60,
    subscription_scan_limit: Annotated[
        int,
        typer.Option(min=1, max=1_000, help="Maximum subscription Job candidates scanned per claim."),
    ] = 100,
    subscription_heartbeat_interval_seconds: Annotated[
        float | None,
        typer.Option(min=0.001, help="Optional sync heartbeat interval shorter than its lease."),
    ] = None,
    pipeline_lease_seconds: Annotated[
        int,
        typer.Option(min=1, max=86_400, help="Lease duration for one complete pipeline attempt."),
    ] = 3_600,
    pipeline_scan_limit: Annotated[
        int,
        typer.Option(min=1, max=1_000, help="Maximum pipeline Job candidates scanned per claim."),
    ] = 100,
    pipeline_heartbeat_interval_seconds: Annotated[
        float | None,
        typer.Option(min=0.001, help="Optional pipeline heartbeat interval shorter than its lease."),
    ] = None,
    pipeline_retry_delay_seconds: Annotated[
        int,
        typer.Option(min=1, max=86_400, help="Delay before retrying a retryable pipeline failure."),
    ] = 30,
    enable_mediacrawler: Annotated[
        bool,
        typer.Option(
            "--enable-mediacrawler",
            help="Enable MediaCrawler sync and signed-locator refresh for this resident process.",
        ),
    ] = False,
    accept_mediacrawler_license: Annotated[
        bool,
        typer.Option(
            "--accept-mediacrawler-license",
            help="Acknowledge the pinned non-commercial learning license for this resident process.",
        ),
    ] = False,
    xhs_detail_reference_ref: Annotated[
        str | None,
        typer.Option(help="Optional ephemeral secret reference for one XHS signed detail authority."),
    ] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Emit one fixed summary after shutdown.")] = False,
) -> None:
    """Run the local scheduler, sync and pipeline chain until cooperatively stopped."""

    if accept_mediacrawler_license and not enable_mediacrawler:
        raise typer.BadParameter("MediaCrawler license acknowledgement requires --enable-mediacrawler")
    if xhs_detail_reference_ref is not None and not enable_mediacrawler:
        raise typer.BadParameter("XHS detail reference requires --enable-mediacrawler")
    for heartbeat, lease, label in (
        (
            subscription_heartbeat_interval_seconds,
            subscription_lease_seconds,
            "subscription heartbeat interval",
        ),
        (pipeline_heartbeat_interval_seconds, pipeline_lease_seconds, "pipeline heartbeat interval"),
    ):
        if heartbeat is not None and (not math.isfinite(heartbeat) or heartbeat <= 0 or heartbeat >= lease):
            raise typer.BadParameter(f"{label} must be finite, positive, and shorter than its lease")

    normalized_xhs_reference = _credential_reference(xhs_detail_reference_ref)
    database: Database | None = None
    try:
        settings = get_settings()
        database = Database(settings.resolved_database_url)
        run_identity = f"resident-{uuid4()}"
        subscription_worker_id = f"{run_identity}:sync"
        pipeline_worker_id = f"{run_identity}:pipeline"
        subscription_worker = _build_subscription_worker(
            database,
            settings,
            enable_mediacrawler=enable_mediacrawler,
            accept_mediacrawler_license=accept_mediacrawler_license,
        )
        pipeline_worker = _build_pipeline_worker(
            database,
            settings,
            worker_id=pipeline_worker_id,
            retry_delay_seconds=pipeline_retry_delay_seconds,
            enable_mediacrawler=enable_mediacrawler,
            accept_mediacrawler_license=accept_mediacrawler_license,
            xhs_detail_reference_ref=normalized_xhs_reference,
        )
        reconciler = MediaCrawlerLoginSessionReconciler(
            database,
            integration_root=settings.resolved_mediacrawler_runtime_dir,
        )
        supervisor = ResidentSchedulerSupervisor(
            stale_login_sweep=reconciler.sweep,
            scheduler=DurableSchedulerService(database),
            subscription_worker=subscription_worker,
            pipeline_worker=pipeline_worker,
            subscription_worker_id=subscription_worker_id,
            pipeline_worker_id=pipeline_worker_id,
            config=ResidentSupervisorConfig(
                idle_interval_seconds=idle_interval_seconds,
                login_sweep_limit=login_sweep_limit,
                materialize_limit=materialize_limit,
                subscription_jobs_per_cycle=subscription_jobs_per_cycle,
                pipeline_jobs_per_cycle=pipeline_jobs_per_cycle,
                subscription_global_capacity=global_capacity,
                subscription_lease_seconds=subscription_lease_seconds,
                subscription_scan_limit=subscription_scan_limit,
                subscription_heartbeat_interval_seconds=subscription_heartbeat_interval_seconds,
                pipeline_lease_seconds=pipeline_lease_seconds,
                pipeline_scan_limit=pipeline_scan_limit,
                pipeline_heartbeat_interval_seconds=pipeline_heartbeat_interval_seconds,
            ),
        )
        result = asyncio.run(_run_resident_supervisor(supervisor))
    except (RepositoryError, SchedulerRepositoryError, SQLAlchemyError):
        raise typer.BadParameter("resident supervisor database operation failed safely") from None
    except (TypeError, ValueError):
        raise typer.BadParameter("resident supervisor arguments or durable state were rejected") from None
    except Exception:
        raise typer.BadParameter("resident supervisor failed safely; no unsafe details were emitted") from None
    finally:
        if database is not None:
            database.dispose()

    _emit_record(
        _resident_supervisor_payload(result),
        json_output=json_output,
        label="Scheduler supervisor",
    )


@pipeline_app.command("run")
def pipeline_run(
    max_jobs: Annotated[
        int,
        typer.Option(min=1, max=1_000, help="Maximum coordinator Jobs to execute without sleeping."),
    ] = 1,
    worker_id: Annotated[
        str,
        typer.Option(help="Stable local coordinator worker label; lease tokens fence attempts."),
    ] = "cli-pipeline-worker",
    lease_seconds: Annotated[
        int,
        typer.Option(min=1, max=86_400, help="Coordinator lease duration for the complete pipeline."),
    ] = 3_600,
    scan_limit: Annotated[
        int,
        typer.Option(min=1, max=1_000, help="Maximum queued coordinator rows inspected per claim."),
    ] = 100,
    heartbeat_interval_seconds: Annotated[
        float | None,
        typer.Option(
            min=0.001,
            help="Optional coordinator lease heartbeat interval; must be shorter than the lease.",
        ),
    ] = None,
    retry_delay_seconds: Annotated[
        int,
        typer.Option(min=1, max=86_400, help="Delay before retrying a retryable coordinator failure."),
    ] = 30,
    enable_mediacrawler: Annotated[
        bool,
        typer.Option(
            "--enable-mediacrawler",
            help="Explicitly enable MediaCrawler signed-locator refresh for pipeline downloads.",
        ),
    ] = False,
    accept_mediacrawler_license: Annotated[
        bool,
        typer.Option(
            "--accept-mediacrawler-license",
            help="Acknowledge the pinned non-commercial learning license for this worker run.",
        ),
    ] = False,
    xhs_detail_reference_ref: Annotated[
        str | None,
        typer.Option(
            help="Optional ephemeral secret reference for a single XHS note detail URL with xsec authority.",
        ),
    ] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Emit machine-readable JSON.")] = False,
) -> None:
    """Run queued sync-success coordinators through download and Emby export."""

    if accept_mediacrawler_license and not enable_mediacrawler:
        raise typer.BadParameter("MediaCrawler license acknowledgement requires --enable-mediacrawler")
    if xhs_detail_reference_ref is not None and not enable_mediacrawler:
        raise typer.BadParameter("XHS detail reference requires --enable-mediacrawler")
    if heartbeat_interval_seconds is not None and (
        not math.isfinite(heartbeat_interval_seconds)
        or heartbeat_interval_seconds <= 0
        or heartbeat_interval_seconds >= lease_seconds
    ):
        raise typer.BadParameter("heartbeat interval must be finite, positive, and shorter than the lease")
    normalized_worker_id = _required_option(worker_id, "worker_id")
    normalized_xhs_reference = _credential_reference(xhs_detail_reference_ref)
    settings = get_settings()
    database = Database(settings.resolved_database_url)
    try:
        worker = _build_pipeline_worker(
            database,
            settings,
            worker_id=normalized_worker_id,
            retry_delay_seconds=retry_delay_seconds,
            enable_mediacrawler=enable_mediacrawler,
            accept_mediacrawler_license=accept_mediacrawler_license,
            xhs_detail_reference_ref=normalized_xhs_reference,
        )
        results = asyncio.run(
            worker.run_bounded(
                worker_id=normalized_worker_id,
                max_jobs=max_jobs,
                lease_seconds=lease_seconds,
                scan_limit=scan_limit,
                heartbeat_interval_seconds=heartbeat_interval_seconds,
            )
        )
    except SQLAlchemyError:
        raise typer.BadParameter("pipeline database operation failed safely") from None
    finally:
        database.dispose()

    _emit_list(
        [_pipeline_worker_payload(result) for result in results],
        json_output=json_output,
        label="pipeline worker results",
    )


@scheduler_job_app.command("list")
def list_scheduler_jobs(
    status: Annotated[JobStatus | None, typer.Option(help="Optional scheduler Job status filter.")] = None,
    subscription_id: Annotated[UUID | None, typer.Option(help="Optional subscription UUID filter.")] = None,
    limit: Annotated[int, typer.Option(min=1, max=1_000, help="Maximum Jobs returned.")] = 100,
    json_output: Annotated[bool, typer.Option("--json", help="Emit machine-readable JSON.")] = False,
) -> None:
    """List only the redaction-safe projection of sync.subscription Jobs."""

    with _scheduler_runtime() as (_database, service):
        jobs = service.list_jobs(
            status=status.value if status is not None else None,
            subscription_id=str(subscription_id) if subscription_id is not None else None,
            limit=limit,
        )
    _emit_list(
        [_scheduler_job_payload(job) for job in jobs],
        json_output=json_output,
        label="scheduler Jobs",
    )


@scheduler_job_app.command("resume")
def resume_scheduler_job(
    job_id: Annotated[UUID, typer.Option(help="Waiting scheduler Job UUID to resume.")],
    json_output: Annotated[bool, typer.Option("--json", help="Emit machine-readable JSON.")] = False,
) -> None:
    """Explicitly resume one waiting_auth or waiting_user Job."""

    with _scheduler_runtime() as (_database, service):
        job = service.resume_job(str(job_id))
    _emit_record(_scheduler_job_payload(job), json_output=json_output, label="Scheduler Job")


@scheduler_job_app.command("cancel")
def cancel_scheduler_job(
    job_id: Annotated[UUID, typer.Option(help="Scheduler Job UUID to cancel.")],
    json_output: Annotated[bool, typer.Option("--json", help="Emit machine-readable JSON.")] = False,
) -> None:
    """Cancel one scheduler-owned sync.subscription Job."""

    with _scheduler_runtime() as (_database, service):
        job = service.cancel_job(str(job_id))
    _emit_record(_scheduler_job_payload(job), json_output=json_output, label="Scheduler Job")


@scheduler_lane_app.command("list")
def list_scheduler_lanes(
    scope: Annotated[SchedulerLaneScope | None, typer.Option("--scope", help="Optional lane scope filter.")] = None,
    platform: Annotated[Platform | None, typer.Option(help="Optional platform filter.")] = None,
    account_id: Annotated[UUID | None, typer.Option(help="Optional account UUID filter.")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Emit machine-readable JSON.")] = False,
) -> None:
    """List persistent platform/account lane policy and circuit state."""

    if scope is SchedulerLaneScope.PLATFORM and account_id is not None:
        raise typer.BadParameter("platform lane filters cannot include account_id")
    with _scheduler_runtime() as (_database, service):
        lanes = service.list_lanes()
    if scope is not None:
        scope_value = _lane_scope(scope)
        lanes = [lane for lane in lanes if lane.policy.scope_type == scope_value]
    if platform is not None:
        lanes = [lane for lane in lanes if lane.policy.platform == platform.value]
    if account_id is not None:
        normalized_account_id = str(account_id)
        lanes = [lane for lane in lanes if lane.policy.account_id == normalized_account_id]
    _emit_list(
        [_scheduler_lane_payload(lane) for lane in lanes],
        json_output=json_output,
        label="scheduler lanes",
    )


@scheduler_lane_app.command("set")
def set_scheduler_lane(
    scope: Annotated[SchedulerLaneScope, typer.Option("--scope", help="Lane scope.")],
    platform: Annotated[Platform, typer.Option(help="Lane platform.")],
    account_id: Annotated[UUID | None, typer.Option(help="Required only for account lanes.")] = None,
    max_concurrency: Annotated[int, typer.Option(min=1, max=1_000, help="Lane concurrency limit.")] = 1,
    min_start_interval_seconds: Annotated[
        int,
        typer.Option(min=0, max=604_800, help="Minimum interval between Job starts."),
    ] = 5,
    failure_threshold: Annotated[
        int,
        typer.Option(min=1, max=2_147_483_647, help="Failures before the circuit opens."),
    ] = 3,
    cooldown_seconds: Annotated[
        int,
        typer.Option(min=1, max=604_800, help="Open-circuit cooldown."),
    ] = 900,
    expected_revision: Annotated[
        int | None,
        typer.Option(min=0, max=2_147_483_647, help="Optional compare-and-swap revision."),
    ] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Emit machine-readable JSON.")] = False,
) -> None:
    """Create or update one bounded lane policy, optionally using revision CAS."""

    with _scheduler_runtime() as (_database, service):
        policy = LanePolicy(
            scope_type=_lane_scope(scope),
            platform=platform.value,
            account_id=str(account_id) if account_id is not None else None,
            max_concurrency=max_concurrency,
            min_start_interval_seconds=min_start_interval_seconds,
            failure_threshold=failure_threshold,
            cooldown_seconds=cooldown_seconds,
        )
        lane = service.update_lane(policy, expected_revision=expected_revision)
    _emit_record(_scheduler_lane_payload(lane), json_output=json_output, label="Scheduler lane")


@scheduler_lane_app.command("reset")
def reset_scheduler_lane(
    scope: Annotated[SchedulerLaneScope, typer.Option("--scope", help="Lane scope.")],
    platform: Annotated[Platform, typer.Option(help="Lane platform.")],
    account_id: Annotated[UUID | None, typer.Option(help="Required only for account lanes.")] = None,
    expected_revision: Annotated[
        int | None,
        typer.Option(min=0, max=2_147_483_647, help="Optional compare-and-swap revision."),
    ] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Emit machine-readable JSON.")] = False,
) -> None:
    """Reset one lane circuit using an optional revision compare-and-swap."""

    with _scheduler_runtime() as (_database, service):
        lane = service.reset_lane(
            scope_type=_lane_scope(scope),
            platform=platform.value,
            account_id=str(account_id) if account_id is not None else None,
            expected_revision=expected_revision,
        )
    _emit_record(_scheduler_lane_payload(lane), json_output=json_output, label="Scheduler lane")


@asset_app.command("list")
def list_assets(
    author_id: Annotated[
        UUID | None,
        typer.Option(help="Limit results to one local author UUID."),
    ] = None,
    status: Annotated[
        AssetStatus | None,
        typer.Option(help="Limit results to one asset lifecycle status."),
    ] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Emit machine-readable JSON.")] = False,
) -> None:
    """List stable asset IDs without locators, source URLs, paths or raw metadata."""

    with _database_session() as session:
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
        )
        records = [
            _asset_payload(asset, author_id=row_author_id) for asset, row_author_id in session.execute(statement).all()
        ]
    _emit_list(records, json_output=json_output, label="assets")


def _execute_asset_download(
    *,
    asset_id: UUID,
    worker_id: str,
    lease_seconds: int,
    max_attempts: int,
    enable_mediacrawler: bool,
    accept_mediacrawler_license: bool,
    subscription_id: UUID | None,
    xhs_detail_reference_ref: str | None,
    settings: Settings,
    database: Database,
    subject_hook: DurableSubjectHook | None = None,
) -> tuple[dict[str, object], bool]:
    """Run one gated asset download and return its redaction-safe payload plus ok flag.

    Shared by the CLI command and the execution 0040 REST API so both drive the
    identical preflight gates and the identical download service. Database
    errors propagate to the caller; every blocked/failed outcome returns.
    """

    def blocked(code: str, *, retryable: bool, persisted_status: object) -> dict[str, object]:
        return {
            "asset_id": str(asset_id),
            "status": "blocked",
            "disposition": "not_started",
            "persisted_status": persisted_status,
            "error_code": code,
            "retryable": retryable,
        }

    with database.session() as session:
        asset_preflight = session.execute(
            select(Asset.status, Asset.kind, Asset.locator, Asset.platform).where(Asset.id == str(asset_id))
        ).one_or_none()
    asset_status = asset_preflight[0] if asset_preflight is not None else None
    asset_kind = asset_preflight[1] if asset_preflight is not None else None
    asset_locator = asset_preflight[2] if asset_preflight is not None else None
    asset_platform = asset_preflight[3] if asset_preflight is not None else None
    if xhs_detail_reference_ref is not None and asset_platform is not None and asset_platform != Platform.XHS.value:
        raise ValueError("XHS detail reference is available only for XHS assets")
    requires_download = asset_status not in {
        None,
        AssetStatus.VERIFIED.value,
        AssetStatus.FAILED_TERMINAL.value,
    }
    adapter_refresh = isinstance(asset_locator, Mapping) and asset_locator.get("type") == "adapter_refresh"
    adapter_name = asset_locator.get("adapter") if isinstance(asset_locator, Mapping) else None
    mediacrawler_refresh = adapter_refresh and adapter_name == AdapterName.MEDIACRAWLER.value
    if requires_download and adapter_refresh and not enable_mediacrawler:
        return blocked("locator_refresh_unsupported", retryable=True, persisted_status=asset_status), False
    if requires_download and adapter_refresh and not mediacrawler_refresh:
        return blocked("locator_refresh_unsupported", retryable=True, persisted_status=asset_status), False
    if requires_download and mediacrawler_refresh and not accept_mediacrawler_license:
        return blocked("license_acknowledgement_required", retryable=False, persisted_status=asset_status), False
    if requires_download and mediacrawler_refresh and settings.mediacrawler_python_executable is None:
        return blocked("locator_refresh_configuration_invalid", retryable=False, persisted_status=asset_status), False
    ffprobe = shutil.which("ffprobe")
    if requires_download and asset_kind in {"video", "audio"} and ffprobe is None:
        return blocked("media_probe_unavailable", retryable=True, persisted_status=asset_status), False
    ffmpeg = shutil.which("ffmpeg")
    requires_bilibili_mux = (
        requires_download and asset_platform == Platform.BILI.value and asset_kind == "video" and mediacrawler_refresh
    )
    if requires_bilibili_mux and ffmpeg is None:
        return blocked("media_mux_unavailable", retryable=True, persisted_status=asset_status), False

    limits = DownloadLimits()
    refresher = None
    verified_archive_recovery_preflight: Callable[[], None] | None = None
    if mediacrawler_refresh and enable_mediacrawler and accept_mediacrawler_license:
        refresher = LazyMediaCrawlerLocatorRefresher(
            database,
            asset_id=asset_id,
            subscription_id=subscription_id,
            lock_path=settings.mediacrawler_lock_path,
            integration_root=settings.resolved_mediacrawler_runtime_dir,
            python_executable=settings.mediacrawler_python_executable,
            secret_resolver=SecretResolver.local(file_root=settings.resolved_secret_file_dir),
            license_acknowledged=True,
            detail_reference_ref=(xhs_detail_reference_ref if asset_platform == Platform.XHS.value else None),
        )
        if requires_download and asset_platform == Platform.XHS.value:
            refresher.preflight()
    if mediacrawler_refresh and asset_platform == Platform.XHS.value:
        if refresher is not None:
            verified_archive_recovery_preflight = refresher.preflight
        else:

            def unavailable_xhs_recovery_preflight() -> None:
                code = (
                    "locator_refresh_unsupported"
                    if not enable_mediacrawler
                    else "locator_refresh_configuration_invalid"
                )
                raise MediaDownloadError(code)

            verified_archive_recovery_preflight = unavailable_xhs_recovery_preflight
    http = SafeHttpClient(
        SocketAddressResolver(),
        limits=NetworkLimits(timeout_seconds=min(limits.total_timeout_seconds, 120.0)),
    )
    probe = FFprobeMediaProbe(ffprobe) if ffprobe is not None else None
    muxer = FFmpegStreamCopyMuxer(ffmpeg) if ffmpeg is not None else None
    if refresher is None:
        downloader = SecureMediaDownloader(http, probe=probe, muxer=muxer, limits=limits)
    else:
        downloader = SecureMediaDownloader(http, refresher=refresher, probe=probe, muxer=muxer, limits=limits)
    try:
        outcome = AssetDownloadService(
            database,
            downloader,
            verified_archive_recovery_preflight=verified_archive_recovery_preflight,
        ).run(
            AssetDownloadRequest(
                asset_id=asset_id,
                worker_id=worker_id,
                work_root=settings.job_dir / "downloads",
                archive_root=settings.archive_dir,
                lease_seconds=lease_seconds,
                max_attempts=max_attempts,
            ),
            subject_hook=subject_hook,
        )
    except AssetDownloadOrchestrationError as error:
        return {
            "asset_id": str(asset_id),
            "status": "failed",
            "error_code": error.code,
            "retryable": error.retryable,
        }, False
    except MediaDownloadError as error:
        return blocked(error.code, retryable=error.retryable, persisted_status=asset_status), False
    return {
        "asset_id": str(outcome.asset_id),
        "generation": outcome.generation,
        "job_id": str(outcome.job_id) if outcome.job_id is not None else None,
        "status": outcome.status.value,
        "disposition": outcome.disposition,
        "archive_path": str(outcome.archive_path),
        "checksum_sha256": outcome.checksum_sha256,
        "size_bytes": outcome.size_bytes,
        "mime_type": outcome.mime_type,
    }, True


@asset_app.command("download")
def download_asset(
    asset_id: Annotated[UUID, typer.Option(help="Local asset UUID to download.")],
    worker_id: Annotated[
        str,
        typer.Option(help="Stable local worker label; lease tokens still fence every attempt."),
    ] = "cli-worker",
    lease_seconds: Annotated[
        int,
        typer.Option(min=1, max=86_400, help="Download job lease duration in seconds."),
    ] = 3_600,
    max_attempts: Annotated[
        int,
        typer.Option(min=1, max=100, help="Maximum attempts for this asset generation."),
    ] = 5,
    enable_mediacrawler: Annotated[
        bool,
        typer.Option(
            "--enable-mediacrawler",
            help="Explicitly enable MediaCrawler signed-locator refresh for this download.",
        ),
    ] = False,
    accept_mediacrawler_license: Annotated[
        bool,
        typer.Option(
            "--accept-mediacrawler-license",
            help="Acknowledge the pinned non-commercial learning license for this download.",
        ),
    ] = False,
    subscription_id: Annotated[
        UUID | None,
        typer.Option(help="Select one eligible subscription when an asset has multiple refresh sources."),
    ] = None,
    xhs_detail_reference_ref: Annotated[
        str | None,
        typer.Option(
            help="Ephemeral secret-provider reference to this XHS note URL with xsec_token/xsec_source.",
        ),
    ] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Emit machine-readable JSON.")] = False,
) -> None:
    """Download one asset; ffprobe is required for media and ffmpeg for Bilibili DASH."""

    if accept_mediacrawler_license and not enable_mediacrawler:
        raise typer.BadParameter("MediaCrawler license acknowledgement requires --enable-mediacrawler")
    if xhs_detail_reference_ref is not None and not enable_mediacrawler:
        raise typer.BadParameter("XHS detail reference requires --enable-mediacrawler")
    normalized_detail_reference_ref = _credential_reference(xhs_detail_reference_ref)
    settings = get_settings()
    database = Database(settings.resolved_database_url)
    try:
        payload, ok = _execute_asset_download(
            asset_id=asset_id,
            worker_id=worker_id,
            lease_seconds=lease_seconds,
            max_attempts=max_attempts,
            enable_mediacrawler=enable_mediacrawler,
            accept_mediacrawler_license=accept_mediacrawler_license,
            subscription_id=subscription_id,
            xhs_detail_reference_ref=normalized_detail_reference_ref,
            settings=settings,
            database=database,
        )
    except ValueError as error:
        raise typer.BadParameter(str(error)) from None
    except SQLAlchemyError:
        raise typer.BadParameter("asset download database operation failed safely") from None
    finally:
        database.dispose()

    _emit_record(payload, json_output=json_output, label="Asset download")
    if not ok:
        raise typer.Exit(code=1)


@emby_app.command("export")
def export_emby_author(
    author_id: Annotated[UUID, typer.Option(help="Local author UUID to export.")],
    worker_id: Annotated[
        str,
        typer.Option(help="Stable local worker label; lease tokens fence every attempt."),
    ] = "cli-worker",
    lease_seconds: Annotated[
        int,
        typer.Option(min=1, max=86_400, help="Export job lease duration in seconds."),
    ] = 300,
    max_attempts: Annotated[
        int,
        typer.Option(min=1, max=100, help="Maximum attempts for this author snapshot."),
    ] = 5,
    json_output: Annotated[bool, typer.Option("--json", help="Emit machine-readable JSON.")] = False,
) -> None:
    """Publish one complete verified author snapshot to the Emby/Jellyfin tree."""

    settings = get_settings()
    database = Database(settings.resolved_database_url)
    try:
        outcome = EmbyExportService(
            database,
            EmbyExporter(
                settings.export_dir,
                staging_root=settings.job_dir / "emby-export",
            ),
        ).export_author(
            EmbyExportRequest(
                author_id=str(author_id),
                worker_id=_required_option(worker_id, "worker_id"),
                lease_seconds=lease_seconds,
                max_attempts=max_attempts,
            )
        )
    except ExportError as error:
        _emit_record(
            {
                "author_id": str(author_id),
                "status": "failed",
                "error_code": error.code,
                "retryable": export_error_is_retryable(error.code),
            },
            json_output=json_output,
            label="Emby export",
        )
        raise typer.Exit(code=1) from None
    except SQLAlchemyError:
        _emit_record(
            {
                "author_id": str(author_id),
                "status": "failed",
                "error_code": "export_database_failed",
                "retryable": True,
            },
            json_output=json_output,
            label="Emby export",
        )
        raise typer.Exit(code=1) from None
    finally:
        database.dispose()

    _emit_record(
        {
            "author_id": str(author_id),
            "job_id": outcome.job_id,
            "status": "succeeded",
            "disposition": "already_exported" if outcome.already_exported else "exported",
            "output_path": outcome.output_path,
            "source_fingerprint": outcome.source_fingerprint,
            "rendered_fingerprint": outcome.rendered_fingerprint,
            "managed_file_count": outcome.managed_file_count,
        },
        json_output=json_output,
        label="Emby export",
    )


def _mark_ingest_failure(database: Database, run_id: str, error_code: str) -> None:
    """Best-effort fixed failure transition that never carries exception text."""

    try:
        with database.session() as session:
            repository = SyncRunRepository(session)
            run = repository.require(run_id)
            if run.status == RunStatus.INGESTING.value:
                repository.set_status(
                    run_id,
                    RunStatus.FAILED_RETRYABLE.value,
                    expected_status=RunStatus.INGESTING.value,
                    error_code=error_code,
                    error_message=None,
                )
    except (RepositoryError, SQLAlchemyError):
        return


@sync_app.command("ingest")
def ingest_mediacrawler_output(
    subscription_id: Annotated[UUID, typer.Option(help="MediaCrawler subscription UUID.")],
    job_id: Annotated[UUID, typer.Option(help="Canonical bridge job UUID.")],
    expected_revision: Annotated[
        int,
        typer.Option(min=0, help="Checkpoint revision captured before the crawler started."),
    ],
    mode: Annotated[IngestionMode, typer.Option(help="Forward scan or historical backfill.")] = IngestionMode.FORWARD,
    batch_size: Annotated[int, typer.Option(min=1, max=1_000)] = 100,
    json_output: Annotated[bool, typer.Option("--json", help="Emit machine-readable JSON.")] = False,
) -> None:
    """Validate and ingest one canonical bridge output using fresh transactions per batch."""

    settings = get_settings()
    database: Database | None = None
    run_id: str | None = None
    try:
        database = Database(settings.resolved_database_url)
        with database.session() as session:
            subscription = SubscriptionRepository(session).get(str(subscription_id))
            if subscription is None:
                raise typer.BadParameter("subscription was not found")
            account = subscription.account
            author = subscription.author
            if account.adapter != AdapterName.MEDIACRAWLER.value:
                raise typer.BadParameter("sync ingest requires a MediaCrawler account")
            if account.login_method is None:
                raise typer.BadParameter("stored MediaCrawler account identity is invalid")
            try:
                platform = Platform(account.platform)
                login_method = LoginMethod(account.login_method)
                account_id = UUID(account.id)
            except (TypeError, ValueError):
                raise typer.BadParameter("stored MediaCrawler account identity is invalid") from None
            cursor_before = dict(subscription.cursor) if subscription.cursor is not None else None
            creator_remote_id = author.remote_id
            creator_display_name = author.display_name
            subscription_max_items = subscription.max_items
            subscription_policy = dict(subscription.policy)

        try:
            expected_creator_fingerprint = _expected_mediacrawler_creator_fingerprint(
                settings,
                platform=platform,
                creator_remote_id=creator_remote_id,
                policy=subscription_policy,
            )
            paths = build_run_paths(
                settings.resolved_mediacrawler_runtime_dir,
                platform,
                account_id,
                job_id,
            )
            manifest = RunnerManifest.load(paths.manifest_path)
            expected_author_fingerprint = hashlib.sha256(creator_remote_id.encode("utf-8")).hexdigest()
            if (
                manifest.account_id != account_id
                or manifest.subscription_id != subscription_id
                or manifest.job_id != job_id
                or manifest.checkpoint_revision_before > expected_revision
                or manifest.intended_mode.value != mode.value
                or manifest.platform is not platform
                or manifest.login_method is not login_method
                or manifest.max_items != subscription_max_items
                or not hmac.compare_digest(
                    manifest.author_remote_id_fingerprint_sha256,
                    expected_author_fingerprint,
                )
                or not hmac.compare_digest(
                    manifest.creator_fingerprint_sha256,
                    expected_creator_fingerprint,
                )
                or manifest.integration_root != settings.resolved_mediacrawler_runtime_dir
                or manifest.lock_path != settings.mediacrawler_lock_path.expanduser().resolve()
            ):
                raise MediaCrawlerPolicyError("runner manifest does not belong to the subscription")
            verify_manifest_checkout(manifest)
            normalized_output = load_normalized_output(
                manifest,
                creator_remote_id=creator_remote_id,
                creator_display_name=creator_display_name,
                ingested_at=datetime.now(UTC),
            )
            output_fingerprint = normalized_output.output_fingerprint_sha256
            normalized_records = normalized_output.records
            quarantined_count = 0
            truncated_tail = False
        except (OSError, ValueError, CheckoutValidationError):
            raise typer.BadParameter("MediaCrawler output validation was rejected") from None

        with database.session() as session:
            run_repository = SyncRunRepository(session)
            run = run_repository.create(
                subscription_id=str(subscription_id),
                cursor_before=cursor_before,
                checkpoint_revision_before=expected_revision,
                manifest={
                    "adapter": AdapterName.MEDIACRAWLER.value,
                    "platform": platform.value,
                    "upstream_sha": manifest.upstream_sha,
                    "job_id": str(job_id),
                    "mode": mode.value,
                    "crawl_revision_before": manifest.checkpoint_revision_before,
                    "output_fingerprint_sha256": output_fingerprint,
                },
            )
            run_id = run.id
            run_repository.set_status(
                run.id,
                RunStatus.CLAIMED.value,
                expected_status=RunStatus.QUEUED.value,
            )
            run_repository.set_status(
                run.id,
                RunStatus.RUNNING.value,
                expected_status=RunStatus.CLAIMED.value,
            )
            run_repository.set_status(
                run.id,
                RunStatus.INGESTING.value,
                expected_status=RunStatus.RUNNING.value,
            )

        assert run_id is not None  # created and committed in the preceding short transaction
        try:
            result = MediaCrawlerIngestionService(database, batch_size=batch_size).ingest(
                normalized_records,
                subscription_id=subscription_id,
                run_id=run_id,
                expected_revision=expected_revision,
                crawl_revision_before=manifest.checkpoint_revision_before,
                mode=mode,
            )
        except StaleCheckpointError:
            _mark_ingest_failure(database, run_id, "checkpoint_conflict")
            failure_payload: dict[str, object] = {
                "run_id": run_id,
                "status": RunStatus.FAILED_RETRYABLE.value,
                "error_code": "checkpoint_conflict",
            }
            _emit_record(failure_payload, json_output=json_output, label="MediaCrawler ingest")
            raise typer.Exit(code=1) from None
        except (RepositoryError, SQLAlchemyError):
            _mark_ingest_failure(database, run_id, "ingestion_failed")
            raise typer.BadParameter("MediaCrawler ingestion failed safely") from None

        payload: dict[str, object] = {
            "run_id": run_id,
            "subscription_id": str(subscription_id),
            "status": RunStatus.SUCCEEDED.value,
            "mode": mode.value,
            "input_count": result.input_count,
            "accepted_count": result.accepted_count,
            "skipped_count": result.skipped_count,
            "discovered_count": result.discovered_count,
            "asset_count": result.asset_count,
            "quarantined_count": quarantined_count,
            "truncated_tail": truncated_tail,
            "committed_batches": result.committed_batches,
            "checkpoint_revision": result.checkpoint_revision,
        }
    except (RepositoryError, SQLAlchemyError):
        if database is not None and run_id is not None:
            _mark_ingest_failure(database, run_id, "ingestion_failed")
        raise typer.BadParameter("MediaCrawler ingestion failed safely") from None
    finally:
        if database is not None:
            database.dispose()

    _emit_record(payload, json_output=json_output, label="MediaCrawler ingest")


@sync_app.command("run")
def run_sync(
    subscription_id: Annotated[UUID, typer.Option(help="Subscription UUID to synchronize.")],
    json_output: Annotated[bool, typer.Option("--json", help="Emit machine-readable JSON.")] = False,
) -> None:
    """Run one deterministic synchronization for an existing subscription."""

    with _database_session() as session:
        subscription = SubscriptionRepository(session).get(str(subscription_id))
        if subscription is None:
            raise typer.BadParameter(f"subscription not found: {subscription_id}")
        account = subscription.account
        if account.adapter != "fake":
            raise typer.BadParameter("sync run currently supports only accounts using the fake adapter")
        if account.login_method is None:
            raise typer.BadParameter("account has no login method")
        try:
            platform = Platform(account.platform)
            login_method = LoginMethod(account.login_method)
            account_uuid = UUID(account.id)
        except ValueError:
            raise typer.BadParameter("stored account has an unsupported platform, login method, or UUID") from None

        account_reference = AccountRef(
            account_id=account_uuid,
            platform=platform,
            login_method=login_method,
            adapter=account.adapter,
            credential_ref=account.credential_ref,
        )
        request = SyncRequest(
            subscription_id=subscription_id,
            account=account_reference,
            creator_reference=subscription.author.remote_id,
            cursor=_stored_cursor(subscription),
            max_items=subscription.max_items,
            page_size=min(subscription.max_items, 30),
        )
        result = asyncio.run(
            SyncService(
                FakePlatformAdapter(platform),
                SQLAlchemySyncRepository(session),
            ).run(request)
        )
        payload: dict[str, object] = {
            "run_id": str(result.run_id),
            "subscription_id": str(subscription_id),
            "status": result.status.value,
            "processed_count": result.processed_count,
            "asset_count": result.asset_count,
            "watermark": _iso_datetime(result.watermark),
            "error_code": result.error_code,
            "retry_after_seconds": result.retry_after_seconds,
        }

    _emit_record(payload, json_output=json_output, label="Sync run")
    if result.status is not RunStatus.SUCCEEDED:
        raise typer.Exit(code=2 if result.status is RunStatus.AWAITING_AUTH else 1)


@app.command("serve")
def serve_api(
    host: Annotated[
        str | None,
        typer.Option(help="Bind address override; defaults to MEDIA_SYNC_API_HOST (127.0.0.1)."),
    ] = None,
    port: Annotated[
        int | None,
        typer.Option(min=1, max=65_535, help="Port override; defaults to MEDIA_SYNC_API_PORT (8632)."),
    ] = None,
) -> None:
    """Serve the local REST API and embedded web console (no authentication)."""

    settings = get_settings()
    resolved_host = host or settings.api_host
    resolved_port = port or settings.api_port
    if not resolved_host or not math.isfinite(float(resolved_port)) or not 1 <= int(resolved_port) <= 65_535:
        raise typer.BadParameter("invalid bind address")

    import uvicorn

    from media_sync.interfaces.api import create_api_app

    typer.echo(
        json.dumps(
            {
                "service": "media-sync-api",
                "bind": f"{resolved_host}:{resolved_port}",
                "console": "http://127.0.0.1:8632/"
                if resolved_host == "127.0.0.1"
                else f"http://{resolved_host}:{resolved_port}/",
                "authentication": "none; trusted networks only",
            },
            ensure_ascii=True,
        )
    )
    uvicorn.run(
        create_api_app(settings),
        host=resolved_host,
        port=int(resolved_port),
        log_level=settings.log_level.lower(),
    )


def run() -> None:
    """Console entry point useful to module runners and tests."""

    app()


if __name__ == "__main__":  # pragma: no cover
    run()
