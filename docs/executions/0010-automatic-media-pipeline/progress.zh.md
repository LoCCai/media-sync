[English](progress.md) | **中文**

# 执行 0010 推进结果

- 状态：功能优先 MVP 已在本地实现
- 开始时间：2026-08-31 00:43 +08:00
- 前置：Execution 0009 commit `98cf387`
- 实现：`IMPLEMENTED LOCALLY`
- 专项验证：`PASS` — combined pipeline/scheduler/CLI gate `154 passed`
- 最终完整套件复跑：`PASS` — `930 passed, 1 skipped in 191.06s`

## 已实现

- 新增 payload v1、幂等 natural key 与 100 次协调器预算；scheduler 正常成功及 succeeded-run 恢复原子入队，其他结果不入队。
- 新增有界 claim 扫描；无效 payload/scope 与陈旧 source/run 协调器会变为固定终态失败，因此一个损坏队首不会饿死后续有效工作。
- 新增精确 Subscription → Account/Author 资产选择及当前 MediaCrawler 来源校验；持久 Account/平台范围在任何下载 child 前检查。
- 新增串行下载编排、失败时导出前停止、导出前权威重选及完整作者 Emby 导出；既有 child Job 提供 generation/发布重启收敛。
- 新增逐资产构造下载器的生产 runtime；MediaCrawler refresh 惰性绑定到精确协调器 Subscription，direct locator 不要求启用 MediaCrawler。
- 新增支持同步/异步 handler、封闭结果映射、重试延迟、精确租约 heartbeat 与旧收尾 fencing 的 worker；`run_once`/`run_bounded` 接受 `scan_limit` 与 `heartbeat_interval_seconds`。
- 新增 `media-sync pipeline run`，包含有界 Job 数、worker 身份、租约、扫描、heartbeat、重试控制，MediaCrawler 启用/许可证 gate，以及可选的单 note 小红书详情引用。

## 实际工作流

`scheduler tick` 物化到期 sync Job；`scheduler run` 只执行所选 sync Job，成功事务 enqueue `pipeline.subscription` 后即返回。只有另一次显式 `pipeline run` 调用 claim 该协调器后，下载与导出才会开始。两个命令都是有界一次性 worker，空闲即返回，均不是 daemon。

## 审查修复

- 把协调器预算从五次提高到 100，避免独立持久 child 共用一个过小计数器。
- 终态化畸形/陈旧已 claim 行，并以 `--scan-limit` 限制扫描。
- 把下载结果范围不匹配改为终态，并在 child 构造前强制 Account/平台范围。
- 新增 heartbeat 续租及 CLI 校验，要求 interval 有限、为正且短于租约。
- 为可能产生网络流量的 pipeline 新增零副作用生产 preflight；在任何 child Job/Asset 生命周期变更前，校验锁定 MediaCrawler lock、checkout、Python runtime 及实际可启动的强制 `ffprobe`，无效但非空的配置同样拒绝。
- 更新历史 scheduled-offline 回归，使其预期新 queued 协调器，同时保留“scheduler 成功本身不执行下游工作”的证明。

## 后置

- 同步生产 handler 运行于 `asyncio.to_thread`；task cancellation 不会终止底层线程。协调器失租后旧 child/export 工作仍可能继续，但旧协调器收尾会被 fencing；协作式取消、强制终止与 HA 压测继续后置。
- 小红书要求操作员提供一个精确 note 详情引用；尚未实现多 note 自动查找。微博/贴吧/知乎 Asset discovery 与 Bilibili 可播放媒体衍生物仍不可用。
- 本执行尚未完成真人平台/CDN/真实 Emby 验收、常驻 worker 或 REST/Docker 生产运维。最终代码/测试/构建/上游门禁已通过；文档与 diff 检查会在这些记录定稿后运行。
