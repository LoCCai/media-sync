**English** | [中文](goal.zh.md)

# Execution 0078 goal

- Status: In progress — implementation start record (authorized by the operator in this session; separate from the frozen XHS/Douyin chain)
- Date: 2026-09-23
- Predecessor: Execution 0077 closeout (`3c31dce` series on `main`)
- Scope: Operator console experience — close the gap between the deployment handoff and what the media-sync console actually shows during native login: an embedded live QR panel, crawler run logs in the media-sync log center, and an artifact-location overview; plus documentation-debt cleanup (status matrix refresh to the 0077 boundary, execution-index backfill)

## Outcome

1. **Embedded QR panel** (accounts area): polls the already-authenticated `/crawler/api/crawler/qrcode` endpoint on a short interval while a native login is expected; shows the image on 200, distinguishes "waiting / expired (180s) / platform selector failure" on 404 with platform-specific guidance (Douyin → use Cookie paste per the 0065 flow). Read-only; no new endpoints, no credential surface.
2. **Crawler log bridge**: the already-redacted crawler stdout lines captured by the WebUI manager are additionally written (bounded, redacted, source-tagged) into the existing media-sync rolling log center so console → Logs shows native crawler runs next to media-sync's own operations; the `/crawler/` page keeps its live panel unchanged.
3. **Artifact-location overview**: an information card (library/settings area) explaining the three artifact layers — raw crawler output (`webui-output`), verified SHA-256 store (`/data/archive`), Emby/Jellyfin tree (`/data/library`) — reading actual configured roots from the existing settings API. UI-only.
4. **Documentation debt**: `docs/status.md`/`.zh.md` milestone, verification-matrix and release-blocker blocks refreshed from the 0075 freeze to the 0077 boundary (narratives unchanged in meaning); execution index in `docs/README.md`/`.zh.md` backfills the missing 0059–0068 rows from the recorded status narratives; the new bilingual operator checklist `docs/handoff-checklist.md`/`.zh.md` is linked from the journal navigation.

## Acceptance boundaries

- The 0077 freeze is honored: no XHS or Douyin delivery logic, contract or semantics change anywhere in this execution; QR polling is read-only reuse of an existing authenticated route.
- No new authority, schema migration or credential surface; the log bridge reuses the existing redaction path and respects existing segment/total budgets.
- Offline verification only (component tests, bridge unit tests, static gates, complete suite on the authoring workstation); live behavior remains the operator's canary scope.

## Explicitly deferred

Douyin source-first delivery design (gated on the XHS canary result), Zhihu avatar CDN broadening, playback-evidence confirmation UI, danmaku/subtitles (0.2).
