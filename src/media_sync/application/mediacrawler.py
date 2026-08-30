"""Reusable validation and normalization for sealed MediaCrawler output."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime

from media_sync.integrations.mediacrawler.bridge import RunnerManifest
from media_sync.integrations.mediacrawler.normalizers import (
    NormalizationContext,
    NormalizedMediaRecord,
    normalize_jsonl_bytes,
)
from media_sync.integrations.mediacrawler.receipt import load_validated_output_snapshot


class MediaCrawlerOutputRejected(ValueError):
    """A sealed snapshot could not produce a complete normalized batch."""


@dataclass(frozen=True, slots=True)
class NormalizedMediaCrawlerOutput:
    """Immutable normalized records and the receipt-derived provenance digest."""

    records: tuple[NormalizedMediaRecord, ...]
    output_fingerprint_sha256: str
    input_records: int


def load_normalized_output(
    manifest: RunnerManifest,
    *,
    creator_remote_id: str,
    creator_display_name: str,
    ingested_at: datetime,
) -> NormalizedMediaCrawlerOutput:
    """Validate a receipt snapshot and normalize its exact in-memory bytes.

    The caller must run this filesystem and CPU boundary outside an async event
    loop.  No database session is accepted, so receipt reads and normalization
    cannot accidentally span a SQLite transaction.
    """

    snapshot = load_validated_output_snapshot(manifest)
    context = NormalizationContext(
        platform=manifest.platform,
        creator_remote_id=creator_remote_id,
        creator_display_name=creator_display_name,
        upstream_sha=manifest.upstream_sha,
        ingested_at=ingested_at,
    )
    records: list[NormalizedMediaRecord] = []
    records_seen = 0
    for jsonl_file in snapshot.files:
        batch = normalize_jsonl_bytes(
            jsonl_file.payload,
            context,
            max_bytes=manifest.watchdogs.max_output_bytes,
            max_records=manifest.watchdogs.max_output_items,
            max_line_bytes=manifest.watchdogs.max_line_bytes,
        )
        if batch.quarantined or batch.truncated_tail:
            raise MediaCrawlerOutputRejected("sealed MediaCrawler output contains rejected records")
        records.extend(batch.records)
        records_seen += batch.records_seen
    fingerprint = hashlib.sha256(
        json.dumps(
            snapshot.receipt.as_payload(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return NormalizedMediaCrawlerOutput(
        records=tuple(records),
        output_fingerprint_sha256=fingerprint,
        input_records=records_seen,
    )


__all__ = [
    "MediaCrawlerOutputRejected",
    "NormalizedMediaCrawlerOutput",
    "load_normalized_output",
]
