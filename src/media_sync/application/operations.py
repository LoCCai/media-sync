"""Process-local execution for durable, lease-fenced operator requests.

The coordinator deliberately persists control-plane identity before it starts
an in-memory callable.  Python callables are never persisted or reconstructed:
after a process restart, expired work is reconciled only from exact durable
LoginSession or Job subjects.
"""

from __future__ import annotations

import re
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal, Protocol, TypeVar
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from media_sync.infrastructure.db import (
    Account,
    Asset,
    Database,
    Job,
    LoginSession,
    OperationEventSnapshot,
    OperationLease,
    OperationLeaseLostError,
    OperationRecoveryCandidate,
    OperationRepository,
    OperationSnapshot,
    OperationStateConflictError,
    OperationSubjectInput,
    OperationSubjectSnapshot,
)
from media_sync.infrastructure.db.database import SQLITE_IMMEDIATE_OPTION

from .operation_payloads import (
    OPERATION_KINDS,
    OperationKind,
    OperationPayloadError,
    operation_event_context,
    operation_result_summary,
)

OperationTerminalState = Literal["succeeded", "failed_retryable", "failed_terminal", "cancelled"]
SubjectType = Literal["login_session", "job", "sync_run"]
SubjectRole = Literal["execution", "result", "related"]
_T = TypeVar("_T")

_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_ERROR_CODE = re.compile(r"[a-z][a-z0-9_.-]{0,127}\Z")
_DEFAULT_OPERATION_LEASE_SECONDS = 60
_DEFAULT_HEARTBEAT_SECONDS = 10.0
_DEFAULT_JOIN_TIMEOUT_SECONDS = 5.0
_WRITE_ATTEMPTS = 4
_WRITE_RETRY_SECONDS = 0.01
_KIND_TARGET_TYPES: Mapping[str, str | None] = {
    "account-login": "account",
    "asset-download": "asset",
    "scheduler-run": None,
    "pipeline-run": None,
    "emby-export": "author",
}


class OperationCoordinatorError(RuntimeError):
    """A fixed-code coordinator failure safe for an API boundary."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class DurableSubjectRef:
    """One exact durable domain identity linked by an application service."""

    subject_type: SubjectType
    subject_id: str
    role: SubjectRole = "execution"

    def __post_init__(self) -> None:
        if self.subject_type not in {"login_session", "job", "sync_run"}:
            raise ValueError("subject_type is outside the application hook vocabulary")
        try:
            canonical_id = str(UUID(self.subject_id))
        except (AttributeError, TypeError, ValueError) as exc:
            raise ValueError("subject_id must be a canonical UUID") from exc
        if canonical_id != self.subject_id:
            raise ValueError("subject_id must be a canonical UUID")
        if self.role not in {"execution", "result", "related"}:
            raise ValueError("role is outside the application hook vocabulary")


class DurableSubjectHook(Protocol):
    """Link a subject using the caller's existing outer transaction."""

    def __call__(self, session: Session, subject: DurableSubjectRef) -> None: ...


@dataclass(frozen=True, slots=True)
class OperationOutcome:
    """Closed terminal intent returned by an in-memory operation callable."""

    state: OperationTerminalState
    payload: Mapping[str, object] | None = field(default=None, repr=False)
    error_code: str | None = None

    def __post_init__(self) -> None:
        if self.state not in {"succeeded", "failed_retryable", "failed_terminal", "cancelled"}:
            raise ValueError("operation outcome state is invalid")
        if self.state in {"failed_retryable", "failed_terminal"}:
            if not isinstance(self.error_code, str) or _ERROR_CODE.fullmatch(self.error_code) is None:
                raise ValueError("failed operation outcomes require a fixed error code")
            operation_event_context(
                "operation_failed",
                {
                    "error_code": self.error_code,
                    "retryable": self.state == "failed_retryable",
                },
            )
        elif self.error_code is not None:
            raise ValueError("successful or cancelled outcomes cannot carry an error code")
        if self.state == "succeeded" and self.payload is None:
            raise ValueError("successful operation outcomes require a result payload")
        if self.payload is not None and not isinstance(self.payload, Mapping):
            raise TypeError("operation outcome payload must be a mapping")

    @classmethod
    def success(cls, payload: Mapping[str, object]) -> OperationOutcome:
        return cls("succeeded", payload=payload)

    @classmethod
    def failed(
        cls,
        error_code: str,
        *,
        retryable: bool,
        payload: Mapping[str, object] | None = None,
    ) -> OperationOutcome:
        if type(retryable) is not bool:
            raise TypeError("retryable must be a boolean")
        return cls(
            "failed_retryable" if retryable else "failed_terminal",
            payload=payload,
            error_code=error_code,
        )

    @classmethod
    def cancelled(cls, payload: Mapping[str, object] | None = None) -> OperationOutcome:
        return cls("cancelled", payload=payload)


class OperationCallable(Protocol):
    def __call__(self, context: OperationExecutionContext) -> OperationOutcome: ...


