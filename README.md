**English** | [中文](README.zh.md)

# media-sync

`media-sync` is a local-first author subscription and media archiving service. It is being designed around the platform coverage of [MediaCrawler](https://github.com/NanmiCoder/MediaCrawler) and the media-library workflow of [bili-sync-up](https://github.com/NeeYoonc/bili-sync-up).

## Current status

The local function-first path is implemented through execution 0027 implementation commit `7f99aa4`. In addition to explicit QR/session recovery and the foreground `scheduler supervise` chain, twelve frozen media shapes across all seven platforms now have focused offline evidence: execution 0013's Bilibili logical-first-page single-progressive video, execution 0014's Kuaishou ordinary single video plus optional cover, execution 0015's ordinary numeric-ID Douyin single video plus optional cover with empty image/music fields, execution 0016's ordinary-original Weibo static IMAGE/GALLERY, execution 0017's ordinary `type="normal"` XHS static IMAGE/GALLERY, execution 0018's ordinary `type="video"` XHS single playable video with zero or one static IMAGE artwork, execution 0019's ordinary Zhihu creator answer with exactly one static IMAGE, executions 0020–0022's compatible one-/two-/3–64-static-image Tieba first-floor shapes, execution 0023's compatible 2–64-page Bilibili multipart progressive upload, and execution 0024's compatible single-/2–64-page Bilibili DASH video/audio lifecycle. Executions 0025–0027 harden or derive the existing Bilibili DASH/progressive shapes and do not add a thirteenth shape.

Execution 0027 upgrades strict Bilibili detail protocol to v7 and grants FLV authority only from a valid explicit top-level playback `format`; absent/`None` and MP4 remain compatible ordinary progressive, while unknown, mixed and malformed formats fail closed. A repr-safe typed target carries one primary plus at most eight backups through bounded single-/multipart private bridges, then disappears before persistence. The downloader reuses strict candidate/resume/restart and one all-auth refresh semantics, requires the source to probe as FLV video, and runs fixed bounded `ffmpeg -c copy` mapping the first video plus optional first audio stream. Only a final probing exactly as MP4 is archived and exported; failed remux/final probing retains the verified generation source but never publishes raw FLV. A generated local H.264+AAC FLV traverses failed primary → backup → production ffprobe/ffmpeg → SHA-256 MP4 → Emby MP4/NFO/source with zero-work replay. Focused regression passes `394 passed in 59.12s`; the complete suite passes `1848 passed, 1 skipped in 347.72s`; all quality/build/docs/upstream/diff gates pass. Implementation `7f99aa4` is pushed and reconciled. Real login, authenticated API/CDN, real Bilibili FLV bytes and Emby/Jellyfin server validation remain `NOT_RUN`. Exact evidence is in [`docs/executions/0027-bilibili-single-segment-flv-remux/verification.md`](docs/executions/0027-bilibili-single-segment-flv-remux/verification.md).

- Implemented with focused offline evidence: the twelve frozen shapes above, including compatible Bilibili single-/2–64-page progressive and DASH publication with ordered primary/backup failover plus explicit single-segment FLV-to-MP4 remux, bounded Zhihu/Tieba discovery and exact canonical refresh/archive/Emby output
- Still pending or unclaimed: Bilibili multiple `durl` segments and FLV concatenation/transcoding, CDN ranking/racing/cross-run cache, fresh-detail refresh after mixed/non-auth exhaustion, subtitles/danmaku and pages above 64; Tieba galleries above 64 and mixed/rich/reply media; Zhihu multiple images/articles/zvideo; other shapes in the larger seven-platform goal; and every live platform/CDN/real-byte/media-server row

## Foundation quickstart

The commands below are network-free and use the deterministic Fake adapter. They do not log in to a real platform or prove live platform compatibility.

```powershell
uv sync --all-groups --locked
uv run media-sync db init
uv run media-sync account add --platform bili --display-name local-demo --login-method cookie --json
uv run media-sync account list --json
```

Use the account UUID returned above to create and run the fixture subscription:

```powershell
uv run media-sync subscription add --account-id <ACCOUNT_UUID> --platform bili --creator-remote-id creator-001 --display-name "Fixture Creator" --max-items 30 --json
uv run media-sync subscription list --json
uv run media-sync scheduler tick --json
uv run media-sync scheduler run --max-jobs 1 --scan-limit 100 --json
uv run media-sync pipeline run --max-jobs 1 --scan-limit 100 --heartbeat-interval-seconds 20 --json
uv run media-sync scheduler job list --subscription-id <SUBSCRIPTION_UUID> --json
```

`sync run` remains available for an explicit one-off Fake synchronization. Scheduler controls also include `subscription pause|resume|run-now`, `scheduler job resume|cancel`, and `scheduler lane list|set|reset`. A successful scheduler Job only enqueues `pipeline.subscription`; it does not download or export inline. With the bounded commands, `pipeline run` must still be invoked separately. Execution 0012 also provides an explicit foreground loop that advances the complete local chain and waits when idle:

```powershell
uv run media-sync scheduler supervise --idle-interval-seconds 1 --json
```

The first Ctrl+C/SIGTERM stops new ticks and claims, cancels and joins active subscription work, and drains one already-active thread-backed pipeline attempt under heartbeat. A repeated signal force-exits and leaves durable leases/fencing to recovery. This command is a single-host foreground supervisor, not an installed or auto-restarting service.

The pipeline heartbeat renews exact Job/worker/token ownership and prevents a stale coordinator from finalizing over a successor. It does not provide forced cancellation: the production handler is synchronous and runs through `asyncio.to_thread`. The resident supervisor therefore shields and drains an already-started pipeline attempt—even under repeated task cancellation—instead of claiming that the underlying thread stopped. Forced synchronous-thread termination and multi-worker HA remain follow-up work.

## Interactive QR login quickstart

This flow can open a headed MediaCrawler browser and access a real platform account. Use only an account you are authorized to access, review the pinned MediaCrawler non-commercial learning license, and configure the pinned checkout/Python runtime first. The current automated evidence is offline only: no real QR row has been qualified.

Create one QR account without a credential reference, then run the blocking login with both per-invocation gates. Scan the QR code in the visible upstream browser; QR bytes and tokens are not printed or stored by media-sync.

```powershell
uv run media-sync db init
uv run media-sync account add --platform bili --adapter mediacrawler --display-name bili-qr --login-method qr --json
uv run media-sync account login --account-id <ACCOUNT_UUID> --enable-mediacrawler --accept-mediacrawler-license --json
uv run media-sync account login-status --account-id <ACCOUNT_UUID> --json
```

A successful result atomically changes the account to `saved_session`. An expired saved-session account may use the same explicit command again: start atomically moves it to `qr/authenticating`, success restores `saved_session/authenticated`, and timeout/cancellation/failure leaves a retryable QR state. If that account already has a `qr_required`/`waiting_auth` scheduler Job, inspect its redaction-safe ID and resume that exact Job explicitly; login does not silently run or replace it. The later scheduler worker remains a separate, default-off invocation.

```powershell
uv run media-sync scheduler job list --subscription-id <SUBSCRIPTION_UUID> --json
uv run media-sync scheduler job resume --job-id <WAITING_JOB_UUID> --json
uv run media-sync scheduler run --max-jobs 1 --scan-limit 100 --enable-mediacrawler --accept-mediacrawler-license --json
```

Background saved-session reuse is forced headless and cannot fall back to QR. A missing derived profile or a probe that reaches the blocked QR fallback fails closed as `auth_expired`; ordinary bridge configuration faults remain `configuration_invalid`. Upstream `pong() == false` can also include network ambiguity, so `auth_expired` is a conservative action state, not a precise remote-cause diagnosis. Run the explicit login command again rather than expecting a scheduler worker to open a challenge. The login child now keeps START/CANCEL/EOF parent control and a post-result guardian: hard parent death terminates the owned child/browser tree before its inherited account lock becomes reusable. Any abandoned durable `waiting_user` state is recovered only after its exact `expires_at` deadline, while holding that same account lock and passing repository CAS; lock availability alone never authorizes early recovery.

Focused offline commands, exact execution 0012 results and the seven-platform live `NOT_RUN` matrix are recorded in [`docs/executions/0012-login-recovery-resident-supervisor/verification.md`](docs/executions/0012-login-recovery-resident-supervisor/verification.md).

For an already configured pinned MediaCrawler checkout/runtime and an authorized due subscription, the external handler remains default-off and requires both per-run switches below. This command can launch the crawler; it is not part of the network-free Fake quickstart.

```powershell
uv run media-sync scheduler run --max-jobs 1 --scan-limit 100 --enable-mediacrawler --accept-mediacrawler-license --json
uv run media-sync pipeline run --max-jobs 1 --scan-limit 100 --lease-seconds 3600 --heartbeat-interval-seconds 20 --enable-mediacrawler --accept-mediacrawler-license --json
uv run media-sync scheduler supervise --enable-mediacrawler --accept-mediacrawler-license --json
```

The two MediaCrawler switches are required independently on each bounded command. For XHS, the default execution 0017 path resolves the exact selected Subscription's opaque `creator_input.secret_ref`; its secret must be an HTTPS `/user/profile/<trusted-author-id>` URL with unique non-empty `xsec_token` and `xsec_source`. An operator may instead provide `--xhs-detail-reference-ref env:MEDIA_SYNC_XHS_NOTE_DETAIL_URL`; this higher-priority compatibility override must resolve to the exact target note URL with the same closed `xsec` requirements. Neither resolved authority is persisted.

Only opaque secret references such as `env:MEDIA_SYNC_BILI_COOKIE` or `keyring:media-sync/bili-demo` may be passed to `--credential-ref`; raw Cookie/password values are rejected. Run the complete offline test suite with `uv run pytest`; the complete quality gate also includes lint, format, strict types, build/package, documentation, pinned-upstream, patch and secret-sentinel checks. See [`docs/executions/0012-login-recovery-resident-supervisor/verification.md`](docs/executions/0012-login-recovery-resident-supervisor/verification.md) for the current supervisor closeout commands and results.

OS-keyring lookup is optional; install it with `uv sync --extra keyring` before using a `keyring:` reference. Confined `file:<relative-path>` references resolve below `MEDIA_SYNC_SECRET_FILE_DIR` (or the private state-directory default).

## Media download and Emby quickstart

First run the deterministic offline contract. It uses temporary SQLite/filesystem roots, a mock transport, and generated media bytes; it does not contact a platform/CDN or start Emby/Jellyfin.

```powershell
uv run pytest tests/integration/test_offline_media_pipeline.py tests/contract/test_emby_export_contract.py
uv run pytest -q tests/integration/test_bilibili_playable_pipeline.py
uv run pytest -q tests/integration/test_bilibili_multipart_progressive_pipeline.py
uv run pytest -q tests/integration/test_bilibili_dash_pipeline.py
uv run pytest -q tests/integration/test_kuaishou_playable_pipeline.py
uv run pytest -q tests/integration/test_douyin_playable_pipeline.py
uv run pytest -q tests/integration/test_weibo_image_pipeline.py
uv run pytest -q tests/integration/test_xhs_creator_authority_pipeline.py
uv run pytest -q tests/integration/test_xhs_playable_video_pipeline.py
uv run pytest -q tests/integration/test_zhihu_answer_image_pipeline.py
uv run pytest -q tests/integration/test_tieba_first_floor_image_pipeline.py
```

The second through eleventh commands cover the execution 0013/0027 single-page progressive plus explicit-FLV-remux tests, execution 0023 multipart progressive, execution 0024 DASH, execution 0014 Kuaishou, execution 0015 Douyin, execution 0016 Weibo, execution 0017 XHS static, execution 0018 XHS playable-video, execution 0019 Zhihu answer-image and executions 0020–0022 Tieba first-floor-image compositions. They use synthetic metadata, fake detail results, mock transport bytes and controlled or production media gates. Execution 0026 makes both progressive compositions fail each primary with `503` and reach an ordered backup. Execution 0027 additionally generates a real local H.264+AAC FLV, verifies the source with production `ffprobe`, remuxes through bounded `ffmpeg -c copy`, verifies a dual-stream MP4, archives/exports only MP4 and proves zero-work replay. Executions 0024–0025 similarly qualify production DASH mux and independent component backup selection. Execution 0018 separately validates an embedded real H.264 MP4, while executions 0019–0022 qualify bounded JPEG/PNG/WebP structures and reject tested animation containers. The Tieba command covers compatible one-image, exact-two-image and v3 three-image ARTICLE rows, with separate unit/contract coverage at the 64/65 boundary. These commands prove local pipeline contracts, not a real creator/feed/detail request, CDN/platform bytes or a running Emby/Jellyfin server; no retained real platform source fixture is claimed.

For a local database that already contains discovered assets, list redaction-safe IDs, download one eligible asset, and publish one complete author snapshot with:

```powershell
uv run media-sync doctor
uv run media-sync asset list --json
uv run media-sync asset list --status discovered --json
uv run media-sync asset download --asset-id <ASSET_UUID> --json
uv run media-sync emby export --author-id <AUTHOR_UUID> --json
```

`asset list` deliberately omits locators, source URLs, archive paths, and raw metadata. `asset download` performs network access for an eligible query-free `direct` locator and writes verified blobs below `MEDIA_SYNC_ARCHIVE_DIR` (default `archive/`). Video and audio are accepted only after mandatory structural probing by `ffprobe`; Bilibili DASH and explicit single-segment FLV derivatives additionally require launchable `ffmpeg` for bounded stream-copy mux/remux. Install both FFmpeg executables and confirm `media-sync doctor` reports `ffmpeg` and `ffprobe` ready. `emby export` is local filesystem work and writes layout v1 below `MEDIA_SYNC_EXPORT_DIR` (default `exports/`), but it requires a complete exportable author snapshot.

MediaCrawler-discovered assets persist only the stable, secret-free `adapter_refresh` locator. Execution 0009 resolves it lazily from the exact current Subscription source when `asset download` or the pipeline receives both MediaCrawler enable/license switches; manual selection also accepts `--subscription-id`. For XHS, executions 0017–0018 use the selected Subscription creator reference by default and retain the explicit one-note reference as an override. For Zhihu and Tieba, executions 0019–0022 accept no operator detail override: they derive the exact non-secret canonical answer/thread URL from the selected persisted ARTICLE/content row. Tieba refresh binds the complete ordered persisted sibling tuple of 1–64 image hints before resolving any position. Executions 0023–0027 similarly bind every Bilibili VIDEO refresh to the complete 1–64 persisted sibling tuple; detail protocol v7 sends only the target CID and may return an ordinary progressive primary/backup locator, a typed ephemeral FLV derivative, or a typed ephemeral DASH target. Before any child Job or Asset lifecycle write, platform authority preflight binds the exact source and authority; the pipeline capability gate separately validates the pinned lock/checkout/Python runtime plus launchable `ffprobe`, and also `ffmpeg` when the selected Bilibili target requires mux/remux. Invalid authority or capability fails with zero child lifecycle side effects. Refreshed signed media results remain in memory and are never written back to SQLite.

Offline refresh shapes are limited to XHS image/video, Douyin image/video/audio/cover, Kuaishou ordinary single video plus optional cover under an exact-one-play-URL boundary, Bilibili cover plus compatible single-page or 2–64-page single-progressive-per-page and DASH ordinary uploads (including explicit single-segment FLV-to-MP4 remux), ordinary-original numeric-ID Weibo static IMAGE/GALLERY, one ordinary Zhihu answer with exactly one static IMAGE, and compatible one-image, exact-two-image or 3–64-static-image ordinary Tieba thread first floors. Composed media-library evidence remains twelve frozen shapes. Execution 0027 passes its 394-test focused regression, 1848-test complete suite with one Windows-inapplicable skip and all quality/build/docs/upstream/audit gates in implementation `7f99aa4`; it adds a derivative to the existing progressive identity rather than a new shape. Tieba galleries above 64 images and mixed/rich/reply media; Zhihu multiple images, articles and zvideo; XHS broader media; Weibo video/GIF/long-image/effective `page_info`; Douyin/Kuaishou expanded media; and Bilibili multiple `durl` segments/FLV concatenation or transcoding/pages above 64/subtitles/danmaku/CDN ranking, racing or cross-run caching/mixed-exhaustion detail refresh/bangumi/paid/live media remain open. Stable-identity replay cannot automatically detect same-origin/path byte replacement for the documented query-rotation cases. No real login, creator/feed/detail request, signed CDN/proxy download or Emby/Jellyfin rescan/playback has run for any platform; all such rows remain `NOT_RUN`.

Secret-sink handling recognizes explicit composite credential keys such as `api_key`, `access_key`, provider-prefixed and camelCase/kebab-case variants, while preserving ordinary fields such as `key`, `public_key` and `key_id`. Credential-marker URL paths such as `/token/<value>/video.mp4`, including percent-encoded and double-encoded forms, are redacted in operator/database sinks and rejected as durable `direct` locators or source hints. Discovery therefore falls back to a stable `adapter_refresh` locator. The `0003` upgrade applies the same path rule while backfilling legacy assets: it clears an unsafe legacy `source_url` and does not copy the credential path into the replacement locator.

Keep `MEDIA_SYNC_JOB_DIR` and `MEDIA_SYNC_ARCHIVE_DIR` stable for a durable asset generation. A download Job stores only a hash of those canonical roots; a request from a different I/O scope fails safely before reclaiming the job or consuming an attempt. A local per-asset OS lock is held from before database mutation through finalization. If archive publication succeeds before the final database commit, the generation-bound partial evidence permits exact recovery without another network request; partial cleanup happens only after verification succeeds.

Filesystem threat boundary for the 0.x line: the configured state, job, archive, staging and export roots—and their ancestors—must be dedicated, operator-controlled directories that are not writable by an untrusted same-permission process. The path guards reject escapes, links/reparse points/hardlinks present at operation time and detected leaf replacement, but path-based operations do not claim to survive an attacker swapping a parent directory between checks. Do not place these roots in a shared adversarial directory.

Emby managed ownership comes from a durable database Job predecessor chain, not from `.media-sync-managed-v1.json` alone. The disk manifest remains a byte-checked description of the database-anchored predecessor. An unexpected or forged manifest is preserved and rejected; an empty author snapshot still receives a Job anchor, and a publish that committed before database finalization can be recovered only when the exact intended source, tree, manifest and managed bytes match.

Schema round trips deliberately clean generation-bound identities. Downgrading `0003` to `0002` first clears every `assets.download_job_id`, then removes all `asset_download` Jobs because `0002` cannot represent their generation. Succeeded Emby Jobs/records remain as the publication chain. Other non-succeeded Emby Jobs/records are removed as identity poison unless a Job carries a structurally valid closed publication intent; that Job and the records named by its intent are retained only for exact byte-validated recovery after re-upgrade.

## Scope

- Platforms: Xiaohongshu, Douyin, Kuaishou, Bilibili, Weibo, Tieba and Zhihu.
- Authentication: explicit double-gated QR command for initial QR accounts and expired saved-session reauthentication, opaque Cookie references, and background-only saved-session reuse; phone login is unsupported. Offline seven-identifier coverage does not imply live qualification.
- Subscription: stores author identity, incremental watermarks and deduplication state. MediaCrawler accounts additionally persist closed policy v1: `schema_version`, optional `creator_input.secret_ref`, explicit `allow_full_history`, positive `request_delay_seconds` bounded at 300, and `headless`; license acknowledgement is separate, per-worker and default-off. `allow_full_history` remains required only for audited unbounded creator paths; execution 0019's Zhihu shim enforces Subscription `max_items`, while execution 0020 hardens Tieba's existing maximum check to exact successful work. Execution 0007 runs forward scheduled attempts through the opt-in handler. Execution 0010 atomically enqueues a downstream coordinator on sync success, but only an explicit bounded `pipeline run` performs download/export. The proven `CRAWLER_MAX_SLEEP_SEC` setting with `MAX_CONCURRENCY_NUM=1` is not a per-request HTTP-spacing guarantee.
- Content: normalized posts, videos, images and related metadata.
- Media library: stable directories, media files, posters/covers and Emby/Jellyfin NFO.

## Important license boundary

MediaCrawler uses a custom non-commercial learning license. Its checkout is treated as an optional external runtime and is not vendored into this repository. See [`docs/decisions/0001-upstream-boundary.md`](docs/decisions/0001-upstream-boundary.md) before distributing or using this project commercially.
