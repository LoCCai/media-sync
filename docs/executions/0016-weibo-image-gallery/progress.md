**English** | [中文](progress.zh.md)

# Execution 0016 progress

- Status: Frozen offline implementation and closeout evidence complete; live qualification remains `NOT_RUN`
- Started: 2026-08-31
- Plan commit: `b7bb818`
- Implementation commit: `a77ca74`

## Implemented

- Audited the locked MediaCrawler Weibo, Tieba and Zhihu paths without modifying either upstream checkout. Weibo was selected because creator/detail already receive raw `mblog.pics`; the locked Weibo JSONL store is the boundary that discarded it.
- Added one shared task-local Weibo media shim to the real creator and detail children after verified-checkout import. Concurrent note tasks keep independent capture state, JSONL enrichment is transient, and `.upstream` remains clean.
- Frozen a narrow ordinary-original boundary: canonical positive numeric note ID, no retweet, no media `page_info`, ordered unique `pid` values, only `sinaimg.cn` or its subdomains, and only `jpg/jpeg/png/webp`. Invalid scalar, nested, missing, duplicate, foreign-host, non-static-extension and reordered refresh shapes fail closed.
- Normalized one picture to `ContentKind.IMAGE` and multiple pictures to `ContentKind.GALLERY`; produced ordered IMAGE Assets, stable adapter-refresh locators and exact SQLite `AssetRefreshSource` observations bound to the Account and Subscription.
- Added WB image-only detail/refresh support with exact same plain numeric ID validation at three boundaries: parent request construction, resolved detail reference and child frame load. Exact content/remote ID/kind/position/source-hint matching prevents cross-item or reordered selection.
- Recursively removed the integration-private field, captured PID values and nested signed-URL drift before durable raw creation. SQLite, runtime/work roots, both archives, export staging/library and sidecar artifacts contain none of those private values.
- Expanded the composition test to a real two-image Gallery: two exact refreshes, two public-DNS/default-profile HTTP transfers, two distinct synthetic PNG byte streams, two independent SHA-256 archives, first-image poster, second-image backdrop, ordered gallery files 001/002, NFO references and allowlisted source metadata.
- Proved zero-work replay: already verified Assets and the completed export add no detail runner, HTTP, DNS, probe, archive or export work and leave both archive and library trees byte-identical.
- Independent review directly caused four corrections: Sina authority restriction, static-extension restriction, exact WB detail-ID equality, and replacement of the single-image composition with a two-image Gallery E2E.

## Verification completed

- Predecessor baseline: `272 passed in 46.92s`.
- Combined focused gate across 15 files: `388 passed in 125.73s`.
- Complete suite: `1251 passed, 1 skipped in 359.38s`; the skip is the Windows-inapplicable POSIX mode-bit test.
- Ruff check passes; `ruff format --check` reports 228 files formatted; strict mypy succeeds for 78 source files.
- Both pinned upstream entries verify; `uv build` creates two distribution artifacts; diff checks pass.
- Final documentation links pass for 80 Markdown files. The retained inventory reports 246 tracked files, zero standard-untracked or forbidden paths, 914 runtime/build files, zero execution-0016 marker hit in retained runtime data and both frozen 0007/0008 sentinel roots preserved.

## Remaining

- Weibo video, GIF/animated-image semantics, long-image special handling, media `page_info`, retweets, restricted/live media and bounded creator pagination remain unimplemented or unqualified.
- A Sina-direct request profile, third-party proxy availability qualification, same-ID media replacement detection and injected cleanup-failure quarantine remain future work.
- Every real QR/Cookie/saved-session login, real creator scan, real detail/proxy/CDN transfer, real platform-byte probe and real Emby/Jellyfin server scan/viewing row remains `NOT_RUN`.
- The broader project objective remains active: remaining media shapes and live qualification across all MediaCrawler platforms are not made complete by this Weibo slice.
