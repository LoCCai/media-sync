# bili-sync-up focused audit / bili-sync-up 专项审计

- Repository / 仓库：`https://github.com/NeeYoonc/bili-sync-up`
- Commit：`dcb5bb73b56ac45b2525da14b389e185b0ea6dbd`
- Workspace version / 工作区版本：`3.0.9`
- License / 许可证：MIT

This is a read-only source audit. No Rust build/test was run, so no upstream `target/` or runtime data was created. Paths below are relative to `.upstream/bili-sync-up`.

本报告来自只读源码审计，没有运行 Rust 构建/测试，因此没有生成上游 `target/` 或运行数据。以下路径均相对于 `.upstream/bili-sync-up`。

## Architecture and workflow / 架构与工作流

The project combines a Rust/Tokio backend, Axum API/WebSocket layer, SeaORM/SQLite persistence and a Svelte administration UI. Startup runs migrations, restores checkpoints/tasks, then supervises HTTP, credential refresh and periodic synchronization (`crates/bili_sync/src/main.rs:60-193`).

项目组合 Rust/Tokio 后端、Axum API/WebSocket、SeaORM/SQLite 和 Svelte 管理界面。启动时执行迁移、恢复断点/任务，然后监督 HTTP、凭据刷新和周期同步。

Its useful persistent workflow is:

```text
source summary -> detail/pages -> media and sidecars -> retry this round's failures
```

摘要每批落库，风控中断前已取数据仍被保留；即使没有新内容，也会修复未完成详情、分页和边车。相关入口位于 `crates/bili_sync/src/workflow.rs:1179-1395,1538-1751` 和 `crates/bili_sync/src/task/video_downloader.rs:446-610,900-1027`。

Submission sources persist latest-row, next-scan and consecutive-failure state (`crates/bili_sync_entity/src/entities/submission.rs:7-50`) and have checkpoint helpers (`crates/bili_sync/src/utils/submission_checkpoint.rs:1-114`). Incrementality relies heavily on publish time (`crates/bili_sync/src/adapter/submission.rs:59-129`); `media-sync` adds platform-ID deduplication and an overlap window to handle identical timestamps and late content.

## Authentication / 登录凭据

- Manual Cookie and QR login are supported.
- QR challenges expire after 180 seconds and distinguish waiting, scanned, expired and successful states (`crates/bili_sync/src/bilibili/auth/mod.rs:46-345,389-435`).
- Credential refresh implements the Bilibili refresh/confirm chain (`crates/bili_sync/src/bilibili/credential.rs:75-260`).
- A daily refresh and scan-time expired-login recovery are scheduled (`crates/bili_sync/src/task/video_downloader.rs:261-303,819-899`).

Security patterns that must not be copied:

- Credential and `auth_token` JSON are stored in SQLite plaintext.
- Configuration history copies complete old/new secret values (`crates/bili_sync/src/config/manager.rs:711-805,836-919`).
- The default listener is `0.0.0.0:12345`, while several credential/QR routes bypass authentication (`crates/bili_sync/src/config/mod.rs:96-97`; `crates/bili_sync/src/api/auth.rs:25-47`).

`media-sync` therefore stores only secret references, keeps QR/OTP material ephemeral, defaults to loopback and applies redaction before both persistence and logging.

## Task state and recovery / 任务状态与恢复

Video/Page work uses compact bit status fields with bounded failure attempts and a special cancelled outcome (`crates/bili_sync/src/utils/status.rs:3-198`). This is efficient but hard to evolve, so it is not copied.

The general task queue declares `Processing`, but a claim does not persist that state; records remain `Pending` during execution (`crates/bili_sync/src/task/mod.rs:303-500`). That produces at-least-once recovery after a crash but can duplicate a completed side effect if the final status write was lost. Failed tasks increment a counter without an evident scheduled requeue.

New design response / 新设计方案：explicit `leased/running/retry_wait/waiting_auth` states, lease expiry, stable idempotency keys and transactional side-effect scheduling.

## Download and processing / 下载与处理

Good ideas include streaming, a native/aria2 fallback, bounded polling, stall detection and FFmpeg stream-copy muxing. Important limitations are:

- Native download writes directly to the final path and has no cross-restart resume, `.part` atomic commit or SHA-256 (`crates/bili_sync/src/downloader.rs:175-298,514-549`).
- aria2 sets `continue=true` but removes the destination before starting, defeating reliable cross-task continuation (`crates/bili_sync/src/aria2_downloader.rs:1011-1030,1143-1165`).
- Debug logging can include complete signed media URLs (`crates/bili_sync/src/aria2_downloader.rs:1138-1141`).
- DASH downloads use `tmp_video/tmp_audio` and FFmpeg muxing with failure cleanup (`crates/bili_sync/src/workflow.rs:8493-8577`), but output is not atomically staged.
- On FLV remux failure, an original FLV may be renamed with an `.mp4` path, making extension and container disagree (`crates/bili_sync/src/workflow.rs:8444-8469`).

New design response / 新设计方案：`.part` plus Range resume, content/MIME/size validation, SHA-256, ffprobe, staging mux output, atomic replacement, and never logging signed URLs.

## Emby/Jellyfin value / Emby/Jellyfin 价值

The strongest reusable design evidence is its sidecar coverage:

- Root: `tvshow.nfo`, poster/folder/thumb/fanart artwork.
- Season: `Season XX/season.nfo` and season artwork.
- Episode: same-stem media, NFO, cover, ASS danmaku and SRT subtitle.
- Creator/person: `folder.jpg` and `person.nfo`.

NFO variants cover `movie`, `tvshow`, `episodedetails`, `season` and `person` (`crates/bili_sync/src/utils/nfo.rs:13-20,210-237`). Episode output includes title, plot, season/episode, stable IDs, dates, duration, creator and artwork (`crates/bili_sync/src/utils/nfo.rs:1030-1326`). Workflow entry points are under `crates/bili_sync/src/workflow.rs:10084-10710`.

`media-sync` independently reimplements platform-neutral XML generation with namespaced unique IDs, a canonical archive and deterministic exporter fingerprints. If any MIT source is later copied or substantially adapted, [`THIRD_PARTY_NOTICES.md`](../../THIRD_PARTY_NOTICES.md) must be updated with affected paths and the full notice.

## Test and delivery evidence / 测试与交付证据

- Rust toolchain is pinned to `1.97.1` (`rust-toolchain.toml:1-2`).
- Static search finds about 245 Rust test attributes, concentrated in workflow, API, NFO and utilities.
- No frontend `*.test.*` or `*.spec.*` files were found.
- Build workflows compile artifacts/images but do not run `cargo test`, Clippy, fmt or frontend tests (`.github/workflows/build.yml`, `docker-build.yml`).

## Reuse verdict / 复用结论

Use the MIT project's ideas for staged persistence, credential refresh, scan checkpoints, error classification and Emby sidecars. Do not adopt its Bilibili-specific enums, compressed status bits, plaintext credential history, non-atomic output paths or monolithic workflow. The `bili_sync` crate exposes only a binary target (`crates/bili_sync/Cargo.toml:88-90`), so running it as a long-term sidecar would duplicate the database, task system and export tree.
