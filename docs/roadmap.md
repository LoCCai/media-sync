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

- Status: offline command construction, fixture normalization and sealed ingestion were delivered; the authorized live smoke test remains `NOT_RUN` because no account or interactive challenge was authorized.
- 状态：离线命令构造、夹具归一化与密封导入已交付；由于未授权账户或真人交互挑战，授权真人 smoke test 继续为 `NOT_RUN`。

- Discover and validate a pinned external MediaCrawler checkout.
- Translate login mode and creator subscription into isolated crawler jobs.
- Ingest JSON/JSONL results into the normalized domain without importing or copying restricted source.
- Acceptance: dry-run command construction and fixture ingestion work for all seven platform identifiers; one authorized live smoke test is documented separately.

### Phase 3 — Download and Emby export / 下载与 Emby 导出

- Status: the execution 0005 offline scope is complete and its final root evidence is recorded. The downloader includes lock/scope and archive-to-database recovery under the documented trusted-runtime-root boundary. Secret sinks cover composite API/access-key variants and credential-bearing URL paths, including legacy asset backfill. The `0003` round trip removes generation-bound and non-recoverable failed identities while preserving the succeeded Emby chain and valid publication-intent recovery state. Emby managed ownership is anchored by a durable Job predecessor chain with publish intent/result recovery, complete-tree validation, empty snapshots and concurrent publication fencing. Live signed-locator refresh/CDN retrieval and Emby/Jellyfin rescans/playback are outside this automated acceptance and remain `NOT_RUN`.
- 状态：执行 0005 的离线范围已完成，并记录最终根任务证据。下载器在已记录的可信运行根目录边界下提供锁/scope 及归档到数据库的恢复。密钥落点覆盖组合 API/access-key 变体及带凭据 URL 路径，包括 legacy 资产回填。`0003` 往返会移除 generation-bound 及不可恢复的失败身份，同时保留已成功 Emby 链与有效发布 intent 恢复状态。Emby 受管所有权由持久 Job predecessor chain 锚定，并提供 publish intent/result 恢复、完整树验证、空快照与并发发布 fencing。真实签名 locator refresh/CDN 下载及 Emby/Jellyfin 重扫/播放不属于本自动验收，继续保持 `NOT_RUN`。

- Download assets with resumability, checksums, type/size limits and safe filenames.
- Map video and image posts into stable creator/content directories.
- Generate XML NFO plus cover, backdrop and sidecar manifest files.
- Acceptance: fixture content renders a library that passes XML validation and golden-tree tests.

### Phase 4 — Scheduler, API and operations / 调度、API 与运维

- Status: execution 0006 freezes the durable scheduler/retry/concurrency/rate-limit plan; implementation has not started at the plan-commit boundary. REST and production packaging remain later executions. Durable Jobs and current CLI services are prerequisites, not evidence that a scheduler, REST service or production worker is already available.
- 状态：执行 0006 已冻结持久调度/重试/并发/限流计划；在计划提交边界，实现尚未开始。REST 与生产打包留给后续执行。持久 Job 与当前 CLI 服务只是前置条件，不能作为调度器、REST 或生产 worker 已可用的证据。

- Job scheduler, retry/backoff, concurrency and per-platform rate limits.
- Local REST API and CLI for account, subscription, sync and export operations.
- Health/readiness endpoints, structured logs and Docker packaging.
- Acceptance: an offline end-to-end test covers subscribe → scan → ingest → download → export and restart idempotency; authorized live platform/CDN and Emby qualification remains Phase 5 evidence.

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
