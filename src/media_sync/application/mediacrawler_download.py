"""Lazy database-bound MediaCrawler locator refresh for asset downloads.

The application downloader can recover an already-published archive without
network access.  This adapter therefore delays database selection, secret
resolution and child-process construction until the downloader actually asks
for a signed locator.
"""

from __future__ import annotations

import contextlib
from pathlib import Path
from threading import Lock
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import joinedload

from media_sync.domain import AssetKind, AuthStatus, ContentKind, LoginMethod, Platform
from media_sync.infrastructure.db import (
    AccountRepository,
    AssetRefreshSourceRepository,
    Database,
    RepositoryError,
)
from media_sync.infrastructure.db.asset_identity import asset_source_hint
from media_sync.infrastructure.db.models import Asset, Content
from media_sync.integrations.mediacrawler import (
    MediaCrawlerDetailProcessRunner,
    MediaCrawlerLocatorRefresher,
    MediaCrawlerRefreshContext,
)
from media_sync.integrations.mediacrawler.bilibili_media import (
    BILIBILI_MAX_PAGES,
    bilibili_video_cid,
)
from media_sync.integrations.mediacrawler.subscription_policy import (
    MediaCrawlerSubscriptionPolicyError,
    from_subscription_policy,
)
from media_sync.integrations.mediacrawler.tieba_media import (
    TIEBA_MAX_GALLERY_IMAGES,
    validate_tieba_image_source_hint,
    validate_tieba_thread_url,
)
from media_sync.integrations.mediacrawler.zhihu_media import validate_zhihu_answer_url, validate_zhihu_image_url
from media_sync.media import (
    AdapterRefreshLocator,
    MediaDownloadError,
    ResolvedLocator,
    parse_locator,
)
from media_sync.security import SecretError, SecretResolver, SecretValue


