**English** | [中文](plan.zh.md)

# Execution 0005 plan

1. Freeze field ownership and version identity: discovery may update locator/raw hints; only the downloader may update actual MIME, bytes, SHA-256, local path and lifecycle status. Same remote ID plus semantic fingerprint preserves lifecycle; a changed remote ID or semantic fingerprint atomically increments generation and resets downloader-owned fields.
2. Add replay/replacement regressions through both Fake sync and MediaCrawler ingestion, then split discovery upsert, explicit generation reset and asset lifecycle CAS before any network code. Signed-query rotation on the same query-stripped origin/path must not reset; a changed path/stable media identity must reset.
3. Define locator schema v1 with canonical JSON fingerprints, `direct` and `adapter_refresh` modes, strict parsing and secret-free persistence tests.
4. Add migration `0003_media_download_emby` for semantic/locator fingerprints, generation, download validators, timestamps and error state where existing columns are insufficient; preserve upgrades from `0002_checkpoint`.
5. Implement reusable confined-path, symlink/reparse and atomic-write primitives outside the MediaCrawler integration package.
6. Implement an injectable resolver and address-pinned HTTP transport, manual redirect validation, `trust_env=False`, identity encoding and fixed redacted failure taxonomy.
7. Implement resumable streaming with `.part` metadata bound to asset UUID, generation, canonical locator fingerprint, validator, expected total length and current byte length; enforce strict 200/206/416 rules, bounded restarts, byte/time limits, rehash-on-resume and fsync.
8. Add bounded magic/MIME/FFprobe validation and content-addressed archive publication; never trust URL suffix or `Content-Disposition`.
9. Orchestrate enqueue/claim/start, network work and final verify/complete with short transactions and lease fencing; inject stale-worker and DB-finalization failures.
10. Implement ExportRecord CAS plus an owned export job/staging token, stable path sanitization/identity keys and canonical source/rendered fingerprints.
11. Implement deterministic Emby tree rendering, XML 1.0 filtering, NFOs, allowlisted provenance, playable copies and gallery/text preservation. Publish per file under an author lock; replace/remove only paths recorded by the prior managed manifest whose bytes still match, and preserve conflicts/unmanaged files.
12. Add CLI download/export commands and an offline fixture ingest → mock download → export integration path with secret scans and golden-tree hashing.
13. Replace the conflicting provisional Emby path/ordinal text in `docs/architecture.md` with this stable layout v1, record that no legacy library migration is needed because no exporter existed before 0005, then run all locked dependency, Ruff, format, strict mypy, pytest/coverage, focused downloader/export, build, packaged migration, docs/upstream and diff gates.

## Frozen design decisions

- A plain creator/media URL with ambiguous query, fragment or credentials is never treated as a durable direct locator. Signed values remain ephemeral and require adapter refresh.
- Downloader-owned DB columns describe locally verified bytes, never remote hints.
- Asset semantic fingerprint v1 uses platform/content remote type and ID, kind/position, remote asset ID, query-stripped normalized origin/path and stable dimension/duration hints when present. Query-only rotation preserves generation; missing/weak or changed semantic evidence chooses reset over stale reuse.
- Network connections use the validated IP address; pre-resolve-then-connect-by-host is insufficient because of DNS rebinding.
- Archive blobs are immutable regular files. Export uses atomic copies, not hardlinks or symlinks.
- Stable filesystem names derive from platform/type/remote identity plus a short hash. Display names and titles live in NFO, not path identity.
- Season is the UTC publish year, falling back to first-seen year; episode number is a stable positive hash-derived integer, with deterministic collision detection.
- `AssetStatus.EXPORTED` is not used by the Emby exporter; `ExportRecord` owns per-exporter completion.
- `source.json` is a strict allowlist and never contains raw records, locators, request/response headers or source URLs with query data.
- Export layout v1 publishes under an author-scoped filesystem lock from job-ID staging. The managed manifest stores relative paths and byte hashes; stale managed files are removed only when their current hash still matches the prior manifest. Pre-0005 has no implemented exporter, so there is no legacy on-disk tree to migrate.

