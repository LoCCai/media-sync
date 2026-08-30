"""Closed, redaction-safe contracts for MediaCrawler account authentication."""

from __future__ import annotations

import math
import threading
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from media_sync.domain import Platform


class MediaCrawlerLoginMode(StrEnum):
    """The only authentication operations exposed by the integration."""

    INTERACTIVE_QR = "interactive_qr"
    SAVED_SESSION_PROBE = "saved_session_probe"


class MediaCrawlerLoginStatus(StrEnum):
    """Fixed parent outcomes containing no upstream-controlled text."""

    AUTHENTICATED = "authenticated"
    EXPIRED = "expired"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"
    ACCOUNT_BUSY = "account_busy"
    CONFIGURATION_INVALID = "configuration_invalid"
    START_FAILED = "start_failed"
    RESULT_INVALID = "result_invalid"


@dataclass(frozen=True, slots=True)
class MediaCrawlerLoginRequest:
    """One exact account login or saved-profile authentication probe."""

    account_id: UUID
    platform: Platform
    mode: MediaCrawlerLoginMode
    timeout_seconds: float = 180.0
    poll_seconds: float = 0.05

    def __post_init__(self) -> None:
        if not isinstance(self.account_id, UUID):
            raise ValueError("account_id must be a UUID")
        try:
            platform = Platform(self.platform)
            mode = MediaCrawlerLoginMode(self.mode)
        except (TypeError, ValueError) as exc:
            raise ValueError("unsupported MediaCrawler login request") from exc
        timeout = self.timeout_seconds
        poll = self.poll_seconds
        if (
            isinstance(timeout, bool)
            or not isinstance(timeout, int | float)
            or not math.isfinite(timeout)
            or not 0 < float(timeout) <= 3_600
        ):
            raise ValueError("timeout_seconds must be finite and between zero and 3600")
        if (
            isinstance(poll, bool)
            or not isinstance(poll, int | float)
            or not math.isfinite(poll)
            or not 0 < float(poll) <= 5
            or float(poll) >= float(timeout)
        ):
            raise ValueError("poll_seconds must be finite, positive, and shorter than timeout_seconds")
        object.__setattr__(self, "platform", platform)
        object.__setattr__(self, "mode", mode)
        object.__setattr__(self, "timeout_seconds", float(timeout))
        object.__setattr__(self, "poll_seconds", float(poll))


@dataclass(frozen=True, slots=True)
class MediaCrawlerLoginResult:
    """A fixed login disposition tied to at most one verified upstream SHA."""

    status: MediaCrawlerLoginStatus
    upstream_sha: str | None = None

    def __post_init__(self) -> None:
        try:
            status = MediaCrawlerLoginStatus(self.status)
        except (TypeError, ValueError) as exc:
            raise ValueError("unsupported MediaCrawler login status") from exc
        sha = self.upstream_sha
        if sha is not None:
            normalized = sha.strip().lower()
            if len(normalized) != 40 or any(character not in "0123456789abcdef" for character in normalized):
                raise ValueError("upstream_sha must be a full Git SHA")
            sha = normalized
        if status is MediaCrawlerLoginStatus.AUTHENTICATED and sha is None:
            raise ValueError("authenticated login results require an upstream SHA")
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "upstream_sha", sha)

    @property
    def authenticated(self) -> bool:
        return self.status is MediaCrawlerLoginStatus.AUTHENTICATED


class MediaCrawlerLoginRunner(Protocol):
    """Application-facing boundary for one account-scoped login operation."""

    def run(
        self,
        request: MediaCrawlerLoginRequest,
        *,
        on_account_locked: Callable[[], None] | None = None,
        cancellation: threading.Event | None = None,
    ) -> MediaCrawlerLoginResult:
        """Run while holding the account lock through complete child-tree join."""
        ...


__all__ = [
    "MediaCrawlerLoginMode",
    "MediaCrawlerLoginRequest",
    "MediaCrawlerLoginResult",
    "MediaCrawlerLoginRunner",
    "MediaCrawlerLoginStatus",
]
