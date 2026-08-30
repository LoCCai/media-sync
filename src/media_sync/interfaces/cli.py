"""Command-line interface for local media-sync administration."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import platform as runtime_platform
import re
import shutil
import sys
from collections.abc import Iterator, Mapping
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
from media_sync.application import SyncRequest, SyncService
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
from media_sync.config import Settings, get_settings
from media_sync.domain import AccountRef, AssetStatus, Cursor, DomainError, JobStatus, LoginMethod, Platform, RunStatus
from media_sync.exporters.emby import EmbyExporter, ExportError
from media_sync.infrastructure.db import (
    Account,
    AccountRepository,
    Asset,
    AuthorRepository,
    AuthorUpsert,
    Base,
    Content,
    Database,
    IngestionMode,
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
from media_sync.integrations.mediacrawler.checkout import (
    MEDIACRAWLER_LICENSE,
    CheckoutValidationError,
    LicenseAcknowledgementRequired,
    verify_mediacrawler_checkout,
    verify_mediacrawler_python,
)
from media_sync.integrations.mediacrawler.policies import (
    MediaCrawlerPolicyError,
    build_run_paths,
    normalize_creator_reference,
)
from media_sync.integrations.mediacrawler.subscription_policy import (
    MAX_REQUEST_DELAY_SECONDS,
    MediaCrawlerSubscriptionPolicy,
)
from media_sync.media import (
    DownloadLimits,
    FFprobeMediaProbe,
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
scheduler_app = typer.Typer(help="Bounded durable scheduler commands.")
scheduler_job_app = typer.Typer(help="Redaction-safe scheduler Job controls.")
scheduler_lane_app = typer.Typer(help="Persistent scheduler lane controls.")
mediacrawler_app = typer.Typer(help="License-gated external MediaCrawler bridge commands.")
asset_app = typer.Typer(help="Verified media asset download commands.")
emby_app = typer.Typer(help="Emby/Jellyfin library export commands.")
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

_EXPECTED_DATABASE_REVISION = "0005_asset_refresh_sources"
_REQUIRED_DATABASE_TABLES = frozenset(str(name) for name in Base.metadata.tables)


class AdapterName(StrEnum):
    """Account adapter identifiers exposed as a closed CLI choice."""

    FAKE = "fake"
    MEDIACRAWLER = "mediacrawler"


class SchedulerLaneScope(StrEnum):
    """Closed lane scopes exposed by the local scheduler CLI."""

    PLATFORM = "platform"
    ACCOUNT = "account"


_MEDIACRAWLER_LOGIN_METHODS = frozenset({LoginMethod.QR, LoginMethod.COOKIE, LoginMethod.SAVED_SESSION})
_STABLE_CREATOR_ID = re.compile(r"[A-Za-z0-9._-]{1,512}\Z")


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
            }
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

    report: dict[str, object] = {
        "ok": False,
        "code": None,
        "upstream_sha": None,
        "license": MEDIACRAWLER_LICENSE,
        "checkout_ready": False,
        "runtime_configured": settings.mediacrawler_python_executable is not None,
        "runtime_ready": False,
        "live_qualification": "NOT_RUN",
    }
    try:
        checkout = verify_mediacrawler_checkout(
            settings.mediacrawler_lock_path,
            license_acknowledged=license_acknowledged,
        )
    except LicenseAcknowledgementRequired:
        return {**report, "code": "license_acknowledgement_required"}
    except CheckoutValidationError:
        return {**report, "code": "checkout_invalid"}

    report.update(
        {
            "checkout_ready": True,
            "upstream_sha": checkout.commit,
        }
    )
    if settings.mediacrawler_python_executable is None:
        return {**report, "code": "runtime_unconfigured"}
    try:
        verify_mediacrawler_python(settings.mediacrawler_python_executable)
    except CheckoutValidationError:
        return {**report, "code": "runtime_invalid"}
    return {
        **report,
        "ok": True,
        "code": "ready",
        "runtime_ready": True,
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

    normalized_creator_id = creator_id.strip()
    if _STABLE_CREATOR_ID.fullmatch(normalized_creator_id) is None:
        raise typer.BadParameter(
            "creator_id must be a stable non-secret ID; token-bearing URLs require a secret reference"
        )
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
    if adapter is AdapterName.FAKE:
        if not FakePlatformAdapter(platform).capabilities().supports_login(login_method):
            raise typer.BadParameter("selected login method is not supported by the fake adapter")
    else:
        if login_method not in _MEDIACRAWLER_LOGIN_METHODS:
            raise typer.BadParameter("MediaCrawler accounts support only QR, Cookie, or saved-session login")
        if login_method is LoginMethod.COOKIE and normalized_credential_ref is None:
            raise typer.BadParameter("MediaCrawler Cookie login requires credential_ref")
        if login_method is not LoginMethod.COOKIE and normalized_credential_ref is not None:
            raise typer.BadParameter("credential_ref is allowed only for MediaCrawler Cookie login")

    with _database_session() as session:
        repository = AccountRepository(session)
        existing = repository.get_by_platform_and_name(platform.value, normalized_name)
        if existing is not None:
            same_configuration = (
                existing.adapter == adapter.value
                and existing.login_method == login_method.value
                and existing.credential_ref == normalized_credential_ref
            )
            if not same_configuration:
                raise typer.BadParameter("account already exists with different login configuration")
            account = existing
            created = False
        else:
            account = repository.create(
                platform=platform.value,
                display_name=normalized_name,
                adapter=adapter.value,
                login_method=login_method.value,
                credential_ref=normalized_credential_ref,
            )
            created = True
        payload = _account_payload(account, created=created)

    _emit_record(payload, json_output=json_output, label="Account")


@account_app.command("list")
def list_accounts(
    json_output: Annotated[bool, typer.Option("--json", help="Emit machine-readable JSON.")] = False,
) -> None:
    """List accounts without credential references or profile paths."""

    with _database_session() as session:
        records = [_account_payload(account) for account in AccountRepository(session).list()]
    _emit_list(records, json_output=json_output, label="accounts")


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
    with _database_session() as session:
        account = AccountRepository(session).get(str(account_id))
        if account is None:
            raise typer.BadParameter(f"account not found: {account_id}")
        if account.platform != platform.value:
            raise typer.BadParameter(
                f"platform conflict: account uses {account.platform!r}, creator uses {platform.value!r}"
            )
        if account.adapter != AdapterName.MEDIACRAWLER.value and normalized_creator_reference_ref is not None:
            raise typer.BadParameter("creator_reference_ref is available only for MediaCrawler accounts")
        if account.adapter == AdapterName.MEDIACRAWLER.value and any(
            marker in normalized_remote_id for marker in ("://", "?", "#", "&", "=", ";")
        ):
            raise typer.BadParameter(
                "MediaCrawler creator_remote_id must be a stable ID; use creator_reference_ref for signed URLs"
            )

        policy: dict[str, object] = {}
        if account.adapter == AdapterName.MEDIACRAWLER.value:
            policy = {
                "mediacrawler": MediaCrawlerSubscriptionPolicy(
                    allow_full_history=allow_full_history,
                    request_delay_seconds=request_delay_seconds,
                    headless=headless,
                    creator_secret_ref=normalized_creator_reference_ref,
                ).to_payload()
            }
        elif allow_full_history or request_delay_seconds != 5.0 or not headless:
            raise typer.BadParameter("MediaCrawler scheduling policy options require a MediaCrawler account")

        author_repository = AuthorRepository(session)
        author = author_repository.upsert(
            AuthorUpsert(
                platform=platform.value,
                remote_id=normalized_remote_id,
                display_name=normalized_display_name,
            )
        )
        repository = SubscriptionRepository(session)
        existing = repository.get_by_account_and_author(account.id, author.id)
        if existing is not None:
            if (
                existing.interval_seconds != interval_seconds
                or existing.max_items != max_items
                or existing.policy != policy
            ):
                raise typer.BadParameter("subscription already exists with different scheduling options")
            subscription = existing
            created = False
        else:
            subscription = repository.create(
                account_id=account.id,
                author_id=author.id,
                interval_seconds=interval_seconds,
                max_items=max_items,
                policy=policy,
            )
            created = True
        payload = _subscription_payload(subscription, created=created)

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
        worker = SubscriptionWorker(
            database,
            SubscriptionHandlerRegistry(handlers),
            claim_registered_only=True,
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
    """Download and archive one asset; ffprobe is required for video/audio assets."""

    if accept_mediacrawler_license and not enable_mediacrawler:
        raise typer.BadParameter("MediaCrawler license acknowledgement requires --enable-mediacrawler")
    if xhs_detail_reference_ref is not None and not enable_mediacrawler:
        raise typer.BadParameter("XHS detail reference requires --enable-mediacrawler")
    normalized_detail_reference_ref = _credential_reference(xhs_detail_reference_ref)
    settings = get_settings()
    database = Database(settings.resolved_database_url)
    try:
        with database.session() as session:
            asset_preflight = session.execute(
                select(Asset.status, Asset.kind, Asset.locator, Asset.platform).where(Asset.id == str(asset_id))
            ).one_or_none()
        asset_status = asset_preflight[0] if asset_preflight is not None else None
        asset_kind = asset_preflight[1] if asset_preflight is not None else None
        asset_locator = asset_preflight[2] if asset_preflight is not None else None
        asset_platform = asset_preflight[3] if asset_preflight is not None else None
        requires_download = asset_status not in {
            None,
            AssetStatus.VERIFIED.value,
            AssetStatus.FAILED_TERMINAL.value,
        }
        adapter_refresh = isinstance(asset_locator, Mapping) and asset_locator.get("type") == "adapter_refresh"
        adapter_name = asset_locator.get("adapter") if isinstance(asset_locator, Mapping) else None
        mediacrawler_refresh = adapter_refresh and adapter_name == AdapterName.MEDIACRAWLER.value
        if requires_download and adapter_refresh and not enable_mediacrawler:
            _emit_record(
                {
                    "asset_id": str(asset_id),
                    "status": "blocked",
                    "disposition": "not_started",
                    "persisted_status": asset_status,
                    "error_code": "locator_refresh_unsupported",
                    "retryable": True,
                },
                json_output=json_output,
                label="Asset download",
            )
            raise typer.Exit(code=1)
        if requires_download and adapter_refresh and not mediacrawler_refresh:
            _emit_record(
                {
                    "asset_id": str(asset_id),
                    "status": "blocked",
                    "disposition": "not_started",
                    "persisted_status": asset_status,
                    "error_code": "locator_refresh_unsupported",
                    "retryable": True,
                },
                json_output=json_output,
                label="Asset download",
            )
            raise typer.Exit(code=1)
        if requires_download and mediacrawler_refresh and not accept_mediacrawler_license:
            _emit_record(
                {
                    "asset_id": str(asset_id),
                    "status": "blocked",
                    "disposition": "not_started",
                    "persisted_status": asset_status,
                    "error_code": "license_acknowledgement_required",
                    "retryable": False,
                },
                json_output=json_output,
                label="Asset download",
            )
            raise typer.Exit(code=1)
        if requires_download and mediacrawler_refresh and settings.mediacrawler_python_executable is None:
            _emit_record(
                {
                    "asset_id": str(asset_id),
                    "status": "blocked",
                    "disposition": "not_started",
                    "persisted_status": asset_status,
                    "error_code": "locator_refresh_configuration_invalid",
                    "retryable": False,
                },
                json_output=json_output,
                label="Asset download",
            )
            raise typer.Exit(code=1)
        if (
            requires_download
            and mediacrawler_refresh
            and asset_platform == Platform.XHS.value
            and normalized_detail_reference_ref is None
        ):
            _emit_record(
                {
                    "asset_id": str(asset_id),
                    "status": "blocked",
                    "disposition": "not_started",
                    "persisted_status": asset_status,
                    "error_code": "locator_refresh_configuration_invalid",
                    "retryable": False,
                },
                json_output=json_output,
                label="Asset download",
            )
            raise typer.Exit(code=1)

        ffprobe = shutil.which("ffprobe")
        if requires_download and asset_kind in {"video", "audio"} and ffprobe is None:
            _emit_record(
                {
                    "asset_id": str(asset_id),
                    "status": "blocked",
                    "disposition": "not_started",
                    "persisted_status": asset_status,
                    "error_code": "media_probe_unavailable",
                    "retryable": True,
                },
                json_output=json_output,
                label="Asset download",
            )
            raise typer.Exit(code=1)

        limits = DownloadLimits()
        refresher = None
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
                detail_reference_ref=normalized_detail_reference_ref,
            )
        http = SafeHttpClient(
            SocketAddressResolver(),
            limits=NetworkLimits(timeout_seconds=min(limits.total_timeout_seconds, 120.0)),
        )
        probe = FFprobeMediaProbe(ffprobe) if ffprobe is not None else None
        if refresher is None:
            downloader = SecureMediaDownloader(http, probe=probe, limits=limits)
        else:
            downloader = SecureMediaDownloader(http, refresher=refresher, probe=probe, limits=limits)
        outcome = AssetDownloadService(database, downloader).run(
            AssetDownloadRequest(
                asset_id=asset_id,
                worker_id=_required_option(worker_id, "worker_id"),
                work_root=settings.job_dir / "downloads",
                archive_root=settings.archive_dir,
                lease_seconds=lease_seconds,
                max_attempts=max_attempts,
            )
        )
    except AssetDownloadOrchestrationError as error:
        payload: dict[str, object] = {
            "asset_id": str(asset_id),
            "status": "failed",
            "error_code": error.code,
            "retryable": error.retryable,
        }
        _emit_record(payload, json_output=json_output, label="Asset download")
        raise typer.Exit(code=1) from None
    except SQLAlchemyError:
        raise typer.BadParameter("asset download database operation failed safely") from None
    finally:
        database.dispose()

    payload = {
        "asset_id": str(outcome.asset_id),
        "generation": outcome.generation,
        "job_id": str(outcome.job_id) if outcome.job_id is not None else None,
        "status": outcome.status.value,
        "disposition": outcome.disposition,
        "archive_path": str(outcome.archive_path),
        "checksum_sha256": outcome.checksum_sha256,
        "size_bytes": outcome.size_bytes,
        "mime_type": outcome.mime_type,
    }
    _emit_record(payload, json_output=json_output, label="Asset download")


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


def run() -> None:
    """Console entry point useful to module runners and tests."""

    app()


if __name__ == "__main__":  # pragma: no cover
    run()
