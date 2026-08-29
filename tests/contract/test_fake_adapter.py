"""Contract tests for the deterministic fake platform adapter."""

from __future__ import annotations

from uuid import UUID

import pytest

from media_sync.adapters.fake import FakeInteraction, FakePlatformAdapter
from media_sync.domain import (
    AccountRef,
    AssetKind,
    AuthStatus,
    ContentKind,
    Cursor,
    DomainValidationError,
    LoginMethod,
    Platform,
    UnsupportedCapabilityError,
)
from media_sync.ports import PlatformAdapter


def account(method: LoginMethod = LoginMethod.COOKIE) -> AccountRef:
    return AccountRef(
        account_id=UUID("00000000-0000-0000-0000-000000000001"),
        platform=Platform.BILI,
        login_method=method,
        credential_ref="keyring:fixture-account",
    )


def test_fake_adapter_satisfies_composite_protocol() -> None:
    adapter = FakePlatformAdapter()
    capabilities = adapter.capabilities()
    assert isinstance(adapter, PlatformAdapter)
    assert capabilities.supports_incremental_cursor
    assert not capabilities.supports_login(LoginMethod.PHONE)
    assert {ContentKind.AUDIO, ContentKind.DYNAMIC} <= capabilities.content_kinds
    assert AssetKind.AVATAR in capabilities.asset_kinds


@pytest.mark.asyncio
async def test_noninteractive_fake_session_is_deterministic() -> None:
    adapter = FakePlatformAdapter()
    first = await adapter.ensure_session(account())
    second = await adapter.ensure_session(account())

    assert first == second
    assert first.status is AuthStatus.AUTHENTICATED
    assert await adapter.auth_status(account()) is AuthStatus.AUTHENTICATED
    assert "keyring" not in (first.session_ref or "")


@pytest.mark.asyncio
async def test_qr_session_requires_and_records_interaction() -> None:
    adapter = FakePlatformAdapter()
    qr_account = account(LoginMethod.QR)

    pending = await adapter.ensure_session(qr_account)
    assert pending.status is AuthStatus.REQUIRED

    interaction = FakeInteraction("approved")
    authenticated = await adapter.ensure_session(qr_account, interaction)
    assert authenticated.status is AuthStatus.AUTHENTICATED
    assert [challenge.method for challenge in interaction.challenges] == [LoginMethod.QR]


@pytest.mark.asyncio
async def test_unsupported_phone_login_fails_before_interaction() -> None:
    adapter = FakePlatformAdapter()
    with pytest.raises(UnsupportedCapabilityError) as raised:
        await adapter.ensure_session(account(LoginMethod.PHONE))
    assert raised.value.code == "unsupported_capability"


@pytest.mark.asyncio
async def test_author_resolution_accepts_id_and_profile_url() -> None:
    adapter = FakePlatformAdapter()
    by_id = await adapter.resolve_author(account(), "creator-001")
    by_url = await adapter.resolve_author(
        account(),
        "https://fixture.invalid/bili/creator-001/",
    )
    assert by_id == by_url
    assert by_id.platform is Platform.BILI


@pytest.mark.asyncio
async def test_pagination_is_replayable_and_exposes_idempotency_edges() -> None:
    adapter = FakePlatformAdapter()
    author = await adapter.resolve_author(account(), "creator-001")

    first = await adapter.fetch_author_page(account(), author, None, limit=2)
    replay = await adapter.fetch_author_page(account(), author, None, limit=2)
    second = await adapter.fetch_author_page(account(), author, first.next_cursor, limit=2)

    assert first == replay
    assert first.has_more and first.next_cursor is not None
    assert second.items[0].remote_id == first.items[-1].remote_id
    assert second.items[1].remote_id != second.items[0].remote_id
    assert second.items[1].published_at == second.items[0].published_at


@pytest.mark.asyncio
async def test_last_page_has_no_cursor() -> None:
    adapter = FakePlatformAdapter()
    author = await adapter.resolve_author(account(), "creator-001")

    page = await adapter.fetch_author_page(account(), author, None, limit=1_000)
    assert len(page.items) == 5
    assert not page.has_more
    assert page.next_cursor is None


@pytest.mark.asyncio
async def test_cursor_is_scoped_to_fake_platform_and_author() -> None:
    adapter = FakePlatformAdapter()
    author = await adapter.resolve_author(account(), "creator-001")

    with pytest.raises(DomainValidationError, match="does not belong"):
        await adapter.fetch_author_page(
            account(),
            author,
            Cursor("fake:v1:xhs:creator-001:2"),
            limit=2,
        )


@pytest.mark.asyncio
async def test_asset_resolution_is_ordered_and_replayable() -> None:
    adapter = FakePlatformAdapter()
    author = await adapter.resolve_author(account(), "creator-001")
    page = await adapter.fetch_author_page(account(), author, None, limit=2)
    content = page.items[-1]

    first = await adapter.resolve_assets(account(), content)
    second = await adapter.resolve_assets(account(), content)
    assert first == second
    assert tuple(asset.position for asset in first) == (0,)
    assert all(asset.content_remote_id == content.remote_id for asset in first)
