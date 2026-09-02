**English** | [中文](plan.zh.md)

# Execution 0015 plan

- Status: Executed within the frozen offline boundary
- Plan date: 2026-08-31
- Completion date: 2026-08-31
- Predecessor: Execution 0014 closeout commit `6098923`
- Plan commit: `76b1973`
- Implementation commit: `95d314d`

## Delivery sequence

1. **Freeze scope and baseline**
   - Create four bilingual execution records plus journal/roadmap entries before source edits. Preserve both pinned upstream commits and the external-runtime/license boundary.
   - Record the 269-test predecessor baseline covering ingestion, detail, refresh/runtime, downloader/network, Emby application/layout and both existing playable-platform compositions.

2. **Close Douyin durable media raw**
   - Add a real normalize→SQLite red test using dynamic known/unknown query, fragment, userinfo and nested-shape sentinels across all four Douyin media fields.
   - Generalize the existing platform media-field sanitizer without changing AssetSnapshot URLs. Mirror `_url_list` comma splitting for string `note_download_url`; sanitize each item independently and fail closed for opaque shapes.
   - Preserve Kuaishou behavior and rerun its raw/pipeline regressions.

3. **Compose the Douyin platform pipeline**
   - Strengthen the existing real fake-checkout contract only where needed for the frozen pure-ID/config/cleanup claims.
   - Add a new SQLite-bound E2E with one numeric aweme video plus optional cover, exact AssetRefreshSource provenance, lazy runtime construction, deterministic signed detail output, public-DNS mock HTTP, controlled MP4 probe, archive and Emby publication.
   - Assert `DEFAULT` profile and no Cookie/Auth/Referer/Origin; keep music empty and do not claim external-track semantics.

4. **Prove replay, failures and sinks**
   - Prove exact missing/drift/duplicate/wrong-source failures through existing and new focused cases.
   - Rotate forward query values and re-read live runner/network/probe counters after replay; scan ORM, SQLite/sidecars, runtime/work/archive/library, repr and Git-visible/build files for constructed markers.
   - Obtain independent read-only review and close every actionable finding before final gates.

5. **Verify, document and commit**
   - Run the focused execution gate, full pytest, Ruff lint/format, mypy, docs/upstream checks, build, patch and retained-marker audits.
   - Update implemented/remaining truth in the four records, README, roadmap, capability matrix and architecture. Keep every live row `NOT_RUN`.
   - Create separate bilingual implementation and closeout commits, push `main`, and verify local/tracking/GitHub SHA equality.

## Risks and rollback points

- `note_download_url` is a comma-joined upstream field. Sanitizing it as one URL could retain later-item queries in a path; implementation must mirror discovery splitting and test multiple items.
- Associated `music_download_url` is background music, not a proven external video track. It remains outside this slice even though the domain can store an audio Asset.
- Douyin remains on `MediaRequestProfile.DEFAULT`. No special header may be introduced without pinned source or live evidence.
- If composition exposes a product defect, repair the smallest shared contract and rerun Bilibili/Kuaishou regressions; do not expand into galleries or live qualification.
