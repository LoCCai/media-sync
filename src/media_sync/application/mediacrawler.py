"""Reusable validation and normalization for sealed MediaCrawler output."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import PurePosixPath

from media_sync.domain import ContentKind, Platform
from media_sync.integrations.mediacrawler.bilibili_scan import BiliIdentity, BiliScanCoverage
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
    bili_coverage: BiliScanCoverage | None = field(default=None, repr=False)


def _closed_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise MediaCrawlerOutputRejected("bounded Bili content contains duplicate fields")
        result[key] = value
    return result


def _bili_content_identities(payload: bytes, *, author_fingerprint_sha256: str) -> tuple[BiliIdentity, ...]:
    identities: list[BiliIdentity] = []
    for line in payload.splitlines():
        if not line.strip():
            continue
        raw = json.loads(line, object_pairs_hook=_closed_object)
        identity = raw.get("__media_sync_bili_scan_identity") if isinstance(raw, Mapping) else None
        if not isinstance(identity, Mapping) or set(identity) != {
            "aid",
            "bvid",
            "pubdate",
            "author_fingerprint_sha256",
        }:
            raise MediaCrawlerOutputRejected("bounded Bili content identity is missing")
        if identity["author_fingerprint_sha256"] != author_fingerprint_sha256:
            raise MediaCrawlerOutputRejected("bounded Bili source author identity differs")
        if (
            type(identity["aid"]) is not str
            or type(identity["bvid"]) is not str
            or type(identity["pubdate"]) is not int
        ):
            raise MediaCrawlerOutputRejected("bounded Bili content identity is invalid")
        identities.append(BiliIdentity(aid=identity["aid"], bvid=identity["bvid"], pubdate=identity["pubdate"]))
    return tuple(identities)


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
    bili_coverage = None
    bili_identities: list[BiliIdentity] = []
    for jsonl_file in snapshot.files:
        if PurePosixPath(jsonl_file.relative_path).name == "_media_sync_bili_coverage.jsonl":
            if (
                manifest.bili_scan is None
                or jsonl_file.relative_path != "_media_sync_bili_coverage.jsonl"
                or bili_coverage is not None
            ):
                raise MediaCrawlerOutputRejected("unexpected Bili coverage sidecar")
            bili_coverage = BiliScanCoverage.from_json_line(jsonl_file.payload.decode("utf-8"))
            continue
        if manifest.bili_scan is not None:
            bili_identities.extend(
                _bili_content_identities(
                    jsonl_file.payload, author_fingerprint_sha256=manifest.author_remote_id_fingerprint_sha256
                )
            )
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
    if manifest.bili_scan is not None:
        if bili_coverage is None:
            raise MediaCrawlerOutputRejected("bounded Bili coverage is missing")
        if (
            hashlib.sha256(creator_remote_id.encode("utf-8")).hexdigest()
            != manifest.author_remote_id_fingerprint_sha256
        ):
            raise MediaCrawlerOutputRejected("bounded Bili creator scope differs")
        bili_coverage.validate(
            input_state=manifest.bili_scan,
            max_items=manifest.max_items,
            normalized_remote_ids=tuple(record.content.remote_id for record in records),
        )
        expected = {identity.aid: identity for identity in bili_coverage.consumed}
        if (
            len(records) != records_seen
            or len(bili_identities) != len(expected)
            or len({identity.aid for identity in bili_identities}) != len(bili_identities)
            or {identity.aid: identity for identity in bili_identities} != expected
        ):
            raise MediaCrawlerOutputRejected("bounded Bili coverage and content differ")
        for record in records:
            identity = expected.get(record.content.remote_id)
            if (
                identity is None
                or record.content.platform is not Platform.BILI
                or record.content.kind is not ContentKind.VIDEO
                or record.author.remote_id != creator_remote_id
                or record.content.published_at is None
                or record.content.published_at.timestamp() != identity.pubdate
            ):
                raise MediaCrawlerOutputRejected("bounded Bili normalized identity differs")
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
        bili_coverage=bili_coverage,
    )


__all__ = [
    "MediaCrawlerOutputRejected",
    "NormalizedMediaCrawlerOutput",
    "load_normalized_output",
]
