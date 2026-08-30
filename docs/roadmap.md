# Delivery roadmap / 交付路线图

## Product outcome / 产品结果

Build a self-hosted service that can authenticate against all platforms supported by the pinned MediaCrawler release, subscribe to authors, incrementally collect their posts, images and videos, and export an Emby/Jellyfin-compatible library.

构建一个可自托管的服务：覆盖锁定版本 MediaCrawler 支持的全部平台登录；允许订阅作者；增量收集作者的图文、图片和视频；最终输出 Emby/Jellyfin 兼容媒体库。

## Phases / 阶段

### Phase 0 — Baseline and legal boundary / 基线与许可证边界

- Pin both upstream repositories and capture their licenses. / 锁定两个上游仓库并记录其许可证。
- Inventory platform/login/creator/media capabilities. / 盘点平台、登录、作者与媒体能力。
- Establish the execution journal and bilingual Git conventions. / 建立执行日志与双语 Git 约定。
- Acceptance: sources are reproducible by SHA; the license boundary is explicit; the roadmap is reviewable. / 验收：源码可按 SHA 复现，许可证边界明确，路线图可审查。

### Phase 1 — Core domain and persistence / 核心领域与持久化

- Python package, configuration and CLI skeleton. / Python 包、配置与 CLI 骨架。
- SQLite schema for accounts, credential references, authors, subscriptions, content, assets and sync runs. / 为账户、凭据引用、作者、订阅、内容、资产与同步运行建立 SQLite schema。
- Adapter protocol plus a deterministic Fake adapter for tests. / 适配器协议及用于测试的确定性 Fake 适配器。
- Acceptance: migrations initialize a database; CRUD and state transitions pass automated tests. / 验收：迁移可初始化数据库，CRUD 与状态转换通过自动测试。

### Phase 2 — MediaCrawler bridge / MediaCrawler 外部适配

- Status: offline command construction, fixture normalization and sealed ingestion were delivered; the authorized live smoke test remains `NOT_RUN` because no account or interactive challenge was authorized.
- 状态：离线命令构造、夹具归一化与密封导入已交付；由于未授权账户或真人交互挑战，授权真人 smoke test 继续为 `NOT_RUN`。

- Discover and validate a pinned external MediaCrawler checkout. / 发现并验证锁定版本的外部 MediaCrawler checkout。
- Translate login mode and creator subscription into isolated crawler jobs. / 把登录方式与作者订阅转换为隔离爬虫任务。
- Ingest JSON/JSONL results into the normalized domain without importing or copying restricted source. / 在不导入或复制受限源码的前提下，把 JSON/JSONL 结果导入归一化领域。
- Acceptance: dry-run command construction and fixture ingestion work for all seven platform identifiers; one authorized live smoke test is documented separately. / 验收：七个平台标识的 dry-run 命令构造与夹具导入均可运行；经授权的真人 smoke test 另行记录。

### Phase 3 — Download and Emby export / 下载与 Emby 导出

- Status: the execution 0005 offline scope is complete and its final root evidence is recorded. The downloader includes lock/scope and archive-to-database recovery under the documented trusted-runtime-root boundary. Secret sinks cover composite API/access-key variants and credential-bearing URL paths, including legacy asset backfill. The `0003` round trip removes generation-bound and non-recoverable failed identities while preserving the succeeded Emby chain and valid publication-intent recovery state. Emby managed ownership is anchored by a durable Job predecessor chain with publish intent/result recovery, complete-tree validation, empty snapshots and concurrent publication fencing. Live signed-locator refresh/CDN retrieval and Emby/Jellyfin rescans/playback are outside this automated acceptance and remain `NOT_RUN`.
- 状态：执行 0005 的离线范围已完成，并记录最终根任务证据。下载器在已记录的可信运行根目录边界下提供锁/scope 及归档到数据库的恢复。密钥落点覆盖组合 API/access-key 变体及带凭据 URL 路径，包括 legacy 资产回填。`0003` 往返会移除 generation-bound 及不可恢复的失败身份，同时保留已成功 Emby 链与有效发布 intent 恢复状态。Emby 受管所有权由持久 Job predecessor chain 锚定，并提供 publish intent/result 恢复、完整树验证、空快照与并发发布 fencing。真实签名 locator refresh/CDN 下载及 Emby/Jellyfin 重扫/播放不属于本自动验收，继续保持 `NOT_RUN`。

- Download assets with resumability, checksums, type/size limits and safe filenames. / 以续传、校验和、类型/大小限制及安全文件名下载资产。
- Map video and image posts into stable creator/content directories. / 把视频和图文内容映射为稳定的作者/内容目录。
- Generate XML NFO plus cover, backdrop and sidecar manifest files. / 生成 XML NFO、封面、背景图与 sidecar manifest。
- Acceptance: fixture content renders a library that passes XML validation and golden-tree tests. / 验收：夹具内容可渲染为通过 XML 验证与 golden-tree 测试的媒体库。

