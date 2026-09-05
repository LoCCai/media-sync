"""Isolated creator identity/auth/generation persistence, never live profile access."""

from __future__ import annotations

import base64
import json
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from sqlalchemy import event

from media_sync.application.workbench import SubscriptionDraft, SubscriptionWorkbenchService, WorkbenchError
from media_sync.domain import Platform
from media_sync.infrastructure.db import (
    Account,
    AccountRepository,
    Author,
    AuthorRepository,
    AuthorUpsert,
    Database,
    LoginSessionRepository,
    Operation,
    OperationRepository,
    Subscription,
)
from media_sync.infrastructure.db.creator_profile_repository import (
    CreatorProfileError,
    CreatorProfileRepository,
    LookupTicket,
    ProfileValue,
)

NOW = datetime.now(UTC)
SHA = "d6f7c5bb906b6dac40ddf343ef9e26438a3de092"
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jVAAAAABJRU5ErkJggg==")


@pytest.fixture
def database(tmp_path: Path) -> Iterator[Database]:
    database = Database(f"sqlite+pysqlite:///{(tmp_path / 'profiles.sqlite3').as_posix()}")
    database.create_schema()
    try:
        yield database
    finally:
        database.dispose()


def _account(database: Database) -> str:
    with database.session() as session:
        return (
            AccountRepository(session)
            .create(
                platform="bili",
                adapter="mediacrawler",
                display_name=str(uuid4()),
                login_method="saved_session",
                auth_status="authenticated",
            )
            .id
        )


def _operation(database: Database, account_id: str) -> str:
    with database.session() as session:
        repository = OperationRepository(session)
        start = repository.create_or_replay(
            kind="creator-profile", request_fingerprint="a" * 64, target_type="account", target_id=account_id, at=NOW
        )
        repository.claim(
            start.operation_id, expected_revision=start.revision, lease_owner="profile-test", lease_seconds=3600, at=NOW
        )
        return start.operation_id


def _begin(database: Database, account: str, *, creator: str = "123", operation: str | None = None) -> LookupTicket:
    operation = operation or _operation(database, account)
    with database.session() as session:
        return CreatorProfileRepository(session).begin_lookup(
            account_id=account,
            platform="bili",
            creator_remote_id=creator,
            operation_id=operation,
            frontend_generation=str(uuid4()),
            at=NOW,
        )


def _value(creator: str = "123", nickname: str = "Remote nickname") -> ProfileValue:
    return ProfileValue("bili", creator, nickname, f"https://space.bilibili.com/{creator}", SHA)


def _finish(database: Database, operation_id: str) -> None:
    with database.session() as session:
        row = session.get(Operation, operation_id)
        assert row is not None and row.lease_owner is not None and row.lease_token is not None
        OperationRepository(session).finish_succeeded(
            operation_id,
            expected_revision=row.revision,
            lease_owner=row.lease_owner,
            lease_token=row.lease_token,
            at=NOW + timedelta(seconds=2),
        )


def test_exact_replay_account_isolation_and_public_payload_omits_private_digest(database: Database) -> None:
    account, other = _account(database), _account(database)
    ticket = _begin(database, account)
    with database.session() as session:
        repository = CreatorProfileRepository(session)
        replay = repository.begin_lookup(
            account_id=account,
            platform="bili",
            creator_remote_id="123",
            operation_id=ticket.operation_id,
            frontend_generation=ticket.frontend_generation,
            at=NOW,
        )
        assert replay == ticket
        snapshot = repository.publish(ticket, _value(), avatar=PNG, at=NOW)
        assert snapshot.revision == snapshot.avatar_revision == 1 and not snapshot.avatar_retained
        assert repository.get_profile(other, "bili", "123") is None
        assert repository.get_profile(account, "xhs", "123") is None
        assert repository.get_avatar(snapshot.profile_id, 1) == PNG
        assert repository.get_avatar(snapshot.profile_id, 2) is None
        lookup = repository.read_lookup(ticket.operation_id)
        assert lookup is not None and lookup.state == "succeeded"
        assert ticket.credential_snapshot_digest not in json.dumps(lookup.to_payload())
        assert ticket.credential_snapshot_digest not in repr(ticket)
        assert session.get(Account, account).auth_revision == 0
    other_ticket = _begin(database, other)
    assert other_ticket.profile_id != ticket.profile_id and other_ticket.generation == 1


