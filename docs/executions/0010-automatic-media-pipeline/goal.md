# Execution 0010 goal / 执行 0010 目标

- Status / 状态：In progress — function-first / 推进中——功能优先
- Started / 开始时间：2026-08-31 00:43 +08:00
- Predecessor / 前置执行：Execution 0009 provenance/cleanup commit `75e69a4`; functional refresh continues in parallel / 执行 0009 来源/清理提交；功能性 refresh 并行推进

## Outcome / 结果目标

Deliver a resumable local `sync.subscription → download current eligible assets → export Emby layout` workflow. A successful sync creates exactly one durable coordinator Job; the coordinator scopes all work to the exact Subscription and author, reuses existing generation-bound download Jobs and Emby publication recovery, and converges safely after process restart.

交付可恢复的本地 `sync.subscription → 下载当前合格资产 → 导出 Emby 布局` 工作流。成功同步精确创建一个持久协调 Job；协调器把全部工作限定到精确 Subscription 与作者，复用既有 generation-bound 下载 Job 和 Emby 发布恢复，并可在进程重启后收敛。

## Functional acceptance / 功能验收

1. Normal sync success and succeeded-run reconciliation each idempotently create one `pipeline.subscription` Job in the same database transaction; failure, waiting and cancellation create none. / 正常同步成功及 succeeded-run 恢复收敛均在同一事务幂等创建一个 `pipeline.subscription` Job；失败、等待与取消不创建。
2. The coordinator binds Subscription, Account, platform, successful SyncRun and originating sync Job. Its natural key prevents duplicates without a new migration. / 协调器绑定 Subscription、Account、平台、成功 SyncRun 与来源 sync Job；natural key 无需新 migration 即可防重。
3. Asset selection uses the exact Subscription author and current provenance. It includes historical eligible assets that still block a complete Emby snapshot and never borrows another account subscription. / Asset 选择使用精确 Subscription 作者与当前来源；包含仍阻塞完整 Emby 快照的历史合格资产，绝不借用其他账户订阅。
4. Assets are downloaded in stable order through `AssetDownloadService`. Any incomplete/retryable download stops export; restart reuses already verified assets and existing generation Jobs. / 资产按稳定顺序通过 `AssetDownloadService` 下载；任一未完成/可重试下载都会阻止导出；重启复用已验证资产及既有 generation Job。
5. After all required assets are verified, `EmbyExportService` publishes the complete author snapshot. Existing intent/result recovery makes repeated execution idempotent. / 全部必需资产验证后，由 `EmbyExportService` 发布完整作者快照；既有 intent/result 恢复保证重复执行幂等。
6. A bounded CLI worker can execute coordinator Jobs locally. MediaCrawler network work remains explicit and uses execution 0009 refresh/login configuration. / 有界 CLI worker 可在本地执行协调 Job；MediaCrawler 网络工作保持显式启用并复用执行 0009 refresh/登录配置。
7. Focused offline Fake/direct tests prove enqueue, exact scoping, retry stop, restart and successful Emby export. Full concurrency hardening and authorized live qualification may follow after the functional MVP. / 离线 Fake/direct 专项证明 enqueue、精确范围、重试阻断、重启及成功 Emby 导出；完整并发强化与授权真人验收可在功能 MVP 后执行。

## Non-goals for the MVP / MVP 非目标

- No new dependency-edge table, fan-out/fan-in scheduler or HA/PostgreSQL coordination. / 不新增依赖边表、fan-out/fan-in 调度或 HA/PostgreSQL 协调。
- No automatic retry daemon or resident service; bounded local workers are sufficient initially. / 初期不实现自动重试守护或常驻服务；有界本地 worker 即可。
- No claim that seven-platform live CDN or real Emby/Jellyfin scanning has run without user-authorized accounts and servers. / 未提供用户授权账户和服务器时，不宣称已运行七平台真人 CDN 或真实 Emby/Jellyfin 扫描。
