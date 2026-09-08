"""Paced XHS creator-note continuation bound to the current upstream lock."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from media_sync.integrations.mediacrawler.checkout import CheckoutValidationError, load_mediacrawler_lock

DEFAULT_XHS_SCAN_CONTINUATION_DELAY_SECONDS = 300
MAX_XHS_SCAN_CONTINUATION_DELAY_SECONDS = 604_800
_SHA1 = re.compile(r"[0-9a-f]{40}\Z")


def validate_xhs_continuation_delay(value: object) -> int:
    if type(value) is not int or (value != 0 and not 60 <= value <= MAX_XHS_SCAN_CONTINUATION_DELAY_SECONDS):
        raise ValueError("xhs_scan_continuation_delay_seconds must be 0 or an integer between 60 and 604800")
    return value


@dataclass(frozen=True, slots=True)
class XhsScanContinuationPolicy:
    """Current lock identity plus a bounded delay; zero disables fast continuation."""

    delay_seconds: int = DEFAULT_XHS_SCAN_CONTINUATION_DELAY_SECONDS
    upstream_sha: str | None = None

    def __post_init__(self) -> None:
        validate_xhs_continuation_delay(self.delay_seconds)
        if self.upstream_sha is not None and (
            type(self.upstream_sha) is not str or _SHA1.fullmatch(self.upstream_sha) is None
        ):
            raise ValueError("XHS continuation upstream SHA must be a full lowercase Git SHA")

    @classmethod
    def from_lock(
        cls,
        lock_path: Path,
        *,
        delay_seconds: int = DEFAULT_XHS_SCAN_CONTINUATION_DELAY_SECONDS,
    ) -> XhsScanContinuationPolicy:
        validate_xhs_continuation_delay(delay_seconds)
        try:
            upstream_sha = load_mediacrawler_lock(lock_path).commit
        except (CheckoutValidationError, OSError, ValueError):
            upstream_sha = None
        return cls(delay_seconds=delay_seconds, upstream_sha=upstream_sha)


__all__ = [
    "DEFAULT_XHS_SCAN_CONTINUATION_DELAY_SECONDS",
    "MAX_XHS_SCAN_CONTINUATION_DELAY_SECONDS",
    "XhsScanContinuationPolicy",
    "validate_xhs_continuation_delay",
]