def test_new_failure_and_avatar_failure_preserve_last_success_in_equal_time(database: Database) -> None:
    account = _account(database)
    first = _begin(database, account)
    with database.session() as session:
        CreatorProfileRepository(session).publish(first, _value(), avatar=PNG, at=NOW)
    failed = _begin(database, account)
    with database.session() as session:
        repository = CreatorProfileRepository(session)
        repository.mark_failed(failed, "SECRET Cookie /private/path", at=NOW)
        snapshot = repository.get_profile(account, "bili", "123")
        assert snapshot is not None and snapshot.revision == 1 and snapshot.nickname == "Remote nickname"
        assert repository.read_lookup(failed.operation_id).error_code == "creator_profile_failed"
        assert repository.get_avatar(first.profile_id, 1) == PNG
    third = _begin(database, account)
    with database.session() as session:
        repository = CreatorProfileRepository(session)
        snapshot = repository.publish(third, _value(nickname="New nickname"), avatar=None, at=NOW)
        assert snapshot.revision == 2 and snapshot.avatar_revision == 1 and snapshot.avatar_retained
        assert repository.get_avatar(first.profile_id, 1) == PNG
        assert repository.read_lookup(first.operation_id).profile is None


@pytest.mark.parametrize("mutation", ["generation", "operation", "frontend", "account", "creator", "digest"])
def test_forged_or_superseded_ticket_cannot_publish(database: Database, mutation: str) -> None:
    account = _account(database)
    ticket = _begin(database, account)
    if mutation == "generation":
        _begin(database, account)
    else:
        fields = {
            "operation": {"operation_id": str(uuid4())},
            "frontend": {"frontend_generation": str(uuid4())},
            "account": {"account_id": _account(database)},
            "creator": {"creator_remote_id": "124"},
            "digest": {"credential_snapshot_digest": "0" * 64},
        }
        ticket = replace(ticket, **fields[mutation])
    with database.session() as session, pytest.raises(CreatorProfileError):
        CreatorProfileRepository(session).publish(ticket, _value(), at=NOW)
    with database.session() as session:
        assert CreatorProfileRepository(session).get_profile(account, "bili", "123") is None


@pytest.mark.parametrize("boundary", ["cancel", "expiry", "auth_aba", "credential", "profile_path"])
def test_operation_and_account_fences_reject_without_publishing(database: Database, boundary: str) -> None:
    account = _account(database)
    ticket = _begin(database, account)
    with database.session() as session:
        if boundary == "cancel":
            session.get(Operation, ticket.operation_id).cancel_requested_at = NOW
        elif boundary == "expiry":
            session.get(Operation, ticket.operation_id).lease_expires_at = NOW
        elif boundary == "auth_aba":
            repository = AccountRepository(session)
            repository.set_auth_status(account, "expired", expected_status="authenticated", at=NOW)
            repository.set_auth_status(account, "authenticating", expected_status="expired", at=NOW)
            repository.set_auth_status(account, "authenticated", expected_status="authenticating", at=NOW)
            assert session.get(Account, account).auth_revision == 3
        elif boundary == "credential":
            session.get(Account, account).credential_ref = "env:PRIVATE_COOKIE"
        else:
            session.get(Account, account).profile_path = "/private/profile"
    with database.session() as session, pytest.raises(CreatorProfileError):
        CreatorProfileRepository(session).publish(ticket, _value(), at=NOW)
    with database.session() as session:
        assert CreatorProfileRepository(session).get_profile(account, "bili", "123") is None


def test_profile_write_and_lookup_state_roll_back_with_outer_effect(database: Database) -> None:
    account = _account(database)
    ticket = _begin(database, account)
    with pytest.raises(RuntimeError, match="outer abort"), database.session() as session:
        CreatorProfileRepository(session).publish(ticket, _value(), avatar=PNG, at=NOW)
        raise RuntimeError("outer abort")
    with database.session() as session:
        repository = CreatorProfileRepository(session)
        assert repository.get_profile(account, "bili", "123") is None
        assert repository.read_lookup(ticket.operation_id).state == "pending"
        assert repository.get_avatar(ticket.profile_id, 1) is None


@pytest.mark.parametrize("bad", [b"<svg />", b"x" * 2_097_153, PNG[:20]], ids=["svg", "oversize", "truncated"])
def test_invalid_avatar_rejects_before_any_profile_write(database: Database, bad: bytes) -> None:
    ticket = _begin(database, _account(database))
    with database.session() as session, pytest.raises(CreatorProfileError, match="creator_profile_invalid"):
        CreatorProfileRepository(session).publish(ticket, _value(), avatar=bad, at=NOW)


