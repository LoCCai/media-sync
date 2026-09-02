**English** | [中文](progress.zh.md)

# Execution 0014 progress

- Status: Offline implementation and closeout gates complete; live qualification remains `NOT_RUN`
- Started: 2026-08-31 06:25 +08:00
- Completed: 2026-08-31 06:59 +08:00
- Plan commit: `95c7082`
- Implementation commit: `c4ab537`

## Implemented

- One ordinary Kuaishou record with exactly one valid `video_play_url` emits `<video_id>:video:0`; an optional valid `video_cover_url` emits `<video_id>:cover:0`. Tests bind content type, remote IDs, positions, MIME hints, query-free source hints and stable `mediacrawler` refresh locators.
- Durable Kuaishou play/cover raw metadata now retains only canonical HTTP(S) origin/path. Userinfo, known and unknown query values and fragments are removed structurally; non-string or nested schema drift fails closed instead of retaining opaque signed data. The in-memory `AssetSnapshot.source_url` still carries the complete transient URL needed by discovery and refresh.
- A real isolated fake checkout runs through `MediaCrawlerDetailProcessRunner` and proves `platform=ks`, pure-ID `KS_SPECIFIED_ID_LIST`, detail/JSONL/media-off/concurrency configuration, saved-profile derivation, bounded result framing, repr safety and successful UUID-attempt cleanup. Missing, drifted and duplicate candidates return fixed failures.
- The platform integration seeds an exact SQLite Account/Author/Subscription and `AssetRefreshSource`, constructs the lazy refresher only on demand, and binds both video and cover detail requests to the exact Account, Subscription, content, Asset identity and runner configuration. Kuaishou stays on `MediaRequestProfile.DEFAULT`; mock HTTP requests contain no Cookie, Authorization, Referer, Origin or caller-controlled headers.
- Deterministic MP4 and PNG bytes pass public-DNS pinning and the bounded downloader. Video receives mandatory controlled structural probing; both assets finalize under immutable SHA-256 archive paths and durable succeeded Asset/Job state.
- Emby/Jellyfin layout publishes the verified `.mp4` as primary episode media, the cover as poster, and emits NFO plus allowlisted `source.json`. Query-only forward URL rotation preserves Asset generation and verified bytes; replay is `already_verified`/`already_exported` with no new detail runner, HTTP, DNS, probe, archive or library mutation.
- Independent review found and closed three evidence defects: nested Kuaishou media-field shapes could retain signed raw data, the replay detail-call assertion used a stale list snapshot, and the platform E2E omitted exact Account/runner-construction assertions. Final review reported no remaining actionable finding.
- The focused gate passes `228` tests; the complete suite passes `1206` tests with one Windows-inapplicable skip. Ruff, formatting, strict typing, documentation, pinned-upstream, build, patch and retained-marker gates pass. Exact commands and results are in `verification.md`.

## Known limitations

- Durable identity is `<video_id>:<kind>:0` plus a query-free source hint. If Kuaishou replaces bytes under the same video ID and origin/path while only query data changes, already-verified bytes do not become stale automatically. Conversely, a harmless CDN host/path move can trigger generation reset or exact-refresh mismatch.
- Normal-success detail cleanup is proven. Injected filesystem cleanup failure still lacks the scheduled runner's full quarantine, incident and account-block protocol, so this execution does not claim zero retained material in that failure case.

## Remaining outside execution 0014

- Real Kuaishou QR/Cookie/saved-session login, creator synchronization, detail/CDN transfer, real platform-byte probing and Emby/Jellyfin server scan/playback; all remain `NOT_RUN`.
- Bounded Kuaishou creator pagination, galleries, multiple play URLs, audio, subtitles, comments, live/paid/restricted/deleted media, trustworthy creator profiles and any proven platform-specific CDN headers.
- Cleanup-failure quarantine/incident/account blocking, media-version-aware replacement, additional primary-media shapes for other platforms, REST/API operations, deployment/service integration and cross-host HA.
