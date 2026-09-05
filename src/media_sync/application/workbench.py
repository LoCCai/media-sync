"""Shared, redaction-safe account and subscription workbench use cases.

The CLI and REST API deliberately submit the same typed drafts here.  Drafts
are completely validated before a repository method that can mutate the
database is called.  Returned previews and results are immutable projections;
they never retain credential or creator-secret reference values.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Final
from uuid import UUID

from sqlalchemy.orm import Session

from media_sync.adapters.fake import FakePlatformAdapter
from media_sync.domain import LoginMethod, Platform
from media_sync.infrastructure.db import (
    Account,
    AccountRepository,
    Author,
    AuthorRepository,
    AuthorUpsert,
    Subscription,
    SubscriptionRepository,
)
from media_sync.infrastructure.db.creator_profile_repository import CreatorProfileError, CreatorProfileRepository
from media_sync.integrations.mediacrawler.capabilities import (
    MediaCrawlerCapabilityError,
    capability_for,
    normalize_creator_stable_id,
)
from media_sync.integrations.mediacrawler.subscription_policy import (
    SUBSCRIPTION_POLICY_SCHEMA_VERSION,
    MediaCrawlerSubscriptionPolicy,
    MediaCrawlerSubscriptionPolicyError,
)
from media_sync.security import InvalidSecretReferenceError, SecretReference

FAKE_ADAPTER: Final = "fake"
MEDIACRAWLER_ADAPTER: Final = "mediacrawler"
SUPPORTED_WORKBENCH_ADAPTERS: Final = frozenset({FAKE_ADAPTER, MEDIACRAWLER_ADAPTER})

_ERROR_MESSAGES: Final = {
    "adapter_not_supported": "the selected account adapter is not supported",
    "platform_not_supported": "the selected platform is not supported",
    "display_name_invalid": "display_name must be a bounded printable value",
    "login_method_not_supported": "the selected login method is not supported",
    "invalid_credential_reference": "credential_ref must be an opaque secret reference",
    "cookie_login_requires_credential_ref": "MediaCrawler Cookie login requires credential_ref",
    "credential_ref_allowed_only_for_cookie_login": ("credential_ref is allowed only for MediaCrawler Cookie login"),
    "account_exists_with_different_configuration": ("the account already exists with different login configuration"),
    "account_not_found": "the selected account was not found",
    "platform_conflict": "the account and creator platforms do not match",
    "creator_remote_id_must_be_stable_id": "creator_remote_id must be a stable non-secret ID",
    "creator_display_name_invalid": "creator display_name must be a bounded printable value",
    "creator_secret_ref_only_for_mediacrawler": ("creator_secret_ref is available only for MediaCrawler accounts"),
    "creator_secret_ref_not_supported": "the platform does not accept a creator secret reference",
    "invalid_creator_secret_reference": "creator_secret_ref must be an opaque secret reference",
    "full_history_acknowledgement_required": ("the platform requires explicit full-history acknowledgement"),
    "subscription_options_invalid": "subscription scheduling options are invalid",
    "mediacrawler_policy_options_require_mediacrawler": (
        "MediaCrawler scheduling policy options require a MediaCrawler account"
    ),
    "subscription_exists_with_different_options": ("the subscription already exists with different scheduling options"),
    "subscription_removed": "the subscription was removed; restore it explicitly before making changes",
    "creator_profile_receipt_invalid": "the creator profile receipt is no longer valid for this exact request",
    "creator_profile_receipt_expired": "the creator profile receipt has expired; perform a new lookup",
}
WORKBENCH_ERROR_CODES: Final = frozenset(_ERROR_MESSAGES)


class WorkbenchError(RuntimeError):
    """Fixed-code workbench rejection safe for every public output sink."""

    def __init__(self, code: str) -> None:
        try:
            message = _ERROR_MESSAGES[code]
        except KeyError as error:  # pragma: no cover - programmer error
            raise ValueError("unknown workbench error code") from error
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True, slots=True)
class AccountDraft:
    """Typed account input; an optional reference is intentionally repr-safe."""

    platform: Platform
    display_name: str
    login_method: LoginMethod = LoginMethod.QR
    adapter: str = MEDIACRAWLER_ADAPTER
    credential_ref: str | None = field(default=None, repr=False)


@dataclass(frozen=True, slots=True)
class AccountDraftPreview:
    """Safe normalized account draft returned without persistence."""

    platform: str
    adapter: str
    display_name: str
    login_method: str
    exists: bool

    def to_payload(self) -> dict[str, object]:
        return {
            "platform": self.platform,
            "adapter": self.adapter,
            "display_name": self.display_name,
            "login_method": self.login_method,
            "exists": self.exists,
        }


@dataclass(frozen=True, slots=True)
class AccountWorkbenchResult:
    """Safe projection of an idempotent account creation."""

    id: str
    platform: str
    adapter: str
    display_name: str
    login_method: str
    auth_status: str
    created_at: datetime
    created: bool
    auth_revision: int = 0

    def to_payload(self) -> dict[str, object]:
        return {
            "id": self.id,
            "platform": self.platform,
            "adapter": self.adapter,
            "display_name": self.display_name,
            "login_method": self.login_method,
            "auth_status": self.auth_status,
            "auth_revision": self.auth_revision,
            "created_at": self.created_at.isoformat(),
            "created": self.created,
        }


@dataclass(frozen=True, slots=True)
class SubscriptionDraft:
    """Typed creator-subscription input shared by API and CLI."""

    account_id: UUID
    platform: Platform
    creator_remote_id: str
    display_name: str
    creator_secret_ref: str | None = field(default=None, repr=False)
    local_alias: str | None = None
    profile_lookup_id: UUID | None = None
    interval_seconds: int = 21_600
    max_items: int = 30
    allow_full_history: bool = False
    request_delay_seconds: float = 5.0
    headless: bool = True
    bili_scope: str | None = None


@dataclass(frozen=True, slots=True)
class SubscriptionPolicySummary:
    """Closed, reference-free summary of a persisted adapter policy."""

    adapter: str
    schema_version: int | None = None
    allow_full_history: bool | None = None
    request_delay_seconds: float | None = None
    headless: bool | None = None
    creator_reference_configured: bool = False
    bili_scope: str | None = None

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {"adapter": self.adapter}
        if self.adapter == MEDIACRAWLER_ADAPTER:
            payload.update(
                {
                    "schema_version": self.schema_version,
                    "allow_full_history": self.allow_full_history,
                    "request_delay_seconds": self.request_delay_seconds,
                    "headless": self.headless,
                    "creator_reference_configured": self.creator_reference_configured,
                }
            )
        if self.bili_scope is not None:
            payload["bili_scope"] = self.bili_scope
        return payload


@dataclass(frozen=True, slots=True)
class SubscriptionDraftPreview:
    """Safe normalized subscription draft returned without persistence."""

    account_id: str
    platform: str
    account_display_name: str
    creator_remote_id: str
    creator_display_name: str
    interval_seconds: int
    max_items: int
    policy_summary: SubscriptionPolicySummary
    exists: bool
    local_alias: str | None = None
    profile_lookup_id: str | None = None

    def to_payload(self) -> dict[str, object]:
        return {
            "account_id": self.account_id,
            "platform": self.platform,
            "account_display_name": self.account_display_name,
            "creator_remote_id": self.creator_remote_id,
            "creator_display_name": self.creator_display_name,
            "interval_seconds": self.interval_seconds,
            "max_items": self.max_items,
            "policy_summary": self.policy_summary.to_payload(),
            "exists": self.exists,
            "local_alias": self.local_alias,
            "profile_lookup_id": self.profile_lookup_id,
        }


@dataclass(frozen=True, slots=True)
class SubscriptionWorkbenchResult:
    """Safe projection of an idempotent subscription creation."""

    id: str
    account_id: str
    platform: str
    account_display_name: str
    author_id: str
    creator_remote_id: str
    creator_display_name: str
    enabled: bool
    interval_seconds: int
    max_items: int
    policy_summary: SubscriptionPolicySummary
    watermarked_at: datetime | None
    last_success_at: datetime | None
    next_run_at: datetime | None
    created: bool
    deleted_at: datetime | None = None
    local_alias: str | None = None
    profile_lookup_id: str | None = None

    def to_payload(self) -> dict[str, object]:
        return {
            "id": self.id,
            "account_id": self.account_id,
            "platform": self.platform,
            "account_display_name": self.account_display_name,
            "author_id": self.author_id,
            "creator_remote_id": self.creator_remote_id,
            "creator_display_name": self.creator_display_name,
            "enabled": self.enabled,
            "deleted_at": _iso_datetime(self.deleted_at),
            "local_alias": self.local_alias,
            "profile_lookup_id": self.profile_lookup_id,
            "interval_seconds": self.interval_seconds,
            "max_items": self.max_items,
            "policy_summary": self.policy_summary.to_payload(),
            "watermarked_at": _iso_datetime(self.watermarked_at),
            "last_success_at": _iso_datetime(self.last_success_at),
            "next_run_at": _iso_datetime(self.next_run_at),
            "created": self.created,
        }


@dataclass(frozen=True, slots=True)
class _ValidatedAccountDraft:
    platform: Platform
    display_name: str
    login_method: LoginMethod
    adapter: str
    credential_ref: str | None = field(repr=False)
    existing: Account | None = field(repr=False)

    def preview(self) -> AccountDraftPreview:
        return AccountDraftPreview(
            platform=self.platform.value,
            adapter=self.adapter,
            display_name=self.display_name,
            login_method=self.login_method.value,
            exists=self.existing is not None,
        )


@dataclass(frozen=True, slots=True)
class _ValidatedSubscriptionDraft:
    account: Account = field(repr=False)
    platform: Platform
    creator_remote_id: str
    display_name: str
    local_alias: str | None
    profile_lookup_id: str | None
    creator_secret_ref: str | None = field(repr=False)
    interval_seconds: int
    max_items: int
    policy: dict[str, object] = field(repr=False)
    policy_summary: SubscriptionPolicySummary
    existing_author: Author | None = field(repr=False)
    existing_subscription: Subscription | None = field(repr=False)

    def preview(self) -> SubscriptionDraftPreview:
        return SubscriptionDraftPreview(
            account_id=self.account.id,
            platform=self.platform.value,
            account_display_name=self.account.display_name,
            creator_remote_id=self.creator_remote_id,
            creator_display_name=self.display_name,
            interval_seconds=self.interval_seconds,
            max_items=self.max_items,
            policy_summary=self.policy_summary,
            exists=self.existing_subscription is not None,
            local_alias=self.local_alias,
            profile_lookup_id=self.profile_lookup_id,
        )


def _iso_datetime(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _reserve_sqlite_writer(session: Session) -> None:
    """Serialize a fresh SQLite mutation before its idempotency reads.

    API and CLI entry points give the workbench a fresh transaction. Taking a
    RESERVED lock first makes concurrent same-draft requests observe the first
    commit instead of racing a deferred read transaction into a lock/unique
    error. Callers that already own a transaction keep their existing boundary.
    """

    bind = session.get_bind()
    if bind.dialect.name == "sqlite" and not session.in_transaction():
        session.connection(execution_options={"media_sync_sqlite_begin_immediate": True})


def _required_text(value: object, *, code: str, maximum: int) -> str:
    if not isinstance(value, str):
        raise WorkbenchError(code)
    normalized = value.strip()
    if not normalized or len(normalized) > maximum or any(not character.isprintable() for character in normalized):
        raise WorkbenchError(code)
    return normalized


def _platform(value: object) -> Platform:
    if not isinstance(value, Platform):
        raise WorkbenchError("platform_not_supported")
    return value


def _login_method(value: object) -> LoginMethod:
    if not isinstance(value, LoginMethod):
        raise WorkbenchError("login_method_not_supported")
    return value


def _opaque_reference(value: object, *, code: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise WorkbenchError(code)
    try:
        return SecretReference.parse(value).serialize()
    except InvalidSecretReferenceError:
        raise WorkbenchError(code) from None


def _account_result(account: Account, *, created: bool) -> AccountWorkbenchResult:
    if account.login_method is None:  # pragma: no cover - workbench-created accounts always have one
        raise WorkbenchError("login_method_not_supported")
    return AccountWorkbenchResult(
        id=account.id,
        platform=account.platform,
        adapter=account.adapter,
        display_name=account.display_name,
        login_method=account.login_method,
        auth_status=account.auth_status,
        auth_revision=account.auth_revision,
        created_at=account.created_at,
        created=created,
    )


def _subscription_result(
    subscription: Subscription,
    *,
    policy_summary: SubscriptionPolicySummary,
    created: bool,
    profile_lookup_id: str | None = None,
) -> SubscriptionWorkbenchResult:
    return SubscriptionWorkbenchResult(
        id=subscription.id,
        account_id=subscription.account_id,
        platform=subscription.account.platform,
        account_display_name=subscription.account.display_name,
        author_id=subscription.author_id,
        creator_remote_id=subscription.author.remote_id,
        creator_display_name=subscription.author.display_name,
        enabled=subscription.enabled,
        interval_seconds=subscription.interval_seconds,
        max_items=subscription.max_items,
        policy_summary=policy_summary,
        watermarked_at=subscription.watermarked_at,
        last_success_at=subscription.last_success_at,
        next_run_at=subscription.next_run_at,
        created=created,
        local_alias=subscription.local_alias,
        profile_lookup_id=profile_lookup_id,
    )


class AccountWorkbenchService:
    """Validate and idempotently create accounts in a caller-owned session."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def validate(self, draft: AccountDraft) -> AccountDraftPreview:
        return self._validated(draft).preview()

    def create(self, draft: AccountDraft) -> AccountWorkbenchResult:
        _reserve_sqlite_writer(self._session)
        validated = self._validated(draft)
        if validated.existing is not None:
            return _account_result(validated.existing, created=False)
        account = AccountRepository(self._session).create(
            platform=validated.platform.value,
            display_name=validated.display_name,
            adapter=validated.adapter,
            login_method=validated.login_method.value,
            credential_ref=validated.credential_ref,
        )
        return _account_result(account, created=True)

    def _validated(self, draft: AccountDraft) -> _ValidatedAccountDraft:
        if not isinstance(draft, AccountDraft):
            raise TypeError("draft must be an AccountDraft")
        platform = _platform(draft.platform)
        display_name = _required_text(draft.display_name, code="display_name_invalid", maximum=255)
        login_method = _login_method(draft.login_method)
        adapter = _required_text(draft.adapter, code="adapter_not_supported", maximum=128)
        if adapter not in SUPPORTED_WORKBENCH_ADAPTERS:
            raise WorkbenchError("adapter_not_supported")
        credential_ref = _opaque_reference(draft.credential_ref, code="invalid_credential_reference")

        if adapter == MEDIACRAWLER_ADAPTER:
            if login_method not in capability_for(platform).login_methods:
                raise WorkbenchError("login_method_not_supported")
            if login_method is LoginMethod.COOKIE and credential_ref is None:
                raise WorkbenchError("cookie_login_requires_credential_ref")
            if login_method is not LoginMethod.COOKIE and credential_ref is not None:
                raise WorkbenchError("credential_ref_allowed_only_for_cookie_login")
        elif not FakePlatformAdapter(platform).capabilities().supports_login(login_method):
            raise WorkbenchError("login_method_not_supported")

        existing = AccountRepository(self._session).get_by_platform_and_name(platform.value, display_name)
        if existing is not None and (
            existing.adapter != adapter
            or existing.login_method != login_method.value
            or existing.credential_ref != credential_ref
        ):
            raise WorkbenchError("account_exists_with_different_configuration")
        return _ValidatedAccountDraft(
            platform=platform,
            display_name=display_name,
            login_method=login_method,
            adapter=adapter,
            credential_ref=credential_ref,
            existing=existing,
        )


