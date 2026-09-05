from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from uuid import UUID, uuid5

import pytest

from media_sync.adapters.fake import FakePlatformAdapter
from media_sync.application import SyncRequest, SyncService
from media_sync.domain import (
    AccountRef,
    AdapterError,
    AssetSnapshot,
    AuthorSnapshot,
    ContentSnapshot,
    Cursor,
    DomainError,
    DomainValidationError,
    LoginMethod,
    Page,
    Platform,
    RateLimitedError,
    RunStatus,
)
from media_sync.infrastructure.db import ContentOwnershipConflictError, LeaseLostError

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


@pytest.mark.asyncio
async def test_short_transaction_hooks_guard_every_mutation_and_external_await() -> None:
    events: list[str] = []

    class ObservedRepository(MemorySyncRepository):
        def upsert_author(self, snapshot: AuthorSnapshot) -> UUID:
            events.append("persist:author")
            return super().upsert_author(snapshot)

        def upsert_content_with_assets(
            self,
            snapshot: ContentSnapshot,
            assets: Sequence[AssetSnapshot],
        ) -> UUID:
            events.append("persist:content")
            return super().upsert_content_with_assets(snapshot, assets)

        def create_run(self, subscription_id: UUID, manifest: Mapping[str, object] | None = None) -> UUID:
            events.append("persist:create_run")
            return super().create_run(subscription_id, manifest)

        def transition_run(
            self,
            run_id: UUID,
            target: RunStatus,
            *,
            error_code: str | None = None,
            error_message: str | None = None,
        ) -> None:
            events.append(f"persist:transition:{target.value}")
            super().transition_run(
                run_id,
                target,
                error_code=error_code,
                error_message=error_message,
            )

        def advance_cursor(
            self,
            subscription_id: UUID,
            cursor: Cursor | None,
            *,
            watermark: datetime | None = None,
        ) -> None:
            events.append("persist:cursor")
            super().advance_cursor(subscription_id, cursor, watermark=watermark)

    class ObservedAdapter(FakePlatformAdapter):
        async def ensure_session(self, account: AccountRef, interaction: object | None = None) -> object:
            events.append("await:ensure_session")
            return await super().ensure_session(account, interaction)  # type: ignore[arg-type]

        async def resolve_author(self, account: AccountRef, reference: str) -> AuthorSnapshot:
            events.append("await:resolve_author")
            return await super().resolve_author(account, reference)

        async def fetch_author_page(
            self,
            account: AccountRef,
            author: AuthorSnapshot,
            cursor: Cursor | None,
            *,
            limit: int,
        ) -> Page[ContentSnapshot]:
            events.append("await:fetch_author_page")
            return await super().fetch_author_page(account, author, cursor, limit=limit)

        async def resolve_assets(
            self,
            account: AccountRef,
            content: ContentSnapshot,
        ) -> Sequence[AssetSnapshot]:
            events.append("await:resolve_assets")
            return await super().resolve_assets(account, content)

    result = await SyncService(ObservedAdapter(), ObservedRepository()).run(
        SyncRequest(
            subscription_id=SUBSCRIPTION_ID,
            account=account(),
            creator_reference="creator-001",
            max_items=1,
            page_size=1,
        ),
        persistence_guard=lambda: events.append("guard"),
        external_io_boundary=lambda: events.append("boundary"),
    )

    assert result.status is RunStatus.SUCCEEDED
    persist_indexes = [index for index, event in enumerate(events) if event.startswith("persist:")]
    await_indexes = [index for index, event in enumerate(events) if event.startswith("await:")]
    assert len(persist_indexes) == 8
    assert len(await_indexes) == 4
    assert all(events[index - 1] == "guard" for index in persist_indexes)
    assert all(events[index - 1] == "boundary" for index in await_indexes)


@pytest.mark.asyncio
async def test_ownership_guard_loss_escapes_without_a_followup_failure_write() -> None:
    repository = MemorySyncRepository()
    guard_calls = 0

    def lose_before_author_persistence() -> None:
        nonlocal guard_calls
        guard_calls += 1
        if guard_calls == 4:
            raise LeaseLostError("test lease was lost")

    with pytest.raises(LeaseLostError, match="lease was lost"):
        await SyncService(FakePlatformAdapter(), repository).run(
            SyncRequest(
                subscription_id=SUBSCRIPTION_ID,
                account=account(),
                creator_reference="creator-001",
                max_items=1,
                page_size=1,
            ),
            persistence_guard=lose_before_author_persistence,
        )

    assert guard_calls == 4
    assert repository.authors == {}
    assert repository.contents == {}
    assert [target for _run_id, target in repository.transitions] == [
        RunStatus.CLAIMED,
        RunStatus.RUNNING,
    ]