def test_successful_exact_receipt_expiry_auth_and_generation_are_independent(database: Database) -> None:
    account = _account(database)
    ticket = _begin(database, account)
    with database.session() as session:
        CreatorProfileRepository(session).publish(ticket, _value(), at=NOW)
    with database.session() as session, pytest.raises(CreatorProfileError, match="receipt_invalid"):
        CreatorProfileRepository(session).require_receipt(ticket.operation_id, account, "bili", "123", at=NOW)
    _finish(database, ticket.operation_id)
    with database.session() as session:
        result = CreatorProfileRepository(session).require_receipt(ticket.operation_id, account, "bili", "123", at=NOW)
        assert result.nickname == "Remote nickname"
    with database.session() as session, pytest.raises(CreatorProfileError, match="receipt_expired"):
        CreatorProfileRepository(session).require_receipt(
            ticket.operation_id, account, "bili", "123", at=NOW + timedelta(seconds=901)
        )
    _begin(database, account)
    with database.session() as session, pytest.raises(CreatorProfileError, match="receipt_invalid"):
        CreatorProfileRepository(session).require_receipt(ticket.operation_id, account, "bili", "123", at=NOW)


def test_metadata_reads_do_not_select_binary_avatar(database: Database) -> None:
    account = _account(database)
    ticket = _begin(database, account)
    with database.session() as session:
        CreatorProfileRepository(session).publish(ticket, _value(), avatar=PNG, at=NOW)
    statements: list[str] = []

    def capture(_connection: object, _cursor: object, statement: str, *_args: object) -> None:
        statements.append(statement)

    event.listen(database.engine, "before_cursor_execute", capture)
    try:
        with database.session() as session:
            repository = CreatorProfileRepository(session)
            assert repository.get_profile(account, "bili", "123") is not None
            assert repository.read_lookup(ticket.operation_id) is not None
    finally:
        event.remove(database.engine, "before_cursor_execute", capture)
    assert not any("avatar_png" in statement for statement in statements)


def test_real_two_connection_generations_are_unique_and_older_response_is_fenced(database: Database) -> None:
    account = _account(database)
    operations = [_operation(database, account), _operation(database, account)]
    barrier = Barrier(2)

    def begin(operation: str) -> LookupTicket:
        barrier.wait(5)
        return _begin(database, account, operation=operation)

    with ThreadPoolExecutor(max_workers=2) as executor:
        tickets = list(executor.map(begin, operations))
    assert sorted(ticket.generation for ticket in tickets) == [1, 2]
    old, newest = sorted(tickets, key=lambda value: value.generation)
    with database.session() as session, pytest.raises(CreatorProfileError, match="superseded"):
        CreatorProfileRepository(session).publish(old, _value(), at=NOW)
    with database.session() as session:
        assert CreatorProfileRepository(session).publish(newest, _value(), at=NOW).revision == 1


def test_workbench_receipt_alias_and_ingestion_do_not_rename_shared_author(database: Database) -> None:
    account, other = _account(database), _account(database)
    with database.session() as session:
        author = AuthorRepository(session).upsert(
            AuthorUpsert(
                platform="bili",
                remote_id="123",
                display_name="Old path",
                profile_url="https://space.bilibili.com/123",
                avatar_url="https://example.invalid/old.png",
            )
        )
        author_id = author.id
    ticket = _begin(database, account)
    with database.session() as session:
        CreatorProfileRepository(session).publish(ticket, _value(), at=NOW)
    _finish(database, ticket.operation_id)
    draft = SubscriptionDraft(
        account_id=UUID(account),
        platform=Platform.BILI,
        creator_remote_id="123",
        display_name="",
        local_alias="Personal note",
        profile_lookup_id=UUID(ticket.operation_id),
        allow_full_history=True,
    )
    with database.session() as session:
        service = SubscriptionWorkbenchService(session)
        preview = service.validate(draft)
        assert preview.local_alias == "Personal note" and preview.profile_lookup_id == ticket.operation_id
        result = service.create(draft)
        assert result.local_alias == "Personal note" and result.profile_lookup_id == ticket.operation_id
        assert result.creator_display_name == "Old path"
        service.create(replace(draft, local_alias="Changed personal note"))
        SubscriptionWorkbenchService(session).create(
            SubscriptionDraft(
                account_id=UUID(other),
                platform=Platform.BILI,
                creator_remote_id="123",
                display_name="Other local note",
                allow_full_history=True,
            )
        )
        author = session.get(Author, author_id)
        assert author.display_name == "Old path" and author.avatar_url == "https://example.invalid/old.png"
        assert session.get(Subscription, result.id).local_alias == "Changed personal note"
        AuthorRepository(session).upsert(AuthorUpsert(platform="bili", remote_id="123", display_name="Ingested name"))
        assert CreatorProfileRepository(session).get_profile(account, "bili", "123").nickname == "Remote nickname"
        assert session.get(Subscription, result.id).local_alias == "Changed personal note"