### Phase 4 — Scheduler, API and operations / 调度、API 与运维

- Status: execution 0006 delivers the offline-qualified single-host scheduler slice: atomic due-cycle materialization, fixed-delay scheduling, bounded retry/backoff, exact-token workers, persistent platform/account launch lanes, explicit waiting recovery, Fake-only handlers and redaction-safe CLI controls. Its restart test explicitly runs the existing downloader/exporter after scheduled Fake sync and proves identity reuse; no automatic downstream DAG is claimed. Execution 0007 now freezes the plan for an opt-in pinned MediaCrawler process handler, but its implementation and verification remain `NOT_RUN`. Per-request upstream throttling, REST, resident supervision and production packaging remain later executions.
- 状态：执行 0006 已交付通过离线验收的单机调度切片：原子到期周期物化、fixed-delay 调度、有界重试/退避、精确 token worker、持久平台/账户启动 lane、显式等待恢复、仅 Fake 的 handler 及脱敏 CLI 控制面。重启测试会在 scheduled Fake sync 后显式运行既有下载/导出服务并证明身份复用；不宣称已有自动下游 DAG。执行 0007 现已冻结“显式启用锁定版 MediaCrawler 进程 handler”的计划，但实现与验证仍为 `NOT_RUN`。逐请求上游限流、REST、常驻守护及生产打包仍属于后续执行。

- Job scheduler, retry/backoff and launch concurrency/throttling: delivered for the execution 0006 Fake/offline boundary. / Job 调度、重试/退避及启动并发/节流：已在执行 0006 的 Fake/离线边界内交付。
- Local REST API for account, subscription, sync and export operations: planned; the equivalent CLI control surfaces are partially implemented. / 账户、订阅、同步与导出的本地 REST API：仍在计划中；对应 CLI 控制面已部分实现。
- Health/readiness endpoints, structured logs and Docker packaging: planned/deferred. / 健康/就绪端点、结构化日志与 Docker 打包：计划中/已延期。
- Planned execution 0007 acceptance: policy v1, manifest v3/receipt v2 with immutable legacy readers, attempt-scoped roots, parent-owned heartbeat, cooperative/parent-death process-tree termination, exact SyncRun/ingestion fencing, seven-platform mocked forward ingestion and secret-bearing failed-artifact cleanup. Every item is currently `NOT_RUN`. / 计划中的执行 0007 验收：policy v1、带不可变 legacy reader 的 manifest v3/receipt v2、attempt-scoped 根、父进程拥有的 heartbeat、协作/父死亡进程树终止、精确 SyncRun/导入 fencing、七平台 mock forward 导入，以及含密钥失败产物清理；当前全部为 `NOT_RUN`。
- Remaining acceptance after 0007 planning: implement and verify that handler, then add REST/operations and production supervision while preserving the completed offline subscribe → schedule → sync → explicit download → export restart contract. Authorized live platform/CDN and Emby qualification remains Phase 5 evidence. / 执行 0007 计划之后的剩余验收：实现并验证该 handler，再补齐 REST/运维与生产守护，同时保持已完成的离线“订阅 → 调度 → 同步 → 显式下载 → 导出”重启契约；经授权的真人平台/CDN 与 Emby 验收仍属于 Phase 5 证据。

### Phase 5 — Platform qualification / 平台逐项验收

- Qualify XHS, Douyin, Kuaishou, Bilibili, Weibo, Tieba and Zhihu using user-authorized accounts. / 使用用户授权账户逐项验收小红书、抖音、快手、哔哩哔哩、微博、贴吧与知乎。
- Document login steps, expected challenges, content gaps and rate limits per platform. / 逐平台记录登录步骤、预期挑战、内容缺口与速率限制。
- Acceptance: every platform has a capability-matrix entry and reproducible smoke-test record; unavailable credentials are marked as external validation blockers, not silently claimed as passing. / 验收：每个平台都有能力矩阵条目与可复现 smoke-test 记录；缺少凭据时标记为外部验证阻塞，不能静默冒充通过。

### Phase 6 — Release readiness / 发布准备

- Security and privacy review, backup/restore and upgrade documentation. / 安全与隐私审查，以及备份/恢复和升级文档。
- Complete notices, license review and GitHub push checklist. / 完成 notices、许可证审查与 GitHub 推送检查清单。
- Acceptance: a clean clone can install, test and run from the documentation; no secret or runtime data is tracked. / 验收：干净 clone 可按文档安装、测试和运行；版本库不跟踪密钥或运行数据。

## Definition of done / 完成定义

The goal is complete only when all implementation phases pass their automated acceptance checks and the seven-platform qualification matrix truthfully records live outcomes. Login challenges requiring a human scan or credentials remain explicit user-assisted verification steps.

只有当全部实现阶段通过自动验收，且七个平台的资格矩阵如实记录真人账户验证结果时，目标才算完成。需要真人扫码或账户凭据的登录挑战必须作为明确的用户协助验证步骤，不能用模拟结果冒充通过。