class SubscriptionWorkbenchService:
    """Validate and idempotently create creator subscriptions."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def validate(self, draft: SubscriptionDraft) -> SubscriptionDraftPreview:
        return self._validated(draft).preview()

    def create(self, draft: SubscriptionDraft) -> SubscriptionWorkbenchResult:
        _reserve_sqlite_writer(self._session)
        validated = self._validated(draft)
        existing = validated.existing_subscription
        if existing is not None:
            existing.local_alias = validated.local_alias
            self._session.flush()
            return _subscription_result(
                existing,
                policy_summary=validated.policy_summary,
                created=False,
                profile_lookup_id=validated.profile_lookup_id,
            )

        author = validated.existing_author or AuthorRepository(self._session).create_if_missing(
            AuthorUpsert(
                platform=validated.platform.value,
                remote_id=validated.creator_remote_id,
                display_name=validated.display_name,
            )
        )
        subscription = SubscriptionRepository(self._session).create(
            account_id=validated.account.id,
            author_id=author.id,
            interval_seconds=validated.interval_seconds,
            max_items=validated.max_items,
            policy=validated.policy,
        )
        subscription.local_alias = validated.local_alias
        self._session.flush()
        return _subscription_result(
            subscription,
            policy_summary=validated.policy_summary,
            created=True,
            profile_lookup_id=validated.profile_lookup_id,
        )

    def _validated(self, draft: SubscriptionDraft) -> _ValidatedSubscriptionDraft:
        if not isinstance(draft, SubscriptionDraft):
            raise TypeError("draft must be a SubscriptionDraft")
        if not isinstance(draft.account_id, UUID):
            raise WorkbenchError("account_not_found")
        platform = _platform(draft.platform)
        if draft.profile_lookup_id is not None and not isinstance(draft.profile_lookup_id, UUID):
            raise WorkbenchError("creator_profile_receipt_invalid")
        if type(draft.display_name) is not str or (
            draft.local_alias is not None and type(draft.local_alias) is not str
        ):
            raise WorkbenchError("creator_display_name_invalid")
        alias_input = draft.local_alias if draft.local_alias is not None else draft.display_name
        local_alias = (
            _required_text(alias_input, code="creator_display_name_invalid", maximum=512) if alias_input else None
        )
        display_name = (
            _required_text(draft.display_name, code="creator_display_name_invalid", maximum=512)
            if draft.profile_lookup_id is None
            else ""
        )
        if type(draft.interval_seconds) is not int or draft.interval_seconds < 60:
            raise WorkbenchError("subscription_options_invalid")
        if type(draft.max_items) is not int or not 1 <= draft.max_items <= 1_000:
            raise WorkbenchError("subscription_options_invalid")
        if type(draft.allow_full_history) is not bool or type(draft.headless) is not bool:
            raise WorkbenchError("subscription_options_invalid")

        account = AccountRepository(self._session).get(str(draft.account_id))
        if account is None:
            raise WorkbenchError("account_not_found")
        if account.platform != platform.value:
            raise WorkbenchError("platform_conflict")
        if account.adapter not in SUPPORTED_WORKBENCH_ADAPTERS:
            raise WorkbenchError("adapter_not_supported")
        if draft.bili_scope is not None and (
            platform is not Platform.BILI
            or account.adapter != MEDIACRAWLER_ADAPTER
            or draft.bili_scope not in {"uploads", "dynamics", "both"}
            or (draft.bili_scope != "uploads" and draft.max_items < 2)
        ):
            raise WorkbenchError("subscription_options_invalid")

        if account.adapter == MEDIACRAWLER_ADAPTER:
            try:
                creator_remote_id = normalize_creator_stable_id(draft.creator_remote_id)
            except MediaCrawlerCapabilityError:
                raise WorkbenchError("creator_remote_id_must_be_stable_id") from None
        else:
            creator_remote_id = _required_text(
                draft.creator_remote_id,
                code="creator_remote_id_must_be_stable_id",
                maximum=255,
            )

        creator_secret_ref = _opaque_reference(
            draft.creator_secret_ref,
            code="invalid_creator_secret_reference",
        )
        if account.adapter != MEDIACRAWLER_ADAPTER:
            if creator_secret_ref is not None:
                raise WorkbenchError("creator_secret_ref_only_for_mediacrawler")
            if draft.allow_full_history or draft.request_delay_seconds != 5.0 or not draft.headless:
                raise WorkbenchError("mediacrawler_policy_options_require_mediacrawler")
            policy: dict[str, object] = {}
            policy_summary = SubscriptionPolicySummary(adapter=account.adapter)
        else:
            capability = capability_for(platform)
            if creator_secret_ref is not None and not capability.creator_input.allows_secret_reference:
                raise WorkbenchError("creator_secret_ref_not_supported")
            if capability.requires_full_history_acknowledgement and not draft.allow_full_history:
                raise WorkbenchError("full_history_acknowledgement_required")
            try:
                media_crawler_policy = MediaCrawlerSubscriptionPolicy(
                    allow_full_history=draft.allow_full_history,
                    request_delay_seconds=draft.request_delay_seconds,
                    headless=draft.headless,
                    creator_secret_ref=creator_secret_ref,
                    bili_scope=draft.bili_scope,
                )
            except MediaCrawlerSubscriptionPolicyError:
                raise WorkbenchError("subscription_options_invalid") from None
            policy = {"mediacrawler": media_crawler_policy.to_payload()}
            policy_summary = SubscriptionPolicySummary(
                adapter=MEDIACRAWLER_ADAPTER,
                schema_version=2 if media_crawler_policy.bili_scope is not None else SUBSCRIPTION_POLICY_SCHEMA_VERSION,
                allow_full_history=media_crawler_policy.allow_full_history,
                request_delay_seconds=media_crawler_policy.request_delay_seconds,
                headless=media_crawler_policy.headless,
                creator_reference_configured=media_crawler_policy.creator_secret_ref is not None,
                bili_scope=media_crawler_policy.bili_scope,
            )

        author_repository = AuthorRepository(self._session)
        existing_author = author_repository.get_by_remote(platform.value, creator_remote_id)
        existing_subscription = None
        if existing_author is not None:
            existing_subscription = SubscriptionRepository(self._session).get_by_account_and_author(
                account.id,
                existing_author.id,
            )
        if existing_subscription is not None and existing_subscription.deleted_at is not None:
            raise WorkbenchError("subscription_removed")
        if draft.profile_lookup_id is not None:
            try:
                profile = CreatorProfileRepository(self._session).require_receipt(
                    str(draft.profile_lookup_id),
                    account.id,
                    platform.value,
                    creator_remote_id,
                )
            except CreatorProfileError as error:
                code = (
                    "creator_profile_receipt_expired"
                    if error.code == "creator_profile_receipt_expired"
                    else "creator_profile_receipt_invalid"
                )
                raise WorkbenchError(code) from None
            display_name = profile.nickname
        if existing_subscription is not None and (
            existing_subscription.interval_seconds != draft.interval_seconds
            or existing_subscription.max_items != draft.max_items
            or existing_subscription.policy != policy
        ):
            raise WorkbenchError("subscription_exists_with_different_options")

        return _ValidatedSubscriptionDraft(
            account=account,
            platform=platform,
            creator_remote_id=creator_remote_id,
            display_name=display_name,
            local_alias=local_alias,
            profile_lookup_id=str(draft.profile_lookup_id) if draft.profile_lookup_id is not None else None,
            creator_secret_ref=creator_secret_ref,
            interval_seconds=draft.interval_seconds,
            max_items=draft.max_items,
            policy=policy,
            policy_summary=policy_summary,
            existing_author=existing_author,
            existing_subscription=existing_subscription,
        )


class WorkbenchService:
    """Convenience facade exposing both shared draft workflows."""

    def __init__(self, session: Session) -> None:
        self.accounts = AccountWorkbenchService(session)
        self.subscriptions = SubscriptionWorkbenchService(session)

    def validate_account(self, draft: AccountDraft) -> AccountDraftPreview:
        return self.accounts.validate(draft)

    def create_account(self, draft: AccountDraft) -> AccountWorkbenchResult:
        return self.accounts.create(draft)

    def validate_subscription(self, draft: SubscriptionDraft) -> SubscriptionDraftPreview:
        return self.subscriptions.validate(draft)

    def create_subscription(self, draft: SubscriptionDraft) -> SubscriptionWorkbenchResult:
        return self.subscriptions.create(draft)


__all__ = [
    "FAKE_ADAPTER",
    "MEDIACRAWLER_ADAPTER",
    "SUPPORTED_WORKBENCH_ADAPTERS",
    "WORKBENCH_ERROR_CODES",
    "AccountDraft",
    "AccountDraftPreview",
    "AccountWorkbenchResult",
    "AccountWorkbenchService",
    "SubscriptionDraft",
    "SubscriptionDraftPreview",
    "SubscriptionPolicySummary",
    "SubscriptionWorkbenchResult",
    "SubscriptionWorkbenchService",
    "WorkbenchError",
    "WorkbenchService",
]
