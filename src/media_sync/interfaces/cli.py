"""Command-line interface for local media-sync administration."""

from __future__ import annotations

import asyncio
import json
import platform as runtime_platform
import re
import shutil
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any
from uuid import UUID

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
    RepositoryError,
    SQLAlchemySyncRepository,
    Subscription,
    SubscriptionRepository,
    upgrade_database,
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
app.add_typer(db_app, name="db")
app.add_typer(account_app, name="account")
app.add_typer(subscription_app, name="subscription")
app.add_typer(sync_app, name="sync")

_EXPECTED_DATABASE_REVISION = "0001_core"
_REQUIRED_DATABASE_TABLES = frozenset(str(name) for name in Base.metadata.tables)


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
    if not normalized:
        raise typer.BadParameter(f"{name} must not be blank")
    return normalized


def _credential_reference(value: str | None) -> str | None:
    """Validate an opaque lookup reference and reject secret-like inline data."""

    if value is None:
        return None
    normalized = value.strip()
    if not normalized or len(normalized) > 512:
        raise typer.BadParameter("credential_ref must be a non-empty opaque reference of at most 512 characters")
    if any(marker in normalized for marker in ("\r", "\n", "\0", ";", "=")):
        raise typer.BadParameter("credential_ref must not contain inline credential data")

    scheme, separator, locator = normalized.partition(":")
    scheme = scheme.lower()
    if not separator or scheme not in {"env", "file", "keyring"} or not locator.strip():
        raise typer.BadParameter("credential_ref must use env:<VAR>, keyring:<locator>, or file:<path-or-key>")
    locator = locator.strip()
    if scheme == "env" and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", locator) is None:
        raise typer.BadParameter("env credential_ref must name one environment variable")
    if scheme == "keyring" and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/@:+-]*", locator) is None:
        raise typer.BadParameter("keyring credential_ref contains unsupported characters")
    return f"{scheme}:{locator}"


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
    login_method: Annotated[LoginMethod, typer.Option(help="Authentication method.")] = LoginMethod.COOKIE,
    credential_ref: Annotated[
        str | None,
        typer.Option(help="Opaque credential-store reference; never a raw cookie or password."),
    ] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Emit machine-readable JSON.")] = False,
) -> None:
    """Add an account backed by the deterministic foundation adapter."""

    normalized_name = _required_option(display_name, "display_name")
    if not FakePlatformAdapter(platform).capabilities().supports_login(login_method):
        raise typer.BadParameter("selected login method is not supported by the fake adapter")
    normalized_credential_ref = _credential_reference(credential_ref)
    with _database_session() as session:
        repository = AccountRepository(session)
        existing = repository.get_by_platform_and_name(platform.value, normalized_name)
        if existing is not None:
            same_configuration = (
                existing.adapter == "fake"
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
                adapter="fake",
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
    interval_seconds: Annotated[int, typer.Option(min=60, help="Polling interval in seconds.")] = 21_600,
    max_items: Annotated[int, typer.Option(min=1, max=1_000, help="Maximum items per run.")] = 30,
    json_output: Annotated[bool, typer.Option("--json", help="Emit machine-readable JSON.")] = False,
) -> None:
    """Idempotently subscribe an account to one platform creator."""

    normalized_remote_id = _required_option(creator_remote_id, "creator_remote_id")
    normalized_display_name = _required_option(display_name, "display_name")
    with _database_session() as session:
        account = AccountRepository(session).get(str(account_id))
        if account is None:
            raise typer.BadParameter(f"account not found: {account_id}")
        if account.platform != platform.value:
            raise typer.BadParameter(
                f"platform conflict: account uses {account.platform!r}, creator uses {platform.value!r}"
            )

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
            if existing.interval_seconds != interval_seconds or existing.max_items != max_items:
                raise typer.BadParameter("subscription already exists with different scheduling options")
            subscription = existing
            created = False
        else:
            subscription = repository.create(
                account_id=account.id,
                author_id=author.id,
                interval_seconds=interval_seconds,
                max_items=max_items,
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
