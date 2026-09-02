**English** | [中文](progress.zh.md)

# Execution 0026 progress

- Status: Frozen offline scope and implementation verification complete
- Last updated: 2026-09-02
- Predecessor: `7cb84fc6c93b832492b95513d9cb6a9708ee6cc9`
- Plan commit: `0694934bc9230151a85c040a061d6e704dffc4fc`
- Implementation commit: `190488f77d1704492cc148b890d6f9ae16d84f84`

## Completed

- [x] Reconciled the Execution 0025 closeout, audited the strict single-segment parser/private bridge/normalizer/downloader boundaries and kept both pinned checkouts unchanged.
- [x] Upgraded the bounded detail process protocol to v6 and parsed `durl[0].url` plus equivalent `backup_url`/`backupUrl` aliases through `ResolvedLocator`; absent backups remain compatible, while malformed, conflicting, duplicate, primary-equal or over-eight candidates fail closed.
- [x] Added a bounded private single-page backup field and optional multipart `backup_urls`, accepted historical primary-only payloads and recursively removed every private field before durable raw/SQLite/Job state.
- [x] Extracted one shared primary-first candidate pass for ordinary and DASH resolved locators under the existing asset lock, shared deadline, byte cap and restart budget.
- [x] Limited failover to DNS, timeout, transport, interruption, HTTP and Range-incompatibility outcomes; network-policy, redirect/header/encoding, chunk/size, filesystem, probe, mux, archive and publication failures remain immediate.
- [x] Preserved exact cross-candidate offset/total-length/validator continuity, retained valid partials through mixed failures and allowed destructive restart only after the complete candidate pass rejected the partial.
- [x] Preserved direct-locator behavior and changed adapter auth rotation only at the intended boundary: one all-`401`/`403` pass re-resolves detail once; a second all-auth pass returns `locator_refresh_auth_expired`.
- [x] Extended both single-page and three-page SQLite compositions so each primary returns `503`, its backup supplies the bytes, the existing probe/archive/Emby publication succeeds and replay performs zero new detail/DNS/HTTP/probe/archive/export work.
- [x] Added 24 focused cases across parser, bridge, normalizer and downloader boundaries; retained signed primary/backup candidates and private fields are absent from SQLite/runtime/work/archive/export/operator evidence.
- [x] Passed focused `490`, complete `1814 + 1 skip`, single-/multipart backup compositions, DASH compatibility, Ruff, format, strict mypy, compileall, build, docs, upstream, diff and repository audits.
- [x] Created and pushed bilingual plan and implementation commits; root truth documents are aligned in the documentation closeout.

## Remaining outside this execution

Multiple progressive segments, FLV remux, CDN ranking/racing/cache, mixed-exhaustion detail refresh, subtitles/danmaku, pages above 64, broader media shapes, REST/production packaging and every real platform/CDN/media-server row remain deferred or `NOT_RUN`; the broader seven-platform goal stays active.
