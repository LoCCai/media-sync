"""Application orchestration for safe media-server item observation.

The module deliberately depends on structural protocols.  API composition can
therefore wire the existing publication resolver, media-server service and
durable Operation context without teaching this layer about HTTP or storage.
"""

from __future__ import annotations

import hashlib
import math
import re
import time
from collections.abc import Callable, Mapping
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Literal, Protocol, overload
from uuid import UUID

from media_sync.application.media_server_publication import MediaServerPublicationTarget
from media_sync.application.operations import OperationOutcome
from media_sync.config import MediaServerSafeSummary
from media_sync.ports.media_server import (
    MediaServerError,
    MediaServerItemLookupResult,
    MediaServerProvider,
    MediaServerScanResult,
)

_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_MODE = "post_refresh_item_observation"
_MAX_TIMEOUT_SECONDS = 120.0
_MIN_POLL_INTERVAL_SECONDS = 2.0
_MAX_PAGES = 128
_MAX_ROWS = 16_384
_MAX_RESPONSE_BYTES = 32 * 1024 * 1024


class MediaServerPublicationResolverPort(Protocol):
    """Resolve the sole current publication authorized for an author."""

    def resolve(
        self,
        author_id: str,
        *,
        deadline: float | None = None,
    ) -> MediaServerPublicationTarget: ...


class MediaServerObservationSnapshotPort(Protocol):
    """The cancellation fact needed from an Operation transition."""

    @property
    def cancel_requested_at(self) -> datetime | None: ...


class MediaServerCancellationPort(Protocol):
    """A ``threading.Event`` compatible cancellation wait boundary."""

    def is_set(self) -> bool: ...

    def wait(self, timeout: float | None = None) -> bool: ...


class MediaServerObservationContextPort(Protocol):
    """Small durable-operation surface consumed by the observation worker."""

    @property
    def cancellation(self) -> MediaServerCancellationPort: ...

    @property
    def cancel_requested(self) -> bool: ...

    def phase(self, phase: str) -> MediaServerObservationSnapshotPort: ...

    def checkpoint(
        self,
        *,
        phase: str,
        result_summary: Mapping[str, object],
    ) -> MediaServerObservationSnapshotPort: ...

    def progress(
        self,
        *,
        phase: str,
        current: int,
        unit: str,
        total: int | None = None,
    ) -> MediaServerObservationSnapshotPort: ...


class MediaServerObservationServerPort(Protocol):
    """Safe profile identity, lookup and one-shot mutation boundary."""

    @property
    def profile_fingerprint(self) -> str | None: ...

    @property
    def safe_summary(self) -> MediaServerSafeSummary | None: ...

    def lookup_item(
        self,
        target: MediaServerPublicationTarget,
        *,
        deadline: float | None = None,
    ) -> MediaServerItemLookupResult: ...

    def scan_observation(
        self,
        cancel_requested: Callable[[], bool],
        before_transport_entry: Callable[[], bool],
        *,
        deadline: float | None = None,
    ) -> MediaServerScanResult: ...


