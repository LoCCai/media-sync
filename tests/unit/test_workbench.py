"""Shared account/subscription workbench correctness and redaction coverage."""

from __future__ import annotations

import json
from collections.abc import Iterator
from uuid import UUID

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from media_sync.application.workbench import (
    AccountDraft,
    AccountWorkbenchService,
    SubscriptionDraft,
    SubscriptionWorkbenchService,
    WorkbenchError,
    WorkbenchService,
)
from media_sync.domain import LoginMethod, Platform
from media_sync.infrastructure.db import Account, Author, Database, Subscription


@pytest.fixture
def database() -> Iterator[Database]:
    database = Database("sqlite+pysqlite:///:memory:")
    database.create_schema()
    try:
        yield database
    finally:
        database.dispose()


def _count(database: Database, model: type[Account] | type[Author] | type[Subscription]) -> int:
    with database.session() as session:
        count = session.scalar(select(func.count()).select_from(model))
        assert count is not None
        return count


def _account(
    database: Database,
    *,
    platform: Platform = Platform.XHS,
    adapter: str = "mediacrawler",
    login_method: LoginMethod = LoginMethod.QR,
    credential_ref: str | None = None,
) -> str:
    with database.session() as session:
        result = AccountWorkbenchService(session).create(
            AccountDraft(
                platform=platform,
                display_name=f"{adapter}-{platform.value}",
                adapter=adapter,
                login_method=login_method,
                credential_ref=credential_ref,
            )
        )
        return result.id


@pytest.mark.parametrize(
    ("method", "reference"),
    [
        (LoginMethod.QR, None),
        (LoginMethod.SAVED_SESSION, None),
        (LoginMethod.COOKIE, "env:MEDIA_SYNC_COOKIE"),
    ],
)
def test_mediacrawler_account_create_is_idempotent_and_returns_no_reference(
    database: Database,
    method: LoginMethod,
    reference: str | None,
) -> None:
    draft = AccountDraft(
        platform=Platform.XHS,
        display_name=f"  account-{method.value}  ",
        login_method=method,
        credential_ref=reference,
    )

    with database.session() as session:
        service = WorkbenchService(session)
        preview = service.validate_account(draft)
        first = service.create_account(draft)
        second = service.create_account(draft)

    assert preview.exists is False
    assert first.created is True
    assert second.created is False
    assert first.id == second.id
    assert _count(database, Account) == 1
    serialized = json.dumps(first.to_payload(), sort_keys=True)
    if reference is not None:
        assert reference not in serialized
        assert reference not in repr(first)
        assert reference not in repr(draft)


@pytest.mark.parametrize(
    ("method", "reference", "code"),
    [
        (LoginMethod.PHONE, None, "login_method_not_supported"),
        (LoginMethod.COOKIE, None, "cookie_login_requires_credential_ref"),
        (
            LoginMethod.QR,
            "env:MEDIA_SYNC_COOKIE",
            "credential_ref_allowed_only_for_cookie_login",
        ),
        (LoginMethod.COOKIE, "sessionid=sentinel-secret", "invalid_credential_reference"),
    ],
)
def test_mediacrawler_account_rejection_writes_nothing_and_uses_fixed_code(
    database: Database,
    method: LoginMethod,
    reference: str | None,
    code: str,
) -> None:
    draft = AccountDraft(
        platform=Platform.BILI,
        display_name="rejected",
        login_method=method,
        credential_ref=reference,
    )

    with database.session() as session, pytest.raises(WorkbenchError) as raised:
        AccountWorkbenchService(session).create(draft)

    assert raised.value.code == code
    assert "sentinel-secret" not in str(raised.value)
    assert _count(database, Account) == 0