@pytest.mark.asyncio
async def test_hostile_custom_adapter_error_is_mapped_before_persistence() -> None:
    sentinel = "SENTINEL-custom-adapter-code-C:/private/cookie.txt"

    class HostileAdapter(FakePlatformAdapter):
        async def resolve_author(self, account: AccountRef, reference: str) -> AuthorSnapshot:
            del account, reference
            raise AdapterError(
                sentinel,
                f"raw message {sentinel}",
                platform="bili",
                retryable=True,
            )

    repository = MemorySyncRepository()
    result = await SyncService(HostileAdapter(), repository).run(
        SyncRequest(
            subscription_id=SUBSCRIPTION_ID,
            account=account(),
            creator_reference="creator-001",
        )
    )

    assert result.status is RunStatus.FAILED_RETRYABLE
    assert result.error_code == "unexpected_failure"
    assert sentinel not in repr((result, repository.errors))
    assert repository.errors[-1] == (
        "unexpected_failure",
        "The adapter reported a classified synchronization failure.",
    )


@pytest.mark.asyncio
async def test_content_owner_conflict_is_fixed_terminal_without_checkpoint_or_assets() -> None:
    class ConflictingRepository(MemorySyncRepository):
        def upsert_content_with_assets(self, snapshot: ContentSnapshot, assets: Sequence[AssetSnapshot]) -> UUID:
            error = ContentOwnershipConflictError()
            # Even the typed exception's mutable attributes are not public data.
            error.code = "PRIVATE-owner-source-cookie"
            error.args = ("PRIVATE-owner-source-cookie",)
            raise error

    repository = ConflictingRepository()
    result = await SyncService(FakePlatformAdapter(), repository).run(
        SyncRequest(subscription_id=SUBSCRIPTION_ID, account=account(), creator_reference="creator-001")
    )
    assert result.status is RunStatus.FAILED_TERMINAL
    assert result.error_code == "content_ownership_conflict"
    assert repository.cursor is None and repository.watermark is None
    assert repository.contents == {} and repository.assets == {}
    assert repository.errors[-1][0] == "content_ownership_conflict"
    assert "PRIVATE" not in repr((result, repository.errors))


@pytest.mark.asyncio
async def test_hostile_adapter_code_preserves_fixed_interaction_disposition() -> None:
    sentinel = "SENTINEL-custom-interaction-code-C:/private/challenge.txt"

    class HostileInteractionAdapter(FakePlatformAdapter):
        async def resolve_author(self, account: AccountRef, reference: str) -> AuthorSnapshot:
            del account, reference
            raise AdapterError(
                sentinel,
                f"raw message {sentinel}",
                platform="bili",
                retryable=False,
                requires_interaction=True,
            )

    repository = MemorySyncRepository()
    result = await SyncService(HostileInteractionAdapter(), repository).run(
        SyncRequest(
            subscription_id=SUBSCRIPTION_ID,
            account=account(),
            creator_reference="creator-001",
        )
    )

    assert result.status is RunStatus.AWAITING_AUTH
    assert result.error_code == "interactive_challenge_required"
    assert sentinel not in repr((result, repository.errors))
    assert repository.errors[-1] == (
        "interactive_challenge_required",
        "The adapter reported a classified synchronization failure.",
    )


@pytest.mark.asyncio
async def test_hostile_custom_domain_error_is_mapped_before_persistence() -> None:
    sentinel = "SENTINEL-custom-domain-code-C:/private/session.json"

    class HostileDomainAdapter(FakePlatformAdapter):
        async def resolve_author(self, account: AccountRef, reference: str) -> AuthorSnapshot:
            del account, reference
            raise DomainError(sentinel, f"raw message {sentinel}")

    repository = MemorySyncRepository()
    result = await SyncService(HostileDomainAdapter(), repository).run(
        SyncRequest(
            subscription_id=SUBSCRIPTION_ID,
            account=account(),
            creator_reference="creator-001",
        )
    )

    assert result.status is RunStatus.FAILED_TERMINAL
    assert result.error_code == "unexpected_failure"
    assert sentinel not in repr((result, repository.errors))
    assert repository.errors[-1] == (
        "unexpected_failure",
        "Synchronization stopped after a classified domain failure.",
    )
