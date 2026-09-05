"""Single-profile application workflow, separate from login and crawling."""

from __future__ import annotations

import re
from collections.abc import Callable
from uuid import UUID

from sqlalchemy.orm import Session

from media_sync.domain import Platform
from media_sync.infrastructure.db import Database
from media_sync.infrastructure.db.creator_profile_repository import (
    PROFILE_ERROR_CODES,
    CreatorProfileError,
    CreatorProfileRepository,
    ProfileSnapshot,
    ProfileValue,
)
from media_sync.integrations.mediacrawler.creator_profile_runner import (
    MediaCrawlerCreatorProfileRequest,
    MediaCrawlerCreatorProfileResult,
    MediaCrawlerCreatorProfileRunner,
)

from .creator_avatar import fetch_creator_avatar
from .operations import OperationExecutionContext, OperationOutcome

_RUNNER_ERRORS = {
    "auth_expired": "creator_profile_auth_required",
    "account_busy": "creator_profile_busy",
    "unsupported": "creator_profile_unsupported",
    "configuration_invalid": "creator_profile_unavailable",
    "browser_launch_failed": "creator_profile_runner_failed",
    "temporary": "creator_profile_unavailable",
    "timed_out": "creator_profile_timeout",
    "cancelled": "creator_profile_cancelled",
    "result_invalid": "creator_profile_invalid",
    "cleanup_failed": "creator_profile_runner_failed",
}


def lookup_error_code(value: str | None) -> str | None:
    if value is None:
        return None
    return (
        value
        if value
        in PROFILE_ERROR_CODES
        | {
            "operation_execution_failed",
            "operation_thread_start_failed",
            "operation_interrupted",
            "operation_lease_lost",
            "operation_result_invalid",
            "operation_outcome_invalid",
        }
        else "creator_profile_failed"
    )


def profile_payload(profile: ProfileSnapshot | None) -> dict[str, object] | None:
    if profile is None:
        return None
    return {
        "id": profile.profile_id,
        "account_id": profile.account_id,
        "platform": profile.platform,
        "creator_remote_id": profile.creator_remote_id,
        "nickname": profile.nickname,
        "profile_url": profile.canonical_homepage,
        "revision": profile.revision,
        "observed_at": profile.observed_at.isoformat(),
        "avatar_revision": profile.avatar_revision,
        "avatar_observed_at": profile.avatar_observed_at.isoformat() if profile.avatar_observed_at else None,
        "avatar_state": (
            "absent" if profile.avatar_revision == 0 else "retained" if profile.avatar_retained else "current"
        ),
        "avatar_url": (
            f"/api/v1/creator-profiles/{profile.profile_id}/avatar/{profile.avatar_revision}"
            if profile.avatar_revision
            else None
        ),
    }


class CreatorProfileService:
    def __init__(
        self,
        database: Database,
        runner: MediaCrawlerCreatorProfileRunner | None,
        *,
        avatar_fetcher: Callable[[str | None], bytes | None] = fetch_creator_avatar,
    ) -> None:
        self.database = database
        self.runner = runner
        self.avatar_fetcher = avatar_fetcher

    def preflight(self, account_id: str, platform: str, creator_remote_id: str) -> str:
        if platform != "bili":
            raise CreatorProfileError("creator_profile_unsupported")
        if re.fullmatch(r"[1-9][0-9]{0,19}", creator_remote_id) is None or int(creator_remote_id) > 2**64 - 1:
            raise CreatorProfileError("creator_profile_identity_mismatch")
        with self.database.session() as session:
            digest = CreatorProfileRepository(session).credential_snapshot(account_id, platform)
        if self.runner is None:
            raise CreatorProfileError("creator_profile_unavailable")
        return digest

    def execute(
        self,
        context: OperationExecutionContext,
        *,
        account_id: str,
        platform: str,
        creator_remote_id: str,
        frontend_generation: str,
        credential_digest: str,
    ) -> OperationOutcome:
        try:
            ticket = context.commit_effect(
                lambda session: CreatorProfileRepository(session).begin_lookup(
                    account_id=account_id,
                    platform=platform,
                    creator_remote_id=creator_remote_id,
                    operation_id=context.operation_id,
                    frontend_generation=frontend_generation,
                    expected_credential_digest=credential_digest,
                )
            )
            if context.cancel_requested:
                return OperationOutcome.cancelled()
            context.phase("looking_up_creator")
            request = MediaCrawlerCreatorProfileRequest(
                account_id=UUID(account_id),
                platform=Platform(platform),
                creator_remote_id=creator_remote_id,
                request_id=UUID(context.operation_id),
            )
            try:
                if self.runner is None:
                    raise ValueError("creator_profile_unavailable")
                result = self.runner.run(request, cancellation=context.cancellation)
            except Exception:
                result = None
            if context.cancel_requested:
                return OperationOutcome.cancelled()
            error = self._result_error(result, request)
            if error is not None:
                context.commit_effect(lambda session: CreatorProfileRepository(session).mark_failed(ticket, error))
                return OperationOutcome.failed(error, retryable=False)
            assert result is not None and result.profile is not None and result.upstream_sha is not None
            value = ProfileValue(
                platform,
                creator_remote_id,
                result.profile.display_name,
                f"https://space.bilibili.com/{creator_remote_id}",
                result.upstream_sha,
            )
            value.validate()
            context.phase("fetching_creator_avatar")
            if context.cancel_requested:
                return OperationOutcome.cancelled()
            # Images are optional evidence; a failure must not erase successful
            # text or the older avatar. All remote work precedes the DB effect.
            try:
                avatar = self.avatar_fetcher(result.profile.avatar_url)
            except Exception:
                avatar = None

            def publish(session: Session) -> dict[str, object]:
                published = CreatorProfileRepository(session).publish(ticket, value, avatar=avatar)
                return {
                    "profile_id": published.profile_id,
                    "generation": ticket.generation,
                    "revision": published.revision,
                }

            return OperationOutcome.success(context.commit_success(publish))
        except CreatorProfileError as error:
            return OperationOutcome.failed(error.code, retryable=False)

    @staticmethod
    def _result_error(
        result: MediaCrawlerCreatorProfileResult | None,
        request: MediaCrawlerCreatorProfileRequest,
    ) -> str | None:
        if not isinstance(result, MediaCrawlerCreatorProfileResult) or (
            result.account_id,
            result.platform,
            result.creator_remote_id,
            result.request_id,
        ) != (request.account_id, request.platform, request.creator_remote_id, request.request_id):
            return "creator_profile_identity_mismatch"
        if result.status.value != "succeeded":
            return _RUNNER_ERRORS.get(result.status.value, "creator_profile_failed")
        if (
            result.profile is None
            or result.profile.remote_id != request.creator_remote_id
            or result.upstream_sha is None
        ):
            return "creator_profile_invalid"
        return None
