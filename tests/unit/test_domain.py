"""Unit tests for framework-free domain contracts."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from media_sync.domain import (
    AccountRef,
    AssetKind,
    AssetSnapshot,
    AssetStatus,
    AuthExpiredError,
    AuthorSnapshot,
    AuthResult,
    AuthStatus,
    CapabilitySet,
    ContentKind,
    ContentNotFoundError,
    ContentSnapshot,
    CreatorReferenceKind,
    Cursor,
    DomainError,
    DomainValidationError,
    InteractiveChallengeRequiredError,
    InvalidStateTransitionError,
    JobStatus,
    LoginMethod,
    Page,
    PermanentUpstreamError,
    Platform,
    RateLimitedError,
    RunStatus,
    TaskStatus,
    TemporaryUpstreamError,
    UpstreamSchemaChangedError,
    transition_asset,
    transition_auth,
    transition_job,
    transition_run,
)


def test_platform_enum_contains_exactly_seven_stable_codes() -> None:
    assert tuple(platform.value for platform in Platform) == (
        "xhs",
        "dy",
        "ks",
        "bili",
        "wb",
        "tieba",
        "zhihu",
    )


def test_task_status_is_the_job_status_vocabulary() -> None:
    assert TaskStatus is JobStatus


def test_content_asset_and_job_enums_include_architecture_contract() -> None:
    assert {ContentKind.AUDIO.value, ContentKind.DYNAMIC.value} == {"audio", "dynamic"}
    assert AssetKind.AVATAR.value == "avatar"
    assert {
        JobStatus.RETRY_WAIT.value,
        JobStatus.WAITING_AUTH.value,
        JobStatus.WAITING_USER.value,
    } == {"retry_wait", "waiting_auth", "waiting_user"}


def test_author_snapshot_is_deeply_immutable() -> None:
    author = AuthorSnapshot(
        platform=Platform.XHS,
        remote_id=" creator-1 ",
        display_name="Creator",
        profile_url="https://example.test/creator-1",
        raw={"nested": {"items": [1, 2]}},
    )

    assert author.remote_id == "creator-1"
    assert author.raw["nested"]["items"] == (1, 2)  # type: ignore[index]
    with pytest.raises(FrozenInstanceError):
        author.display_name = "Changed"  # type: ignore[misc]
    with pytest.raises(TypeError):
        author.raw["new"] = True  # type: ignore[index]


def test_content_snapshot_normalizes_time_to_utc_and_freezes_metrics() -> None:
    source_time = datetime(2026, 8, 30, 8, 0, tzinfo=UTC) + timedelta(hours=0)
    content = ContentSnapshot(
        platform=Platform.BILI,
        remote_id="item-1",
        author_remote_id="author-1",
        kind=ContentKind.VIDEO,
        published_at=source_time,
        metrics={"likes": 3},
    )

    assert content.published_at == source_time
    with pytest.raises(TypeError):
        content.metrics["likes"] = 4  # type: ignore[index]


def test_snapshot_rejects_naive_timestamp_and_invalid_url() -> None:
    with pytest.raises(DomainValidationError, match="timezone-aware"):
        ContentSnapshot(
            platform=Platform.BILI,
            remote_id="item-1",
            author_remote_id="author-1",
            kind=ContentKind.VIDEO,
            published_at=datetime(2026, 8, 30),
        )

    with pytest.raises(DomainValidationError, match=r"HTTP\(S\)"):
        AuthorSnapshot(
            platform=Platform.XHS,
            remote_id="author-1",
            display_name="Creator",
            profile_url="file:///secret",
        )


def test_asset_snapshot_validates_download_metadata() -> None:
    asset = AssetSnapshot(
        platform=Platform.DY,
        remote_id="asset-1",
        content_remote_id="item-1",
        kind=AssetKind.VIDEO,
        source_url="https://example.test/video.mp4",
        checksum_sha256="A" * 64,
    )
    assert asset.checksum_sha256 == "a" * 64

    with pytest.raises(DomainValidationError, match="non-negative"):
        AssetSnapshot(
            platform=Platform.DY,
            remote_id="asset-1",
            content_remote_id="item-1",
            kind=AssetKind.VIDEO,
            source_url="https://example.test/video.mp4",
            position=-1,
        )


def test_capabilities_require_interactive_methods_to_be_supported() -> None:
    with pytest.raises(DomainValidationError, match="interactive login"):
        CapabilitySet(
            platform=Platform.WB,
            login_methods=frozenset({LoginMethod.COOKIE}),
            creator_reference_kinds=frozenset({CreatorReferenceKind.REMOTE_ID}),
            content_kinds=frozenset({ContentKind.TEXT}),
            asset_kinds=frozenset({AssetKind.IMAGE}),
            interactive_login_methods=frozenset({LoginMethod.QR}),
        )


def test_capability_helpers_are_explicit() -> None:
    capabilities = CapabilitySet(
        platform=Platform.XHS,
        login_methods=frozenset({LoginMethod.QR, LoginMethod.COOKIE}),
        creator_reference_kinds=frozenset({CreatorReferenceKind.PROFILE_URL}),
        content_kinds=frozenset({ContentKind.GALLERY}),
        asset_kinds=frozenset({AssetKind.IMAGE}),
        interactive_login_methods=frozenset({LoginMethod.QR}),
    )
    assert capabilities.supports_login(LoginMethod.COOKIE)
    assert capabilities.requires_interaction(LoginMethod.QR)
    assert not capabilities.supports_login(LoginMethod.PHONE)


def test_page_enforces_cursor_contract_and_immutable_items() -> None:
    cursor = Cursor("next")
    page = Page(["a", "b"], next_cursor=cursor, has_more=True)
    assert page.items == ("a", "b")

    with pytest.raises(DomainValidationError, match="requires next_cursor"):
        Page([], has_more=True)
    with pytest.raises(DomainValidationError, match="terminal page"):
        Page([], next_cursor=cursor, has_more=False)
    with pytest.raises(DomainValidationError, match="blank"):
        Cursor("  ")


@pytest.mark.parametrize(
    ("transition", "current", "target"),
    [
        (transition_run, RunStatus.QUEUED, RunStatus.CLAIMED),
        (transition_asset, AssetStatus.DOWNLOADING, AssetStatus.DOWNLOADED),
        (transition_job, JobStatus.RUNNING, JobStatus.SUCCEEDED),
        (transition_job, JobStatus.CLAIMED, JobStatus.WAITING_AUTH),
        (transition_job, JobStatus.WAITING_AUTH, JobStatus.QUEUED),
        (transition_job, JobStatus.RETRY_WAIT, JobStatus.CANCELLED),
        (transition_auth, AuthStatus.AUTHENTICATING, AuthStatus.AUTHENTICATED),
    ],
)
def test_valid_state_transitions_return_target(transition: object, current: object, target: object) -> None:
    assert transition(current, target) is target  # type: ignore[operator]


@pytest.mark.parametrize(
    ("transition", "current", "target"),
    [
        (transition_run, RunStatus.QUEUED, RunStatus.SUCCEEDED),
        (transition_asset, AssetStatus.EXPORTED, AssetStatus.QUEUED),
        (transition_job, JobStatus.SUCCEEDED, JobStatus.RUNNING),
        (transition_auth, AuthStatus.AUTHENTICATED, AuthStatus.REQUIRED),
    ],
)
def test_invalid_state_transitions_use_unified_domain_error(
    transition: object,
    current: object,
    target: object,
) -> None:
    with pytest.raises(InvalidStateTransitionError) as raised:
        transition(current, target)  # type: ignore[operator]
    assert isinstance(raised.value, DomainError)
    assert raised.value.code == "invalid_state_transition"


def test_authenticated_result_requires_opaque_session_reference() -> None:
    with pytest.raises(DomainValidationError, match="session_ref"):
        AuthResult(status=AuthStatus.AUTHENTICATED)


def test_adapter_errors_expose_worker_classification_without_message_parsing() -> None:
    auth = AuthExpiredError("bili")
    interaction = InteractiveChallengeRequiredError("xhs", "captcha")
    temporary = TemporaryUpstreamError("dy")
    permanent = PermanentUpstreamError("tieba")
    missing = ContentNotFoundError("wb", "post-1")
    schema = UpstreamSchemaChangedError("zhihu")

    assert auth.requires_auth and not auth.retryable
    assert interaction.requires_interaction and interaction.challenge == "captcha"
    assert temporary.retryable and not permanent.retryable
    assert missing.remote_id == "post-1" and missing.code == "content_not_found"
    assert not schema.retryable and schema.code == "upstream_schema_changed"


def test_rate_limit_normalizes_retry_after_for_scheduling() -> None:
    limited = RateLimitedError("ks", retry_after=timedelta(seconds=12.5))
    assert limited.retryable
    assert limited.retry_after == 12.5
    assert limited.context["retry_after"] == 12.5

    with pytest.raises(DomainValidationError, match="non-negative"):
        RateLimitedError("ks", retry_after=-1)


def test_secret_adjacent_snapshot_fields_are_not_in_repr() -> None:
    account = AccountRef(
        account_id=UUID("00000000-0000-0000-0000-000000000001"),
        platform=Platform.BILI,
        login_method=LoginMethod.COOKIE,
        credential_ref="keyring:sentinel-credential",
    )
    cursor = Cursor("sentinel-cursor-token")
    content = ContentSnapshot(
        platform=Platform.BILI,
        remote_id="item-1",
        author_remote_id="creator-1",
        kind=ContentKind.VIDEO,
        body="sentinel-private-body",
        canonical_url="https://example.invalid/item?token=sentinel-url-token",
        raw={"cookie": "sentinel-raw-cookie"},
    )
    asset = AssetSnapshot(
        platform=Platform.BILI,
        remote_id="asset-1",
        content_remote_id="item-1",
        kind=AssetKind.VIDEO,
        source_url="https://example.invalid/video?token=sentinel-signed-url",
        raw={"authorization": "sentinel-raw-token"},
    )

    assert "sentinel" not in repr((account, cursor, content, asset))
