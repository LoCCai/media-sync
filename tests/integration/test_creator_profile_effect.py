"""Real coordinator transactions fence profile database effects."""

from __future__ import annotations

import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import select, update

from media_sync.application.operations import (
    OperationCoordinator,
    OperationExecution,
    OperationExecutionContext,
    OperationOutcome,
)
from media_sync.infrastructure.db import (
    AccountRepository,
    Database,
    OperationLeaseLostError,
    OperationStateConflictError,
)
from media_sync.infrastructure.db.models import Account, Operation


@pytest.mark.parametrize(
    "boundary", ["valid", "cancel_before", "cancel_during", "expire_before", "expire_during", "raise"]
)
def test_effect_rolls_back_if_lease_or_cancellation_boundary_changes(tmp_path: Path, boundary: str) -> None:
    database = Database(f"sqlite+pysqlite:///{(tmp_path / 'effects.sqlite3').as_posix()}")
    database.create_schema()
    now = datetime.now(UTC)
    clock = [now]
    with database.session() as session:
        account_id = AccountRepository(session).create(platform="bili", display_name="original").id
    outcome = threading.Event()
    failures: list[type[Exception]] = []

    def execute(context: OperationExecutionContext) -> OperationOutcome:
        if boundary == "cancel_before":
            context.cancellation.set()
        if boundary == "expire_before":
            clock[0] = now + timedelta(seconds=120)

        def effect(session: Any) -> str:
            session.execute(update(Account).where(Account.id == account_id).values(display_name="changed"))
            if boundary == "cancel_during":
                context.cancellation.set()
            if boundary == "expire_during":
                clock[0] = now + timedelta(seconds=120)
            if boundary == "raise":
                raise ValueError("private callback error")
            return "effect result"

        try:
            assert context.commit_effect(effect) == "effect result"
        except (OperationLeaseLostError, OperationStateConflictError, ValueError) as exc:
            failures.append(type(exc))
        finally:
            clock[0] = now
            outcome.set()
        return OperationOutcome.failed("creator_profile_failed", retryable=False)

    try:
        with OperationCoordinator(database, clock=lambda: clock[0]) as coordinator:
            submitted = coordinator.submit(
                OperationExecution(
                    kind="creator-profile",
                    request_fingerprint="a" * 64,
                    target_type="account",
                    target_id=account_id,
                    execute=execute,
                )
            )
            assert outcome.wait(5)
            deadline = time.monotonic() + 5
            while coordinator.get(submitted.operation_id).state == "running" and time.monotonic() < deadline:
                time.sleep(0.01)
            assert coordinator.get(submitted.operation_id).state != "running"
        with database.session() as session:
            assert session.get(Account, account_id).display_name == ("changed" if boundary == "valid" else "original")
        assert (not failures) == (boundary == "valid")
    finally:
        database.dispose()


def test_completed_operation_cannot_use_held_effect_capability(tmp_path: Path) -> None:
    database = Database(f"sqlite+pysqlite:///{(tmp_path / 'effects.sqlite3').as_posix()}")
    database.create_schema()
    captured = []
    ended = threading.Event()

    def execute(context: OperationExecutionContext) -> OperationOutcome:
        captured.append(context)
        ended.set()
        return OperationOutcome.failed("creator_profile_failed", retryable=False)

    try:
        with OperationCoordinator(database) as coordinator:
            submitted = coordinator.submit(
                OperationExecution(
                    kind="creator-profile",
                    request_fingerprint="b" * 64,
                    target_type="account",
                    target_id=str(uuid4()),
                    execute=execute,
                )
            )
            assert ended.wait(5)
            deadline = time.monotonic() + 5
            while coordinator.get(submitted.operation_id).state == "running" and time.monotonic() < deadline:
                time.sleep(0.01)
            calls = []
            with pytest.raises((OperationLeaseLostError, OperationStateConflictError)):
                captured[0].commit_effect(lambda session: calls.append(True))
            assert calls == []
            with database.session() as session:
                assert session.scalar(select(Operation)).state == "failed_terminal"
    finally:
        database.dispose()


@pytest.mark.parametrize("invalid_result", [False, True])
def test_profile_success_is_atomic_with_effect_and_fresh_orm_revision(tmp_path: Path, invalid_result: bool) -> None:
    database = Database(f"sqlite+pysqlite:///{(tmp_path / 'atomic.sqlite3').as_posix()}")
    database.create_schema()
    with database.session() as session:
        account_id = AccountRepository(session).create(platform="bili", display_name="original").id
    done = threading.Event()
    held = []

    def execute(context: OperationExecutionContext) -> OperationOutcome:
        def effect(session: Any) -> dict[str, object]:
            held.append(session.get(Operation, context.operation_id))
            session.execute(update(Account).where(Account.id == account_id).values(display_name="changed"))
            if invalid_result:
                return {"raw_nickname_or_secret": "must-not-persist"}
            return {"profile_id": str(uuid4()), "generation": 1, "revision": 1}

        try:
            return OperationOutcome.success(context.commit_success(effect))
        finally:
            done.set()

    try:
        with OperationCoordinator(database) as coordinator:
            submission = coordinator.submit(
                OperationExecution(
                    kind="creator-profile",
                    request_fingerprint="c" * 64,
                    target_type="account",
                    target_id=account_id,
                    execute=execute,
                )
            )
            assert done.wait(5)
            deadline = time.monotonic() + 5
            while coordinator.get(submission.operation_id).state == "running" and time.monotonic() < deadline:
                time.sleep(0.01)
            state = coordinator.get(submission.operation_id).state
            assert (state == "succeeded") is (not invalid_result)
        with database.session() as session:
            assert session.get(Account, account_id).display_name == ("original" if invalid_result else "changed")
            assert "must-not-persist" not in str(session.get(Operation, submission.operation_id).result_summary)
    finally:
        database.dispose()
