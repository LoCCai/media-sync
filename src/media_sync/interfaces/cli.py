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
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError
from sqlalchemy.orm import Session

from media_sync import __version__
from media_sync.adapters.fake import FakePlatformAdapter
from media_sync.application import SyncRequest, SyncService
from media_sync.config import Settings, get_settings
from media_sync.domain import AccountRef, Cursor, DomainError, LoginMethod, Platform, RunStatus
from media_sync.infrastructure.db import (
    Account,
    AccountRepository,
    AuthorRepository,
    AuthorUpsert,
    Base,
    Database,
    IngestionMode,
    MediaCrawlerIngestionService,
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
from media_sync.integrations.mediacrawler.normalizers import (
    NormalizationContext,
    NormalizedMediaRecord,
    normalize_jsonl_bytes,
)
from media_sync.integrations.mediacrawler.policies import (
    MediaCrawlerPolicyError,
    build_run_paths,
    normalize_creator_reference,
)
from media_sync.integrations.mediacrawler.receipt import load_validated_output_snapshot
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
mediacrawler_app = typer.Typer(help="License-gated external MediaCrawler bridge commands.")
app.add_typer(db_app, name="db")
app.add_typer(account_app, name="account")
app.add_typer(subscription_app, name="subscription")
app.add_typer(sync_app, name="sync")
app.add_typer(mediacrawler_app, name="mediacrawler")

_EXPECTED_DATABASE_REVISION = "0002_checkpoint"
_REQUIRED_DATABASE_TABLES = frozenset(str(name) for name in Base.metadata.tables)


class AdapterName(StrEnum):
    """Account adapter identifiers exposed as a closed CLI choice."""

    FAKE = "fake"
    MEDIACRAWLER = "mediacrawler"


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
        "tools": {
            "ffmpeg": shutil.which("ffmpeg"),
            "ffprobe": shutil.which("ffprobe"),
            "git": shutil.which("git"),
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
        if normalized_creator_reference_ref is not None:
            policy = {
                "mediacrawler": {
                    "creator_input": {"secret_ref": normalized_creator_reference_ref},
                }
            }

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
            output_snapshot = load_validated_output_snapshot(manifest)
            output_fingerprint = hashlib.sha256(
                json.dumps(
                    output_snapshot.receipt.as_payload(),
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()
            context = NormalizationContext(
                platform=platform,
                creator_remote_id=creator_remote_id,
                creator_display_name=creator_display_name,
                upstream_sha=manifest.upstream_sha,
                ingested_at=datetime.now(UTC),
            )
            normalized_records: list[NormalizedMediaRecord] = []
            quarantined_count = 0
            truncated_tail = False
            for jsonl_file in output_snapshot.files:
                batch = normalize_jsonl_bytes(
                    jsonl_file.payload,
                    context,
                    max_bytes=manifest.watchdogs.max_output_bytes,
                    max_records=manifest.watchdogs.max_output_items,
                    max_line_bytes=manifest.watchdogs.max_line_bytes,
                )
                normalized_records.extend(batch.records)
                quarantined_count += len(batch.quarantined)
                truncated_tail = truncated_tail or batch.truncated_tail
            if quarantined_count or truncated_tail:
                raise MediaCrawlerPolicyError("MediaCrawler output is incomplete or contains quarantined records")
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
