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

- Status: the execution 0005 platform-neutral offline foundation is complete. Execution 0013 adds one Bilibili logical-first-page single-progressive shape, and execution 0014 qualifies one Kuaishou ordinary single-video plus optional-cover shape through exact refresh, controlled probe/archive and Emby `.mp4`/poster publication. The downloader retains lock/scope, archive-to-database recovery and closed secret sinks under the documented trusted-runtime-root boundary. Real signed CDN retrieval and Emby/Jellyfin rescans/playback are outside automated acceptance and remain `NOT_RUN`.
- 状态：执行 0005 的平台无关离线基础已完成。执行 0013 新增一个 Bilibili 逻辑首 P 单 progressive 形状；执行 0014 把一个快手普通单视频与可选封面形状，经精确刷新、受控探测/归档及 Emby `.mp4`/海报发布完成验收。下载器在已记录的可信运行根目录边界下继续保留锁/scope、归档到数据库恢复及封闭密钥落点。真实签名 CDN 下载及 Emby/Jellyfin 重扫/播放不属于自动验收，继续保持 `NOT_RUN`。

- Download assets with resumability, checksums, type/size limits and safe filenames. / 以续传、校验和、类型/大小限制及安全文件名下载资产。
- Map video and image posts into stable creator/content directories. / 把视频和图文内容映射为稳定的作者/内容目录。
- Generate XML NFO plus cover, backdrop and sidecar manifest files. / 生成 XML NFO、封面、背景图与 sidecar manifest。
- Acceptance: fixture content renders a library that passes XML validation and golden-tree tests. / 验收：夹具内容可渲染为通过 XML 验证与 golden-tree 测试的媒体库。

### Phase 4 — Scheduler, API and operations / 调度、API 与运维

- Status: execution 0009's function-first refresh MVP is implemented in commit `98cf387`, execution 0010's durable enqueue plus explicit bounded pipeline worker is complete in commit `f2e5899`, execution 0011's explicit QR-login/saved-session handoff is complete in commit `8bb16f6`, and execution 0012's hard-parent-death containment, deadline-fenced login recovery and local foreground supervisor are complete in commit `28655f8`. The 0012 focused gate passes 283 tests with one skip; the full suite passes 1156 with the same Windows-inapplicable skip. The foreground supervisor is not an installed/auto-restarting daemon. Cross-host HA, seven-platform complete download and live platform/CDN/Emby qualification remain unclaimed; every live row remains `NOT_RUN`.
- 状态：执行 0009 的功能优先刷新 MVP 已在提交 `98cf387` 中实现，执行 0010 的持久入队与显式有界 pipeline worker 已在提交 `f2e5899` 完成，执行 0011 的显式 QR 登录/saved-session 交接已在提交 `8bb16f6` 完成，执行 0012 的父进程硬终止收容、受截止时间 fencing 保护的登录回收和本地前台监督器已在提交 `28655f8` 完成。0012 专项门禁通过 283 项并跳过 1 项；完整套件通过 1156 项，跳过的仍是同一 Windows 不适用项。该前台监督器不是已安装或自动重启的 daemon。跨主机 HA、七平台完整下载和真人平台/CDN/Emby 验收仍未声明；全部真人行保持 `NOT_RUN`。

