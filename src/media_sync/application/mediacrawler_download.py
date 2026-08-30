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

from media_sync.domain import AssetKind, AuthStatus, LoginMethod, Platform
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
from media_sync.integrations.mediacrawler.subscription_policy import (
    MediaCrawlerSubscriptionPolicyError,
    from_subscription_policy,
)
from media_sync.media import (
    AdapterRefreshLocator,
    MediaDownloadError,
    ResolvedLocator,
    parse_locator,
)
from media_sync.security import SecretError, SecretResolver


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

        delegate = self._delegate
        if delegate is None:
            with self._lock:
                delegate = self._delegate
                if delegate is None:
                    delegate = self._build()
                    self._delegate = delegate
        try:
            return delegate.resolve(locator)
        except MediaDownloadError as error:
            if error.code == "locator_refresh_auth_expired":
                self._record_saved_session_expiry()
            raise

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
            locator = parse_locator(asset.locator)
            if not isinstance(locator, AdapterRefreshLocator) or locator.adapter != "mediacrawler":
                raise MediaDownloadError("locator_refresh_source_mismatch")
            source_hint = asset_source_hint(asset.source_url)
            if source_hint is None or source_hint != asset.source_url:
                raise MediaDownloadError("locator_refresh_configuration_invalid")

            cookie = None
            if login_method is LoginMethod.COOKIE:
                if account.credential_ref is None:
                    raise MediaDownloadError("locator_refresh_credentials_unavailable")
                cookie = self._secret_resolver.resolve(account.credential_ref)

            detail_reference = None
            if self._detail_reference_ref is not None:
                if platform is not Platform.XHS:
                    raise MediaDownloadError("locator_refresh_configuration_invalid")
                detail_reference = self._secret_resolver.resolve(self._detail_reference_ref)

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
                    detail_reference=detail_reference,
                    cookie=cookie,
                    headless=policy.headless,
                    request_delay_seconds=policy.request_delay_seconds,
                )
            except MediaDownloadError:
                raise
            except (TypeError, ValueError) as exc:
                raise MediaDownloadError("locator_refresh_configuration_invalid") from exc


__all__ = ["LazyMediaCrawlerLocatorRefresher"]
