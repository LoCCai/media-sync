"""Short-transaction, lease-fencing, and secret-sink coverage for handlers."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from media_sync.adapters.fake import FakePlatformAdapter
from media_sync.domain import (
    AccountRef,
    AdapterError,
    AuthorSnapshot,
    DomainError,
    LoginMethod,
    Platform,
)
from media_sync.infrastructure.db import (
    AccountRepository,
    AuthorRepository,
    AuthorUpsert,
    Database,
    LeaseLostError,
    SubscriptionRepository,
)
from media_sync.infrastructure.db.models import Author, Content, SyncRun
from media_sync.scheduler.handlers import FakeSubscriptionHandler, SubscriptionJobContext

SENTINEL = "SENTINEL-hostile-sync-error"


@pytest.fixture
def database(tmp_path: Path) -> Iterator[Database]:
    instance = Database(f"sqlite+pysqlite:///{(tmp_path / 'handler.sqlite3').as_posix()}")
    instance.create_schema()
    try:
        yield instance
    finally:
        instance.dispose()


def _seed(database: Database, *, label: str = "handler-safety") -> SubscriptionJobContext:
    with database.session() as session:
        account = AccountRepository(session).create(
            platform="bili",
            adapter="fake",
            display_name=label,
            login_method="cookie",
            auth_status="authenticated",
        )
        author = AuthorRepository(session).upsert(
            AuthorUpsert(
                platform="bili",
                remote_id="creator-001",
                display_name="Unchanged placeholder",
            )
        )
        subscription = SubscriptionRepository(session).create(
            account_id=account.id,
            author_id=author.id,
            interval_seconds=60,
            max_items=1,
        )
    return SubscriptionJobContext(
        job_id=uuid4(),
        subscription_id=UUID(subscription.id),
        account=AccountRef(
            account_id=UUID(account.id),
            platform=Platform.BILI,
            login_method=LoginMethod.COOKIE,
            adapter="fake",
        ),
        creator_reference="creator-001",
        max_items=1,
    )


class _BlockingResolveAdapter(FakePlatformAdapter):
    def __init__(self, platform: Platform, entered: asyncio.Event, release: asyncio.Event) -> None:
        super().__init__(platform)
        self.entered = entered
        self.release = release

    async def resolve_author(self, account: AccountRef, reference: str) -> AuthorSnapshot:
        self.entered.set()
        await self.release.wait()
        return await super().resolve_author(account, reference)


@pytest.mark.asyncio
async def test_blocked_adapter_await_does_not_hold_the_sqlite_writer(database: Database) -> None:
    context = _seed(database, label="blocking-adapter")
    entered = asyncio.Event()
    release = asyncio.Event()
    handler = FakeSubscriptionHandler(
        database,
        adapter_factory=lambda platform: _BlockingResolveAdapter(platform, entered, release),
    )
    task = asyncio.create_task(handler.run(context))

    def independent_write() -> None:
        independent = Database(database.url)
        try:
            with independent.session() as session:
                result = session.execute(
                    text("UPDATE subscriptions SET max_items = max_items WHERE id = :subscription_id"),
                    {"subscription_id": str(context.subscription_id)},
                )
                assert result.rowcount == 1
        finally:
            independent.dispose()

    try:
        await asyncio.wait_for(entered.wait(), timeout=2)
        await asyncio.wait_for(asyncio.to_thread(independent_write), timeout=2)
    finally:
        release.set()

    result = await asyncio.wait_for(task, timeout=5)
    assert result.succeeded is True


@pytest.mark.asyncio
async def test_same_session_guard_loss_prevents_subsequent_handler_persistence(database: Database) -> None:
    context = _seed(database, label="guard-loss")
    calls = 0
    session_ids: set[int] = set()

    def ownership_guard(session: Session) -> None:
        nonlocal calls
        calls += 1
        session_ids.add(id(session))
        if calls == 4:
            raise LeaseLostError("handler lease lost before author persistence")
        session.execute(
            text("UPDATE subscriptions SET max_items = max_items WHERE id = :subscription_id"),
            {"subscription_id": str(context.subscription_id)},
        )

    guarded_context = SubscriptionJobContext(
        job_id=context.job_id,
        subscription_id=context.subscription_id,
        account=context.account,
        creator_reference=context.creator_reference,
        max_items=context.max_items,
        ownership_guard=ownership_guard,
    )

    with pytest.raises(LeaseLostError, match="before author persistence"):
        await FakeSubscriptionHandler(database).run(guarded_context)

    assert calls == 4
    assert len(session_ids) == 1
    with database.session() as session:
        run = session.scalar(select(SyncRun))
        author = session.scalar(select(Author).where(Author.remote_id == "creator-001"))
        assert run is not None and run.status == "running"
        assert run.error_code is None and run.error_message is None
        assert author is not None and author.display_name == "Unchanged placeholder"
        assert session.scalar(select(func.count()).select_from(Content)) == 0


class _HostileResolveAdapter(FakePlatformAdapter):
    def __init__(self, platform: Platform, error: DomainError) -> None:
        super().__init__(platform)
        self.error = error

    async def resolve_author(self, account: AccountRef, reference: str) -> AuthorSnapshot:
        del account, reference
        raise self.error


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error_kind", "expected_handler_code"),
    [
        ("adapter", "unexpected_handler_failure"),
        ("domain", "schema_invalid"),
    ],
)
async def test_hostile_error_code_and_message_never_reach_sqlite_bytes(
    tmp_path: Path,
    error_kind: str,
    expected_handler_code: str,
) -> None:
    database_path = tmp_path / f"hostile-{error_kind}.sqlite3"
    database = Database(f"sqlite+pysqlite:///{database_path.as_posix()}")
    database.create_schema()
    context = _seed(database, label=f"hostile-{error_kind}")
    hostile_value = f"{SENTINEL}-{error_kind}:C:\\private\\cookies\\session.json"
    error: DomainError
    if error_kind == "adapter":
        error = AdapterError(
            hostile_value,
            f"raw adapter message {hostile_value}",
            platform="bili",
            retryable=True,
        )
    else:
        error = DomainError(hostile_value, f"raw domain message {hostile_value}")
    handler = FakeSubscriptionHandler(
        database,
        adapter_factory=lambda platform: _HostileResolveAdapter(platform, error),
    )

    try:
        result = await handler.run(context)
        assert result.error_code == expected_handler_code
        with database.session() as session:
            run = session.scalar(select(SyncRun))
            assert run is not None
            assert run.error_code == "unexpected_failure"
            assert SENTINEL not in repr((run.error_code, run.error_message, run.manifest))
    finally:
        database.dispose()

    retained_sqlite_files = tuple(path for path in tmp_path.glob(f"{database_path.name}*") if path.is_file())
    assert database_path in retained_sqlite_files
    assert all(SENTINEL.encode() not in path.read_bytes() for path in retained_sqlite_files)
