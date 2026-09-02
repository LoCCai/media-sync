**English** | [中文](plan.zh.md)

# Execution 0016 plan

- Status: Complete for the frozen offline delivery sequence
- Plan date: 2026-08-31
- Predecessor: Execution 0015 closeout commit `b105d00`
- Plan commit: `b7bb818`
- Implementation commit: `a77ca74`

## Executed delivery sequence

1. **Freeze scope and baseline — COMPLETE**
   - Audited the locked Weibo, Tieba and Zhihu paths and selected Weibo because raw `mblog.pics` already reaches creator/detail workflows while the pinned JSONL store discards it. Tieba required new HTML extraction and Zhihu exposed no equivalent stable media contract.
   - Created the four bilingual execution records before source edits and recorded the predecessor gate: `272 passed in 46.92s`.

2. **Install one shared Weibo media shim — COMPLETE**
   - Added one integration-owned task-local shim and installed it after verified-checkout import in both creator and detail children. It enriches only the transient contents JSONL boundary and leaves `.upstream` untouched.
   - Frozen the accepted raw shape to canonical positive numeric original posts, no `retweeted_status`, no media `page_info`, unique ordered `pid` entries, source authority `sinaimg.cn` or a subdomain, and static `jpg/jpeg/png/webp` files. All other shapes fail closed.

3. **Normalize and refresh exact image Assets — COMPLETE**
   - Parsed only the private v1 image field, mapped one image to `IMAGE`, multiple images to `GALLERY`, and generated ordered position-based IMAGE Assets. All media-sync private fields are recursively removed before durable raw is built.
   - Added WB image-only detail/refresh support. Request construction, resolved reference and child loading require the same canonical plain numeric ID, while refresh retains exact Account, Subscription, content, Asset identity, order and query-free source-hint matching.

4. **Compose the production path offline — COMPLETE**
   - Extended isolated fake-checkout contracts for creator/detail installation, concurrency isolation, configuration, framing and normal-success cleanup. Normalization plus SQLite proves ordered Assets and exact `AssetRefreshSource` provenance.
   - Expanded the platform composition E2E to two pictures. Each Asset independently performs exact detail refresh, default-profile public-DNS/HTTP transfer and SHA-256 archive publication; Emby layout receives first-image poster, second-image backdrop, two ordered gallery files, NFO and allowlisted source metadata. Replay performs zero additional work.

5. **Review and repair — COMPLETE**
   - Independent review found and closed three boundary defects: arbitrary embedded proxy host acceptance, non-static/unknown extension acceptance, and different-but-valid WB numeric detail references.
   - The same review found the one-picture composition evidence too weak for a Gallery claim; the E2E now proves two distinct Assets, downloads, archives and gallery outputs.

6. **Verify implementation — COMPLETE**
   - Combined 15-file focused gate: `388 passed in 125.73s`.
   - Complete suite: `1251 passed, 1 skipped in 359.38s`; the skip is the Windows-inapplicable POSIX mode-bit case.
   - Ruff check passes; all 228 files are formatted; strict mypy passes 78 source files; both pinned upstream entries verify; `uv build` produces the wheel and source distribution; diff checks pass.

7. **Close out for delivery — COMPLETE**
   - Finalized the bilingual truth documents, reran documentation/build/diff checks, audited retained artifacts and prepared the separate bilingual closeout commit. Pushing that commit and reconciling local, `origin/main` and GitHub SHAs are post-commit delivery actions reported in the task handoff.

## Deferred scope and risks

- Weibo video, GIF/animated-image semantics, long-image handling, media `page_info`, retweets and restricted/live media remain outside this slice.
- Creator mode still walks full history; explicit `allow_full_history` and outer watchdogs remain mandatory because bounded creator pagination is not implemented.
- Offline acceptance proves deterministic proxy URL construction and the closed request profile, not third-party proxy availability, rate limits, service terms or a Sina-direct profile.
- Same-ID media replacement detection, injected cleanup-failure quarantine and all live platform/CDN/media-server qualification remain deferred or `NOT_RUN`.
