**English** | [中文](progress.zh.md)

# Execution 0015 progress

- Status: Offline implementation and closeout gates complete; live qualification remains `NOT_RUN`
- Started: 2026-08-31 07:24 +08:00
- Completed: 2026-08-31
- Plan commit: `76b1973`
- Implementation commit: `95d314d`

## Implemented

- One ordinary Douyin record with a decimal `aweme_id`, empty `note_download_url`, exactly one valid `video_download_url`, empty `music_download_url` and an optional valid cover now has a frozen offline composition. The accepted video is `<aweme_id>:video:0`; the optional cover is `<aweme_id>:cover:0`. Tests bind content kind, remote IDs, positions, MIME hints, query-free source hints and stable `mediacrawler` refresh locators.
- Durable raw sanitization now covers `video_download_url`, `cover_url`, `music_download_url` and `note_download_url`. It removes URL userinfo, known and unknown query values and fragments while accepted `AssetSnapshot.source_url` values remain complete in memory. A comma-joined note scalar becomes an ordered flat sequence; mixed flat sequences retain safe canonical origin/path items and replace comma-smuggled or nested opaque children with `null`. The gallery/audio-shaped records in this boundary regression prove sanitization only; they do not qualify gallery download or external-audio semantics.
- A real isolated fake checkout runs through `MediaCrawlerDetailProcessRunner` and proves `platform=dy`, decimal-string `DY_SPECIFIED_ID_LIST`, detail/JSONL/media-off/comment-off/concurrency switches, `CRAWLER_MAX_SLEEP_SEC=0.25`, saved-profile derivation, bounded result framing, representation redaction and normal-success attempt cleanup. This is a fake checkout using deterministic JSONL, not real Douyin detail traffic or login.
- The platform E2E seeds an exact SQLite Account/Author/Subscription plus two `AssetRefreshSource` rows, then lazily binds the video and cover refreshes to the exact Account, Subscription, content and Asset identities. The composed E2E deliberately substitutes a fake detail runner and creates two exact detail calls, one per Asset; the separate process contract above supplies the actual child-runner evidence. Existing focused cases prove missing, drifted, duplicate and wrong-Subscription/source failures before media transfer.
- Both Assets use `MediaRequestProfile.DEFAULT`. Mock media HTTP contains only the downloader's fixed default headers and no Cookie, Authorization, Referer, Origin or caller-controlled header. Deterministic MP4/PNG bytes pass mock public-DNS pinning and bounded transfer; only video receives the controlled mandatory structural probe. Both Assets finalize under immutable SHA-256 archive paths and durable succeeded Asset/Job state.
- The local Emby/Jellyfin layout publishes the verified `.mp4` as primary episode media, the cover as poster, and emits NFO, the managed manifest and allowlisted `source.json`. Query-only forward URL rotation preserves Asset generation and verified bytes; replay returns `already_verified`/`already_exported`, keeps the archive/library trees byte-identical and re-reads live counts to prove no new fake detail runner, detail call, HTTP request, DNS resolution or probe.
- The first complete-suite run exposed a Windows timing race in the account-profile-lock contract: polling for a JSONL file did not prove that the first runner already held the account lock. The test now synchronizes on an Event reached only inside the lock-owned `_run_locked` path. Non-timeout watchdog cases received a 10-second wall-clock budget instead of 4 seconds for Windows cold startup and scanning, while the dedicated timeout contract remains 0.8 seconds. The final complete suite then passed.
- The focused gate passes `231` tests in 41.79 seconds. The final complete suite passes `1209` tests with one Windows-inapplicable skip in 438.39 seconds. Ruff, formatting, strict typing, documentation, pinned-upstream, build and patch gates pass. The final inventory contains 240 tracked files, no standard-untracked file, no forbidden tracked path, 914 runtime/build files, zero exact marker hit and both frozen sentinel roots.

## Known limitations

- Durable identity is `<aweme_id>:<kind>:0` plus a query-free source hint. If Douyin replaces bytes under the same aweme ID and origin/path while only query data changes, already-verified bytes do not become stale automatically. Conversely, CDN host/path movement may reset generation or fail exact refresh.
- Detail output inherits the trusted Subscription's author ownership and does not independently prove that the aweme still belongs to that creator. Normal-success detail cleanup is proven; injected filesystem cleanup failure still lacks the scheduled runner's full quarantine, incident and account-block protocol.

## Remaining outside execution 0015

- Real Douyin QR/Cookie/saved-session login remains `NOT_RUN`.
- Real creator scan and incremental rerun remain `NOT_RUN`.
- Real detail and signed-CDN transfer remain `NOT_RUN`.
- Real platform bytes through FFmpeg/ffprobe remain `NOT_RUN`.
- Real Emby/Jellyfin scan and playback remain `NOT_RUN`.
- Douyin galleries/images, associated music/audio semantics, multiple video or cover URLs, slideshows, subtitles, comments, live/paid/restricted/deleted content, trustworthy creator profiles, bounded creator pagination and any proven platform-specific CDN header remain unsupported or deferred rather than passed.
- Media-version-aware replacement, cleanup-failure quarantine/incident/account blocking, XHS multi-note authority, new Weibo/Tieba/Zhihu Asset capture, REST/API operations, deployment/service integration and cross-host HA remain later work.
