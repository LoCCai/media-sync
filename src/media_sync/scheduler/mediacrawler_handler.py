"""Opt-in, lease-fenced scheduled MediaCrawler subscription handler."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import hmac
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import NoReturn, Protocol, TypeVar, cast
from uuid import UUID, uuid4, uuid5

from sqlalchemy.orm import Session

from media_sync.application.mediacrawler import (
    MediaCrawlerOutputRejected,
    NormalizedMediaCrawlerOutput,
    load_normalized_output,
    validate_bili_record_keys,
)
from media_sync.domain import AuthStatus, LoginMethod, Platform, RunStatus
from media_sync.infrastructure.db import (
    AccountRepository,
    ContentOwnershipConflictError,
    Database,
    LeaseLostError,
    MediaCrawlerIngestionResult,
    MediaCrawlerIngestionService,
    RepositoryError,
    StaleCheckpointError,
    SyncRunRepository,
)
from media_sync.infrastructure.db.models import TERMINAL_RUN_STATUSES, Subscription, SyncRun
from media_sync.integrations.mediacrawler.bridge import (
    MANIFEST_SCHEMA_VERSION,
    BridgeConfigurationError,
    BridgeRequest,
    MediaCrawlerBridge,
    MediaCrawlerRunMode,
    MediaCrawlerRunSpec,
    RunnerManifest,
    SavedSessionUnavailableError,
    verify_manifest_checkout,
)
from media_sync.integrations.mediacrawler.checkout import (
    CheckoutValidationError,
    LicenseAcknowledgementRequired,
    normalize_python_executable,
)
from media_sync.integrations.mediacrawler.normalizers import NormalizedMediaRecord
from media_sync.integrations.mediacrawler.policies import (
    FullHistoryAcknowledgementRequired,
    MediaCrawlerPolicyError,
    RunPaths,
    WatchdogLimits,
    build_run_paths,
    normalize_creator_reference,
)
from media_sync.integrations.mediacrawler.receipt import (
    COMPLETION_RECEIPT_NAME,
    CompletionReceiptError,
)
from media_sync.integrations.mediacrawler.runner import (
    AttemptCleanupError,
    AttemptCleanupStatus,
    MediaCrawlerProcessResult,
    MediaCrawlerProcessRunner,
    MediaCrawlerProcessStatus,
    cleanup_attempt_root,
    is_attempt_cleanup_blocked,
    record_attempt_cleanup_incident,
)
from media_sync.integrations.mediacrawler.subscription_policy import (
    MediaCrawlerSubscriptionPolicy,
    MediaCrawlerSubscriptionPolicyError,
    from_subscription_policy,
)
from media_sync.scheduler.handlers import (
    SubscriptionHandlerResult,
    SubscriptionJobContext,
)
from media_sync.scheduler.policy import FailureDisposition, classify_failure
from media_sync.scheduler.repository import SchedulerLeaseLostError
from media_sync.security import SecretError, SecretResolver, SecretValue

_RUN_METADATA_SCHEMA_VERSION = 1
_FINGERPRINT_HEX_LENGTH = 64
_T = TypeVar("_T")

_RUN_METADATA_BASE_KEYS = frozenset(
    {
        "schema_version",
        "adapter",
        "scheduler_job_id",
        "schedule_revision",
        "attempt",
        "execution_id",
        "sync_run_id",
        "platform",
        "mode",
        "crawl_revision_before",
    }
)
_RUN_METADATA_PROVENANCE_KEYS = frozenset(
    {
        "artifact_schema_version",
        "upstream_sha",
        "output_fingerprint_sha256",
        "input_records",
    }
)
_RECOVERED_ARTIFACT_KEYS = frozenset(
    {
        "schema_version",
        "attempt",
        "execution_id",
        "sync_run_id",
    }
)

_PROCESS_FAILURES: Mapping[MediaCrawlerProcessStatus, str] = {
    MediaCrawlerProcessStatus.AUTH_EXPIRED: "auth_expired",
    MediaCrawlerProcessStatus.BILI_DYNAMIC_UNSUPPORTED: "bili_dynamic_unsupported",
    MediaCrawlerProcessStatus.BILI_DYNAMIC_IDENTITY: "bili_dynamic_identity_mismatch",
    MediaCrawlerProcessStatus.BILI_DYNAMIC_SCHEMA: "bili_dynamic_schema_invalid",
    MediaCrawlerProcessStatus.ACCOUNT_BUSY: "account_busy",
    MediaCrawlerProcessStatus.TIMED_OUT: "upstream_timeout",
    MediaCrawlerProcessStatus.START_FAILED: "upstream_unavailable",
    MediaCrawlerProcessStatus.CONFIGURATION_FAILED: "configuration_invalid",
    MediaCrawlerProcessStatus.UPSTREAM_FAILED: "temporary_upstream",
    MediaCrawlerProcessStatus.OUTPUT_BYTES_EXCEEDED: "output_security_failed",
    MediaCrawlerProcessStatus.OUTPUT_ITEMS_EXCEEDED: "output_security_failed",
    MediaCrawlerProcessStatus.OUTPUT_FILES_EXCEEDED: "output_security_failed",
    MediaCrawlerProcessStatus.OUTPUT_LINE_EXCEEDED: "output_security_failed",
    MediaCrawlerProcessStatus.OUTPUT_TREE_INVALID: "output_security_failed",
    MediaCrawlerProcessStatus.COMPLETION_FAILED: "output_security_failed",
}


class _SecretResolver(Protocol):
    def resolve(self, reference: str) -> SecretValue: ...


class _Bridge(Protocol):
    def prepare(self, request: BridgeRequest) -> MediaCrawlerRunSpec: ...


class _Runner(Protocol):
    def run(
        self,
        spec: MediaCrawlerRunSpec,
        cancellation: threading.Event | None = None,
    ) -> MediaCrawlerProcessResult: ...


class _Normalizer(Protocol):
    def __call__(
        self,
        manifest: RunnerManifest,
        *,
        creator_remote_id: str,
        creator_display_name: str,
        ingested_at: datetime,
    ) -> NormalizedMediaCrawlerOutput: ...


class _ManifestLoader(Protocol):
    def __call__(self, manifest_path: Path) -> RunnerManifest: ...


class _CheckoutVerifier(Protocol):
    def __call__(self, manifest: RunnerManifest) -> object: ...


class _IngestionService(Protocol):
    def ingest_bili_bounded(
        self,
        records: tuple[NormalizedMediaRecord, ...],
        *,
        subscription_id: str | UUID,
        run_id: str | UUID,
        expected_revision: int,
        input_cursor: str | None,
        next_cursor: str,
        crawl_revision_before: int | None = None,
        ownership_guard: Callable[[Session], None] | None = None,
        bili_scope: str | None = None,
    ) -> MediaCrawlerIngestionResult: ...

    def ingest(
        self,
        records: tuple[NormalizedMediaRecord, ...],
        *,
        subscription_id: str | UUID,
        run_id: str | UUID,
        expected_revision: int,
        crawl_revision_before: int | None = None,
        mode: str,
        ownership_guard: Callable[[Session], None] | None = None,
    ) -> MediaCrawlerIngestionResult: ...


class _CancellationObserved(RuntimeError):
    """Stop synchronous ingestion at its next same-session ownership guard."""


class _SealedRecoveryRejected(RuntimeError):
    """A prior artifact claimed a receipt but failed strict validation."""


class MediaCrawlerCleanupBlockedError(SchedulerLeaseLostError):
    """Fence scheduler completion while an account cleanup block is active."""

    def __init__(self) -> None:
        super().__init__("MediaCrawler account is blocked by an unresolved cleanup incident")


@dataclass(frozen=True, slots=True)
class _ScopeSnapshot:
    checkpoint_revision: int
    cursor: Mapping[str, object] | None
    creator_remote_id: str
    creator_display_name: str
    current_run_status: str | None
    current_run_manifest: Mapping[str, object] | None
    current_run_attempt: int | None
    current_run_checkpoint_revision_before: int | None


@dataclass(frozen=True, slots=True)
class _PreparedRun:
    run_id: UUID
    checkpoint_revision: int
    creator_remote_id: str
    creator_display_name: str
    cursor_before: str | None = None


@dataclass(frozen=True, slots=True)
class _RecoveredOutput:
    manifest: RunnerManifest
    output: NormalizedMediaCrawlerOutput
    source_run_id: UUID
    source_paths: RunPaths


@dataclass(frozen=True, slots=True)
class _IngestionTruth:
    """Authoritative durable state observed after the ingestion boundary."""

    run_succeeded: bool
    commit_complete: bool
    checkpoint_revision: int | None


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _attempt_execution_id(job_id: UUID, attempt: int) -> UUID:
    """Derive a stable root identity without ever reusing another attempt."""

    return uuid5(job_id, f"media-sync/mediacrawler/attempt/{attempt}")


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == _FINGERPRINT_HEX_LENGTH
        and all(character in "0123456789abcdef" for character in value)
    )


def _canonical_uuid(value: object) -> UUID | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = UUID(value)
    except ValueError:
        return None
    return parsed if str(parsed) == value else None


def _cleanup_exact_attempt(paths: RunPaths) -> AttemptCleanupStatus:
    """Treat an absent root as clean; otherwise require the public safe remover."""

    try:
        if not paths.job_root.exists() and not paths.job_root.is_symlink():
            return AttemptCleanupStatus.ABSENT
    except OSError:
        return AttemptCleanupStatus.UNRESOLVED
    return cleanup_attempt_root(paths)


class MediaCrawlerScheduledHandler:
    """Run one forward-only MediaCrawler attempt behind scheduler fencing.

    Enablement and the pinned-license acknowledgement are independent,
    explicit operator authorizations and intentionally default to ``False``.
    The child process receives only :class:`BridgeRequest` data; database and
    scheduler ownership material stay inside the trusted parent.
    """

    def __init__(
        self,
        database: Database,
        *,
        lock_path: Path,
        integration_root: Path,
        python_executable: Path | None,
        secret_resolver: SecretResolver | _SecretResolver,
        enabled: bool = False,
        license_acknowledged: bool = False,
        bridge: MediaCrawlerBridge | _Bridge | None = None,
        runner: MediaCrawlerProcessRunner | _Runner | None = None,
        clock: Callable[[], datetime] = _utc_now,
        watchdogs: WatchdogLimits | None = None,
        normalizer: _Normalizer = load_normalized_output,
        manifest_loader: _ManifestLoader = RunnerManifest.load,
        checkout_verifier: _CheckoutVerifier = verify_manifest_checkout,
        ingestion_factory: Callable[[Database], _IngestionService] = MediaCrawlerIngestionService,
        uuid_factory: Callable[[], UUID] = uuid4,
    ) -> None:
        if type(enabled) is not bool or type(license_acknowledged) is not bool:
            raise ValueError("MediaCrawler enablement and license acknowledgement must be boolean")
        self.database = database
        self.lock_path = lock_path.expanduser().resolve()
        self.integration_root = integration_root.expanduser().resolve()
        self.python_executable = (
            normalize_python_executable(python_executable) if python_executable is not None else None
        )
        self.secret_resolver = secret_resolver
        self.enabled = enabled
        self.license_acknowledged = license_acknowledged
        self.bridge = bridge or MediaCrawlerBridge()
        self.runner = runner or MediaCrawlerProcessRunner()
        self.clock = clock
        self.watchdogs = watchdogs or WatchdogLimits()
        self.normalizer = normalizer
        self.manifest_loader = manifest_loader
        self.checkout_verifier = checkout_verifier
        self.ingestion_factory = ingestion_factory
        self.uuid_factory = uuid_factory

    def _now(self) -> datetime:
        value = self.clock()
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("clock must return a timezone-aware datetime")
        return value.astimezone(UTC)

    @staticmethod
    def _require_scheduler_callbacks(context: SubscriptionJobContext) -> None:
        if context.ownership_guard is None or context.run_attacher is None:
            raise ValueError("scheduled MediaCrawler execution requires exact ownership callbacks")

    @staticmethod
    def _guard(context: SubscriptionJobContext, session: Session) -> None:
        guard = context.ownership_guard
        if guard is None:  # pragma: no cover - checked at the public boundary
            raise ValueError("scheduled MediaCrawler ownership guard is unavailable")
        guard(session)

    async def _offload(self, operation: Callable[..., _T], /, *args: object, **kwargs: object) -> _T:
        """Run a blocking boundary and always join it before propagating cancel."""

        task = asyncio.create_task(asyncio.to_thread(operation, *args, **kwargs))
        return await self._join_security_task(task)

    @staticmethod
    async def _join_security_task(
        task: asyncio.Task[_T],
        *,
        on_cancel: Callable[[], None] | None = None,
    ) -> _T:
        """Join blocking or security-critical work despite repeated cancellation.

        Cancellation remains the public outcome, but only after the protected
        operation reaches a definite result.  ``on_cancel`` is invoked once,
        before joining, so cancellable synchronous work can stop cooperatively.
        """

        cancellation: asyncio.CancelledError | None = None
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError as error:
                if cancellation is None:
                    cancellation = error
                    if on_cancel is not None:
                        with contextlib.suppress(BaseException):
                            on_cancel()
            except BaseException:
                break
        if cancellation is not None:
            with contextlib.suppress(BaseException):
                task.result()
            raise cancellation
        return task.result()

    async def _resolve_secret(self, reference: str) -> SecretValue:
        return await self._offload(self.secret_resolver.resolve, reference)

    def _load_scope(self, context: SubscriptionJobContext) -> _ScopeSnapshot:
        with self.database.session() as session:
            self._guard(context, session)
            subscription = session.get(Subscription, str(context.subscription_id))
            if subscription is None:
                raise RepositoryError("scheduled subscription is unavailable")
            account = subscription.account
            author = subscription.author
            if (
                subscription.account_id != str(context.account.account_id)
                or account.platform != context.account.platform.value
                or account.adapter != "mediacrawler"
                or account.login_method != context.account.login_method.value
                or account.credential_ref != context.account.credential_ref
                or author.platform != context.account.platform.value
                or author.remote_id != context.creator_reference
                or subscription.max_items != context.max_items
                or subscription.policy != dict(context.subscription_policy)
                or subscription.schedule_revision != context.schedule_revision + 1
            ):
                raise RepositoryError("scheduled MediaCrawler scope changed")

            current_status: str | None = None
            current_manifest: Mapping[str, object] | None = None
            current_attempt: int | None = None
            current_checkpoint_revision_before: int | None = None
            if context.current_run_id is not None:
                current = session.get(SyncRun, str(context.current_run_id))
                if current is None or current.subscription_id != subscription.id:
                    raise RepositoryError("attached MediaCrawler run scope is invalid")
                current_status = current.status
                current_attempt = current.attempt
                current_checkpoint_revision_before = current.checkpoint_revision_before
                if isinstance(current.manifest, Mapping):
                    current_manifest = dict(current.manifest)
            return _ScopeSnapshot(
                checkpoint_revision=subscription.checkpoint_revision,
                cursor=(dict(subscription.cursor) if subscription.cursor is not None else None),
                creator_remote_id=author.remote_id,
                creator_display_name=author.display_name,
                current_run_status=current_status,
                current_run_manifest=current_manifest,
                current_run_attempt=current_attempt,
                current_run_checkpoint_revision_before=current_checkpoint_revision_before,
            )

    def _record_saved_session_expiry(self, context: SubscriptionJobContext) -> None:
        """Persist normal saved-session expiry without widening stale ownership."""

        if context.account.login_method is not LoginMethod.SAVED_SESSION:
            return
        with self.database.session() as session:
            self._guard(context, session)
            account = AccountRepository(session).require(str(context.account.account_id))
            if account.adapter != "mediacrawler" or account.login_method != LoginMethod.SAVED_SESSION.value:
                raise RepositoryError("scheduled MediaCrawler account scope changed")
            if account.auth_status == AuthStatus.AUTHENTICATED.value:
                AccountRepository(session).set_auth_status(
                    account.id,
                    AuthStatus.EXPIRED.value,
                    expected_status=AuthStatus.AUTHENTICATED.value,
                    at=self._now(),
                )

    @staticmethod
    def _run_metadata(
        context: SubscriptionJobContext,
        *,
        execution_id: UUID,
        sync_run_id: UUID,
        crawl_revision_before: int,
        recovered: _RecoveredOutput | None = None,
    ) -> dict[str, object]:
        payload: dict[str, object] = {
            "schema_version": _RUN_METADATA_SCHEMA_VERSION,
            "adapter": "mediacrawler",
            "scheduler_job_id": str(context.job_id),
            "schedule_revision": context.schedule_revision,
            "attempt": context.attempt,
            "execution_id": str(execution_id),
            "sync_run_id": str(sync_run_id),
            "platform": context.account.platform.value,
            "mode": MediaCrawlerRunMode.FORWARD.value,
            "crawl_revision_before": crawl_revision_before,
        }
        if recovered is not None:
            payload["recovered_artifact"] = {
                "schema_version": recovered.manifest.schema_version,
                "attempt": recovered.manifest.attempt,
                "execution_id": str(recovered.manifest.execution_id),
                "sync_run_id": str(recovered.source_run_id),
            }
        return payload

    def _create_attached_run(
        self,
        context: SubscriptionJobContext,
        *,
        execution_id: UUID,
        attempt_paths: RunPaths,
        recovered: _RecoveredOutput | None = None,
    ) -> _PreparedRun:
        self._require_cleanup_unblocked_sync(attempt_paths)
        run_id = self.uuid_factory()
        if not isinstance(run_id, UUID):
            raise ValueError("uuid_factory must return a UUID")
        with self.database.session() as session:
            self._guard(context, session)
            subscription = session.get(Subscription, str(context.subscription_id))
            if subscription is None:
                raise RepositoryError("scheduled subscription is unavailable")
            if subscription.account_id != str(context.account.account_id):
                raise RepositoryError("scheduled account scope changed")
            creator_remote_id = subscription.author.remote_id
            creator_display_name = subscription.author.display_name
            checkpoint_revision = subscription.checkpoint_revision
            cursor_before = None
            if subscription.cursor is not None:
                raw_cursor = subscription.cursor.get("value")
                if set(subscription.cursor) != {"value"} or type(raw_cursor) is not str or not raw_cursor.strip():
                    raise RepositoryError("scheduled subscription cursor is invalid")
                cursor_before = raw_cursor

            runs = SyncRunRepository(session)
            if context.current_run_id is not None:
                previous = runs.require(str(context.current_run_id))
                if previous.subscription_id != subscription.id:
                    raise RepositoryError("attached MediaCrawler run scope is invalid")
                if previous.status not in TERMINAL_RUN_STATUSES:
                    self._guard(context, session)
                    runs.set_status(
                        previous.id,
                        RunStatus.CANCELLED.value,
                        expected_status=previous.status,
                        error_code="scheduler_replaced",
                        error_message=None,
                        at=self._now(),
                    )

            crawl_revision = (
                recovered.manifest.checkpoint_revision_before if recovered is not None else checkpoint_revision
            )
            self._guard(context, session)
            run = runs.create(
                subscription_id=subscription.id,
                run_id=str(run_id),
                status=RunStatus.QUEUED.value,
                attempt=context.attempt,
                cursor_before=(dict(subscription.cursor) if subscription.cursor is not None else None),
                checkpoint_revision_before=checkpoint_revision,
                manifest=self._run_metadata(
                    context,
                    execution_id=execution_id,
                    sync_run_id=run_id,
                    crawl_revision_before=crawl_revision,
                    recovered=recovered,
                ),
            )
            self._guard(context, session)
            attacher = context.run_attacher
            if attacher is None:  # pragma: no cover - checked before database work
                raise ValueError("scheduled MediaCrawler run attacher is unavailable")
            attacher(session, run_id, context.current_run_id)
            self._guard(context, session)
            runs.set_status(
                run.id,
                RunStatus.CLAIMED.value,
                expected_status=RunStatus.QUEUED.value,
                at=self._now(),
            )
            self._guard(context, session)
            runs.set_status(
                run.id,
                RunStatus.RUNNING.value,
                expected_status=RunStatus.CLAIMED.value,
                at=self._now(),
            )
        return _PreparedRun(
            run_id=run_id,
            checkpoint_revision=checkpoint_revision,
            creator_remote_id=creator_remote_id,
            creator_display_name=creator_display_name,
            cursor_before=cursor_before,
        )

    def _set_run_failure(
        self,
        context: SubscriptionJobContext,
        run_id: UUID,
        error_code: str,
    ) -> None:
        classification = classify_failure(error_code)
        target = (
            RunStatus.AWAITING_AUTH
            if classification.disposition in {FailureDisposition.WAITING_AUTH, FailureDisposition.WAITING_USER}
            else RunStatus.FAILED_RETRYABLE
            if classification.disposition is FailureDisposition.RETRY
            else RunStatus.FAILED_TERMINAL
        )
        with self.database.session() as session:
            self._guard(context, session)
            runs = SyncRunRepository(session)
            run = runs.require(str(run_id))
            if run.subscription_id != str(context.subscription_id):
                raise RepositoryError("MediaCrawler run belongs to another subscription")
            if run.status in TERMINAL_RUN_STATUSES or run.status == target.value:
                return
            self._guard(context, session)
            runs.set_status(
                run.id,
                target.value,
                expected_status=run.status,
                error_code=classification.code,
                error_message=None,
                at=self._now(),
            )

    def _set_ingesting(
        self,
        context: SubscriptionJobContext,
        prepared: _PreparedRun,
        manifest: RunnerManifest,
        output: NormalizedMediaCrawlerOutput,
    ) -> None:
        if not _is_sha256(output.output_fingerprint_sha256):
            raise MediaCrawlerOutputRejected("normalized output fingerprint is invalid")
        with self.database.session() as session:
            self._guard(context, session)
            runs = SyncRunRepository(session)
            run = runs.require(str(prepared.run_id))
            if run.subscription_id != str(context.subscription_id) or run.status != RunStatus.RUNNING.value:
                raise RepositoryError("MediaCrawler run is no longer ready for ingestion")
            self._guard(context, session)
            provenance = dict(run.manifest)
            provenance.update(
                {
                    "artifact_schema_version": manifest.schema_version,
                    "upstream_sha": manifest.upstream_sha,
                    "output_fingerprint_sha256": output.output_fingerprint_sha256,
                    "input_records": output.input_records,
                }
            )
            run.manifest = provenance
            session.flush()
            self._guard(context, session)
            runs.set_status(
                run.id,
                RunStatus.INGESTING.value,
                expected_status=RunStatus.RUNNING.value,
                at=self._now(),
            )

    def _read_ingestion_truth(
        self,
        context: SubscriptionJobContext,
        prepared: _PreparedRun,
        *,
        bounded_next_cursor: str | None = None,
    ) -> _IngestionTruth:
        """Read durable success before interpreting any in-memory summary.

        The ownership check deliberately runs after the read. If ownership was
        lost after ingestion committed, the caller can still enter the
        post-commit cleanup fence without attempting a contradictory failure
        transition.
        """

        with self.database.session() as session:
            run = session.get(SyncRun, str(prepared.run_id))
            subscription = session.get(Subscription, str(context.subscription_id))
            run_succeeded = run is not None and run.status == RunStatus.SUCCEEDED.value
            checkpoint_revision = (
                run.checkpoint_revision_after
                if run is not None and type(run.checkpoint_revision_after) is int and run.checkpoint_revision_after >= 0
                else None
            )
            commit_complete = bool(
                run_succeeded
                and run is not None
                and run.subscription_id == str(context.subscription_id)
                and checkpoint_revision is not None
                and subscription is not None
                and subscription.checkpoint_revision == checkpoint_revision
            )
            if bounded_next_cursor is not None:
                expected_before = None if prepared.cursor_before is None else {"value": prepared.cursor_before}
                expected_after = {"value": bounded_next_cursor}
                commit_complete = bool(
                    run_succeeded
                    and run is not None
                    and run.subscription_id == str(context.subscription_id)
                    and run.checkpoint_revision_before == prepared.checkpoint_revision
                    and checkpoint_revision == prepared.checkpoint_revision + 1
                    and run.cursor_before == expected_before
                    and run.cursor_after == expected_after
                    and subscription is not None
                    and subscription.checkpoint_revision >= checkpoint_revision
                    and (
                        subscription.checkpoint_revision > checkpoint_revision or subscription.cursor == expected_after
                    )
                )
            self._guard(context, session)
        return _IngestionTruth(
            run_succeeded=run_succeeded,
            commit_complete=commit_complete,
            checkpoint_revision=checkpoint_revision,
        )

    def _succeeded_source_paths(
        self,
        context: SubscriptionJobContext,
        scope: _ScopeSnapshot,
    ) -> RunPaths | None:
        """Derive one exact terminal source from a closed successful manifest."""

        metadata = scope.current_run_manifest
        current_run_id = context.current_run_id
        current_attempt = scope.current_run_attempt
        if metadata is None or current_run_id is None or type(current_attempt) is not int:
            return None

        has_recovered_artifact = "recovered_artifact" in metadata
        expected_keys = _RUN_METADATA_BASE_KEYS | _RUN_METADATA_PROVENANCE_KEYS
        if has_recovered_artifact:
            expected_keys = expected_keys | {"recovered_artifact"}
        if set(metadata) != expected_keys:
            return None

        expected_values = {
            "schema_version": _RUN_METADATA_SCHEMA_VERSION,
            "adapter": "mediacrawler",
            "scheduler_job_id": str(context.job_id),
            "schedule_revision": context.schedule_revision,
            "attempt": current_attempt,
            "sync_run_id": str(current_run_id),
            "platform": context.account.platform.value,
            "mode": MediaCrawlerRunMode.FORWARD.value,
            "artifact_schema_version": MANIFEST_SCHEMA_VERSION,
        }
        if any(metadata.get(key) != value for key, value in expected_values.items()):
            return None
        if current_attempt != context.attempt or current_attempt < 1:
            return None
        if type(metadata.get("crawl_revision_before")) is not int:
            return None
        if type(metadata.get("input_records")) is not int or cast(int, metadata["input_records"]) < 0:
            return None
        if not _is_sha256(metadata.get("output_fingerprint_sha256")):
            return None
        upstream_sha = metadata.get("upstream_sha")
        if (
            not isinstance(upstream_sha, str)
            or len(upstream_sha) != 40
            or any(character not in "0123456789abcdef" for character in upstream_sha)
        ):
            return None

        execution_id = _canonical_uuid(metadata.get("execution_id"))
        if execution_id != _attempt_execution_id(context.job_id, current_attempt):
            return None
        source_attempt = current_attempt
        source_execution_id = execution_id
        source_run_id = current_run_id

        if has_recovered_artifact:
            recovered = metadata.get("recovered_artifact")
            if not isinstance(recovered, Mapping) or set(recovered) != _RECOVERED_ARTIFACT_KEYS:
                return None
            source_attempt_value = recovered.get("attempt")
            if (
                recovered.get("schema_version") != MANIFEST_SCHEMA_VERSION
                or type(source_attempt_value) is not int
                or not 1 <= source_attempt_value < current_attempt
            ):
                return None
            source_execution = _canonical_uuid(recovered.get("execution_id"))
            recovered_run_id = _canonical_uuid(recovered.get("sync_run_id"))
            if (
                source_execution != _attempt_execution_id(context.job_id, source_attempt_value)
                or recovered_run_id is None
                or recovered_run_id == current_run_id
            ):
                return None
            source_attempt = source_attempt_value
            source_execution_id = source_execution
            source_run_id = recovered_run_id

        with self.database.session() as session:
            source_run_record = session.get(SyncRun, str(source_run_id))
            if (
                source_run_record is None
                or source_run_record.subscription_id != str(context.subscription_id)
                or source_run_record.attempt != source_attempt
            ):
                return None
            self._guard(context, session)
        return build_run_paths(
            self.integration_root,
            context.account.platform,
            context.account.account_id,
            source_execution_id,
        )

    async def _block_unverifiable_terminal_cleanup(
        self,
        context: SubscriptionJobContext,
        scope: _ScopeSnapshot,
    ) -> NoReturn:
        """Hard-fence an account when successful source identity is not closed."""

        attempt = scope.current_run_attempt
        if type(attempt) is not int or attempt < 1:
            attempt = context.attempt
        paths = await self._offload(
            build_run_paths,
            self.integration_root,
            context.account.platform,
            context.account.account_id,
            _attempt_execution_id(context.job_id, attempt),
        )
        with contextlib.suppress(BaseException):
            await self._offload(record_attempt_cleanup_incident, paths)
        raise MediaCrawlerCleanupBlockedError

    async def _finish_durable_success(
        self,
        run_id: UUID,
        paths: RunPaths,
    ) -> SubscriptionHandlerResult:
        """Secure one exact source before publishing durable success."""

        await self._secure_durable_source(paths)
        return SubscriptionHandlerResult.success(run_id)

    async def _secure_durable_source(self, paths: RunPaths) -> AttemptCleanupStatus:
        """Reach a secured terminal verdict without allowing cancellation gaps."""

        cleanup_status = await self._cleanup_attempt(paths)
        if cleanup_status is AttemptCleanupStatus.UNRESOLVED:
            raise MediaCrawlerCleanupBlockedError
        return cleanup_status

    async def _cleanup_attempt_uninterrupted(self, paths: RunPaths) -> AttemptCleanupStatus:
        try:
            cleanup_status = await self._offload(_cleanup_exact_attempt, paths)
        except BaseException:
            cleanup_status = AttemptCleanupStatus.UNRESOLVED
        if cleanup_status is AttemptCleanupStatus.UNRESOLVED:
            # Marker persistence is best-effort only in the sense that its own
            # failure cannot relax the hard security fence returned below.
            with contextlib.suppress(BaseException):
                await self._offload(record_attempt_cleanup_incident, paths)
        return cleanup_status

    async def _cleanup_attempt(self, paths: RunPaths) -> AttemptCleanupStatus:
        """Resolve cleanup and incident persistence before propagating cancel."""

        task = asyncio.create_task(self._cleanup_attempt_uninterrupted(paths))
        return await self._join_security_task(task)

    async def _require_cleanup_unblocked(self, paths: RunPaths) -> None:
        try:
            blocked = await self._offload(is_attempt_cleanup_blocked, paths)
        except asyncio.CancelledError:
            raise
        except BaseException:
            raise MediaCrawlerCleanupBlockedError from None
        if blocked:
            raise MediaCrawlerCleanupBlockedError

    @staticmethod
    def _require_cleanup_unblocked_sync(paths: RunPaths) -> None:
        try:
            blocked = is_attempt_cleanup_blocked(paths)
        except BaseException:
            raise MediaCrawlerCleanupBlockedError from None
        if blocked:
            raise MediaCrawlerCleanupBlockedError

    async def _hard_stop_cleanup(self, paths: RunPaths) -> NoReturn:
        await self._cleanup_attempt(paths)
        raise MediaCrawlerCleanupBlockedError

    async def _cleanup_failure_code(self, paths: RunPaths | None, error_code: str) -> str:
        if paths is None:
            return error_code
        cleanup_status = await self._cleanup_attempt(paths)
        if cleanup_status is AttemptCleanupStatus.UNRESOLVED:
            raise MediaCrawlerCleanupBlockedError
        if cleanup_status.clean:
            return error_code
        return "output_security_failed"

    async def _cleanup_before_fence(self, paths: RunPaths | None) -> None:
        if paths is not None:
            # Cancellation/lease loss remains the authoritative fence. An
            # unresolved cleanup records its out-of-band block but never
            # substitutes a stale database write or a different exception.
            await self._cleanup_attempt(paths)

    async def _fail_attempt(
        self,
        context: SubscriptionJobContext,
        prepared: _PreparedRun,
        paths: RunPaths,
        error_code: str,
    ) -> SubscriptionHandlerResult:
        safe_code = await self._cleanup_failure_code(paths, error_code)
        self._set_run_failure(context, prepared.run_id, safe_code)
        return SubscriptionHandlerResult.failure(safe_code, run_id=prepared.run_id)

    async def _prepare_bridge(self, request: BridgeRequest) -> MediaCrawlerRunSpec:
        return await self._offload(self.bridge.prepare, request)

    async def _run_process(self, spec: MediaCrawlerRunSpec) -> MediaCrawlerProcessResult:
        cancellation = threading.Event()
        task = asyncio.create_task(asyncio.to_thread(self.runner.run, spec, cancellation))
        return await self._join_security_task(task, on_cancel=cancellation.set)

    async def _normalize(
        self,
        spec: MediaCrawlerRunSpec,
        *,
        creator_remote_id: str,
        creator_display_name: str,
    ) -> NormalizedMediaCrawlerOutput:
        return await self._offload(
            self.normalizer,
            spec.manifest,
            creator_remote_id=creator_remote_id,
            creator_display_name=creator_display_name,
            ingested_at=self._now(),
        )

    async def _ingest(
        self,
        context: SubscriptionJobContext,
        prepared: _PreparedRun,
        manifest: RunnerManifest,
        output: NormalizedMediaCrawlerOutput,
        *,
        attempt_paths: RunPaths,
    ) -> SubscriptionHandlerResult:
        if (
            not isinstance(output, NormalizedMediaCrawlerOutput)
            or isinstance(output.input_records, bool)
            or output.input_records < len(output.records)
            or (manifest.bili_scan is None) != (output.bili_coverage is None)
        ):
            error_code = await self._cleanup_failure_code(attempt_paths, "output_security_failed")
            self._set_run_failure(context, prepared.run_id, error_code)
            return SubscriptionHandlerResult.failure(
                error_code,
                run_id=prepared.run_id,
            )

        try:
            self._set_ingesting(context, prepared, manifest, output)
        except LeaseLostError:
            await self._cleanup_before_fence(attempt_paths)
            raise
        except (MediaCrawlerOutputRejected, RepositoryError):
            error_code = await self._cleanup_failure_code(attempt_paths, "output_security_failed")
            self._set_run_failure(context, prepared.run_id, error_code)
            return SubscriptionHandlerResult.failure(
                error_code,
                run_id=prepared.run_id,
            )

        cancellation = threading.Event()

        def guarded(session: Session) -> None:
            self._guard(context, session)
            if cancellation.is_set():
                raise _CancellationObserved("scheduled MediaCrawler ingestion was cancelled")

        service = self.ingestion_factory(self.database)
        if manifest.bili_scan is not None and output.bili_coverage is not None:
            # Revalidate the pure transition even when a custom normalizer was
            # injected. Filesystem/content validation precedes this DB boundary.
            try:
                validate_bili_record_keys(
                    output.bili_coverage,
                    input_state=manifest.bili_scan,
                    max_items=manifest.max_items,
                    records=output.records,
                )
            except ValueError:
                return await self._fail_attempt(context, prepared, attempt_paths, "output_security_failed")
            ingest_call = asyncio.to_thread(
                service.ingest_bili_bounded,
                output.records,
                subscription_id=context.subscription_id,
                run_id=prepared.run_id,
                expected_revision=prepared.checkpoint_revision,
                crawl_revision_before=manifest.checkpoint_revision_before,
                input_cursor=manifest.bili_scan_input_cursor,
                next_cursor=output.bili_coverage.next_state.to_cursor(),
                bili_scope=getattr(manifest.bili_scan, "scope", None),
                ownership_guard=guarded,
            )
        else:
            ingest_call = asyncio.to_thread(
                service.ingest,
                output.records,
                subscription_id=context.subscription_id,
                run_id=prepared.run_id,
                expected_revision=prepared.checkpoint_revision,
                crawl_revision_before=manifest.checkpoint_revision_before,
                mode=MediaCrawlerRunMode.FORWARD.value,
                ownership_guard=guarded,
            )
        task = asyncio.create_task(ingest_call)
        ingestion_error_code: str | None = None
        try:
            await self._join_security_task(task, on_cancel=cancellation.set)
        except asyncio.CancelledError:
            await self._cleanup_before_fence(attempt_paths)
            raise
        except LeaseLostError:
            await self._cleanup_before_fence(attempt_paths)
            raise
        except StaleCheckpointError:
            ingestion_error_code = "temporary_upstream"
        except ContentOwnershipConflictError:
            ingestion_error_code = "content_ownership_conflict"
        except (_CancellationObserved, RepositoryError):
            ingestion_error_code = "unexpected_handler_failure"
        except Exception:
            ingestion_error_code = "unexpected_handler_failure"

        try:
            if output.bili_coverage is not None:
                truth = self._read_ingestion_truth(
                    context, prepared, bounded_next_cursor=output.bili_coverage.next_state.to_cursor()
                )
            else:
                truth = self._read_ingestion_truth(context, prepared)
        except LeaseLostError:
            await self._cleanup_before_fence(attempt_paths)
            raise
        except Exception:
            # A readback error cannot prove that the ingestion transaction did
            # not commit. Secure the source and leave any durable Run truth for
            # scheduler reconciliation; never manufacture a post-commit
            # failure transition from an unavailable observation.
            await self._secure_durable_source(attempt_paths)
            return SubscriptionHandlerResult.failure(
                "unexpected_handler_failure",
                run_id=prepared.run_id,
            )

        if truth.run_succeeded:
            await self._secure_durable_source(attempt_paths)
            if truth.commit_complete:
                return SubscriptionHandlerResult.success(prepared.run_id)
            return SubscriptionHandlerResult.failure(
                "output_security_failed",
                run_id=prepared.run_id,
            )

        error_code = ingestion_error_code or "output_security_failed"
        error_code = await self._cleanup_failure_code(attempt_paths, error_code)
        self._set_run_failure(context, prepared.run_id, error_code)
        return SubscriptionHandlerResult.failure(error_code, run_id=prepared.run_id)

    @staticmethod
    def _recovery_execution_id(
        context: SubscriptionJobContext,
        scope: _ScopeSnapshot,
    ) -> UUID | None:
        metadata = scope.current_run_manifest
        if context.current_run_id is None or metadata is None:
            return None
        expected = {
            "schema_version": _RUN_METADATA_SCHEMA_VERSION,
            "adapter": "mediacrawler",
            "scheduler_job_id": str(context.job_id),
            "schedule_revision": context.schedule_revision,
            "platform": context.account.platform.value,
            "mode": MediaCrawlerRunMode.FORWARD.value,
        }
        if any(metadata.get(key) != value for key, value in expected.items()):
            return None
        previous_attempt = metadata.get("attempt")
        raw_execution_id = metadata.get("execution_id")
        raw_sync_run_id = metadata.get("sync_run_id")
        if (
            type(previous_attempt) is not int
            or not 1 <= previous_attempt < context.attempt
            or previous_attempt != scope.current_run_attempt
            or raw_sync_run_id != str(context.current_run_id)
            or not isinstance(raw_execution_id, str)
        ):
            return None
        try:
            execution_id = UUID(raw_execution_id)
        except ValueError:
            return None
        if str(execution_id) != raw_execution_id:
            return None
        if execution_id != _attempt_execution_id(context.job_id, previous_attempt):
            return None
        return execution_id

    def _validate_recovery_manifest(
        self,
        context: SubscriptionJobContext,
        scope: _ScopeSnapshot,
        manifest: RunnerManifest,
        *,
        execution_id: UUID,
        creator_reference: str | SecretValue,
        policy: MediaCrawlerSubscriptionPolicy,
    ) -> None:
        raw_creator_reference = (
            creator_reference.reveal() if isinstance(creator_reference, SecretValue) else creator_reference
        )
        normalized_creator = normalize_creator_reference(context.account.platform, raw_creator_reference)
        creator_fingerprint = hashlib.sha256(normalized_creator.encode("utf-8")).hexdigest()
        author_fingerprint = hashlib.sha256(scope.creator_remote_id.encode("utf-8")).hexdigest()
        metadata = scope.current_run_manifest
        metadata_attempt = metadata.get("attempt") if metadata is not None else None
        metadata_crawl_revision = metadata.get("crawl_revision_before") if metadata is not None else None
        if (
            manifest.schema_version != MANIFEST_SCHEMA_VERSION
            or manifest.account_id != context.account.account_id
            or manifest.subscription_id != context.subscription_id
            or manifest.scheduler_job_id != context.job_id
            or manifest.schedule_revision != context.schedule_revision
            or manifest.attempt is None
            or manifest.attempt != metadata_attempt
            or manifest.attempt != scope.current_run_attempt
            or manifest.execution_id != execution_id
            or manifest.sync_run_id != context.current_run_id
            or manifest.checkpoint_revision_before != metadata_crawl_revision
            or manifest.checkpoint_revision_before != scope.current_run_checkpoint_revision_before
            or manifest.checkpoint_revision_before > scope.checkpoint_revision
            or manifest.intended_mode is not MediaCrawlerRunMode.FORWARD
            or manifest.platform is not context.account.platform
            or manifest.login_method is not context.account.login_method
            or manifest.max_items != context.max_items
            or manifest.allow_full_history is not policy.allow_full_history
            or getattr(manifest.bili_scan, "scope", None) != policy.bili_scope
            or manifest.headless is not policy.headless
            or manifest.request_delay_seconds != policy.request_delay_seconds
            or manifest.watchdogs != self.watchdogs
            or manifest.integration_root != self.integration_root
            or manifest.lock_path != self.lock_path
            or not manifest.license_acknowledged
            or not hmac.compare_digest(
                manifest.author_remote_id_fingerprint_sha256,
                author_fingerprint,
            )
            or not hmac.compare_digest(manifest.creator_fingerprint_sha256, creator_fingerprint)
        ):
            raise _SealedRecoveryRejected("sealed MediaCrawler recovery identity is invalid")

    async def _recover_sealed_output_uninterrupted(
        self,
        context: SubscriptionJobContext,
        scope: _ScopeSnapshot,
        *,
        creator_reference: str | SecretValue,
        policy: MediaCrawlerSubscriptionPolicy,
    ) -> _RecoveredOutput | None:
        execution_id = self._recovery_execution_id(context, scope)
        if execution_id is None or context.current_run_id is None:
            return None
        paths = await self._offload(
            build_run_paths,
            self.integration_root,
            context.account.platform,
            context.account.account_id,
            execution_id,
        )
        await self._require_cleanup_unblocked(paths)
        receipt_path = paths.job_root / COMPLETION_RECEIPT_NAME
        if not await self._offload(receipt_path.is_file):
            cleanup_status = await self._cleanup_attempt(paths)
            if cleanup_status is AttemptCleanupStatus.UNRESOLVED:
                raise MediaCrawlerCleanupBlockedError
            if not cleanup_status.clean:
                raise _SealedRecoveryRejected("unsealed MediaCrawler recovery root was unsafe")
            return None
        try:
            manifest = await self._offload(self.manifest_loader, paths.manifest_path)
            self._validate_recovery_manifest(
                context,
                scope,
                manifest,
                execution_id=execution_id,
                creator_reference=creator_reference,
                policy=policy,
            )
            await self._offload(self.checkout_verifier, manifest)
            output = await self._offload(
                self.normalizer,
                manifest,
                creator_remote_id=scope.creator_remote_id,
                creator_display_name=scope.creator_display_name,
                ingested_at=self._now(),
            )
        except asyncio.CancelledError:
            raise
        except Exception as error:
            cleanup_status = await self._cleanup_attempt(paths)
            if cleanup_status is AttemptCleanupStatus.UNRESOLVED:
                raise MediaCrawlerCleanupBlockedError from None
            raise _SealedRecoveryRejected("sealed MediaCrawler recovery was rejected") from error
        await self._require_cleanup_unblocked(paths)
        return _RecoveredOutput(
            manifest=manifest,
            output=output,
            source_run_id=context.current_run_id,
            source_paths=paths,
        )

    async def _recover_sealed_output(
        self,
        context: SubscriptionJobContext,
        scope: _ScopeSnapshot,
        *,
        creator_reference: str | SecretValue,
        policy: MediaCrawlerSubscriptionPolicy,
    ) -> _RecoveredOutput | None:
        """Reach a sealed/clean/blocked recovery verdict before cancellation."""

        task = asyncio.create_task(
            self._recover_sealed_output_uninterrupted(
                context,
                scope,
                creator_reference=creator_reference,
                policy=policy,
            )
        )
        return await self._join_security_task(task)

    async def run(self, context: SubscriptionJobContext) -> SubscriptionHandlerResult:
        """Execute one scheduler-owned forward attempt without holding I/O transactions."""

        if not self.enabled:
            return SubscriptionHandlerResult.failure("handler_unsupported")
        if not self.license_acknowledged:
            return SubscriptionHandlerResult.failure("license_acknowledgement_required")
        if self.python_executable is None:
            return SubscriptionHandlerResult.failure("configuration_invalid")
        try:
            self._require_scheduler_callbacks(context)
            if context.account.adapter != "mediacrawler":
                raise ValueError("scheduled handler received another adapter")
            policy = from_subscription_policy(context.subscription_policy)
            if policy.bili_scope is not None and context.account.platform is not Platform.BILI:
                raise ValueError("Bili scope is invalid for this platform")
            policy.validate_bili_max_items(context.max_items)
            if context.account.login_method not in {
                LoginMethod.QR,
                LoginMethod.COOKIE,
                LoginMethod.SAVED_SESSION,
            }:
                raise ValueError("scheduled MediaCrawler login method is unsupported")
            scope = self._load_scope(context)
        except LeaseLostError:
            raise
        except (MediaCrawlerSubscriptionPolicyError, RepositoryError, TypeError, ValueError):
            return SubscriptionHandlerResult.failure("configuration_invalid")

        if scope.current_run_status == RunStatus.SUCCEEDED.value and context.current_run_id is not None:
            try:
                source_paths = self._succeeded_source_paths(context, scope)
            except LeaseLostError:
                raise
            except Exception:
                source_paths = None
            if source_paths is None:
                await self._block_unverifiable_terminal_cleanup(context, scope)
            return await self._finish_durable_success(context.current_run_id, source_paths)
        execution_id = _attempt_execution_id(context.job_id, context.attempt)
        attempt_paths = await self._offload(
            build_run_paths,
            self.integration_root,
            context.account.platform,
            context.account.account_id,
            execution_id,
        )
        await self._require_cleanup_unblocked(attempt_paths)
        if context.account.login_method is LoginMethod.QR:
            return SubscriptionHandlerResult.failure("qr_required")

        creator_reference: str | SecretValue = scope.creator_remote_id
        cookie: SecretValue | None = None
        try:
            if policy.creator_secret_ref is not None:
                creator_reference = await self._resolve_secret(policy.creator_secret_ref)
            if context.account.login_method is LoginMethod.COOKIE:
                if context.account.credential_ref is None:
                    return SubscriptionHandlerResult.failure("credentials_unavailable")
                cookie = await self._resolve_secret(context.account.credential_ref)
        except asyncio.CancelledError:
            raise
        except SecretError:
            return SubscriptionHandlerResult.failure("credentials_unavailable")
        except Exception:
            return SubscriptionHandlerResult.failure("credentials_unavailable")

        recovery_rejected = False
        try:
            recovered = await self._recover_sealed_output(
                context,
                scope,
                creator_reference=creator_reference,
                policy=policy,
            )
        except LeaseLostError:
            raise
        except _SealedRecoveryRejected:
            recovered = None
            recovery_rejected = True

        await self._require_cleanup_unblocked(attempt_paths)
        try:
            prepared = self._create_attached_run(
                context,
                execution_id=execution_id,
                attempt_paths=attempt_paths,
                recovered=recovered,
            )
        except LeaseLostError:
            raise
        except (RepositoryError, TypeError, ValueError):
            return SubscriptionHandlerResult.failure("unexpected_handler_failure")

        if recovery_rejected:
            try:
                self._set_run_failure(context, prepared.run_id, "output_security_failed")
            except LeaseLostError:
                raise
            except RepositoryError:
                return SubscriptionHandlerResult.failure(
                    "unexpected_handler_failure",
                    run_id=prepared.run_id,
                )
            return SubscriptionHandlerResult.failure(
                "output_security_failed",
                run_id=prepared.run_id,
            )

        if recovered is not None:
            return await self._ingest(
                context,
                prepared,
                recovered.manifest,
                recovered.output,
                attempt_paths=recovered.source_paths,
            )

        request = BridgeRequest(
            lock_path=self.lock_path,
            integration_root=self.integration_root,
            python_executable=self.python_executable,
            account_id=context.account.account_id,
            subscription_id=context.subscription_id,
            job_id=context.job_id,
            scheduler_job_id=context.job_id,
            schedule_revision=context.schedule_revision,
            attempt=context.attempt,
            execution_id=execution_id,
            sync_run_id=prepared.run_id,
            checkpoint_revision_before=prepared.checkpoint_revision,
            intended_mode=MediaCrawlerRunMode.FORWARD,
            platform=context.account.platform,
            login_method=context.account.login_method,
            author_remote_id=prepared.creator_remote_id,
            creator_reference=creator_reference,
            license_acknowledged=self.license_acknowledged,
            allow_full_history=policy.allow_full_history,
            cookie=cookie,
            headless=policy.headless,
            max_items=context.max_items,
            watchdogs=self.watchdogs,
            request_delay_seconds=policy.request_delay_seconds,
            bili_bounded_capture=context.account.platform is Platform.BILI,
            bili_scan_cursor_before=prepared.cursor_before if context.account.platform is Platform.BILI else None,
            bili_scope=policy.bili_scope,
        )
        try:
            await self._require_cleanup_unblocked(attempt_paths)
            spec = await self._prepare_bridge(request)
        except asyncio.CancelledError:
            await self._cleanup_before_fence(attempt_paths)
            raise
        except LeaseLostError:
            await self._cleanup_before_fence(attempt_paths)
            raise
        except LicenseAcknowledgementRequired:
            return await self._fail_attempt(
                context,
                prepared,
                attempt_paths,
                "license_acknowledgement_required",
            )
        except SavedSessionUnavailableError:
            try:
                self._record_saved_session_expiry(context)
            except LeaseLostError:
                raise
            except Exception:
                pass
            return await self._fail_attempt(context, prepared, attempt_paths, "auth_expired")
        except BridgeConfigurationError:
            return await self._fail_attempt(context, prepared, attempt_paths, "configuration_invalid")
        except (CheckoutValidationError, FullHistoryAcknowledgementRequired, MediaCrawlerPolicyError, OSError):
            return await self._fail_attempt(context, prepared, attempt_paths, "configuration_invalid")
        except Exception:
            return await self._fail_attempt(context, prepared, attempt_paths, "unexpected_handler_failure")

        if spec.paths != attempt_paths:
            return await self._fail_attempt(context, prepared, attempt_paths, "configuration_invalid")

        try:
            await self._require_cleanup_unblocked(attempt_paths)
            process = await self._run_process(spec)
        except asyncio.CancelledError:
            await self._cleanup_before_fence(attempt_paths)
            raise
        except LeaseLostError:
            await self._cleanup_before_fence(attempt_paths)
            raise
        except AttemptCleanupError:
            await self._hard_stop_cleanup(attempt_paths)
        except Exception:
            return await self._fail_attempt(context, prepared, attempt_paths, "unexpected_handler_failure")
        if process.status is MediaCrawlerProcessStatus.CANCELLED:
            await self._cleanup_before_fence(attempt_paths)
            raise asyncio.CancelledError
        if not process.succeeded:
            error_code = _PROCESS_FAILURES.get(process.status, "unexpected_handler_failure")
            if error_code == "auth_expired":
                try:
                    self._record_saved_session_expiry(context)
                except LeaseLostError:
                    raise
                except Exception:
                    pass
            return await self._fail_attempt(context, prepared, attempt_paths, error_code)

        try:
            output = await self._normalize(
                spec,
                creator_remote_id=prepared.creator_remote_id,
                creator_display_name=prepared.creator_display_name,
            )
        except asyncio.CancelledError:
            await self._cleanup_before_fence(attempt_paths)
            raise
        except (CompletionReceiptError, MediaCrawlerOutputRejected, MediaCrawlerPolicyError, OSError, ValueError):
            return await self._fail_attempt(context, prepared, attempt_paths, "output_security_failed")
        except Exception:
            return await self._fail_attempt(context, prepared, attempt_paths, "output_security_failed")

        return await self._ingest(
            context,
            prepared,
            spec.manifest,
            output,
            attempt_paths=attempt_paths,
        )


__all__ = ["MediaCrawlerCleanupBlockedError", "MediaCrawlerScheduledHandler"]