- Job scheduler, retry/backoff and launch concurrency/throttling: delivered for the execution 0006 Fake/offline boundary. / Job 调度、重试/退避及启动并发/节流：已在执行 0006 的 Fake/离线边界内交付。
- Local REST API for account, subscription, sync and export operations: planned; the equivalent CLI control surfaces are partially implemented. / 账户、订阅、同步与导出的本地 REST API：仍在计划中；对应 CLI 控制面已部分实现。
- Health/readiness endpoints, structured logs and Docker packaging: planned/deferred. / 健康/就绪端点、结构化日志与 Docker 打包：计划中/已延期。
- Execution 0007 offline acceptance: policy/artifact/attempt identity, off-loop parent heartbeat, parent-death/control handshake, exact fencing, conservative status mapping, four-state cleanup and the seven-platform protocol chain are implemented and exercised. Repeated runner cancellation and a deterministic between-batch cancellation barrier now prove join-before-unwind and no second-batch mutation. AC6 remains `PARTIAL` only because deterministic child-exit/pre-seal and post-seal/pre-ingest barriers are incomplete. AC13 is `PARTIAL`: cleanup/redaction/sentinel coverage is substantial, but the full known-secret/nonzero/timeout/all-limits/receipt/cancel/lease-loss × retained-filesystem/SQLite/operator-sink matrix is incomplete. / 执行 0007 离线验收：策略/产物/attempt 身份、移出事件循环的父进程 heartbeat、父死亡/control handshake、精确 fencing、保守状态映射、四状态清理及七平台协议链均已实现并执行。重复 runner 取消及确定性批次间取消 barrier 已证明先 join 再 unwind，且第二批无变更。AC6 仍为 `PARTIAL`，仅因为 child 退出后/seal 前及 seal 后/导入前的确定性 barrier 尚不完整。AC13 为 `PARTIAL`：清理/脱敏/哨兵覆盖已较充分，但“已知密钥/非零/timeout/全部超限/回执/取消/lease 丢失 × 保留文件系统/SQLite/运维落点”的完整矩阵尚不完整。
- Execution 0008 completes the offline successor closeout for those two partial criteria: the child-exit/pre-seal and single/repeated post-seal/pre-ingest barriers pass; the exact eleven-failure × three-sink matrix proves 33 cells with fail-closed filesystem/SQLite scanning and fixed operator authority. The full suite passes 837 tests with one Windows-inapplicable skip and 79% branch-aware coverage. Refresh and DAG work remain excluded from this result. / 执行 0008 已完成上述两项 partial 的离线继任收口：child-exit/pre-seal 及单次/重复 post-seal/pre-ingest barrier 通过；精确“11 种失败 × 3 类落点”矩阵以 fail-closed 文件系统/SQLite 扫描及固定运维权限证明 33 个 cell。完整套件通过 837 项测试、1 项 Windows 不适用的 skip，分支感知覆盖率 79%。refresh 与 DAG 工作仍不属于本结论。
- Execution 0009 delivery: exact current provenance, bounded detail refresh and explicit default-off asset-download wiring are implemented. At that historical boundary, offline shapes were XHS image/video, Douyin image/video/audio/cover, Kuaishou video/cover and Bilibili cover; execution 0013 extends the current Bilibili capability below. XHS multi-note authority lookup and additional platform assets remain later work. / 执行 0009 交付：精确当前来源、有界 detail 刷新及默认关闭的显式资产下载接线已实现。在该历史边界，离线形状为小红书 image/video、抖音 image/video/audio/cover、快手 video/cover 与 Bilibili cover；当前 Bilibili 能力已由下方执行 0013 扩展。小红书多 note 权限查找和更多平台 Asset 留待后续。
- Execution 0010 delivery: sync success atomically enqueues one `pipeline.subscription` coordinator and stops. A separate operator-invoked `pipeline run` command scans a bounded queue, renews its lease, downloads exact-subscription assets sequentially and then calls the existing Emby publisher. Existing Job schema, generation recovery and publication recovery are reused without a migration. / 执行 0010 交付：sync 成功会原子 enqueue 一个 `pipeline.subscription` 协调器后停止；另一个由操作员调用的 `pipeline run` 命令有界扫描队列、续租、串行下载精确 Subscription 资产，再调用既有 Emby publisher。复用既有 Job schema、generation 恢复及发布恢复，不新增 migration。
- Execution 0012 delivery: login hard-parent-death containment, deadline-fenced/fair LoginSession recovery and a local foreground supervisor now cover scheduler, subscription and pipeline phases. Shutdown cancels and joins MediaCrawler sync, while one already-active thread-backed pipeline attempt remains heartbeat-protected and is drained exactly—even under repeated task cancellation—instead of being falsely called force-stopped. The next product slices are additional playable platform media, local REST/operations and authorized per-platform/CDN/real-media-server qualification; each must retain explicit unsupported versus `NOT_RUN` distinctions. / 执行 0012 交付：登录父进程硬终止收容、受截止时间 fencing 保护且公平的 LoginSession 回收，以及本地前台监督器现已覆盖 scheduler、订阅与 pipeline 阶段。停止时会取消并 join MediaCrawler 同步；对于一项已经 active 的线程型 pipeline 尝试，即使遭遇重复 task cancellation，也会保持 heartbeat 并精确等待收尾，不虚假声称可以强停。后续产品切片为更多平台可播放媒体、本地 REST/运维，以及经授权的逐平台/CDN/真实媒体服务器验收；每项都必须继续明确区分“不支持”与 `NOT_RUN`。
- Execution 0013 delivery (`dd6cfec`): one Bilibili ordinary numeric-aid upload now contributes a stable `NULL`-source `<aid>:video:0` Asset. Exact Subscription-bound refresh validates the current first CID, accepts exactly one progressive `durl`, carries a closed UA/Referer/Origin request profile without Cookie/Authorization, and composes synthetic bytes through controlled probing, archive finalization and idempotent Emby `.mp4` publication. The focused gate passes 223 tests and the complete suite passes 1199 with one Windows-inapplicable skip. Because forward metadata lacks CID, a same-aid first-CID replacement cannot automatically invalidate already-verified bytes. DASH/mux, FLV remux, multiple segments/pages, subtitles, danmaku, backup failover and paid/bangumi/live media remain deferred; real account/CDN/media-server rows remain `NOT_RUN`. / 执行 0013 交付（`dd6cfec`）：一个 Bilibili 普通 numeric-aid 投稿现在会产生稳定的 `NULL` source `<aid>:video:0` Asset。绑定精确 Subscription 的刷新会校验当前首 CID，只接受一个 progressive `durl`，携带无 Cookie/Authorization 的封闭 UA/Referer/Origin request profile，并把合成字节接入受控探测、归档收尾及幂等 Emby `.mp4` 发布。专项门禁通过 223 项；完整套件通过 1199 项，另有一项在 Windows 不适用而跳过。由于 forward 元数据没有 CID，同 aid 首 CID 替换无法自动使已验证字节失效。DASH/mux、FLV remux、多段/多 P、字幕、弹幕、备用地址故障切换及付费/番剧/直播媒体继续延期；真人账户/CDN/媒体服务器行保持 `NOT_RUN`。
- Execution 0014 delivery (`c4ab537`): one Kuaishou ordinary record with exactly one valid play URL and an optional cover now has locked raw-ID detail/process evidence, exact Account/Subscription-bound lazy refresh and deterministic MP4/PNG download through the default request profile. Durable raw removes userinfo/query/fragment and nested schema drift; video probing, SHA-256 archive and idempotent Emby `.mp4`/poster/NFO/source publication pass. The focused gate passes 228 tests and the complete suite passes 1206 with one Windows-inapplicable skip. Same-ID/same-path byte replacement, bounded creator pagination, galleries/multiple URLs, special CDN headers, cleanup-failure quarantine and all live rows remain deferred or `NOT_RUN`. / 执行 0014 交付（`c4ab537`）：一条包含精确一个合法播放 URL 与可选封面的快手普通记录，现在已有锁定纯 ID detail/process 证据、绑定精确 Account/Subscription 的惰性刷新，以及通过默认 request profile 的确定性 MP4/PNG 下载证据。持久 raw 会移除 userinfo/query/fragment 与嵌套 schema 漂移；视频探测、SHA-256 归档及幂等 Emby `.mp4`/海报/NFO/source 发布全部通过。专项门禁通过 228 项；完整套件通过 1206 项，另有一项在 Windows 不适用而跳过。同 ID/同 path 字节替换、有界作者分页、图集/多 URL、专用 CDN header、清理失败 quarantine 及全部真人行继续延期或保持 `NOT_RUN`。

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