@dataclass(frozen=True, slots=True)
class OperationExecution:
    """Persistable operation identity plus its process-local callable."""

    kind: OperationKind
    request_fingerprint: str
    execute: OperationCallable = field(repr=False)
    idempotency_key_hash: str | None = field(default=None, repr=False)
    exclusive_key: str | None = None
    target_type: str | None = None
    target_id: str | None = None
    requested_by: str = "local-api"
    correlation_id: str | None = None
    phase: str = "starting"

    def __post_init__(self) -> None:
        if self.kind not in OPERATION_KINDS:
            raise ValueError("operation kind is invalid")
        if not isinstance(self.request_fingerprint, str) or _DIGEST.fullmatch(self.request_fingerprint) is None:
            raise ValueError("request_fingerprint must be a lowercase SHA-256 digest")
        if self.idempotency_key_hash is not None and (
            not isinstance(self.idempotency_key_hash, str) or _DIGEST.fullmatch(self.idempotency_key_hash) is None
        ):
            raise ValueError("idempotency_key_hash must be a lowercase SHA-256 digest")
        if not callable(self.execute):
            raise TypeError("execute must be callable")
        if (self.target_type is None) != (self.target_id is None):
            raise ValueError("target_type and target_id must be supplied together")
        expected_target_type = _KIND_TARGET_TYPES[self.kind]
        if self.target_type != expected_target_type:
            raise ValueError("target_type does not match operation kind")
        if self.target_id is not None:
            try:
                canonical_target = str(UUID(self.target_id))
            except (TypeError, ValueError) as exc:
                raise ValueError("target_id must be a canonical UUID") from exc
            if canonical_target != self.target_id:
                raise ValueError("target_id must be a canonical UUID")
        if not isinstance(self.phase, str) or not self.phase:
            raise ValueError("phase must be non-empty")


@dataclass(frozen=True, slots=True)
class OperationSubmission:
    """Durable identity returned after submit has committed."""

    operation: OperationSnapshot
    replayed: bool

    @property
    def operation_id(self) -> str:
        return self.operation.id


@dataclass(frozen=True, slots=True)
class OperationShutdownSummary:
    requested: int
    joined: int
    still_running: int


@dataclass(frozen=True, slots=True)
class OperationReconciliationSummary:
    scanned: int
    succeeded: int
    failed_terminal: int
    cancelled: int
    interrupted: int
    conflicted: int


@dataclass(slots=True)
class _OperationHandle:
    cancellation: threading.Event = field(repr=False)
    lease_owner: str
    lease_token: str = field(repr=False)
    thread: threading.Thread = field(repr=False)


@dataclass(frozen=True, slots=True)
class _TerminalIntent:
    state: OperationTerminalState
    summary: Mapping[str, object] = field(repr=False)
    error_code: str | None = None


@dataclass(frozen=True, slots=True)
class OperationExecutionContext:
    """Safe process-local capabilities supplied to one operation callable."""

    operation_id: str
    cancellation: threading.Event = field(repr=False)
    worker_id: str
    _coordinator: OperationCoordinator = field(repr=False, compare=False)
    _handle: _OperationHandle = field(repr=False, compare=False)

    @property
    def subject_hook(self) -> DurableSubjectHook:
        return self._link_subject

    @property
    def cancel_requested(self) -> bool:
        return self.cancellation.is_set()

    def _link_subject(self, session: Session, subject: DurableSubjectRef) -> None:
        self._coordinator._link_subject(session, self._handle, self.operation_id, subject)

    def progress(
        self,
        *,
        phase: str,
        current: int,
        unit: str,
        total: int | None = None,
    ) -> OperationSnapshot:
        return self._coordinator._progress(
            self._handle,
            self.operation_id,
            phase=phase,
            current=current,
            total=total,
            unit=unit,
        )

    def phase(self, phase: str) -> OperationSnapshot:
        return self._coordinator._phase(self._handle, self.operation_id, phase)


@dataclass(frozen=True, slots=True)
class _ReconciliationDecision:
    state: Literal["succeeded", "failed_terminal", "cancelled", "interrupted"]
    error_code: str | None
    subject_type: Literal["login_session", "job"]
    subject_state: str
    summary: Mapping[str, object] = field(default_factory=dict, repr=False)


def operation_worker_id(operation_id: str) -> str:
    """Derive every domain Job owner from its durable Operation UUID."""

    try:
        canonical_id = str(UUID(operation_id))
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError("operation_id must be a canonical UUID") from exc
    if canonical_id != operation_id:
        raise ValueError("operation_id must be a canonical UUID")
    return f"operation-{canonical_id}"