class LazyMediaCrawlerLocatorRefresher:
    """Resolve one asset through its exact current subscription observation."""

    def __init__(
        self,
        database: Database,
        *,
        asset_id: UUID,
        lock_path: Path,
        integration_root: Path,
        python_executable: Path | None,
        secret_resolver: SecretResolver,
        license_acknowledged: bool,
        subscription_id: UUID | None = None,
        detail_reference_ref: str | None = None,
    ) -> None:
        if not isinstance(asset_id, UUID) or (subscription_id is not None and not isinstance(subscription_id, UUID)):
            raise ValueError("asset_id and subscription_id must be UUIDs")
        if type(license_acknowledged) is not bool:
            raise ValueError("license_acknowledged must be boolean")
        self._database = database
        self._asset_id = asset_id
        self._subscription_id = subscription_id
        self._lock_path = lock_path
        self._integration_root = integration_root
        self._python_executable = python_executable
        self._secret_resolver = secret_resolver
        self._license_acknowledged = license_acknowledged
        self._detail_reference_ref = detail_reference_ref
        self._delegate: MediaCrawlerLocatorRefresher | None = None
        self._saved_session_account_id: UUID | None = None
        self._lock = Lock()

    def resolve(self, locator: AdapterRefreshLocator) -> ResolvedLocator:
        """Build the bound refresher once, then allow its one-retry caller."""

        delegate = self._bound_delegate()
        try:
            return delegate.resolve(locator)
        except MediaDownloadError as error:
            if error.code == "locator_refresh_auth_expired":
                self._record_saved_session_expiry()
            raise

    def preflight(self) -> None:
        """Bind exact durable scope and secrets without starting child or Job work."""

        self._bound_delegate()

    def _bound_delegate(self) -> MediaCrawlerLocatorRefresher:
        delegate = self._delegate
        if delegate is not None:
            return delegate
        with self._lock:
            delegate = self._delegate
            if delegate is None:
                delegate = self._build()
                self._delegate = delegate
        return delegate

    def _build(self) -> MediaCrawlerLocatorRefresher:
        if self._python_executable is None or not self._license_acknowledged:
            raise MediaDownloadError("locator_refresh_configuration_invalid")
        try:
            context = self._load_context()
        except MediaDownloadError:
            raise
        except SecretError as exc:
            raise MediaDownloadError("locator_refresh_credentials_unavailable") from exc
        except SQLAlchemyError as exc:
            raise MediaDownloadError("locator_refresh_temporary") from exc
        except (MediaCrawlerSubscriptionPolicyError, RepositoryError, TypeError, ValueError) as exc:
            raise MediaDownloadError("locator_refresh_configuration_invalid") from exc

        runner = MediaCrawlerDetailProcessRunner(
            lock_path=self._lock_path,
            integration_root=self._integration_root,
            python_executable=self._python_executable,
            license_acknowledged=self._license_acknowledged,
        )
        if context.login_method is LoginMethod.SAVED_SESSION:
            self._saved_session_account_id = context.account_id
        return MediaCrawlerLocatorRefresher(context, runner)

    def _record_saved_session_expiry(self) -> None:
        account_id = self._saved_session_account_id
        if account_id is None:
            return
        # The fixed download error remains authoritative even if a concurrent
        # account update wins this best-effort authentication-state CAS.
        with contextlib.suppress(Exception), self._database.session() as session:
            account = AccountRepository(session).require(str(account_id))
            if (
                account.adapter == "mediacrawler"
                and account.login_method == LoginMethod.SAVED_SESSION.value
                and account.auth_status == AuthStatus.AUTHENTICATED.value
            ):
                AccountRepository(session).set_auth_status(
                    account.id,
                    AuthStatus.EXPIRED.value,
                    expected_status=AuthStatus.AUTHENTICATED.value,
                )

    def _load_context(self) -> MediaCrawlerRefreshContext:
        with self._database.session() as session:
            asset = session.scalar(
                select(Asset)
                .where(Asset.id == str(self._asset_id))
                .options(joinedload(Asset.content).joinedload(Content.author))
            )
            if asset is None:
                raise MediaDownloadError("locator_refresh_asset_not_found")

            sources = AssetRefreshSourceRepository(session).list_eligible(asset.id)
            if self._subscription_id is None:
                if not sources:
                    raise MediaDownloadError("locator_refresh_source_unavailable")
                if len(sources) != 1:
                    raise MediaDownloadError("locator_refresh_source_ambiguous")
                source = sources[0]
            else:
                selected = [item for item in sources if item.subscription_id == str(self._subscription_id)]
                if len(selected) != 1:
                    raise MediaDownloadError("locator_refresh_source_mismatch")
                source = selected[0]

            subscription = source.subscription
            account = subscription.account
            content = asset.content
            author = content.author
            policy = from_subscription_policy(subscription.policy)
            platform = Platform(asset.platform)
            if account.login_method is None:
                raise MediaDownloadError("locator_refresh_configuration_invalid")
            login_method = LoginMethod(account.login_method)
            asset_kind = AssetKind(asset.kind)
            bili_video_remote_ids: tuple[str, ...] = ()
            tieba_image_source_hints: tuple[str, ...] = ()
            locator = parse_locator(asset.locator)
            if not isinstance(locator, AdapterRefreshLocator) or locator.adapter != "mediacrawler":
                raise MediaDownloadError("locator_refresh_source_mismatch")
            if platform is Platform.ZHIHU:
                if type(asset.source_url) is not str:
                    raise MediaDownloadError("locator_refresh_configuration_invalid")
                try:
                    validate_zhihu_image_url(asset.source_url)
                except ValueError as exc:
                    raise MediaDownloadError("locator_refresh_configuration_invalid") from exc
            if platform is Platform.TIEBA:
                if type(asset.source_url) is not str:
                    raise MediaDownloadError("locator_refresh_configuration_invalid")
                try:
                    validate_tieba_image_source_hint(asset.source_url)
                except ValueError as exc:
                    raise MediaDownloadError("locator_refresh_configuration_invalid") from exc
                tieba_assets = tuple(
                    session.scalars(
                        select(Asset).where(Asset.content_id == content.id).order_by(Asset.position, Asset.id)
                    ).all()
                )
                if (
                    not 1 <= len(tieba_assets) <= TIEBA_MAX_GALLERY_IMAGES
                    or asset.position >= len(tieba_assets)
                    or tieba_assets[asset.position].id != asset.id
                ):
                    raise MediaDownloadError("locator_refresh_configuration_invalid")
                hints: list[str] = []
                for position, sibling in enumerate(tieba_assets):
                    if (
                        sibling.platform != Platform.TIEBA.value
                        or sibling.kind != AssetKind.IMAGE.value
                        or sibling.position != position
                        or sibling.remote_id != f"{content.remote_id}:image:{position}"
                        or type(sibling.source_url) is not str
                    ):
                        raise MediaDownloadError("locator_refresh_configuration_invalid")
                    try:
                        hint = validate_tieba_image_source_hint(sibling.source_url)
                    except ValueError as exc:
                        raise MediaDownloadError("locator_refresh_configuration_invalid") from exc
                    hints.append(hint)
                if len(set(hints)) != len(hints):
                    raise MediaDownloadError("locator_refresh_configuration_invalid")
                tieba_image_source_hints = tuple(hints)
            bili_video_slot = (
                platform is Platform.BILI and content.remote_type == "content" and asset_kind is AssetKind.VIDEO
            )
            if bili_video_slot:
                bili_assets = tuple(
                    session.scalars(
                        select(Asset)
                        .where(Asset.content_id == content.id, Asset.kind == AssetKind.VIDEO.value)
                        .order_by(Asset.position, Asset.id)
                    ).all()
                )
                if (
                    not 1 <= len(bili_assets) <= BILIBILI_MAX_PAGES
                    or asset.position >= len(bili_assets)
                    or bili_assets[asset.position].id != asset.id
                ):
                    raise MediaDownloadError("locator_refresh_configuration_invalid")
                remote_ids: list[str] = []
                cids: list[int | None] = []
                for position, sibling in enumerate(bili_assets):
                    if (
                        sibling.platform != Platform.BILI.value
                        or sibling.kind != AssetKind.VIDEO.value
                        or sibling.position != position
                        or type(sibling.remote_id) is not str
                        or sibling.source_url is not None
                    ):
                        raise MediaDownloadError("locator_refresh_configuration_invalid")
                    try:
                        cid = bilibili_video_cid(content.remote_id, sibling.remote_id)
                    except ValueError as exc:
                        raise MediaDownloadError("locator_refresh_configuration_invalid") from exc
                    remote_ids.append(sibling.remote_id)
                    cids.append(cid)
                if (len(cids) == 1 and cids != [None]) or (
                    len(cids) > 1 and (any(cid is None for cid in cids) or len(set(cids)) != len(cids))
                ):
                    raise MediaDownloadError("locator_refresh_configuration_invalid")
                bili_video_remote_ids = tuple(remote_ids)
            source_hint = asset_source_hint(asset.source_url)
            locator_only_bili_video = bili_video_slot and bool(bili_video_remote_ids) and asset.source_url is None
            if source_hint is None:
                if asset.source_url is not None or not locator_only_bili_video:
                    raise MediaDownloadError("locator_refresh_configuration_invalid")
            elif source_hint != asset.source_url:
                raise MediaDownloadError("locator_refresh_configuration_invalid")
            if bili_video_slot and not locator_only_bili_video:
                raise MediaDownloadError("locator_refresh_configuration_invalid")

            cookie = None
            if login_method is LoginMethod.COOKIE:
                if account.credential_ref is None:
                    raise MediaDownloadError("locator_refresh_credentials_unavailable")
                cookie = self._secret_resolver.resolve(account.credential_ref)

            detail_reference: str | SecretValue | None = None
            creator_reference = None
            creator_max_items = None
            if platform is Platform.XHS:
                if self._detail_reference_ref is not None:
                    detail_reference = self._secret_resolver.resolve(self._detail_reference_ref)
                else:
                    if policy.creator_secret_ref is None:
                        raise MediaDownloadError("locator_refresh_authority_required")
                    creator_reference = self._secret_resolver.resolve(policy.creator_secret_ref)
                    creator_max_items = subscription.max_items
            elif platform is Platform.ZHIHU:
                if self._detail_reference_ref is not None:
                    raise MediaDownloadError("locator_refresh_configuration_invalid")
                if (
                    content.kind != ContentKind.ARTICLE.value
                    or content.remote_type != "content"
                    or type(content.canonical_url) is not str
                ):
                    raise MediaDownloadError("locator_refresh_configuration_invalid")
                detail_reference = validate_zhihu_answer_url(
                    content.canonical_url,
                    answer_id=content.remote_id,
                )
            elif platform is Platform.TIEBA:
                if self._detail_reference_ref is not None:
                    raise MediaDownloadError("locator_refresh_configuration_invalid")
                if (
                    content.kind != ContentKind.ARTICLE.value
                    or content.remote_type != "content"
                    or type(content.canonical_url) is not str
                ):
                    raise MediaDownloadError("locator_refresh_configuration_invalid")
                detail_reference = validate_tieba_thread_url(
                    content.canonical_url,
                    note_id=content.remote_id,
                )
            elif self._detail_reference_ref is not None:
                raise MediaDownloadError("locator_refresh_configuration_invalid")

            try:
                return MediaCrawlerRefreshContext(
                    asset_id=UUID(asset.id),
                    account_id=UUID(account.id),
                    subscription_id=UUID(subscription.id),
                    platform=platform,
                    login_method=login_method,
                    content_remote_type=content.remote_type,
                    content_remote_id=content.remote_id,
                    author_remote_id=author.remote_id,
                    author_display_name=author.display_name,
                    asset_remote_id=asset.remote_id,
                    asset_kind=asset_kind,
                    asset_position=asset.position,
                    source_hint=source_hint,
                    locator=locator,
                    bili_video_remote_ids=bili_video_remote_ids,
                    tieba_image_source_hints=tieba_image_source_hints,
                    detail_reference=detail_reference,
                    creator_reference=creator_reference,
                    creator_max_items=creator_max_items,
                    cookie=cookie,
                    headless=policy.headless,
                    request_delay_seconds=policy.request_delay_seconds,
                )
            except MediaDownloadError:
                raise
            except (TypeError, ValueError) as exc:
                raise MediaDownloadError("locator_refresh_configuration_invalid") from exc


__all__ = ["LazyMediaCrawlerLocatorRefresher"]
