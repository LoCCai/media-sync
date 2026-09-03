**English** | [中文](goal.zh.md)

# Execution 0047 goal

- Status: Open — the operator-assisted live qualification master phase; restructured by execution 0048 per the release-candidate review
- Date: 2026-09-03 (restructured)
- Predecessor: Execution 0046; roadmap Phase 5 consolidated here by execution 0042
- Scope: Operator-driven live qualification of all seven platforms on the Linux deployment host, organized as canary-first phases with explicit support tiers, an honest acceptance model, and a defect-fix loop — not a single pass/fail document task

## Outcome (recorded by the operator, per platform)

1. **Phase B baseline first**: clean clone → full suite → Docker build → health/ready → restart persistence → backup-restore drill (see [`docs/operations.zh.md`](../../operations.zh.md)). Execution 0041 upgrades from "packaging delivered" to "deployment passed" only when Phase B is green.
2. **Phase C canary**: Bilibili (most complex media chain: progressive/DASH/mux/multi-part/FLV/backup CDN/ffmpeg/Emby playback) and XHS (most complex authority chain: QR/saved-session, creator authority, signed URLs, mixed media) run the FULL matrix first. Remaining platforms follow only after both canaries reach at least Experimental.
3. **Per-platform sample matrix** (not just "one creator"): main-path creator; creators covering shapes this repository claims (e.g. Bilibili multi-part + DASH + FLV; XHS video/multi-video/live photo); a no-media or partial-media creator; one expired-login re-authentication; one deleted-content or dead-URL case. Each cell records what actually happened.
4. **Incrementality split into two separate rows**: (a) no-change rerun — new Content = 0, new Asset = 0, downloaded bytes = 0; (b) true increment — via an operator-controlled test account publishing one new item between runs, or a watermark/page-boundary relaxation with two captured real responses. Immediate rerun alone never counts as the increment row.
5. **Emby/Jellyfin is mandatory for the Supported tier**: read-only mount of the real library, library rescan, verification of show/season/episode identity, NFO parse, posters/backdrops, and at least one sampled playable video per platform (image/article platforms verify NFO/gallery/body rendering). Record the media-server version. A directory listing alone proves only the exporter, not the product.
6. **Support tiers with a minimum release condition**: Supported / Experimental / Metadata-only / Blocked External / Unsupported. v0.1.0-rc1 requires the two canaries at Supported and every other platform honestly classified; the project then describes itself as "seven-platform adapter framework; qualification status in the matrix", never "supports seven platforms".
7. **Defect loop allowed**: live runs will surface real defects (field drift, challenge changes, session expiry, CDN headers, container quirks, NFO compatibility). Each defect gets a numbered fix sub-execution (code change → automated regression → rerun the affected platform → rerun affected same-class platforms) before the parent record closes. What stays forbidden is silently patching code inside a qualification record.

## Acceptance boundaries

- Every row records what actually ran; `NOT_RUN`/`BLOCKED_EXTERNAL` never silently become pass; fixture results never substitute live rows.
- Accounts are the operator's own; volumes stay bounded (small `max_items`, polite delays) per the SAFE requirements.
- All execution happens on the Linux deployment host; this repository only records the plan and the outcomes.

## Explicitly deferred

Multi-account fleets, soak tests, playback tuning beyond the sampled check, danmaku/subtitle sidecar qualification (deferred with 0043 to 0.2).
