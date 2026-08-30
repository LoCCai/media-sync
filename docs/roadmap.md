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

- Status: execution 0006 delivers the offline-qualified single-host scheduler foundation, and execution 0007 adds the default-off, license-gated pinned MediaCrawler handler with closed policy v1, manifest v3/receipt v2, attempt-scoped roots, parent-owned heartbeat/process-tree supervision, exact same-transaction SyncRun/ingestion fencing, conservative status mapping and four-state cleanup. Strict byte-exact manifest-v2/receipt-v1 readers remain shared-normalization/manual-ingest-only; scheduled recovery trusts v3. Execution 0008 now closes execution 0007 AC6/AC13 as successor offline evidence with both remaining deterministic cancellation barriers and the exact eleven-failure × three-sink matrix. Execution 0007's own historical records remain `PARTIAL`. Per-request HTTP spacing, signed-locator refresh, automatic downstream planning, REST, resident supervision and production packaging remain later executions; every live qualification row remains `NOT_RUN`.
- 状态：执行 0006 已交付通过离线验收的单机调度基础，执行 0007 新增默认关闭、受许可证约束的锁定版 MediaCrawler handler，包括封闭 policy v1、manifest v3/receipt v2、attempt-scoped 根、父进程拥有的 heartbeat/进程树监督、精确同事务 SyncRun/导入 fencing、保守状态映射及四状态清理。严格、逐字节精确的 manifest-v2/receipt-v1 reader 只用于共享归一化/手工导入；定时恢复只信任 v3。执行 0008 现以继任离线证据关闭执行 0007 的 AC6/AC13，覆盖两个剩余确定性取消 barrier 及精确“11 种失败 × 3 类落点”矩阵；执行 0007 自身的历史记录继续为 `PARTIAL`。逐 HTTP 请求间隔、签名 locator refresh、自动下游规划、REST、常驻守护及生产打包仍属于后续执行；全部真人资格行继续为 `NOT_RUN`。

- Job scheduler, retry/backoff and launch concurrency/throttling: delivered for the execution 0006 Fake/offline boundary. / Job 调度、重试/退避及启动并发/节流：已在执行 0006 的 Fake/离线边界内交付。
- Local REST API for account, subscription, sync and export operations: planned; the equivalent CLI control surfaces are partially implemented. / 账户、订阅、同步与导出的本地 REST API：仍在计划中；对应 CLI 控制面已部分实现。
- Health/readiness endpoints, structured logs and Docker packaging: planned/deferred. / 健康/就绪端点、结构化日志与 Docker 打包：计划中/已延期。
- Execution 0007 offline acceptance: policy/artifact/attempt identity, off-loop parent heartbeat, parent-death/control handshake, exact fencing, conservative status mapping, four-state cleanup and the seven-platform protocol chain are implemented and exercised. Repeated runner cancellation and a deterministic between-batch cancellation barrier now prove join-before-unwind and no second-batch mutation. AC6 remains `PARTIAL` only because deterministic child-exit/pre-seal and post-seal/pre-ingest barriers are incomplete. AC13 is `PARTIAL`: cleanup/redaction/sentinel coverage is substantial, but the full known-secret/nonzero/timeout/all-limits/receipt/cancel/lease-loss × retained-filesystem/SQLite/operator-sink matrix is incomplete. / 执行 0007 离线验收：策略/产物/attempt 身份、移出事件循环的父进程 heartbeat、父死亡/control handshake、精确 fencing、保守状态映射、四状态清理及七平台协议链均已实现并执行。重复 runner 取消及确定性批次间取消 barrier 已证明先 join 再 unwind，且第二批无变更。AC6 仍为 `PARTIAL`，仅因为 child 退出后/seal 前及 seal 后/导入前的确定性 barrier 尚不完整。AC13 为 `PARTIAL`：清理/脱敏/哨兵覆盖已较充分，但“已知密钥/非零/timeout/全部超限/回执/取消/lease 丢失 × 保留文件系统/SQLite/运维落点”的完整矩阵尚不完整。
- Execution 0008 completes the offline successor closeout for those two partial criteria: the child-exit/pre-seal and single/repeated post-seal/pre-ingest barriers pass; the exact eleven-failure × three-sink matrix proves 33 cells with fail-closed filesystem/SQLite scanning and fixed operator authority. The full suite passes 837 tests with one Windows-inapplicable skip and 79% branch-aware coverage. Refresh and DAG work remain excluded from this result. / 执行 0008 已完成上述两项 partial 的离线继任收口：child-exit/pre-seal 及单次/重复 post-seal/pre-ingest barrier 通过；精确“11 种失败 × 3 类落点”矩阵以 fail-closed 文件系统/SQLite 扫描及固定运维权限证明 33 个 cell。完整套件通过 837 项测试、1 项 Windows 不适用的 skip，分支感知覆盖率 79%。refresh 与 DAG 工作仍不属于本结论。
- Planned order after execution 0008: deliver explicit signed-locator refresh with successful/recovery artifact terminal cleanup or isolation in execution 0009; then add the durable automatic `sync → download → Emby` DAG in execution 0010. REST/operations and production supervision remain later work. Authorized live platform/CDN and Emby qualification remains Phase 5 evidence. / 执行 0008 之后的计划顺序：执行 0009 交付显式签名 locator refresh 及成功/恢复产物终态清理或隔离；执行 0010 再新增持久自动 `sync → download → Emby` DAG。REST/运维与生产监督仍属于后续工作；经授权的真人平台/CDN 与 Emby 验收仍属于 Phase 5 证据。

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