class OperationCoordinator:
    """Own one process's local operation threads and a single lease monitor."""

    def __init__(
        self,
        database: Database,
        *,
        lease_seconds: int = _DEFAULT_OPERATION_LEASE_SECONDS,
        heartbeat_interval_seconds: float = _DEFAULT_HEARTBEAT_SECONDS,
        join_timeout_seconds: float = _DEFAULT_JOIN_TIMEOUT_SECONDS,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if not isinstance(database, Database):
            raise TypeError("database must be a Database")
        if type(lease_seconds) is not int or not 1 <= lease_seconds <= 86_400:
            raise ValueError("lease_seconds must be between 1 and 86400")
        if (
            isinstance(heartbeat_interval_seconds, bool)
            or not isinstance(heartbeat_interval_seconds, int | float)
            or not 0 < float(heartbeat_interval_seconds) < lease_seconds
        ):
            raise ValueError("heartbeat_interval_seconds must be positive and shorter than the lease")
        if (
            isinstance(join_timeout_seconds, bool)
            or not isinstance(join_timeout_seconds, int | float)
            or float(join_timeout_seconds) < 0
        ):
            raise ValueError("join_timeout_seconds must be non-negative")
        if clock is not None and not callable(clock):
            raise TypeError("clock must be callable")

        self._database = database
        self._lease_seconds = lease_seconds
        self._heartbeat_interval_seconds = float(heartbeat_interval_seconds)
        self._join_timeout_seconds = float(join_timeout_seconds)
        self._clock = clock or (lambda: datetime.now(UTC))
        self._instance_id = str(uuid4())
        self._handles: dict[str, _OperationHandle] = {}
        self._pending_terminals: dict[str, _TerminalIntent] = {}
        self._observing_cancel: set[str] = set()
        self._lock = threading.Lock()
        self._monitor_stop = threading.Event()
        self._monitor: threading.Thread | None = None
        self._closing = False

    @property
    def instance_id(self) -> str:
        return self._instance_id

    def __enter__(self) -> OperationCoordinator:
        self.start()
        return self

    def __exit__(self, *_: object) -> None:
        self.shutdown()

    def start(self) -> None:
        """Start the one process-wide heartbeat monitor for this coordinator."""

        with self._lock:
            if self._closing:
                raise OperationCoordinatorError("operation_coordinator_closed")
            if self._monitor is not None and self._monitor.is_alive():
                return
            self._monitor_stop.clear()
            monitor = threading.Thread(
                target=self._monitor_loop,
                name=f"media-sync-operation-monitor-{self._instance_id}",
                daemon=True,
            )
            self._monitor = monitor
            monitor.start()

    def submit(self, execution: OperationExecution) -> OperationSubmission:
        """Atomically create/replay and claim before starting an in-memory thread."""

        if not isinstance(execution, OperationExecution):
            raise TypeError("execution must be an OperationExecution")
        with self._lock:
            if self._closing:
                raise OperationCoordinatorError("operation_coordinator_closed")

        owner: str | None = None
        lease: OperationLease | None = None
        with self._database.session() as session:
            repository = OperationRepository(session)
            start = repository.create_or_replay(
                kind=execution.kind,
                request_fingerprint=execution.request_fingerprint,
                idempotency_key_hash=execution.idempotency_key_hash,
                exclusive_key=execution.exclusive_key,
                target_type=execution.target_type,
                target_id=execution.target_id,
                requested_by=execution.requested_by,
                correlation_id=execution.correlation_id,
                phase=execution.phase,
                at=self._now(),
            )
            if not start.replayed:
                owner = self._lease_owner(start.operation_id)
                lease = repository.claim(
                    start.operation_id,
                    expected_revision=start.revision,
                    lease_owner=owner,
                    lease_seconds=self._lease_seconds,
                    at=self._now(),
                )
            snapshot = repository.require(start.operation_id)

        if start.replayed:
            return OperationSubmission(snapshot, replayed=True)
        assert owner is not None and lease is not None

        cancellation = threading.Event()
        placeholder = threading.current_thread()
        handle = _OperationHandle(cancellation, owner, lease.lease_token, placeholder)
        try:
            context = OperationExecutionContext(
                operation_id=start.operation_id,
                cancellation=cancellation,
                worker_id=operation_worker_id(start.operation_id),
                _coordinator=self,
                _handle=handle,
            )
            worker = threading.Thread(
                target=self._run_execution,
                args=(execution, context, handle),
                name=f"media-sync-operation-{start.operation_id}",
                daemon=True,
            )
            handle.thread = worker
            with self._lock:
                if self._closing:
                    cancellation.set()
                self._handles[start.operation_id] = handle
            self.start()
            worker.start()
        except Exception:
            with self._lock:
                self._handles.setdefault(start.operation_id, handle)
            intent = self._fixed_failure_intent("operation_thread_start_failed", retryable=True)
            if self._finish_intent(start.operation_id, handle, intent):
                self._drop_handle(start.operation_id, handle)
            else:
                self._defer_terminal(start.operation_id, handle, intent)
        return OperationSubmission(self.get(start.operation_id), replayed=False)

    def get(self, operation_id: str) -> OperationSnapshot:
        with self._database.session() as session:
            return OperationRepository(session).require(operation_id)

    def list_operations(
        self,
        *,
        kind: str | None = None,
        state: str | None = None,
        target_type: str | None = None,
        target_id: str | None = None,
        correlation_id: str | None = None,
        before: tuple[datetime, str] | None = None,
        limit: int = 100,
    ) -> list[OperationSnapshot]:
        with self._database.session() as session:
            return OperationRepository(session).list(
                kind=kind,
                state=state,
                target_type=target_type,
                target_id=target_id,
                correlation_id=correlation_id,
                before=before,
                limit=limit,
            )

    def list_subjects(self, operation_id: str) -> list[OperationSubjectSnapshot]:
        with self._database.session() as session:
            return OperationRepository(session).list_subjects(operation_id)

    def events_for_operation(
        self,
        operation_id: str,
        *,
        after_operation_sequence: int = 0,
        limit: int = 100,
    ) -> list[OperationEventSnapshot]:
        with self._database.session() as session:
            return OperationRepository(session).events_for_operation(
                operation_id,
                after_operation_sequence=after_operation_sequence,
                limit=limit,
            )

    def events_after(
        self,
        after_stream_sequence: int,
        *,
        operation_id: str | None = None,
        limit: int = 100,
    ) -> list[OperationEventSnapshot]:
        with self._database.session() as session:
            return OperationRepository(session).events_after(
                after_stream_sequence,
                operation_id=operation_id,
                limit=limit,
            )

    def stream_bounds(self) -> tuple[int, int]:
        with self._database.session() as session:
            return OperationRepository(session).stream_bounds()

    def request_cancel(
        self,
        operation_id: str,
        *,
        expected_revision: int | None = None,
    ) -> OperationSnapshot:
        """Persist cancellation; notify a local owner after durable commit."""

        def request(session: Session) -> OperationSnapshot:
            repository = OperationRepository(session)
            observed = repository.require(operation_id)
            revision = observed.revision if expected_revision is None else expected_revision
            return repository.request_cancel(operation_id, expected_revision=revision, at=self._now())

        snapshot = self._run_write(request)
        handle = self._local_handle(operation_id)
        if handle is not None and snapshot.state == "running" and snapshot.cancel_requested_at is not None:
            self._observe_cancel(operation_id, handle)
        return self.get(operation_id)

    cancel = request_cancel

    def reconcile_expired(
        self,
        *,
        limit: int = 100,
        at: datetime | None = None,
    ) -> OperationReconciliationSummary:
        """Converge expired operations from exact durable truth without rerunning work."""

        current = self._normalize_time(at) if at is not None else self._now()
        with self._database.session() as session:
            candidates = OperationRepository(session).list_expired_candidates(at=current, limit=limit)

        counts = {
            "succeeded": 0,
            "failed_terminal": 0,
            "cancelled": 0,
            "interrupted": 0,
            "conflicted": 0,
        }
        for candidate in candidates:
            try:

                def reconcile(
                    session: Session,
                    recovery_candidate: OperationRecoveryCandidate = candidate,
                ) -> tuple[OperationSnapshot, _ReconciliationDecision]:
                    repository = OperationRepository(session)
                    subjects = repository.list_subjects(recovery_candidate.operation_id)
                    decision = self._reconciliation_decision(session, recovery_candidate, subjects)
                    context = operation_event_context(
                        "operation_reconciled",
                        {
                            "subject_type": decision.subject_type,
                            "subject_state": decision.subject_state,
                        },
                    )
                    return (
                        repository.reconcile(
                            recovery_candidate,
                            state=decision.state,
                            error_code=decision.error_code,
                            context=context,
                            result_summary=decision.summary,
                            at=current,
                        ),
                        decision,
                    )

                _snapshot, decision = self._run_write(reconcile)
            except Exception:
                counts["conflicted"] += 1
            else:
                counts[decision.state] += 1
        return OperationReconciliationSummary(
            scanned=len(candidates),
            succeeded=counts["succeeded"],
            failed_terminal=counts["failed_terminal"],
            cancelled=counts["cancelled"],
            interrupted=counts["interrupted"],
            conflicted=counts["conflicted"],
        )

    def shutdown(self, *, timeout_seconds: float | None = None) -> OperationShutdownSummary:
        """Request cooperative cancellation and join local workers for a bounded time."""

        timeout = self._join_timeout_seconds if timeout_seconds is None else timeout_seconds
        if isinstance(timeout, bool) or not isinstance(timeout, int | float) or float(timeout) < 0:
            raise ValueError("timeout_seconds must be non-negative")
        with self._lock:
            self._closing = True
            handles = tuple(self._handles.items())

        for operation_id, handle in handles:
            try:

                def request_shutdown_cancel(
                    session: Session,
                    target_operation_id: str = operation_id,
                ) -> OperationSnapshot:
                    repository = OperationRepository(session)
                    snapshot = repository.require(target_operation_id)
                    if snapshot.state == "running" and snapshot.cancel_requested_at is None:
                        return repository.request_cancel(
                            target_operation_id,
                            expected_revision=snapshot.revision,
                            at=self._now(),
                        )
                    return snapshot

                self._run_write(request_shutdown_cancel)
            except Exception:
                pass
            self._observe_cancel(operation_id, handle)

        deadline = time.monotonic() + float(timeout)
        joined = 0
        current_thread = threading.current_thread()
        for _operation_id, handle in handles:
            if handle.thread is current_thread:
                continue
            remaining = max(0.0, deadline - time.monotonic())
            if handle.thread.ident is not None:
                handle.thread.join(remaining)
            if not handle.thread.is_alive():
                joined += 1

        still_running = sum(1 for _operation_id, handle in handles if handle.thread.is_alive())
        monitor = self._monitor
        self._monitor_stop.set()
        if monitor is not None and monitor is not current_thread and monitor.is_alive():
            monitor.join(max(0.0, deadline - time.monotonic()))
        return OperationShutdownSummary(len(handles), joined, still_running)

    close = shutdown

    def _run_execution(
        self,
        execution: OperationExecution,
        context: OperationExecutionContext,
        handle: _OperationHandle,
    ) -> None:
        if handle.cancellation.is_set():
            intent = self._terminal_intent(execution.kind, OperationOutcome.cancelled())
        else:
            try:
                outcome = execution.execute(context)
            except BaseException:
                intent = self._fixed_failure_intent("operation_execution_failed", retryable=True)
            else:
                if not isinstance(outcome, OperationOutcome):
                    intent = self._fixed_failure_intent("operation_outcome_invalid", retryable=False)
                else:
                    intent = self._terminal_intent(execution.kind, outcome)

        if self._finish_intent(context.operation_id, handle, intent):
            self._drop_handle(context.operation_id, handle)
        else:
            self._defer_terminal(context.operation_id, handle, intent)

    def _terminal_intent(
        self,
        kind: OperationKind,
        outcome: OperationOutcome,
    ) -> _TerminalIntent:
        try:
            summary = operation_result_summary(kind, outcome.payload) if outcome.payload is not None else {}
        except OperationPayloadError:
            return self._fixed_failure_intent("operation_result_invalid", retryable=False)
        if outcome.state == "cancelled":
            # The authoritative phase is projected immediately before CAS.
            return _TerminalIntent(outcome.state, summary)
        if outcome.state in {"failed_retryable", "failed_terminal"}:
            assert outcome.error_code is not None
            operation_event_context(
                "operation_failed",
                {
                    "error_code": outcome.error_code,
                    "retryable": outcome.state == "failed_retryable",
                },
            )
        return _TerminalIntent(outcome.state, summary, outcome.error_code)

    @staticmethod
    def _fixed_failure_intent(error_code: str, *, retryable: bool) -> _TerminalIntent:
        operation_event_context(
            "operation_failed",
            {"error_code": error_code, "retryable": retryable},
        )
        return _TerminalIntent(
            "failed_retryable" if retryable else "failed_terminal",
            {},
            error_code,
        )

    def _finish_intent(
        self,
        operation_id: str,
        handle: _OperationHandle,
        intent: _TerminalIntent,
    ) -> bool:
        def finish(session: Session) -> OperationSnapshot:
            repository = OperationRepository(session)
            snapshot = repository.require(operation_id)
            if snapshot.state != "running":
                return snapshot
            if intent.state == "succeeded":
                return repository.finish_succeeded(
                    operation_id,
                    expected_revision=snapshot.revision,
                    lease_owner=handle.lease_owner,
                    lease_token=handle.lease_token,
                    result_summary=intent.summary,
                    at=self._now(),
                )
            if intent.state == "cancelled":
                operation_event_context("operation_cancelled", {"phase": snapshot.phase})
                return repository.finish_cancelled(
                    operation_id,
                    expected_revision=snapshot.revision,
                    lease_owner=handle.lease_owner,
                    lease_token=handle.lease_token,
                    result_summary=intent.summary,
                    at=self._now(),
                )
            assert intent.error_code is not None
            return repository.finish_failed(
                operation_id,
                expected_revision=snapshot.revision,
                lease_owner=handle.lease_owner,
                lease_token=handle.lease_token,
                retryable=intent.state == "failed_retryable",
                error_code=intent.error_code,
                result_summary=intent.summary,
                at=self._now(),
            )

        try:
            self._run_write(finish)
        except (OperationLeaseLostError, OperationStateConflictError):
            handle.cancellation.set()
            return True
        except Exception:
            return False
        return True

    def _finish_outcome(
        self,
        kind: OperationKind,
        operation_id: str,
        handle: _OperationHandle,
        outcome: OperationOutcome,
    ) -> bool:
        return self._finish_intent(operation_id, handle, self._terminal_intent(kind, outcome))

    def _finish_fixed_failure(
        self,
        operation_id: str,
        handle: _OperationHandle,
        *,
        error_code: str,
        retryable: bool,
    ) -> bool:
        return self._finish_intent(
            operation_id,
            handle,
            self._fixed_failure_intent(error_code, retryable=retryable),
        )

    def _finish_cancelled(
        self,
        kind: OperationKind,
        operation_id: str,
        handle: _OperationHandle,
        payload: Mapping[str, object] | None,
    ) -> bool:
        return self._finish_outcome(kind, operation_id, handle, OperationOutcome.cancelled(payload))

    def _progress(
        self,
        handle: _OperationHandle,
        operation_id: str,
        *,
        phase: str,
        current: int,
        total: int | None,
        unit: str,
    ) -> OperationSnapshot:
        context = operation_event_context(
            "operation_progressed",
            {
                "phase": phase,
                "progress_current": current,
                "progress_total": total,
                "progress_unit": unit,
            },
        )

        def progress(session: Session) -> OperationSnapshot:
            repository = OperationRepository(session)
            snapshot = repository.require(operation_id)
            return repository.progress(
                operation_id,
                expected_revision=snapshot.revision,
                lease_owner=handle.lease_owner,
                lease_token=handle.lease_token,
                phase=phase,
                current=current,
                total=total,
                unit=unit,
                context=context,
                at=self._now(),
            )

        return self._run_write(progress)

    def _phase(
        self,
        handle: _OperationHandle,
        operation_id: str,
        phase: str,
    ) -> OperationSnapshot:
        context = operation_event_context("operation_phase_changed", {"phase": phase})

        def change_phase(session: Session) -> OperationSnapshot:
            repository = OperationRepository(session)
            snapshot = repository.require(operation_id)
            return repository.progress(
                operation_id,
                expected_revision=snapshot.revision,
                lease_owner=handle.lease_owner,
                lease_token=handle.lease_token,
                phase=phase,
                event_code="operation_phase_changed",
                context=context,
                at=self._now(),
            )

        return self._run_write(change_phase)

    def _link_subject(
        self,
        session: Session,
        handle: _OperationHandle,
        operation_id: str,
        subject: DurableSubjectRef,
    ) -> None:
        if not isinstance(session, Session):
            raise TypeError("session must be a SQLAlchemy Session")
        if not isinstance(subject, DurableSubjectRef):
            raise TypeError("subject must be a DurableSubjectRef")
        repository = OperationRepository(session)
        snapshot = repository.require(operation_id)
        context = operation_event_context(
            "operation_entity_linked",
            {
                "subject_type": subject.subject_type,
                "subject_id": subject.subject_id,
                "role": subject.role,
            },
        )
        repository.link_subject(
            operation_id,
            OperationSubjectInput(subject.subject_type, subject.subject_id, subject.role),
            expected_revision=snapshot.revision,
            lease_owner=handle.lease_owner,
            lease_token=handle.lease_token,
            context=context,
            at=self._now(),
        )

    def _monitor_loop(self) -> None:
        while not self._monitor_stop.wait(self._heartbeat_interval_seconds):
            with self._lock:
                handles = tuple(self._handles.items())
            for operation_id, handle in handles:
                self._monitor_handle(operation_id, handle)

    def _monitor_handle(self, operation_id: str, handle: _OperationHandle) -> None:
        with self._lock:
            pending = self._pending_terminals.get(operation_id)
        if pending is not None:
            if self._finish_intent(operation_id, handle, pending):
                self._drop_handle(operation_id, handle)
            return
        try:
            with self._database.session() as session:
                snapshot = OperationRepository(session).require(operation_id)
            if snapshot.state != "running":
                handle.cancellation.set()
                if not handle.thread.is_alive():
                    self._drop_handle(operation_id, handle)
                return
            if snapshot.cancel_requested_at is not None and not handle.cancellation.is_set():
                self._observe_cancel(operation_id, handle)

            def heartbeat(session: Session) -> OperationLease:
                repository = OperationRepository(session)
                current = repository.require(operation_id)
                if current.state != "running":
                    raise OperationStateConflictError("operation_state_conflict", operation_id)
                return repository.heartbeat(
                    operation_id,
                    expected_revision=current.revision,
                    lease_owner=handle.lease_owner,
                    lease_token=handle.lease_token,
                    lease_seconds=self._lease_seconds,
                    at=self._now(),
                )

            self._run_write(heartbeat)
        except (OperationLeaseLostError, OperationStateConflictError):
            handle.cancellation.set()
            if not handle.thread.is_alive():
                self._drop_handle(operation_id, handle)
        except Exception:
            handle.cancellation.set()

    def _observe_cancel(self, operation_id: str, handle: _OperationHandle) -> None:
        with self._lock:
            if handle.cancellation.is_set() or operation_id in self._observing_cancel:
                return
            self._observing_cancel.add(operation_id)
        try:
            try:

                def observe(session: Session) -> OperationSnapshot:
                    repository = OperationRepository(session)
                    snapshot = repository.require(operation_id)
                    if snapshot.state != "running" or snapshot.cancel_requested_at is None:
                        return snapshot
                    phase = snapshot.phase or "running"
                    context = operation_event_context("operation_cancel_observed", {"phase": phase})
                    return repository.progress(
                        operation_id,
                        expected_revision=snapshot.revision,
                        lease_owner=handle.lease_owner,
                        lease_token=handle.lease_token,
                        phase=phase,
                        event_code="operation_cancel_observed",
                        context=context,
                        at=self._now(),
                    )

                self._run_write(observe)
            finally:
                handle.cancellation.set()
        except Exception:
            # Cancellation is a local safety capability. Persistence failure
            # cannot justify continuing work after the request was observed.
            handle.cancellation.set()
        finally:
            with self._lock:
                self._observing_cancel.discard(operation_id)

    def _reconciliation_decision(
        self,
        session: Session,
        candidate: OperationRecoveryCandidate,
        subjects: Sequence[OperationSubjectSnapshot],
    ) -> _ReconciliationDecision:
        if candidate.kind in {"scheduler-run", "pipeline-run"}:
            return self._interrupted("job", "incomplete")
        if candidate.kind == "account-login":
            return self._reconcile_login(session, candidate, subjects)
        if candidate.kind == "asset-download":
            return self._reconcile_asset(session, candidate, subjects)
        if candidate.kind == "emby-export":
            return self._reconcile_emby(session, candidate, subjects)
        return self._interrupted("job", "incomplete")

    def _reconcile_login(
        self,
        session: Session,
        candidate: OperationRecoveryCandidate,
        subjects: Sequence[OperationSubjectSnapshot],
    ) -> _ReconciliationDecision:
        subject_id = self._single_execution_subject(subjects, "login_session")
        if subject_id is None or candidate.target_type != "account" or candidate.target_id is None:
            return self._interrupted("login_session", "missing")
        login = session.get(LoginSession, subject_id)
        if login is None or login.account_id != candidate.target_id:
            return self._interrupted("login_session", "missing")
        account = session.get(Account, login.account_id)
        if account is None:
            return self._interrupted("login_session", "incomplete")
        if login.status == "succeeded" and account.auth_status == "authenticated":
            payload = self._login_recovery_payload(login, account.auth_status, "authenticated")
            return _ReconciliationDecision(
                "succeeded",
                None,
                "login_session",
                "succeeded",
                self._safe_result("account-login", payload),
            )
        if login.status == "cancelled":
            return _ReconciliationDecision("cancelled", None, "login_session", "cancelled")
        if login.status in {"expired", "failed"}:
            runner_status = "expired" if login.status == "expired" else "failed"
            payload = self._login_recovery_payload(login, account.auth_status, runner_status)
            return _ReconciliationDecision(
                "failed_terminal",
                "operation_login_expired" if login.status == "expired" else "operation_login_failed",
                "login_session",
                login.status,
                self._safe_result("account-login", payload),
            )
        return self._interrupted("login_session", login.status)

    def _reconcile_asset(
        self,
        session: Session,
        candidate: OperationRecoveryCandidate,
        subjects: Sequence[OperationSubjectSnapshot],
    ) -> _ReconciliationDecision:
        job_id = self._single_execution_subject(subjects, "job")
        if job_id is None or candidate.target_type != "asset" or candidate.target_id is None:
            return self._interrupted("job", "missing")
        job = session.get(Job, job_id)
        asset = session.get(Asset, candidate.target_id)
        if job is None or asset is None or not isinstance(job.payload, Mapping):
            return self._interrupted("job", "missing")
        if (
            job.job_type != "asset_download"
            or job.payload.get("asset_id") != asset.id
            or job.payload.get("generation") != asset.generation
            or asset.download_job_id != job.id
        ):
            return self._interrupted("job", "incomplete")
        if job.status == "succeeded" and asset.status == "verified":
            payload = {
                "asset_id": asset.id,
                "job_id": job.id,
                "ok": True,
                "status": asset.status,
                "disposition": "downloaded",
                "generation": asset.generation,
                "size_bytes": asset.size_bytes,
            }
            return _ReconciliationDecision(
                "succeeded",
                None,
                "job",
                "succeeded",
                self._safe_result("asset-download", payload),
            )
        if job.status == "failed_terminal" and asset.status == "failed_terminal":
            return _ReconciliationDecision(
                "failed_terminal",
                "operation_domain_failed_terminal",
                "job",
                "failed_terminal",
            )
        if job.status == "cancelled" and asset.status != "downloading":
            return _ReconciliationDecision("cancelled", None, "job", "cancelled")
        return self._interrupted("job", job.status)

    def _reconcile_emby(
        self,
        session: Session,
        candidate: OperationRecoveryCandidate,
        subjects: Sequence[OperationSubjectSnapshot],
    ) -> _ReconciliationDecision:
        job_id = self._single_execution_subject(subjects, "job")
        if job_id is None or candidate.target_type != "author" or candidate.target_id is None:
            return self._interrupted("job", "missing")
        job = session.get(Job, job_id)
        if (
            job is None
            or job.job_type != "export.emby"
            or not isinstance(job.payload, Mapping)
            or job.payload.get("author_id") != candidate.target_id
        ):
            return self._interrupted("job", "missing")
        if job.status == "succeeded":
            raw_result = job.payload.get("result")
            if not isinstance(raw_result, Mapping):
                return self._interrupted("job", "incomplete")
            managed_count = raw_result.get("managed_file_count")
            if isinstance(managed_count, bool) or not isinstance(managed_count, int) or managed_count < 0:
                return self._interrupted("job", "incomplete")
            payload = {
                "author_id": candidate.target_id,
                "job_id": job.id,
                "already_exported": False,
                "managed_file_count": managed_count,
            }
            return _ReconciliationDecision(
                "succeeded",
                None,
                "job",
                "succeeded",
                self._safe_result("emby-export", payload),
            )
        if job.status == "failed_terminal":
            return _ReconciliationDecision(
                "failed_terminal",
                "operation_domain_failed_terminal",
                "job",
                "failed_terminal",
            )
        if job.status == "cancelled":
            return _ReconciliationDecision("cancelled", None, "job", "cancelled")
        return self._interrupted("job", job.status)

    @staticmethod
    def _single_execution_subject(
        subjects: Sequence[OperationSubjectSnapshot],
        subject_type: str,
    ) -> str | None:
        execution = [item.subject_id for item in subjects if item.role == "execution"]
        if len(execution) != 1:
            return None
        matching = [
            item.subject_id for item in subjects if item.role == "execution" and item.subject_type == subject_type
        ]
        return matching[0] if len(matching) == 1 else None

    @staticmethod
    def _login_recovery_payload(
        login: LoginSession,
        auth_status: str,
        runner_status: str,
    ) -> Mapping[str, object]:
        return {
            "account_id": login.account_id,
            "login_session_id": login.id,
            "runner_status": runner_status,
            "login_session_status": login.status,
            "auth_status": auth_status,
            "expires_at": login.expires_at,
            "completed_at": login.completed_at,
        }

    @staticmethod
    def _safe_result(kind: OperationKind, payload: Mapping[str, object]) -> Mapping[str, object]:
        try:
            return operation_result_summary(kind, payload)
        except OperationPayloadError:
            return {}

    @staticmethod
    def _interrupted(
        subject_type: Literal["login_session", "job"],
        subject_state: str,
    ) -> _ReconciliationDecision:
        return _ReconciliationDecision(
            "interrupted",
            "operation_interrupted",
            subject_type,
            subject_state,
        )

    def _local_handle(self, operation_id: str) -> _OperationHandle | None:
        with self._lock:
            return self._handles.get(operation_id)

    def _defer_terminal(
        self,
        operation_id: str,
        handle: _OperationHandle,
        intent: _TerminalIntent,
    ) -> None:
        with self._lock:
            if self._handles.get(operation_id) is handle:
                self._pending_terminals[operation_id] = intent

    def _drop_handle(self, operation_id: str, handle: _OperationHandle) -> None:
        with self._lock:
            if self._handles.get(operation_id) is handle:
                self._handles.pop(operation_id, None)
                self._pending_terminals.pop(operation_id, None)
            self._observing_cancel.discard(operation_id)
            should_stop_monitor = self._closing and not self._handles
        if should_stop_monitor:
            self._monitor_stop.set()

    def _lease_owner(self, operation_id: str) -> str:
        return f"operation:{self._instance_id}:{operation_id}"

    def _run_write(self, action: Callable[[Session], _T]) -> _T:
        """Run one authoritative read/CAS transaction with bounded retry.

        SQLite WAL cannot upgrade a deferred read transaction after another
        writer commits.  Reserving the writer before the authoritative read
        removes that BUSY_SNAPSHOT window; fresh transactions cover bounded
        storage contention without reusing a stale revision.
        """

        for attempt in range(_WRITE_ATTEMPTS):
            try:
                with self._database.session() as session:
                    if session.get_bind().dialect.name == "sqlite" and not session.in_transaction():
                        session.connection(
                            execution_options={SQLITE_IMMEDIATE_OPTION: True},  # type: ignore[misc]
                        )
                    return action(session)
            except (OperationLeaseLostError, OperationStateConflictError):
                raise
            except Exception:
                if attempt + 1 >= _WRITE_ATTEMPTS:
                    raise
                time.sleep(_WRITE_RETRY_SECONDS * (attempt + 1))
        raise AssertionError("bounded operation write loop did not return")

    def _now(self) -> datetime:
        return self._normalize_time(self._clock())

    @staticmethod
    def _normalize_time(value: datetime) -> datetime:
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("clock must return a timezone-aware datetime")
        return value.astimezone(UTC)


__all__ = [
    "DurableSubjectHook",
    "DurableSubjectRef",
    "OperationCallable",
    "OperationCoordinator",
    "OperationCoordinatorError",
    "OperationExecution",
    "OperationExecutionContext",
    "OperationOutcome",
    "OperationReconciliationSummary",
    "OperationShutdownSummary",
    "OperationSubmission",
    "OperationTerminalState",
    "operation_worker_id",
]
