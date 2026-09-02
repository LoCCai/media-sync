**English** | [中文](plan.zh.md)

# Execution 0013 plan

- Status: Executed within the frozen offline boundary
- Plan date: 2026-08-31
- Completion date: 2026-08-31
- Predecessor: Execution 0012 closeout commit `7c6f567`
- Plan commit: `46323bd`
- Implementation commit: `dd6cfec`

## Delivery sequence

1. **Freeze contracts and baseline**
   - Record all four bilingual execution files, add execution 0013 to the journal/roadmap, and create a bilingual local plan commit before source edits.
   - Preserve the exact pinned upstream commits and the external-runtime/license boundary; do not copy MediaCrawler or bili-sync-up source.
   - Run the existing ingestion/detail-refresh/locator/network/downloader/layout/offline-pipeline tests as the starting baseline.

2. **Create a stable Bilibili video discovery slot**
   - Add red tests showing that one Bilibili video metadata record emits a cover and one position-zero video Asset while a dynamic emits no synthetic media.
   - Make the domain snapshot source URL explicitly optional and emit a locator-only `<aid>:video:0` slot with `source_url=None`. The database column, `AssetUpsert`, fingerprinting and refresh-source provenance already support this shape, so no migration is planned.
   - Permit a missing source hint only for the exact Bilibili video/position-zero shape in the application and refresher. Select the refreshed candidate by bound content/remote-id/kind/position; keep exact non-null source-hint matching unchanged for every predecessor shape.

3. **Resolve the first-page progressive URL in the isolated child**
   - Extend the numeric-aid detail path to validate returned aid and first-page CID, call the pinned `get_video_play_url_task`, and parse a closed single-`durl` result.
   - Return a typed, repr-safe progressive result alongside upstream completion. Read the ordinary content JSONL first, then inject one private bridge field into bounded bytes in memory; do not rewrite the attempt tree. A default-off detail-only normalization gate accepts that field, strips it before envelope/raw retention and emits the same durable Asset identity with the transient URL.
   - Add closed child outcomes for unsupported progressive shapes and distinguish them from temporary play-url fetch failures and malformed results.

4. **Carry a non-secret Bilibili HTTP profile to the downloader**
   - Extend ephemeral `ResolvedLocator` with a closed request-profile identifier; persisted locator schema v1 remains unchanged.
   - Apply exact fixed User-Agent, Referer and Origin headers inside the bounded HTTP layer while continuing to accept only Range/If-Range from resume state. Never pass Cookie, Authorization or arbitrary headers.
   - Prove the profile across redirects, resume and the existing one-time 401/403 re-resolution without weakening DNS/redirect/header limits.

5. **Compose the offline playable-to-Emby path**
   - Add contract tests for exact aid/CID binding, transient signed output, unsupported/malformed play-url shapes and attempt-root cleanup.
   - Add a focused integration using synthetic metadata, a fake current Subscription source, deterministic CDN bytes and a controlled media probe. Assert durable download success, SHA-256/archive identity, primary `.mp4` episode output, NFO/source metadata and idempotent replay.
   - Scan SQLite, runtime output, CLI/log capture and Git-visible files for the signed URL, Cookie sentinel and forbidden headers.

6. **Verify, document and commit**
   - Run the focused execution gate, full pytest, Ruff lint/format, mypy, docs/upstream checks, build and `git diff --check`.
   - Run the retained-artifact and high-confidence secret audits without printing matched secret values.
   - Update goal/plan/progress/verification with exact commands, results and commits; update capability documents without promoting any live row; create bilingual implementation and closeout commits.

## Risks and rollback points

- A `NULL` source URL is allowed only for the exact Bilibili first-page video slot and only with the stable MediaCrawler refresh locator. Every other predecessor shape retains its current source-hint rule.
- `durl` can represent legacy segmented media. Execution 0013 accepts exactly one segment so its output is independently playable; multi-segment concatenation and FLV remux remain future work.
- Fixed Bilibili headers are non-secret protocol metadata. They must be selected by a closed profile, not persisted as caller-controlled mappings or mixed with credentials.
- Because forward metadata lacks CID, the stable 0013 identity is the logical `<aid>:video:0` slot. A same-aid first-CID replacement cannot invalidate already-verified bytes automatically and is deferred with CID-aware multi-page discovery.
- Rollback removes the synthetic Bilibili video discovery slot, play-url enrichment and request profile while retaining execution 0012 and the historical cover-only Bilibili support. No destructive migration is required.
