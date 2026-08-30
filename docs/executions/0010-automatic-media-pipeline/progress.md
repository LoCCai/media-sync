# Execution 0010 progress / 执行 0010 推进结果

- Status / 状态：Function-first MVP implemented locally / 功能优先 MVP 已在本地实现
- Started / 开始时间：2026-08-31 00:43 +08:00
- Predecessor / 前置：Execution 0009 commit `98cf387`
- Implementation / 实现：`IMPLEMENTED LOCALLY`
- Focused verification / 专项验证：`PASS` — combined pipeline/scheduler/CLI gate `154 passed`
- Final full-suite rerun / 最终完整套件复跑：`PASS` — `930 passed, 1 skipped in 191.06s`

## Implemented / 已实现

- Added `pipeline.subscription` payload v1, idempotent natural key and a 100-attempt coordinator budget. Normal scheduler success and succeeded-run reconciliation enqueue it atomically; other outcomes enqueue none. / 新增 payload v1、幂等 natural key 与 100 次协调器预算；scheduler 正常成功及 succeeded-run 恢复原子入队，其他结果不入队。
- Added bounded claim scanning. Invalid payload/scope and stale source/run coordinators become fixed terminal failures, so one corrupt queue head cannot starve valid work behind it. / 新增有界 claim 扫描；无效 payload/scope 与陈旧 source/run 协调器会变为固定终态失败，因此一个损坏队首不会饿死后续有效工作。
- Added exact Subscription → Account/Author asset selection and current MediaCrawler provenance checks. Durable Account/platform scope is checked before any download child. / 新增精确 Subscription → Account/Author 资产选择及当前 MediaCrawler 来源校验；持久 Account/平台范围在任何下载 child 前检查。
- Added sequential download orchestration, failure-before-export behavior, authoritative pre-export re-selection and complete-author Emby export. Existing child Jobs provide generation/publication restart convergence. / 新增串行下载编排、失败时导出前停止、导出前权威重选及完整作者 Emby 导出；既有 child Job 提供 generation/发布重启收敛。
- Added production runtime composition with per-asset downloader construction. MediaCrawler refresh is bound lazily to the exact coordinator Subscription; direct locators do not require MediaCrawler enablement. / 新增逐资产构造下载器的生产 runtime；MediaCrawler refresh 惰性绑定到精确协调器 Subscription，direct locator 不要求启用 MediaCrawler。
- Added `PipelineSubscriptionWorker` with sync/async handler support, closed result mapping, retry delay, exact lease heartbeat and stale-finalization fencing. `run_once` and `run_bounded` accept `scan_limit` and `heartbeat_interval_seconds`. / 新增支持同步/异步 handler、封闭结果映射、重试延迟、精确租约 heartbeat 与旧收尾 fencing 的 worker；`run_once`/`run_bounded` 接受 `scan_limit` 与 `heartbeat_interval_seconds`。
- Added `media-sync pipeline run` with bounded job count, worker identity, lease, scan, heartbeat and retry controls; MediaCrawler enable/license gates; and optional one-note XHS detail reference. / 新增 `media-sync pipeline run`，包含有界 Job 数、worker 身份、租约、扫描、heartbeat、重试控制，MediaCrawler 启用/许可证 gate，以及可选的单 note 小红书详情引用。

## Actual workflow / 实际工作流

`scheduler tick` materializes due sync Jobs. `scheduler run` executes only the selected sync Jobs; a successful sync transaction enqueues `pipeline.subscription` and then returns. Downloads and export do not start until a separate explicit `pipeline run` invocation claims that coordinator. Both commands are bounded one-shot workers and return when idle; neither is a daemon.

`scheduler tick` 物化到期 sync Job；`scheduler run` 只执行所选 sync Job，成功事务 enqueue `pipeline.subscription` 后即返回。只有另一次显式 `pipeline run` 调用 claim 该协调器后，下载与导出才会开始。两个命令都是有界一次性 worker，空闲即返回，均不是 daemon。

## Review repairs / 审查修复

- Raised the coordinator budget from five to 100 so independently durable child retries do not share one small counter. / 把协调器预算从五次提高到 100，避免独立持久 child 共用一个过小计数器。
- Terminalized malformed/stale claimed rows and bounded the scan with `--scan-limit`. / 终态化畸形/陈旧已 claim 行，并以 `--scan-limit` 限制扫描。
- Made download-result scope mismatch terminal and enforced Account/platform scope before child construction. / 把下载结果范围不匹配改为终态，并在 child 构造前强制 Account/平台范围。
- Added heartbeat renewal and CLI validation requiring a finite positive interval shorter than the lease. / 新增 heartbeat 续租及 CLI 校验，要求 interval 有限、为正且短于租约。
- Added side-effect-free production preflight for network-bearing pipelines. Before any child Job/Asset lifecycle mutation, it verifies the pinned MediaCrawler lock, checkout and Python runtime plus an actually launchable mandatory `ffprobe`; invalid non-empty configuration is rejected too. / 为可能产生网络流量的 pipeline 新增零副作用生产 preflight；在任何 child Job/Asset 生命周期变更前，校验锁定 MediaCrawler lock、checkout、Python runtime 及实际可启动的强制 `ffprobe`，无效但非空的配置同样拒绝。
- Updated the historical scheduled-offline regression to expect the new queued coordinator while preserving the proof that scheduler success itself performs no downstream work. / 更新历史 scheduled-offline 回归，使其预期新 queued 协调器，同时保留“scheduler 成功本身不执行下游工作”的证明。

## Deferred / 后置

- The synchronous production handler runs in `asyncio.to_thread`; task cancellation does not terminate the underlying thread. Old child/export work may continue after coordinator lease loss even though stale coordinator finalization is fenced. Cooperative cancellation, forced termination and HA stress remain deferred. / 同步生产 handler 运行于 `asyncio.to_thread`；task cancellation 不会终止底层线程。协调器失租后旧 child/export 工作仍可能继续，但旧协调器收尾会被 fencing；协作式取消、强制终止与 HA 压测继续后置。
- XHS requires one operator-supplied exact note detail reference; automatic multi-note lookup is not implemented. Weibo/Tieba/Zhihu Asset discovery and Bilibili playable media derivatives remain unavailable. / 小红书要求操作员提供一个精确 note 详情引用；尚未实现多 note 自动查找。微博/贴吧/知乎 Asset discovery 与 Bilibili 可播放媒体衍生物仍不可用。
- No live platform/CDN/real Emby qualification, resident worker or REST/Docker production operations has been completed in this execution. The final code/test/build/upstream gates pass; documentation and diff checks run after these records are finalized. / 本执行尚未完成真人平台/CDN/真实 Emby 验收、常驻 worker 或 REST/Docker 生产运维。最终代码/测试/构建/上游门禁已通过；文档与 diff 检查会在这些记录定稿后运行。