def test_account_conflict_is_safe_and_does_not_insert_a_second_row(database: Database) -> None:
    original = AccountDraft(
        platform=Platform.XHS,
        display_name="same-name",
        login_method=LoginMethod.COOKIE,
        credential_ref="env:FIRST_COOKIE",
    )
    conflict = AccountDraft(
        platform=Platform.XHS,
        display_name="same-name",
        login_method=LoginMethod.COOKIE,
        credential_ref="env:SECOND_COOKIE",
    )

    with database.session() as session:
        AccountWorkbenchService(session).create(original)
    with database.session() as session, pytest.raises(WorkbenchError) as raised:
        AccountWorkbenchService(session).create(conflict)

    assert raised.value.code == "account_exists_with_different_configuration"
    assert "FIRST_COOKIE" not in str(raised.value)
    assert "SECOND_COOKIE" not in str(raised.value)
    assert _count(database, Account) == 1


def test_fake_account_and_default_subscription_behavior_remain_compatible(database: Database) -> None:
    account_id = _account(
        database,
        platform=Platform.BILI,
        adapter="fake",
        login_method=LoginMethod.QR,
        credential_ref="env:FAKE_QR_REFERENCE",
    )
    draft = SubscriptionDraft(
        account_id=_uuid(account_id),
        platform=Platform.BILI,
        creator_remote_id="https://fixture.invalid/bili/creator-001",
        display_name="Fake creator",
    )

    with database.session() as session:
        result = SubscriptionWorkbenchService(session).create(draft)

    assert result.created is True
    assert result.policy_summary.to_payload() == {"adapter": "fake"}
    assert _count(database, Subscription) == 1


@pytest.mark.parametrize("platform", [Platform.BILI, Platform.DY, Platform.KS, Platform.WB])
def test_full_history_platform_rejection_occurs_before_author_or_subscription_write(
    database: Database,
    platform: Platform,
) -> None:
    account_id = _account(database, platform=platform)
    draft = SubscriptionDraft(
        account_id=_uuid(account_id),
        platform=platform,
        creator_remote_id="stable-creator",
        display_name="Rejected creator",
    )

    with database.session() as session, pytest.raises(WorkbenchError) as raised:
        SubscriptionWorkbenchService(session).create(draft)

    assert raised.value.code == "full_history_acknowledgement_required"
    assert _count(database, Author) == 0
    assert _count(database, Subscription) == 0


@pytest.mark.parametrize(
    ("platform", "remote_id", "secret_ref", "code"),
    [
        (
            Platform.XHS,
            "https://example.invalid/creator?token=sentinel",
            None,
            "creator_remote_id_must_be_stable_id",
        ),
        (Platform.XHS, "stable-creator", "cookie=sentinel", "invalid_creator_secret_reference"),
        (Platform.BILI, "stable-creator", "env:BILI_CREATOR", "creator_secret_ref_not_supported"),
    ],
)
def test_mediacrawler_creator_identity_and_secret_rejections_write_nothing(
    database: Database,
    platform: Platform,
    remote_id: str,
    secret_ref: str | None,
    code: str,
) -> None:
    account_id = _account(database, platform=platform)
    draft = SubscriptionDraft(
        account_id=_uuid(account_id),
        platform=platform,
        creator_remote_id=remote_id,
        display_name="Rejected creator",
        creator_secret_ref=secret_ref,
        allow_full_history=platform in {Platform.BILI, Platform.DY, Platform.KS, Platform.WB},
    )

    with database.session() as session, pytest.raises(WorkbenchError) as raised:
        SubscriptionWorkbenchService(session).create(draft)

    assert raised.value.code == code
    assert "sentinel" not in str(raised.value)
    assert _count(database, Author) == 0
    assert _count(database, Subscription) == 0


