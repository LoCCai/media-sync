"""Versioned raw envelope for records emitted by the pinned MediaCrawler checkout."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from types import MappingProxyType

from media_sync.domain import Platform, freeze_mapping

ENVELOPE_SCHEMA = "media-sync.mediacrawler.raw"
ENVELOPE_VERSION = 1
ADAPTER_NAME = "mediacrawler"

_GIT_SHA = re.compile(r"[0-9a-fA-F]{40}\Z")


def _copy_json(value: object) -> object:
    """Copy one JSON value while rejecting ambiguous/non-portable Python objects."""

    if value is None or isinstance(value, str | bool | int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("raw records must not contain non-finite numbers")
        return value
    if isinstance(value, Mapping):
        copied: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("raw record keys must be strings")
            copied[key] = _copy_json(item)
        return copied
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [_copy_json(item) for item in value]
    raise ValueError("raw records must contain only JSON-compatible values")


@dataclass(frozen=True, slots=True)
class MediaCrawlerEnvelope:
    """Immutable provenance wrapper around one complete upstream JSON object."""

    platform: Platform
    upstream_sha: str
    ingested_at: datetime
    record: Mapping[str, object] = field(repr=False)

    def __post_init__(self) -> None:
        normalized_sha = self.upstream_sha.strip().lower()
        if _GIT_SHA.fullmatch(normalized_sha) is None:
            raise ValueError("upstream_sha must be a full 40-character Git commit")
        if self.ingested_at.tzinfo is None or self.ingested_at.utcoffset() is None:
            raise ValueError("ingested_at must be timezone-aware")
        copied = _copy_json(self.record)
        if not isinstance(copied, Mapping):  # pragma: no cover - statically guaranteed by the field type
            raise ValueError("raw record must be a JSON object")
        object.__setattr__(self, "upstream_sha", normalized_sha)
        object.__setattr__(self, "ingested_at", self.ingested_at.astimezone(UTC))
        object.__setattr__(self, "record", freeze_mapping(copied))

    def as_mapping(self) -> Mapping[str, object]:
        """Return the public, versioned raw-envelope representation."""

        return MappingProxyType(
            {
                "schema": ENVELOPE_SCHEMA,
                "version": ENVELOPE_VERSION,
                "adapter": ADAPTER_NAME,
                "platform": self.platform.value,
                "upstream_sha": self.upstream_sha,
                "ingested_at": self.ingested_at.isoformat(),
                "record": self.record,
            }
        )


__all__ = [
    "ADAPTER_NAME",
    "ENVELOPE_SCHEMA",
    "ENVELOPE_VERSION",
    "MediaCrawlerEnvelope",
]
