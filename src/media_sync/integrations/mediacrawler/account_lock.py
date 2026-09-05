"""Public account-lock identity shared by MediaCrawler orchestration layers."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

from media_sync.domain import Platform

from .policies import confined_path
from .runner import _AccountFileLock


class MediaCrawlerAccountLock:
    """Acquire the exact OS lock used by MediaCrawler profile runners.

    Construction and acquisition never create account directories. A recovery
    caller may therefore inspect an existing runtime without introducing a new
    profile path; a missing or unsafe directory simply remains unavailable.
    """

    def __init__(self, integration_root: Path, platform: Platform, account_id: UUID) -> None:
        if not isinstance(integration_root, Path):
            raise TypeError("integration_root must be a Path")
        if not isinstance(platform, Platform):
            raise TypeError("platform must be a Platform")
        if not isinstance(account_id, UUID):
            raise TypeError("account_id must be a UUID")
        account_root = confined_path(
            integration_root,
            "accounts",
            platform.value,
            str(account_id),
        )
        self._lock = _AccountFileLock(account_root)

    def acquire(self) -> bool:
        """Try once without blocking; return whether this caller owns the lock."""

        return self._lock.acquire()

    def release(self) -> None:
        """Release this caller's lock ownership, if any."""

        self._lock.release()

    @property
    def descriptor(self) -> int:
        """Expose the held OS descriptor for supervised child inheritance."""

        return self._lock.descriptor


__all__ = ["MediaCrawlerAccountLock"]
