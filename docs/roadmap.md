# Delivery roadmap / 交付路线图

## Product outcome / 产品结果

Build a self-hosted service that can authenticate against all platforms supported by the pinned MediaCrawler release, subscribe to authors, incrementally collect their posts, images and videos, and export an Emby/Jellyfin-compatible library.

构建一个可自托管的服务：覆盖锁定版本 MediaCrawler 支持的全部平台登录；允许订阅作者；增量收集作者的图文、图片和视频；最终输出 Emby/Jellyfin 兼容媒体库。

## Phases / 阶段

### Phase 0 — Baseline and legal boundary / 基线与许可证边界

- Pin both upstream repositories and capture their licenses.
- Inventory platform/login/creator/media capabilities.
- Establish the execution journal and bilingual Git conventions.
- Acceptance: sources are reproducible by SHA; license boundary is explicit; roadmap is reviewable.

### Phase 1 — Core domain and persistence / 核心领域与持久化

- Python package, configuration and CLI skeleton.
- SQLite schema for accounts, credentials references, authors, subscriptions, content, assets and sync runs.
- Adapter protocol plus deterministic fake adapter for tests.
- Acceptance: migrations initialize a database; CRUD and state transitions pass automated tests.

### Phase 2 — MediaCrawler bridge / MediaCrawler 外部适配

- Discover and validate a pinned external MediaCrawler checkout.
- Translate login mode and creator subscription into isolated crawler jobs.
- Ingest JSON/JSONL results into the normalized domain without importing or copying restricted source.
- Acceptance: dry-run command construction and fixture ingestion work for all seven platform identifiers; one authorized live smoke test is documented separately.

### Phase 3 — Download and Emby export / 下载与 Emby 导出

- Download assets with resumability, checksums, type/size limits and safe filenames.
- Map video and image posts into stable creator/content directories.
- Generate XML NFO plus cover, backdrop and sidecar manifest files.
- Acceptance: fixture content renders a library that passes XML validation and golden-tree tests.

### Phase 4 — Scheduler, API and operations / 调度、API 与运维

- Job scheduler, retry/backoff, concurrency and per-platform rate limits.
- Local REST API and CLI for account, subscription, sync and export operations.
- Health/readiness endpoints, structured logs and Docker packaging.
- Acceptance: end-to-end test covers subscribe → scan → ingest → download → export; restart is idempotent.

### Phase 5 — Platform qualification / 平台逐项验收

- Qualify XHS, Douyin, Kuaishou, Bilibili, Weibo, Tieba and Zhihu using user-authorized accounts.
- Document login steps, expected challenges, content gaps and rate limits per platform.
- Acceptance: every platform has a capability matrix entry and reproducible smoke-test record; unavailable credentials are marked as external validation blockers, not silently claimed as passing.

### Phase 6 — Release readiness / 发布准备

- Security and privacy review, backup/restore and upgrade documentation.
- Complete notices, license review and GitHub push checklist.
- Acceptance: clean clone can install, test and run from documentation; no secret or runtime data is tracked.

## Definition of done / 完成定义

The goal is complete only when all implementation phases pass their automated acceptance checks and the seven-platform qualification matrix truthfully records live outcomes. Login challenges requiring a human scan or credentials remain explicit user-assisted verification steps.

只有当全部实现阶段通过自动验收，且七个平台的资格矩阵如实记录真人账户验证结果时，目标才算完成。需要真人扫码或账户凭据的登录挑战必须作为明确的用户协助验证步骤，不能用模拟结果冒充通过。
