# Execution 0010 goal / 执行 0010 目标

- Status / 状态：Function-first MVP implemented locally; complete offline gate passes / 功能优先 MVP 已在本地实现；完整离线门禁通过
- Started / 开始时间：2026-08-31 00:43 +08:00
- Predecessor / 前置执行：Execution 0009 functional refresh commit `98cf387` / 执行 0009 功能性刷新提交 `98cf387`

## Delivered outcome / 已交付结果

Deliver a resumable local `sync.subscription success → durable pipeline.subscription coordinator → download current eligible assets → export Emby layout` workflow. Scheduler success only enqueues the coordinator; it never starts downloads or export inline. Operators explicitly invoke the bounded `media-sync pipeline run` worker, which returns when its available batch is exhausted and is not a daemon.

交付可恢复的本地 `sync.subscription 成功 → 持久 pipeline.subscription 协调器 → 下载当前合格资产 → 导出 Emby 布局` 工作流。调度成功只负责 enqueue 协调 Job，绝不会内联启动下载或导出；操作员必须显式运行有界 `media-sync pipeline run` worker。该 worker 在可用批次耗尽后返回，不是常驻守护进程。

## Functional acceptance / 功能验收

1. Normal sync success and succeeded-run reconciliation each idempotently create one `pipeline.subscription` Job in the same database transaction; failure, waiting and cancellation create none. / 正常同步成功及 succeeded-run 恢复收敛均在同一数据库事务中幂等创建一个 `pipeline.subscription` Job；失败、等待与取消不创建。
2. Closed payload v1 and natural key `sync-job:<sync_job_id>` bind the originating sync Job, successful SyncRun and exact Subscription. Duplicated Account/platform columns are execution-time authority and are checked before any child work. / 封闭 payload v1 与 natural key 绑定来源 sync Job、成功 SyncRun 和精确 Subscription；重复保存的 Account/平台列是执行权限，并在任何 child 工作前校验。
3. Claiming is type-isolated and bounded by `--scan-limit`. Malformed or stale queue heads are terminalized with fixed redacted codes and scanning continues without starving later valid coordinators. The coordinator has a separate 100-attempt convergence budget rather than sharing a small child retry budget. / Claim 按 Job 类型隔离并受 `--scan-limit` 限制；畸形或陈旧队首会以固定脱敏代码终态化，并继续扫描而不饿死后续有效协调器。协调器使用独立的 100 次收敛预算，不与较小的 child 重试预算混用。
4. Selection resolves the exact Subscription → Account/Author, enumerates current non-tombstoned author assets and requires current exact-Subscription provenance for MediaCrawler refresh locators. Scope drift is rejected before constructing or running a download child. / 选择器解析精确 Subscription → Account/Author，枚举作者当前未 tombstone 的资产，并要求 MediaCrawler refresh locator 具备当前精确 Subscription 来源；范围漂移会在构造或运行下载 child 前拒绝。
5. Assets run sequentially in deterministic order through `AssetDownloadService`. Any failure or non-verified result stops before export. A second authoritative selection verifies durable generations and catches newly added/replaced blockers. / 资产按确定性顺序经 `AssetDownloadService` 串行执行；任何失败或未 verified 结果都会在导出前停止。导出前再次读取权威选择，复核持久 generation 并发现新增或替换的 blocker。
6. Once every selected asset is durably verified, `EmbyExportService` publishes the complete author snapshot. Existing generation-bound download recovery and Emby intent/result recovery make explicit reruns converge after ordinary process restarts. / 全部已选资产持久 verified 后，`EmbyExportService` 发布完整作者快照；既有 generation-bound 下载恢复与 Emby intent/result 恢复使显式重跑可在普通进程重启后收敛。
7. The bounded coordinator worker renews the exact Job/worker/token lease while its handler runs and fences stale finalization. `--heartbeat-interval-seconds` is optional and must be finite, positive and shorter than the lease. / 有界协调 worker 在 handler 运行时续租精确 Job/worker/token，并阻止旧 token 收尾；`--heartbeat-interval-seconds` 可选，且必须有限、为正并短于租约。
8. MediaCrawler refresh remains default-off and requires both `--enable-mediacrawler` and `--accept-mediacrawler-license` for each pipeline invocation. XHS currently accepts one ephemeral `--xhs-detail-reference-ref` for an exact note detail URL; automatic multi-note authority discovery is not implemented. / MediaCrawler refresh 保持默认关闭，每次 pipeline 调用都必须同时传入 `--enable-mediacrawler` 与 `--accept-mediacrawler-license`。小红书当前接受一个一次性 `--xhs-detail-reference-ref`，用于精确 note 详情 URL；尚未实现多 note 自动权限发现。

## Truth boundary / 真实性边界

- Offline platform shapes are limited to the Assets currently normalized and refreshable: XHS image/video, Douyin image/video/audio/cover, Kuaishou video/cover and Bilibili cover. Weibo, Tieba and Zhihu currently produce no downloadable Asset; Bilibili playable video/DASH/multi-part/subtitle/danmaku is not claimed. / 离线平台形状仅限当前已归一化且可刷新的 Asset：小红书 image/video、抖音 image/video/audio/cover、快手 video/cover 与 Bilibili cover。微博、贴吧、知乎当前不产生可下载 Asset；不宣称支持 Bilibili 可播放视频、DASH、多 P、字幕或弹幕。
- No user-authorized platform login, creator request, signed CDN download or real Emby/Jellyfin scan/playback ran in execution 0010; every live row remains `NOT_RUN`. / 执行 0010 未运行用户授权的平台登录、作者请求、签名 CDN 下载或真实 Emby/Jellyfin 扫描/播放；全部真人行保持 `NOT_RUN`。
- The production CLI handler is synchronous and runs through `asyncio.to_thread`. Cancelling its asyncio task after coordinator lease loss does not forcibly terminate the underlying thread, so an old thread may continue child/download/export work. Exact Job CAS prevents stale coordinator `complete/fail`, but full cancellation micro-windows, cooperative child authority checks and multi-worker HA are deferred. / 生产 CLI handler 为同步函数并通过 `asyncio.to_thread` 运行；协调器失租后取消 asyncio task 不能强制终止底层线程，因此旧线程仍可能继续 child/download/export 工作。精确 Job CAS 会阻止旧协调器错误 `complete/fail`，但完整取消微窗口、协作式 child 权限检查及多 worker HA 均已后置。
- No resident worker, retry daemon, REST service, Docker/production supervisor or PostgreSQL HA is delivered by this execution. / 本执行不交付常驻 worker、重试 daemon、REST 服务、Docker/生产 supervisor 或 PostgreSQL HA。