## Implementation addendum — 2026-08-30

This addendum preserves the frozen plan above as historical intent while superseding its incomplete statement that a prior on-disk managed manifest establishes ownership. Adversarial review proved that a self-consistent forged manifest could otherwise claim an unmanaged user file. The implemented convergence is:

- Migration `0003_media_download_emby` preserves only complete legacy `verified` rows, normalizes their checksum and timestamps, and keeps them eligible for current exporter byte validation. Legacy `downloading`, `downloaded`, `exported` and incomplete `verified` rows reset to `discovered`, clear downloader-owned fields and record `legacy_asset_reset`; source downgrade plus source and unpacked-wheel upgrade behavior is covered.
- Redaction normalizes composite API/access-key names across snake_case, kebab-case, camelCase and provider-prefixed forms while preserving ordinary `key`, `public_key` and `key_id` fields. Credential-marker URL paths are redacted through bounded percent decoding, including encoded and double-encoded forms; `direct` locators and source hints reject them. The `0003` legacy backfill clears such an unsafe `source_url` and generates only a stable `adapter_refresh` locator.
- Downgrading `0003` first clears every `assets.download_job_id`, then deletes all generation-bound `asset_download` Jobs. It preserves succeeded Emby publication-chain Jobs/records and non-succeeded Jobs/records named by a structurally valid closed publication intent for exact recovery, while deleting all other non-succeeded Emby identity poison before re-upgrade.
- One canonical work/archive I/O scope hash is stored in each asset-download Job without exposing either path. A same-`work_root` asset OS lock is acquired before `_begin` and held through database finalization; lock contention and scope mismatch happen before reclaim/attempt mutation. An exact owner/token may renew after nominal expiry only if reclaim has not changed the token, making renewal versus reclaim a single-winner CAS.
- The archive guard runs after the temporary copy is fsynced and rehashed and immediately before no-clobber commit, including existing-blob reuse. `.part` evidence is retained until asset verification and Job completion commit atomically. A committed result can be recovered without network or a new attempt, including an expired final attempt; cleanup after success is best-effort and cannot reverse verified state. These 0.x guarantees require dedicated operator-controlled runtime roots and ancestors; hostile same-permission parent-directory substitution is outside the threat model.
- Every successful Emby author publication is a durable `export.emby` Job result anchored by publication scope, source fingerprint, tree SHA-256, manifest SHA-256, managed-file count and exact `predecessor_job_id`. The unique predecessor chain, not timestamps or a manifest discovered only from disk, determines the head. The natural key includes the source and exact predecessor, so source cycles such as `A → B → A` are valid while forks, cycles in the Job graph and broken ancestry fail closed.
- Immediately before filesystem publication, the owned Job lease is renewed with an exact `intent` containing the rendered source/tree/manifest identities, managed-file count and affected ExportRecord identities. If filesystem publication succeeds but database finalization fails, a later call validates that exact intent against every published byte and atomically converts records plus Job to the final result. A live owner is not displaced, and a changed/tampered tree is not adopted.
- An empty snapshot still creates a successful Job anchor even though it has no ExportRecord. It may remove only unchanged files named by the database-trusted predecessor and retains unmanaged files. First publication rejects any unexpected managed manifest. A self-consistent forged manifest cannot acquire ownership. Concurrent sibling publications from one predecessor serialize under the author lock; one wins and the other fails retryably with `stale_publish`, then converges from the winner's durable head.
- The CLI rejects unavailable `adapter_refresh` and missing mandatory `ffprobe` before orchestration, returning `blocked`/`not_started`, `persisted_status` and a fixed redacted code without creating a Job or changing the Asset.

## Rollback and safety

Tests use temporary SQLite databases, generated files and in-memory/mock transports only. They never contact platform/CDN addresses or start Emby/Jellyfin. Schema changes are additive and have a tested downgrade; implementation commits must leave runtime/archive/export roots untracked.
