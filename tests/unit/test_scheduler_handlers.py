"""Closed scheduler handler contracts."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from media_sync.domain import AccountRef, LoginMethod, Platform
from media_sync.scheduler.handlers import (
    SubscriptionHandlerRegistry,
    SubscriptionHandlerResult,
    SubscriptionJobContext,
)


class _Handler:
    async def run(self, context: SubscriptionJobContext) -> SubscriptionHandlerResult:
        return SubscriptionHandlerResult.success(context.job_id)


class _SyncHandler:
    def run(self, context: SubscriptionJobContext) -> SubscriptionHandlerResult:
        return SubscriptionHandlerResult.success(context.job_id)


def _context() -> SubscriptionJobContext:
    return SubscriptionJobContext(
        job_id=uuid4(),
        subscription_id=uuid4(),
        account=AccountRef(
            account_id=uuid4(),
            platform=Platform.BILI,
            login_method=LoginMethod.COOKIE,
        ),
        creator_reference="creator-001",
    )


def test_handler_registry_is_closed_and_resolves_only_valid_keys() -> None:
    handler = _Handler()
    registry = SubscriptionHandlerRegistry({"fake": handler})

    assert registry.keys == ("fake",)
    assert registry.resolve("fake") is handler
    assert registry.resolve("raw\nsecret") is None
    assert registry.resolve("missing") is None
    with pytest.raises(TypeError):
        SubscriptionHandlerRegistry({"fake": object()})  # type: ignore[dict-item]
    with pytest.raises(TypeError):
        SubscriptionHandlerRegistry({"fake": _SyncHandler()})  # type: ignore[dict-item]
    with pytest.raises(ValueError):
        SubscriptionHandlerRegistry({"bad key": handler})
    with pytest.raises(ValueError):
        SubscriptionHandlerRegistry({1: handler})  # type: ignore[dict-item]
    assert registry.resolve(1) is None  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "result",
    [
        lambda: SubscriptionHandlerResult(succeeded=True, error_code="rate_limited"),
        lambda: SubscriptionHandlerResult(succeeded=False),
        lambda: SubscriptionHandlerResult(succeeded=1),  # type: ignore[arg-type]
        lambda: SubscriptionHandlerResult(succeeded=True, run_id="not-a-uuid"),  # type: ignore[arg-type]
        lambda: SubscriptionHandlerResult.failure(1),  # type: ignore[arg-type]
        lambda: SubscriptionHandlerResult.failure("raw_exception_text"),
        lambda: SubscriptionHandlerResult.failure("auth_expired", retry_after=30),
        lambda: SubscriptionHandlerResult.failure("rate_limited", retry_after=float("nan")),
        lambda: SubscriptionHandlerResult.failure("rate_limited", retry_after=604_801),
        lambda: SubscriptionHandlerResult.failure(
            "rate_limited",
            retry_after=datetime(2026, 8, 30, tzinfo=UTC),  # type: ignore[arg-type]
        ),
    ],
)
def test_handler_result_rejects_open_or_invalid_failure_shapes(result: object) -> None:
    with pytest.raises(ValueError):
        result()  # type: ignore[operator]


def test_handler_result_and_context_accept_closed_safe_values() -> None:
    context = _context()
    result = SubscriptionHandlerResult.failure(
        "rate_limited",
        run_id=uuid4(),
        retry_after=604_800,
    )

    assert context.max_items == 30
    assert result.error_code == "rate_limited"
    assert SubscriptionHandlerResult.success().succeeded is True

    guarded = SubscriptionJobContext(
        job_id=context.job_id,
        subscription_id=context.subscription_id,
        account=context.account,
        creator_reference=context.creator_reference,
        ownership_guard=lambda _session: None,
    )
    assert "ownership_guard" not in repr(guarded)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"creator_reference": ""},
        {"creator_reference": "bad\nvalue"},
        {"creator_reference": object()},
        {"max_items": 0},
        {"max_items": True},
        {"max_items": 1.5},
        {"max_items": 1_001},
        {"attempt": 0},
        {"attempt": True},
        {"attempt": 1.5},
        {"attempt": 101},
        {"ownership_guard": object()},
    ],
)
def test_handler_context_rejects_invalid_boundaries(kwargs: dict[str, object]) -> None:
    values = {
        "job_id": uuid4(),
        "subscription_id": uuid4(),
        "account": _context().account,
        "creator_reference": "creator-001",
    }
    values.update(kwargs)
    with pytest.raises(ValueError):
        SubscriptionJobContext(**values)  # type: ignore[arg-type]