def test_platform_conflict_and_fake_creator_secret_reject_before_author_write(database: Database) -> None:
    account_id = _account(database, platform=Platform.XHS, adapter="fake")
    platform_conflict = SubscriptionDraft(
        account_id=_uuid(account_id),
        platform=Platform.BILI,
        creator_remote_id="creator-001",
        display_name="Creator",
    )
    fake_secret = SubscriptionDraft(
        account_id=_uuid(account_id),
        platform=Platform.XHS,
        creator_remote_id="creator-001",
        display_name="Creator",
        creator_secret_ref="env:FAKE_CREATOR_REFERENCE",
    )

    with database.session() as session, pytest.raises(WorkbenchError) as conflict:
        SubscriptionWorkbenchService(session).create(platform_conflict)
    with database.session() as session, pytest.raises(WorkbenchError) as secret:
        SubscriptionWorkbenchService(session).create(fake_secret)

    assert conflict.value.code == "platform_conflict"
    assert secret.value.code == "creator_secret_ref_only_for_mediacrawler"
    assert _count(database, Author) == 0
    assert _count(database, Subscription) == 0


def test_subscription_preview_is_read_only_and_create_uses_exact_policy_without_secret_output(
    database: Database,
) -> None:
    account_id = _account(database, platform=Platform.XHS)
    secret_ref = "env:MEDIA_SYNC_XHS_CREATOR_URL"
    draft = SubscriptionDraft(
        account_id=_uuid(account_id),
        platform=Platform.XHS,
        creator_remote_id=" stable-creator ",
        display_name=" Creator ",
        creator_secret_ref=secret_ref,
        interval_seconds=600,
        max_items=12,
        request_delay_seconds=2,
        headless=False,
    )

    with database.session() as session:
        service = WorkbenchService(session)
        preview = service.validate_subscription(draft)
        assert _session_count(session, Author) == 0
        assert _session_count(session, Subscription) == 0
        first = service.create_subscription(draft)
        second = service.create_subscription(draft)

    assert preview.creator_remote_id == "stable-creator"
    assert preview.exists is False
    assert first.created is True
    assert second.created is False
    assert first.id == second.id
    assert first.policy_summary.to_payload() == {
        "adapter": "mediacrawler",
        "schema_version": 1,
        "allow_full_history": False,
        "request_delay_seconds": 2.0,
        "headless": False,
        "creator_reference_configured": True,
    }
    public_output = json.dumps(first.to_payload(), sort_keys=True)
    assert secret_ref not in public_output
    assert secret_ref not in repr(first)
    assert secret_ref not in repr(draft)
    assert _count(database, Author) == 1
    assert _count(database, Subscription) == 1

    with database.session() as session:
        stored = session.scalar(select(Subscription))
        assert stored is not None
        assert stored.policy == {
            "mediacrawler": {
                "schema_version": 1,
                "allow_full_history": False,
                "request_delay_seconds": 2.0,
                "headless": False,
                "creator_input": {"secret_ref": secret_ref},
            }
        }


def test_subscription_conflict_is_detected_before_author_update(database: Database) -> None:
    account_id = _account(database, platform=Platform.BILI)
    original = SubscriptionDraft(
        account_id=_uuid(account_id),
        platform=Platform.BILI,
        creator_remote_id="12345",
        display_name="Original creator",
        max_items=10,
        allow_full_history=True,
    )
    conflict = SubscriptionDraft(
        account_id=_uuid(account_id),
        platform=Platform.BILI,
        creator_remote_id="12345",
        display_name="Must not be written",
        max_items=11,
        allow_full_history=True,
    )

    with database.session() as session:
        SubscriptionWorkbenchService(session).create(original)
    with database.session() as session, pytest.raises(WorkbenchError) as raised:
        SubscriptionWorkbenchService(session).create(conflict)

    assert raised.value.code == "subscription_exists_with_different_options"
    assert _count(database, Author) == 1
    assert _count(database, Subscription) == 1
    with database.session() as session:
        author = session.scalar(select(Author))
        assert author is not None
        assert author.display_name == "Original creator"


def _uuid(value: str) -> UUID:
    return UUID(value)


def _session_count(session: Session, model: type[Author] | type[Subscription]) -> int:
    count = session.scalar(select(func.count()).select_from(model))
    assert count is not None
    return count