@dataclass(frozen=True, slots=True)
class MediaServerObservationLimits:
    """Server-owned aggregate limits that callers may lower but never raise."""

    timeout_seconds: float = _MAX_TIMEOUT_SECONDS
    poll_interval_seconds: float = _MIN_POLL_INTERVAL_SECONDS
    max_pages: int = _MAX_PAGES
    max_rows: int = _MAX_ROWS
    max_response_bytes: int = _MAX_RESPONSE_BYTES

    def __post_init__(self) -> None:
        timeout = self.timeout_seconds
        interval = self.poll_interval_seconds
        if (
            isinstance(timeout, bool)
            or not isinstance(timeout, int | float)
            or not math.isfinite(timeout)
            or not 0 < float(timeout) <= _MAX_TIMEOUT_SECONDS
        ):
            raise ValueError("timeout_seconds must be finite and at most 120 seconds")
        if (
            isinstance(interval, bool)
            or not isinstance(interval, int | float)
            or not math.isfinite(interval)
            or not _MIN_POLL_INTERVAL_SECONDS <= float(interval) <= float(timeout)
        ):
            raise ValueError("poll_interval_seconds must be finite, at least two seconds, and within timeout")
        for name, value, maximum in (
            ("max_pages", self.max_pages, _MAX_PAGES),
            ("max_rows", self.max_rows, _MAX_ROWS),
            ("max_response_bytes", self.max_response_bytes, _MAX_RESPONSE_BYTES),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
                raise ValueError(f"{name} must be a positive integer no greater than {maximum}")
        object.__setattr__(self, "timeout_seconds", float(timeout))
        object.__setattr__(self, "poll_interval_seconds", float(interval))


@dataclass(frozen=True, slots=True, repr=False)
class MediaServerAuthorLookupResult:
    """API-safe evidence from one complete author lookup."""

    schema_version: Literal[1]
    author_id: str
    provider: MediaServerProvider
    library_id_digest: str
    publication_fingerprint: str
    selector_fingerprint: str
    lookup_state: Literal["not_found", "matched"]
    match_count: Literal[0, 1]
    observed_at: str
    complete: Literal[True]
    item_fingerprint: str | None = field(default=None, repr=False)
    observation_fingerprint: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if (
            self.schema_version != 1
            or not _is_canonical_uuid(self.author_id)
            or self.provider not in {"emby", "jellyfin"}
        ):
            raise ValueError("author lookup identity is invalid")
        for value in (self.library_id_digest, self.publication_fingerprint, self.selector_fingerprint):
            if not _is_digest(value):
                raise ValueError("author lookup fingerprint is invalid")
        try:
            observed = datetime.fromisoformat(self.observed_at)
        except (TypeError, ValueError):
            raise ValueError("observed_at must be an aware ISO timestamp") from None
        if observed.tzinfo is None or observed.utcoffset() is None:
            raise ValueError("observed_at must be an aware ISO timestamp")
        if self.lookup_state == "matched":
            if (
                self.match_count != 1
                or not _is_digest(self.item_fingerprint)
                or not _is_digest(self.observation_fingerprint)
            ):
                raise ValueError("matched lookup evidence is invalid")
        elif self.lookup_state == "not_found":
            if self.match_count != 0 or self.item_fingerprint is not None or self.observation_fingerprint is not None:
                raise ValueError("not-found lookup evidence is invalid")
        else:
            raise ValueError("lookup_state is invalid")
        if self.complete is not True:
            raise ValueError("author lookup must be complete")

    def as_dict(self) -> dict[str, object]:
        """Return the exact public response shape without process-local selectors."""

        payload: dict[str, object] = {
            "schema_version": self.schema_version,
            "author_id": self.author_id,
            "provider": self.provider,
            "library_id_digest": self.library_id_digest,
            "publication_fingerprint": self.publication_fingerprint,
            "selector_fingerprint": self.selector_fingerprint,
            "lookup_state": self.lookup_state,
            "match_count": self.match_count,
            "observed_at": self.observed_at,
            "complete": self.complete,
        }
        if self.item_fingerprint is not None:
            payload["item_fingerprint"] = self.item_fingerprint
        if self.observation_fingerprint is not None:
            payload["observation_fingerprint"] = self.observation_fingerprint
        return payload

    def __repr__(self) -> str:
        return (
            "MediaServerAuthorLookupResult("
            f"schema_version={self.schema_version!r}, author_id={self.author_id!r}, "
            f"provider={self.provider!r}, lookup_state={self.lookup_state!r}, "
            f"match_count={self.match_count!r}, complete={self.complete!r})"
        )

    __str__ = __repr__


@dataclass(frozen=True, slots=True)
class _PassReservation:
    pages: int
    rows: int
    response_bytes: int


_PASS_RESERVATIONS: dict[MediaServerProvider, _PassReservation] = {
    "emby": _PassReservation(pages=1, rows=2, response_bytes=256 * 1024),
    "jellyfin": _PassReservation(pages=32, rows=4_096, response_bytes=8 * 1024 * 1024),
}


class _LookupBudgetExhausted(RuntimeError):
    pass


@dataclass(slots=True, repr=False)
class _LookupBudget:
    limits: MediaServerObservationLimits
    passes_started: int = 0
    pages: int = 0
    rows: int = 0
    response_bytes: int = 0

    def start(self, provider: MediaServerProvider) -> None:
        reservation = _PASS_RESERVATIONS[provider]
        maximum_passes = min(
            self.limits.max_pages // reservation.pages,
            self.limits.max_rows // reservation.rows,
            self.limits.max_response_bytes // reservation.response_bytes,
        )
        if self.passes_started >= maximum_passes:
            raise _LookupBudgetExhausted
        self.passes_started += 1

    def finish(self, provider: MediaServerProvider, result: MediaServerItemLookupResult) -> None:
        reservation = _PASS_RESERVATIONS[provider]
        if (
            result.page_count > reservation.pages
            or result.inspected_item_count > reservation.rows
            or result.response_byte_count > reservation.response_bytes
        ):
            raise _LookupBudgetExhausted
        self.pages += result.page_count
        self.rows += result.inspected_item_count
        self.response_bytes += result.response_byte_count
        if (
            self.pages > self.limits.max_pages
            or self.rows > self.limits.max_rows
            or self.response_bytes > self.limits.max_response_bytes
        ):
            raise _LookupBudgetExhausted


@dataclass(slots=True, repr=False)
class _TransportFence:
    calls: int = 0
    approved: bool = False
    failure: tuple[str, bool] | None = None
    exception: Exception | None = field(default=None, repr=False)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _is_digest(value: object) -> bool:
    return isinstance(value, str) and _DIGEST.fullmatch(value) is not None


def _is_canonical_uuid(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        return str(UUID(value)) == value
    except ValueError:
        return False


def _bounded_item_id(value: object) -> str:
    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= 128
        or any(
            ord(character) < 0x20 or ord(character) == 0x7F or 0xD800 <= ord(character) <= 0xDFFF for character in value
        )
    ):
        raise ValueError("item_id must be bounded non-control text")
    return value


def media_server_item_fingerprint(
    *,
    profile_fingerprint: str,
    publication_fingerprint: str,
    selector_fingerprint: str,
    item_id: str,
) -> str:
    """Digest an item ID only inside three high-entropy authority contexts."""

    if not all(_is_digest(value) for value in (profile_fingerprint, publication_fingerprint, selector_fingerprint)):
        raise ValueError("item fingerprint context is invalid")
    normalized_id = _bounded_item_id(item_id)
    digest = hashlib.sha256(b"media-sync:media-server-observed-item:v1\0")
    for value in (profile_fingerprint, publication_fingerprint, selector_fingerprint, normalized_id):
        encoded = value.encode("utf-8")
        digest.update(len(encoded).to_bytes(4, "big"))
        digest.update(encoded)
    return digest.hexdigest()


def media_server_observation_fingerprint(
    *,
    author_id: str,
    profile_fingerprint: str,
    publication_fingerprint: str,
    selector_fingerprint: str,
    item_fingerprint: str,
) -> str:
    """Bind one canonical author to four already-safe authority digests."""

    if not _is_canonical_uuid(author_id):
        raise ValueError("observation fingerprint author is invalid")
    context = (
        profile_fingerprint,
        publication_fingerprint,
        selector_fingerprint,
        item_fingerprint,
    )
    if not all(_is_digest(value) for value in context):
        raise ValueError("observation fingerprint context is invalid")
    digest = hashlib.sha256(b"media-sync:media-server-playback-observation:v1\0")
    for value in (author_id, *context):
        encoded = value.encode("ascii")
        digest.update(len(encoded).to_bytes(4, "big"))
        digest.update(encoded)
    return digest.hexdigest()


class MediaServerObservationService:
    """Resolve, baseline, refresh once, and prove a bounded item postcondition."""

    def __init__(
        self,
        resolver: MediaServerPublicationResolverPort,
        server: MediaServerObservationServerPort,
        *,
        limits: MediaServerObservationLimits | None = None,
        monotonic: Callable[[], float] = time.monotonic,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        if not hasattr(resolver, "resolve"):
            raise TypeError("resolver must expose resolve")
        if not all(hasattr(server, name) for name in ("lookup_item", "scan_observation")):
            raise TypeError("server must expose lookup_item and scan_observation")
        if limits is not None and not isinstance(limits, MediaServerObservationLimits):
            raise TypeError("limits must be MediaServerObservationLimits")
        if not callable(monotonic) or not callable(clock):
            raise TypeError("monotonic and clock must be callable")
        self._resolver = resolver
        self._server = server
        self._limits = limits or MediaServerObservationLimits()
        self._monotonic = monotonic
        self._clock = clock

    @property
    def profile_fingerprint(self) -> str:
        """Expose only the validated immutable profile identity."""

        return self._profile_identity()[0]

    def resolve_target(
        self,
        author_id: str,
        *,
        deadline: float | None = None,
    ) -> MediaServerPublicationTarget:
        """Expose the resolver's safe author-only entry point for API composition."""

        try:
            target = self._resolver.resolve(author_id, deadline=deadline)
        except MediaServerError:
            raise
        except Exception:
            raise MediaServerError("media_server_publication_not_ready") from None
        if not isinstance(target, MediaServerPublicationTarget):
            raise MediaServerError("media_server_publication_not_ready")
        return target

    @overload
    def lookup_author(
        self,
        target_or_author_id: str,
        *,
        deadline: float | None = None,
    ) -> MediaServerAuthorLookupResult: ...

    @overload
    def lookup_author(
        self,
        target_or_author_id: MediaServerPublicationTarget,
        *,
        deadline: float | None = None,
    ) -> MediaServerAuthorLookupResult: ...

    def lookup_author(
        self,
        target_or_author_id: str | MediaServerPublicationTarget,
        *,
        deadline: float | None = None,
    ) -> MediaServerAuthorLookupResult:
        """Return one complete, safe lookup snapshot for an authorized author."""

        target = (
            self.resolve_target(target_or_author_id, deadline=deadline)
            if isinstance(target_or_author_id, str)
            else target_or_author_id
        )
        if not isinstance(target, MediaServerPublicationTarget):
            raise TypeError("target_or_author_id must be an author ID or publication target")
        profile_fingerprint, provider, library_id_digest = self._profile_identity()
        result = self._lookup_once(target, provider, _LookupBudget(self._limits), deadline=deadline)
        observed_at = self._timestamp()
        item_fingerprint = None
        observation_fingerprint = None
        if result.lookup_state == "matched":
            assert result.item_id is not None
            item_fingerprint = media_server_item_fingerprint(
                profile_fingerprint=profile_fingerprint,
                publication_fingerprint=target.publication_fingerprint,
                selector_fingerprint=target.selector_fingerprint,
                item_id=result.item_id,
            )
            observation_fingerprint = media_server_observation_fingerprint(
                author_id=target.author_id,
                profile_fingerprint=profile_fingerprint,
                publication_fingerprint=target.publication_fingerprint,
                selector_fingerprint=target.selector_fingerprint,
                item_fingerprint=item_fingerprint,
            )
        return MediaServerAuthorLookupResult(
            schema_version=1,
            author_id=target.author_id,
            provider=provider,
            library_id_digest=library_id_digest,
            publication_fingerprint=target.publication_fingerprint,
            selector_fingerprint=target.selector_fingerprint,
            lookup_state=result.lookup_state,
            match_count=1 if result.lookup_state == "matched" else 0,
            item_fingerprint=item_fingerprint,
            observation_fingerprint=observation_fingerprint,
            observed_at=observed_at,
            complete=True,
        )

    def observe_author(
        self,
        target: MediaServerPublicationTarget,
        context: MediaServerObservationContextPort,
    ) -> OperationOutcome:
        """Run an absent-to-unique-match author observation Operation worker."""

        if not isinstance(target, MediaServerPublicationTarget):
            raise TypeError("target must be a MediaServerPublicationTarget")
        started = self._time()
        deadline = started + self._limits.timeout_seconds
        profile_fingerprint, provider, library_id_digest = self._profile_identity()

        baseline_phase = context.phase("baselining")
        if self._snapshot_cancelled(baseline_phase) or self._cancel_requested(context):
            return OperationOutcome.cancelled()
        initial_failure = self._require_same_target(target, deadline)
        if initial_failure is not None:
            return initial_failure
        if self._cancel_requested(context):
            return OperationOutcome.cancelled()

        budget = _LookupBudget(self._limits)
        baseline = self._pre_dispatch_lookup(target, provider, budget, deadline)
        if isinstance(baseline, OperationOutcome):
            return baseline
        if baseline.lookup_state == "matched":
            return OperationOutcome.failed(
                "media_server_scan_observation_precondition_failed",
                retryable=False,
            )
        if provider == "jellyfin":
            if self._cancel_requested(context):
                return OperationOutcome.cancelled()
            if self._time() >= deadline:
                return OperationOutcome.failed("media_server_timeout", retryable=True)
            second = self._pre_dispatch_lookup(target, provider, budget, deadline)
            if isinstance(second, OperationOutcome):
                return second
            if second.lookup_state == "matched":
                return OperationOutcome.failed(
                    "media_server_scan_observation_precondition_failed",
                    retryable=False,
                )
            if (
                second.item_id_set_fingerprint != baseline.item_id_set_fingerprint
                or second.inspected_item_count != baseline.inspected_item_count
            ):
                return OperationOutcome.failed("media_server_item_lookup_incomplete", retryable=False)

        fence = _TransportFence()

        def reject_before_transport_entry(code: str, retryable: bool) -> bool:
            """Durably restore a pre-dispatch phase only while the hook still owns entry."""

            fence.failure = (code, retryable)
            try:
                snapshot = context.phase("baselining")
                if self._snapshot_cancelled(snapshot) or self._cancel_requested(context):
                    fence.failure = ("media_server_scan_cancelled", False)
            except Exception as error:
                # Keeping ``dispatching`` makes coordinator finalization choose
                # acceptance-unknown, which is the only safe fallback when the
                # clean pre-entry rejection could not itself be persisted.
                fence.exception = error
            return False

        def before_transport_entry() -> bool:
            fence.calls += 1
            if fence.calls != 1:
                fence.failure = ("media_server_scan_acceptance_unknown", False)
                return False
            try:
                snapshot = context.phase("dispatching")
                if self._snapshot_cancelled(snapshot) or self._cancel_requested(context):
                    fence.failure = ("media_server_scan_cancelled", False)
                    return False
                if self._time() >= deadline:
                    return reject_before_transport_entry("media_server_timeout", True)
                resolved = self.resolve_target(target.author_id, deadline=deadline)
                if resolved != target:
                    return reject_before_transport_entry("media_server_publication_changed", False)
                if self._cancel_requested(context):
                    fence.failure = ("media_server_scan_cancelled", False)
                    return False
                if self._time() >= deadline:
                    return reject_before_transport_entry("media_server_timeout", True)
            except MediaServerError as error:
                return reject_before_transport_entry(error.code, error.retryable)
            except Exception as error:
                fence.exception = error
                with suppress(Exception):
                    context.phase("baselining")
                return False
            fence.approved = True
            return True

        try:
            scan = self._server.scan_observation(
                lambda: self._cancel_requested(context),
                before_transport_entry,
                deadline=deadline,
            )
        except MediaServerError as error:
            if fence.exception is not None:
                raise fence.exception from None
            if fence.failure is not None:
                code, retryable = fence.failure
                if code == "media_server_scan_cancelled":
                    return OperationOutcome.cancelled()
                return OperationOutcome.failed(code, retryable=retryable)
            if error.code == "media_server_scan_cancelled":
                return OperationOutcome.cancelled()
            return OperationOutcome.failed(error.code, retryable=error.retryable)

        if (
            not isinstance(scan, MediaServerScanResult)
            or fence.calls != 1
            or not fence.approved
            or scan.provider != provider
            or scan.library_id_digest != library_id_digest
        ):
            return OperationOutcome.failed("media_server_scan_acceptance_unknown", retryable=False)

        accepted_at = self._timestamp()
        accepted = self._accepted_payload(
            target=target,
            scan=scan,
            profile_fingerprint=profile_fingerprint,
            accepted_at=accepted_at,
        )
        try:
            accepted_snapshot = context.checkpoint(phase="accepted", result_summary=accepted)
        except Exception:
            return self._completion_unknown(accepted)
        if self._snapshot_cancelled(accepted_snapshot) or self._cancel_requested(context):
            return self._completion_unknown(accepted)
        if self._time() >= deadline:
            return self._completion_unknown(accepted)
        return self._poll_observation(
            target=target,
            context=context,
            provider=provider,
            profile_fingerprint=profile_fingerprint,
            budget=budget,
            deadline=deadline,
            accepted=accepted,
            accepted_at=accepted_at,
        )

    def _poll_observation(
        self,
        *,
        target: MediaServerPublicationTarget,
        context: MediaServerObservationContextPort,
        provider: MediaServerProvider,
        profile_fingerprint: str,
        budget: _LookupBudget,
        deadline: float,
        accepted: dict[str, object],
        accepted_at: str,
    ) -> OperationOutcome:
        try:
            progress = context.progress(phase="polling", current=0, total=None, unit="steps")
            if self._snapshot_cancelled(progress) or self._cancel_requested(context):
                return self._completion_unknown(accepted)
            first_item_id: str | None = None
            next_poll_at = self._time() + self._limits.poll_interval_seconds
            while self._wait_until(context, next_poll_at, deadline):
                result = self._lookup_once(target, provider, budget, deadline=deadline)
                completed_at = self._time()
                if completed_at >= deadline:
                    return self._completion_unknown(accepted)
                if result.lookup_state == "not_found":
                    if first_item_id is not None:
                        return self._completion_unknown(accepted)
                    next_poll_at = completed_at + self._limits.poll_interval_seconds
                    continue

                assert result.item_id is not None
                if first_item_id is None:
                    first_item_id = result.item_id
                    progress = context.progress(phase="polling", current=1, total=None, unit="steps")
                    if self._snapshot_cancelled(progress) or self._cancel_requested(context):
                        return self._completion_unknown(accepted)
                    next_poll_at = completed_at + self._limits.poll_interval_seconds
                    continue
                if result.item_id != first_item_id:
                    return self._completion_unknown(accepted)
                if self._cancel_requested(context):
                    return self._completion_unknown(accepted)
                if self.resolve_target(target.author_id, deadline=deadline) != target:
                    return self._completion_unknown(accepted)
                if self._cancel_requested(context) or self._time() >= deadline:
                    return self._completion_unknown(accepted)

                item_fingerprint = media_server_item_fingerprint(
                    profile_fingerprint=profile_fingerprint,
                    publication_fingerprint=target.publication_fingerprint,
                    selector_fingerprint=target.selector_fingerprint,
                    item_id=first_item_id,
                )
                observed_at = self._timestamp()
                if datetime.fromisoformat(observed_at) - datetime.fromisoformat(accepted_at) < timedelta(
                    seconds=_MIN_POLL_INTERVAL_SECONDS
                ):
                    return self._completion_unknown(accepted)
                observed = {
                    **accepted,
                    "observation_state": "observed",
                    "match_count": 1,
                    "verification_count": 2,
                    "item_fingerprint": item_fingerprint,
                    "observed_at": observed_at,
                }
                progress = context.progress(phase="polling", current=2, total=None, unit="steps")
                if self._snapshot_cancelled(progress) or self._cancel_requested(context):
                    return self._completion_unknown(accepted)
                try:
                    context.checkpoint(phase="observed", result_summary=observed)
                except Exception:
                    return self._completion_unknown(accepted)
                return OperationOutcome.success(observed)
            return self._completion_unknown(accepted)
        except Exception:
            return self._completion_unknown(accepted)

    def _pre_dispatch_lookup(
        self,
        target: MediaServerPublicationTarget,
        provider: MediaServerProvider,
        budget: _LookupBudget,
        deadline: float,
    ) -> MediaServerItemLookupResult | OperationOutcome:
        if self._time() >= deadline:
            return OperationOutcome.failed("media_server_timeout", retryable=True)
        try:
            result = self._lookup_once(target, provider, budget, deadline=deadline)
        except MediaServerError as error:
            return OperationOutcome.failed(error.code, retryable=error.retryable)
        if self._time() >= deadline:
            return OperationOutcome.failed("media_server_timeout", retryable=True)
        return result

    def _lookup_once(
        self,
        target: MediaServerPublicationTarget,
        provider: MediaServerProvider,
        budget: _LookupBudget,
        *,
        deadline: float | None,
    ) -> MediaServerItemLookupResult:
        try:
            budget.start(provider)
        except _LookupBudgetExhausted:
            raise MediaServerError("media_server_item_lookup_incomplete") from None
        try:
            result = self._server.lookup_item(target, deadline=deadline)
        except MediaServerError:
            raise
        except Exception:
            raise MediaServerError("media_server_item_lookup_incomplete") from None
        if not isinstance(result, MediaServerItemLookupResult):
            raise MediaServerError("media_server_item_lookup_incomplete")
        try:
            budget.finish(provider, result)
        except _LookupBudgetExhausted:
            raise MediaServerError("media_server_item_lookup_incomplete") from None
        return result

    def _require_same_target(
        self,
        target: MediaServerPublicationTarget,
        deadline: float,
    ) -> OperationOutcome | None:
        try:
            resolved = self.resolve_target(target.author_id, deadline=deadline)
        except MediaServerError as error:
            return OperationOutcome.failed(error.code, retryable=error.retryable)
        if resolved != target:
            return OperationOutcome.failed("media_server_publication_changed", retryable=False)
        if self._time() >= deadline:
            return OperationOutcome.failed("media_server_timeout", retryable=True)
        return None

    def _profile_identity(self) -> tuple[str, MediaServerProvider, str]:
        fingerprint = self._server.profile_fingerprint
        summary = self._server.safe_summary
        if fingerprint is None or summary is None or not summary.configured:
            raise MediaServerError("media_server_not_configured")
        if (
            not _is_digest(fingerprint)
            or summary.profile_fingerprint != fingerprint
            or summary.provider not in {"emby", "jellyfin"}
            or not _is_digest(summary.library_id_digest)
        ):
            raise MediaServerError("media_server_provider_mismatch")
        assert summary.library_id_digest is not None
        return fingerprint, summary.provider, summary.library_id_digest

    def _accepted_payload(
        self,
        *,
        target: MediaServerPublicationTarget,
        scan: MediaServerScanResult,
        profile_fingerprint: str,
        accepted_at: str,
    ) -> dict[str, object]:
        return {
            "schema_version": 2,
            "mode": _MODE,
            "provider": scan.provider,
            "server_version": scan.server_version,
            "profile_fingerprint": profile_fingerprint,
            "library_id_digest": scan.library_id_digest,
            "scan_state": scan.scan_state,
            "publication_fingerprint": target.publication_fingerprint,
            "selector_fingerprint": target.selector_fingerprint,
            "baseline_state": "not_found",
            "observation_state": "pending",
            "match_count": 0,
            "verification_count": 0,
            "accepted_at": accepted_at,
        }

    @staticmethod
    def _completion_unknown(accepted: Mapping[str, object]) -> OperationOutcome:
        return OperationOutcome.failed(
            "media_server_scan_completion_unknown",
            retryable=False,
            payload=accepted,
        )

    def _wait_until(
        self,
        context: MediaServerObservationContextPort,
        not_before: float,
        deadline: float,
    ) -> bool:
        while True:
            if self._cancel_requested(context):
                return False
            now = self._time()
            if now >= deadline:
                return False
            if now >= not_before:
                return True
            if context.cancellation.wait(min(not_before, deadline) - now):
                return False

    @staticmethod
    def _snapshot_cancelled(snapshot: MediaServerObservationSnapshotPort) -> bool:
        return snapshot.cancel_requested_at is not None

    @staticmethod
    def _cancel_requested(context: MediaServerObservationContextPort) -> bool:
        return context.cancel_requested or context.cancellation.is_set()

    def _time(self) -> float:
        try:
            value = self._monotonic()
        except (TypeError, ValueError, OverflowError):
            raise MediaServerError("media_server_item_lookup_incomplete") from None
        if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
            raise MediaServerError("media_server_item_lookup_incomplete")
        return float(value)

    def _timestamp(self) -> str:
        try:
            value = self._clock()
        except (TypeError, ValueError, OverflowError):
            raise MediaServerError("media_server_item_lookup_incomplete") from None
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise MediaServerError("media_server_item_lookup_incomplete")
        return value.astimezone(UTC).isoformat()


__all__ = [
    "MediaServerAuthorLookupResult",
    "MediaServerCancellationPort",
    "MediaServerObservationContextPort",
    "MediaServerObservationLimits",
    "MediaServerObservationServerPort",
    "MediaServerObservationService",
    "MediaServerObservationSnapshotPort",
    "MediaServerPublicationResolverPort",
    "media_server_item_fingerprint",
    "media_server_observation_fingerprint",
]
