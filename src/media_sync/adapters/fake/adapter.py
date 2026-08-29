"""Deterministic, network-free platform adapter used by tests and demos."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from urllib.parse import urlparse

from media_sync.domain import (
    AccountRef,
    AssetKind,
    AssetSnapshot,
    AuthChallenge,
    AuthorSnapshot,
    AuthResult,
    AuthStatus,
    CapabilitySet,
    ContentKind,
    ContentSnapshot,
    CreatorReferenceKind,
    Cursor,
    DomainValidationError,
    EntityNotFoundError,
    LoginMethod,
    Page,
    Platform,
    UnsupportedCapabilityError,
)
from media_sync.ports import InteractionPort

_FIXTURE_TIME = datetime(2026, 8, 30, 0, 0, tzinfo=UTC)


class FakePlatformAdapter:
    """A deterministic adapter that deliberately emits realistic idempotency edges."""

    name = "fake"

    def __init__(
        self,
        platform: Platform = Platform.BILI,
        *,
        author: AuthorSnapshot | None = None,
        contents: Sequence[ContentSnapshot] | None = None,
        assets: Mapping[str, Sequence[AssetSnapshot]] | None = None,
    ) -> None:
        self._platform = platform
        self._author = author or self._build_author(platform)
        self._contents = tuple(contents) if contents is not None else self._build_contents(platform)
        default_assets = self._build_assets(platform, self._contents)
        selected_assets = assets if assets is not None else default_assets
        self._assets = {remote_id: tuple(items) for remote_id, items in selected_assets.items()}
        self._auth_states: dict[str, AuthStatus] = {}
        self._validate_fixtures()

    @staticmethod
    def _build_author(platform: Platform) -> AuthorSnapshot:
        return AuthorSnapshot(
            platform=platform,
            remote_id="creator-001",
            display_name="Fixture Creator / 测试作者",
            handle="fixture-creator",
            profile_url=f"https://fixture.invalid/{platform.value}/creator-001",
            avatar_url=f"https://fixture.invalid/{platform.value}/creator-001/avatar.jpg",
            raw={"fixture": {"version": 1}},
        )

    @staticmethod
    def _build_contents(platform: Platform) -> tuple[ContentSnapshot, ...]:
        def content(remote_id: str, title: str, kind: ContentKind, sequence: int) -> ContentSnapshot:
            return ContentSnapshot(
                platform=platform,
                remote_id=remote_id,
                author_remote_id="creator-001",
                kind=kind,
                title=title,
                body=f"Deterministic fixture body {sequence}",
                canonical_url=f"https://fixture.invalid/{platform.value}/content/{remote_id}",
                # Every fixture item intentionally shares one timestamp. Distinct
                # IDs therefore exercise deterministic tie-breaking.
                published_at=_FIXTURE_TIME,
                metrics={"likes": sequence},
                raw={"fixture_sequence": sequence},
            )

        duplicate = content("item-duplicate", "Boundary duplicate", ContentKind.VIDEO, 2)
        return (
            content("item-001", "First fixture item", ContentKind.GALLERY, 1),
            duplicate,
            duplicate,  # repeated ID crosses the default two-item page boundary
            content("item-003", "Same timestamp peer", ContentKind.ARTICLE, 3),
            content("item-004", "Final fixture item", ContentKind.MIXED, 4),
        )

    @staticmethod
    def _build_assets(
        platform: Platform,
        contents: Sequence[ContentSnapshot],
    ) -> dict[str, tuple[AssetSnapshot, ...]]:
        result: dict[str, tuple[AssetSnapshot, ...]] = {}
        for content in contents:
            if content.remote_id in result:
                continue
            if content.kind is ContentKind.VIDEO:
                kind = AssetKind.VIDEO
                suffix = "mp4"
                mime_type = "video/mp4"
            else:
                kind = AssetKind.IMAGE
                suffix = "jpg"
                mime_type = "image/jpeg"
            result[content.remote_id] = (
                AssetSnapshot(
                    platform=platform,
                    remote_id=f"{content.remote_id}-asset-000",
                    content_remote_id=content.remote_id,
                    kind=kind,
                    source_url=(f"https://fixture.invalid/{platform.value}/assets/{content.remote_id}/000.{suffix}"),
                    position=0,
                    mime_type=mime_type,
                    raw={"fixture": True},
                ),
            )
        return result

    def _validate_fixtures(self) -> None:
        if self._author.platform is not self._platform:
            raise DomainValidationError("fake author platform does not match adapter platform", field="author")
        for content in self._contents:
            if content.platform is not self._platform:
                raise DomainValidationError(
                    "fake content platform does not match adapter platform",
                    field="contents",
                )
            if content.author_remote_id != self._author.remote_id:
                raise DomainValidationError(
                    "fake content author does not match fixture author",
                    field="contents",
                )
        for content_remote_id, assets in self._assets.items():
            for asset in assets:
                if asset.platform is not self._platform or asset.content_remote_id != content_remote_id:
                    raise DomainValidationError(
                        "fake asset does not match its fixture content",
                        field="assets",
                    )

    def capabilities(self) -> CapabilitySet:
        return CapabilitySet(
            platform=self._platform,
            login_methods=frozenset({LoginMethod.QR, LoginMethod.COOKIE, LoginMethod.SAVED_SESSION}),
            creator_reference_kinds=frozenset({CreatorReferenceKind.REMOTE_ID, CreatorReferenceKind.PROFILE_URL}),
            content_kinds=frozenset(ContentKind),
            asset_kinds=frozenset(AssetKind),
            interactive_login_methods=frozenset({LoginMethod.QR}),
            supports_incremental_cursor=True,
        )

    def _validate_account(self, account: AccountRef) -> None:
        if account.platform is not self._platform:
            raise UnsupportedCapabilityError(
                self._platform.value,
                f"account platform {account.platform.value}",
            )

    async def auth_status(self, account: AccountRef) -> AuthStatus:
        self._validate_account(account)
        await asyncio.sleep(0)
        return self._auth_states.get(str(account.account_id), AuthStatus.UNKNOWN)

    async def ensure_session(
        self,
        account: AccountRef,
        interaction: InteractionPort | None = None,
    ) -> AuthResult:
        self._validate_account(account)
        capabilities = self.capabilities()
        if not capabilities.supports_login(account.login_method):
            raise UnsupportedCapabilityError(
                self._platform.value,
                f"login:{account.login_method.value}",
            )

        account_key = str(account.account_id)
        if capabilities.requires_interaction(account.login_method):
            if interaction is None:
                self._auth_states[account_key] = AuthStatus.REQUIRED
                await asyncio.sleep(0)
                return AuthResult(
                    status=AuthStatus.REQUIRED,
                    message="interactive approval required",
                )
            self._auth_states[account_key] = AuthStatus.AUTHENTICATING
            response = await interaction.request(
                AuthChallenge(
                    method=account.login_method,
                    prompt="Approve deterministic fake login",
                    payload={"verification_uri": "https://fixture.invalid/login/qr"},
                )
            )
            if response != "approved":
                self._auth_states[account_key] = AuthStatus.FAILED
                return AuthResult(status=AuthStatus.FAILED, message="fake login was not approved")

        await asyncio.sleep(0)
        self._auth_states[account_key] = AuthStatus.AUTHENTICATED
        return AuthResult(
            status=AuthStatus.AUTHENTICATED,
            session_ref=f"fake-session:{self._platform.value}:{account.account_id}",
        )

    async def resolve_author(self, account: AccountRef, reference: str) -> AuthorSnapshot:
        self._validate_account(account)
        normalized = reference.strip()
        if not normalized:
            raise DomainValidationError("creator reference must not be blank", field="reference")
        parsed = urlparse(normalized)
        candidate = parsed.path.rstrip("/").rsplit("/", maxsplit=1)[-1] if parsed.scheme else normalized
        await asyncio.sleep(0)
        if candidate != self._author.remote_id:
            raise EntityNotFoundError("author", reference)
        return self._author

    def _cursor_for_offset(self, offset: int) -> Cursor:
        return Cursor(f"fake:v1:{self._platform.value}:{self._author.remote_id}:{offset}")

    def _offset_from_cursor(self, cursor: Cursor | None) -> int:
        if cursor is None:
            return 0
        prefix = f"fake:v1:{self._platform.value}:{self._author.remote_id}:"
        if not cursor.value.startswith(prefix):
            raise DomainValidationError("cursor does not belong to this fake author", field="cursor")
        raw_offset = cursor.value.removeprefix(prefix)
        try:
            offset = int(raw_offset)
        except ValueError as error:
            raise DomainValidationError("fake cursor offset must be an integer", field="cursor") from error
        if offset < 0 or offset > len(self._contents):
            raise DomainValidationError("fake cursor offset is out of range", field="cursor")
        return offset

    async def fetch_author_page(
        self,
        account: AccountRef,
        author: AuthorSnapshot,
        cursor: Cursor | None,
        *,
        limit: int,
    ) -> Page[ContentSnapshot]:
        self._validate_account(account)
        if author != self._author:
            raise EntityNotFoundError("author", author.remote_id)
        if limit < 1 or limit > 1_000:
            raise DomainValidationError("limit must be between 1 and 1000", field="limit")
        offset = self._offset_from_cursor(cursor)
        end = min(offset + limit, len(self._contents))
        items = self._contents[offset:end]
        has_more = end < len(self._contents)
        next_cursor = self._cursor_for_offset(end) if has_more else None
        await asyncio.sleep(0)
        return Page(items, next_cursor=next_cursor, has_more=has_more)

    async def resolve_assets(
        self,
        account: AccountRef,
        content: ContentSnapshot,
    ) -> tuple[AssetSnapshot, ...]:
        self._validate_account(account)
        if content.platform is not self._platform:
            raise EntityNotFoundError("content", content.remote_id)
        await asyncio.sleep(0)
        return self._assets.get(content.remote_id, ())


class FakeInteraction:
    """Deterministic interaction helper for fake QR-login tests."""

    def __init__(self, response: str | None = "approved") -> None:
        self.response = response
        self.challenges: list[AuthChallenge] = []

    async def request(self, challenge: AuthChallenge) -> str | None:
        self.challenges.append(challenge)
        await asyncio.sleep(0)
        return self.response


__all__ = ["FakeInteraction", "FakePlatformAdapter"]
