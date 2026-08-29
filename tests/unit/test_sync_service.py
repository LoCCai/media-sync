from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from uuid import UUID, uuid5

import pytest

from media_sync.adapters.fake import FakePlatformAdapter
from media_sync.application import SyncRequest, SyncService
from media_sync.domain import (
    AccountRef,
    AssetSnapshot,
    AuthorSnapshot,
    ContentSnapshot,
    Cursor,
    DomainValidationError,
    LoginMethod,
    Page,
    Platform,
    RateLimitedError,
    RunStatus,
)

NAMESPACE = UUID("00000000-0000-0000-0000-000000000099")
ACCOUNT_ID = UUID("00000000-0000-0000-0000-000000000001")
SUBSCRIPTION_ID = UUID("00000000-0000-0000-0000-000000000002")


class MemorySyncRepository:
    def __init__(self) -> None:
        self.authors: dict[tuple[Platform, str], AuthorSnapshot] = {}
        self.contents: dict[tuple[Platform, str], ContentSnapshot] = {}
        self.assets: dict[tuple[Platform, str, int], AssetSnapshot] = {}
        self.runs: dict[UUID, RunStatus] = {}
        self.transitions: list[tuple[UUID, RunStatus]] = []
        self.errors: list[tuple[str | None, str | None]] = []
        self.cursor: Cursor | None = None
        self.watermark: datetime | None = None

    def upsert_author(self, snapshot: AuthorSnapshot) -> UUID:
        self.authors[(snapshot.platform, snapshot.remote_id)] = snapshot
        return uuid5(NAMESPACE, f"author:{snapshot.platform}:{snapshot.remote_id}")

    def upsert_content_with_assets(
        self,
        snapshot: ContentSnapshot,
        assets: Sequence[AssetSnapshot],
    ) -> UUID:
        self.contents[(snapshot.platform, snapshot.remote_id)] = snapshot
        for asset in assets:
            self.assets[(asset.platform, asset.remote_id, asset.position)] = asset
        return uuid5(NAMESPACE, f"content:{snapshot.platform}:{snapshot.remote_id}")

    def create_run(self, subscription_id: UUID, manifest: Mapping[str, object] | None = None) -> UUID:
        run_id = uuid5(NAMESPACE, f"run:{subscription_id}:{len(self.runs)}")
        self.runs[run_id] = RunStatus.QUEUED
        return run_id

    def transition_run(
        self,
        run_id: UUID,
        target: RunStatus,
        *,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> None:
        self.runs[run_id] = target
        self.transitions.append((run_id, target))
        self.errors.append((error_code, error_message))

    def advance_cursor(
        self,
        subscription_id: UUID,
        cursor: Cursor | None,
        *,
        watermark: datetime | None = None,
    ) -> None:
        assert subscription_id == SUBSCRIPTION_ID
        self.cursor = cursor
        self.watermark = watermark


def account(login_method: LoginMethod = LoginMethod.COOKIE) -> AccountRef:
    return AccountRef(
        account_id=ACCOUNT_ID,
        platform=Platform.BILI,
        login_method=login_method,
        adapter="fake",
        credential_ref="keyring:test-account",
    )


@pytest.mark.asyncio
async def test_sync_is_bounded_and_repository_state_is_idempotent() -> None:
    repository = MemorySyncRepository()
    service = SyncService(FakePlatformAdapter(), repository)
    request = SyncRequest(
        subscription_id=SUBSCRIPTION_ID,
        account=account(),
        creator_reference="creator-001",
        max_items=4,
        page_size=2,
    )

    first = await service.run(request)
    second = await service.run(request)

    assert first.status is RunStatus.SUCCEEDED
    assert second.status is RunStatus.SUCCEEDED
    assert first.processed_count == second.processed_count == 4
    assert len(repository.authors) == 1
    assert len(repository.contents) == 4
    assert len(repository.assets) == 4
    assert repository.watermark is not None


@pytest.mark.asyncio
async def test_qr_sync_waits_for_interaction_without_resolving_content() -> None:
    repository = MemorySyncRepository()
    service = SyncService(FakePlatformAdapter(), repository)
    request = SyncRequest(
        subscription_id=SUBSCRIPTION_ID,
        account=account(LoginMethod.QR),
        creator_reference="creator-001",
    )

    result = await service.run(request)

    assert result.status is RunStatus.AWAITING_AUTH
    assert repository.authors == {}
    assert repository.contents == {}
    assert [target for _run_id, target in repository.transitions] == [RunStatus.CLAIMED, RunStatus.AWAITING_AUTH]


@pytest.mark.asyncio
async def test_platform_mismatch_fails_before_a_run_is_created() -> None:
    repository = MemorySyncRepository()
    service = SyncService(FakePlatformAdapter(Platform.XHS), repository)
    request = SyncRequest(
        subscription_id=SUBSCRIPTION_ID,
        account=account(),
        creator_reference="creator-001",
    )

    with pytest.raises(DomainValidationError, match="adapter platform"):
        await service.run(request)
    assert repository.runs == {}


@pytest.mark.asyncio
async def test_unsupported_login_fails_before_a_run_is_created() -> None:
    repository = MemorySyncRepository()
    service = SyncService(FakePlatformAdapter(), repository)
    request = SyncRequest(
        subscription_id=SUBSCRIPTION_ID,
        account=account(LoginMethod.PHONE),
        creator_reference="creator-001",
    )

    with pytest.raises(DomainValidationError, match="login method"):
        await service.run(request)
    assert repository.runs == {}


@pytest.mark.asyncio
async def test_rate_limit_is_classified_as_retryable_without_leaking_message() -> None:
    class RateLimitedFake(FakePlatformAdapter):
        async def fetch_author_page(
            self,
            account: AccountRef,
            author: AuthorSnapshot,
            cursor: Cursor | None,
            *,
            limit: int,
        ) -> Page[ContentSnapshot]:
            del account, author, cursor, limit
            raise RateLimitedError("bili", retry_after=30, message="sentinel-secret signed URL")

    repository = MemorySyncRepository()
    service = SyncService(RateLimitedFake(), repository)
    request = SyncRequest(
        subscription_id=SUBSCRIPTION_ID,
        account=account(),
        creator_reference="creator-001",
    )

    result = await service.run(request)

    assert result.status is RunStatus.FAILED_RETRYABLE
    assert result.error_code == "rate_limited"
    assert result.retry_after_seconds == 30
    assert "sentinel-secret" not in repr(repository.errors)


@pytest.mark.asyncio
async def test_oversized_adapter_page_fails_before_any_content_is_persisted() -> None:
    class OversizedFake(FakePlatformAdapter):
        async def fetch_author_page(
            self,
            account: AccountRef,
            author: AuthorSnapshot,
            cursor: Cursor | None,
            *,
            limit: int,
        ) -> Page[ContentSnapshot]:
            del limit
            return await super().fetch_author_page(account, author, cursor, limit=2)

    repository = MemorySyncRepository()
    result = await SyncService(OversizedFake(), repository).run(
        SyncRequest(
            subscription_id=SUBSCRIPTION_ID,
            account=account(),
            creator_reference="creator-001",
            max_items=1,
            page_size=1,
        )
    )

    assert result.status is RunStatus.FAILED_TERMINAL
    assert result.error_code == "domain_validation"
    assert repository.contents == {}


@pytest.mark.asyncio
async def test_repeated_next_cursor_fails_even_when_page_reaches_item_cap() -> None:
    class RepeatedCursorFake(FakePlatformAdapter):
        async def fetch_author_page(
            self,
            account: AccountRef,
            author: AuthorSnapshot,
            cursor: Cursor | None,
            *,
            limit: int,
        ) -> Page[ContentSnapshot]:
            page = await super().fetch_author_page(account, author, cursor, limit=limit)
            if cursor is None:
                return page
            return Page(page.items, next_cursor=cursor, has_more=True)

    repository = MemorySyncRepository()
    result = await SyncService(RepeatedCursorFake(), repository).run(
        SyncRequest(
            subscription_id=SUBSCRIPTION_ID,
            account=account(),
            creator_reference="creator-001",
            max_items=2,
            page_size=1,
        )
    )

    assert result.status is RunStatus.FAILED_TERMINAL
    assert result.error_code == "domain_validation"
    assert len(repository.contents) == 1
    assert repository.cursor is None