def test_receipt_can_create_new_author_without_local_alias_but_forged_receipt_cannot(database: Database) -> None:
    account = _account(database)
    ticket = _begin(database, account)
    with database.session() as session:
        CreatorProfileRepository(session).publish(ticket, _value(), at=NOW)
    _finish(database, ticket.operation_id)
    draft = SubscriptionDraft(
        account_id=UUID(account),
        platform=Platform.BILI,
        creator_remote_id="123",
        display_name="",
        profile_lookup_id=UUID(ticket.operation_id),
        allow_full_history=True,
    )
    with database.session() as session:
        result = SubscriptionWorkbenchService(session).create(draft)
        assert result.creator_display_name == "Remote nickname" and result.local_alias is None
    with database.session() as session, pytest.raises(WorkbenchError, match="receipt_invalid"):
        SubscriptionWorkbenchService(session).create(replace(draft, creator_remote_id="124"))


def test_qr_start_finish_and_reconciliation_advance_auth_revision(database: Database) -> None:
    with database.session() as session:
        account = AccountRepository(session).create(
            platform="bili", adapter="mediacrawler", display_name="QR", login_method="qr", auth_status="unknown"
        )
        repository = LoginSessionRepository(session)
        login = repository.start_mediacrawler_qr(account.id, expires_at=NOW + timedelta(minutes=5), at=NOW)
        assert session.get(Account, account.id).auth_revision == 1
        repository.mark_waiting_user(login.id, at=NOW)
        repository.succeed_mediacrawler_qr(login.id, at=NOW)
        assert session.get(Account, account.id).auth_revision == 2
        account_id = account.id
    with database.session() as session:
        AccountRepository(session).set_auth_status(account_id, "expired", expected_status="authenticated", at=NOW)
        LoginSessionRepository(session).start_mediacrawler_qr(account_id, expires_at=NOW + timedelta(seconds=1), at=NOW)
        assert session.get(Account, account_id).auth_revision == 4
    with database.session() as session:
        candidates = LoginSessionRepository(session).list_expired_mediacrawler_qr_candidates(
            at=NOW + timedelta(seconds=2), account_id=account_id
        )
    assert len(candidates) == 1
    with database.session() as session:
        LoginSessionRepository(session).recover_expired_mediacrawler_qr(candidates[0], at=NOW + timedelta(seconds=2))
        assert session.get(Account, account_id).auth_revision == 5


def test_subscription_author_initialization_never_mutates_an_existing_row(database: Database) -> None:
    with database.session() as session:
        repository = AuthorRepository(session)
        first = repository.create_if_missing(
            AuthorUpsert(
                platform="bili",
                remote_id="123",
                display_name="Stable export directory",
                profile_url="https://space.bilibili.com/123",
                avatar_url="https://example.invalid/retained.png",
            ),
            seen_at=NOW,
        )
        second = repository.create_if_missing(
            AuthorUpsert(
                platform="bili",
                remote_id="123",
                display_name="Do not overwrite",
            ),
            seen_at=NOW + timedelta(seconds=1),
        )
        assert second.id == first.id
        assert second.display_name == "Stable export directory"
        assert second.avatar_url == "https://example.invalid/retained.png"
        assert second.profile_url == "https://space.bilibili.com/123"
        assert second.last_seen_at == NOW


def test_real_two_connection_author_first_name_wins_without_overwrite(database: Database) -> None:
    barrier = Barrier(2)

    def create(name: str) -> tuple[str, str]:
        barrier.wait(5)
        with database.session() as session:
            result = AuthorRepository(session).create_if_missing(
                AuthorUpsert(platform="bili", remote_id="123", display_name=name), seen_at=NOW
            )
            return result.id, result.display_name

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(create, ["First contender", "Second contender"]))
    assert results[0] == results[1]
