**English** | [中文](plan.zh.md)

# Execution 0014 plan

- Status: Executed within the frozen offline boundary
- Plan date: 2026-08-31
- Completion date: 2026-08-31
- Predecessor: Execution 0013 closeout commit `be979d6`
- Plan commit: `95c7082`
- Implementation commit: `c4ab537`

## Delivery sequence

1. **Freeze scope and baseline**
   - Record four bilingual execution files, index/roadmap entries, exact exclusions and live `NOT_RUN` rows before source/test edits.
   - Preserve both pinned upstream commits and the external-runtime/license boundary; do not modify or vendor the MediaCrawler checkout.
   - Run the existing ingestion/detail/refresh/runtime/downloader/network/layout/application pipeline tests as a predecessor baseline.

2. **Prove discovery and locked detail shape**
   - Add a red real-normalize→SQLite test with known and unknown query-key sentinels, then structurally remove query/fragment data from durable Kuaishou play/cover raw fields while preserving full ephemeral URLs for Asset discovery and detail refresh. Strengthen exact video/cover remote IDs, positions, MIME hints, source hints and replay/generation assertions.
   - Add a Kuaishou fake checkout that exercises the actual process runner with a pure video ID, exact config switches, signed JSONL output, result framing and normal-success cleanup.
   - Add fixed negative cases for missing/drifted/duplicate candidate identity and verify request/result representations do not disclose the signed sentinel.

3. **Compose the platform runtime and playable pipeline**
   - Seed a real SQLite Account/Author/Subscription, ingest one ordinary Kuaishou video plus optional cover, and assert exact AssetRefreshSource provenance and stable adapter locators.
   - Resolve video and cover from the exact Subscription through lazy MediaCrawler runtime construction. Use deterministic signed URLs, public-DNS mock transport, controlled MP4 probe and image magic to download both assets.
   - Assert no Cookie/Authorization/caller header, existing redirect/resume and one 401/403 behavior, SHA-256 archive identity, durable Asset/Job state, Emby primary `.mp4`/poster/NFO/source metadata and idempotent replay.

4. **Close data sinks and identity behavior**
   - Scan ORM raw/source/locator values, disposed SQLite/sidecars, normal-success detail runtime, download/export work roots, archive, Emby library, object representations and Git-visible files for both known-key and unknown-key dynamic signed sentinels.
   - Prove query-only rotation preserves generation and verified shortcuts. Record same-ID/same-path byte replacement and cleanup-failure retention as explicit limitations rather than false passes.

5. **Verify, document and commit**
   - Run the focused execution gate, full pytest, Ruff lint/format, mypy, documentation/upstream checks, build, patch checks and final retained/Git scans.
   - Update goal/plan/progress/verification, platform truth, architecture and README with exact commands, results, implementation commit and remaining work; keep every live row `NOT_RUN`.
   - Create separate bilingual implementation and documentation-closeout commits, push `main`, and verify local/tracking/remote SHA equality.

## Risks and rollback points

- Exactly one valid play URL is the accepted fixture shape. Comma-expanded/multiple URLs, missing play URLs and locator-only Kuaishou discovery are outside this execution; do not silently promote them.
- Kuaishou uses `MediaRequestProfile.DEFAULT`; adding headers without pinned source or live evidence could break CDN behavior and is forbidden in this slice.
- Successful detail cleanup removes the UUID attempt root. Filesystem-denied cleanup and durable account blocking require a separate hardened design; the fixed failure must not be described as zero retention.
- If new tests expose a product defect, repair the smallest shared contract and rerun predecessor platform tests. If the existing composition already passes, test-only platform qualification remains a valid delivery and must not be inflated with unrelated features.
