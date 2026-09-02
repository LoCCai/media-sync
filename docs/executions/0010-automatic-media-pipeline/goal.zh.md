[English](goal.md) | **中文**

# 执行 0010 目标

- 状态：功能优先 MVP 已在本地实现；完整离线门禁通过
- 开始时间：2026-08-31 00:43 +08:00
- 前置执行：执行 0009 功能性刷新提交 `98cf387`

## 已交付结果

交付可恢复的本地 `sync.subscription 成功 → 持久 pipeline.subscription 协调器 → 下载当前合格资产 → 导出 Emby 布局` 工作流。调度成功只负责 enqueue 协调 Job，绝不会内联启动下载或导出；操作员必须显式运行有界 `media-sync pipeline run` worker。该 worker 在可用批次耗尽后返回，不是常驻守护进程。

## 功能验收

1. 正常同步成功及 succeeded-run 恢复收敛均在同一数据库事务中幂等创建一个 `pipeline.subscription` Job；失败、等待与取消不创建。
2. 封闭 payload v1 与 natural key 绑定来源 sync Job、成功 SyncRun 和精确 Subscription；重复保存的 Account/平台列是执行权限，并在任何 child 工作前校验。
3. Claim 按 Job 类型隔离并受 `--scan-limit` 限制；畸形或陈旧队首会以固定脱敏代码终态化，并继续扫描而不饿死后续有效协调器。协调器使用独立的 100 次收敛预算，不与较小的 child 重试预算混用。
4. 选择器解析精确 Subscription → Account/Author，枚举作者当前未 tombstone 的资产，并要求 MediaCrawler refresh locator 具备当前精确 Subscription 来源；范围漂移会在构造或运行下载 child 前拒绝。
5. 资产按确定性顺序经 `AssetDownloadService` 串行执行；任何失败或未 verified 结果都会在导出前停止。导出前再次读取权威选择，复核持久 generation 并发现新增或替换的 blocker。
6. 全部已选资产持久 verified 后，`EmbyExportService` 发布完整作者快照；既有 generation-bound 下载恢复与 Emby intent/result 恢复使显式重跑可在普通进程重启后收敛。
7. 有界协调 worker 在 handler 运行时续租精确 Job/worker/token，并阻止旧 token 收尾；`--heartbeat-interval-seconds` 可选，且必须有限、为正并短于租约。
8. MediaCrawler refresh 保持默认关闭，每次 pipeline 调用都必须同时传入 `--enable-mediacrawler` 与 `--accept-mediacrawler-license`。小红书当前接受一个一次性 `--xhs-detail-reference-ref`，用于精确 note 详情 URL；尚未实现多 note 自动权限发现。

## 真实性边界

- 离线平台形状仅限当前已归一化且可刷新的 Asset：小红书 image/video、抖音 image/video/audio/cover、快手 video/cover 与 Bilibili cover。微博、贴吧、知乎当前不产生可下载 Asset；不宣称支持 Bilibili 可播放视频、DASH、多 P、字幕或弹幕。
- 执行 0010 未运行用户授权的平台登录、作者请求、签名 CDN 下载或真实 Emby/Jellyfin 扫描/播放；全部真人行保持 `NOT_RUN`。
- 生产 CLI handler 为同步函数并通过 `asyncio.to_thread` 运行；协调器失租后取消 asyncio task 不能强制终止底层线程，因此旧线程仍可能继续 child/download/export 工作。精确 Job CAS 会阻止旧协调器错误 `complete/fail`，但完整取消微窗口、协作式 child 权限检查及多 worker HA 均已后置。
- 本执行不交付常驻 worker、重试 daemon、REST 服务、Docker/生产 supervisor 或 PostgreSQL HA。
