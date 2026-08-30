# Execution 0010 plan / 执行 0010 计划

- Status / 状态：Implemented locally; complete offline MVP gate passes / 已在本地实现；完整离线 MVP 门禁通过
- Plan date / 计划日期：2026-08-31
- Schema decision / Schema 决策：reuse existing `jobs` scope/lease/natural-key columns; no migration / 复用既有 `jobs` 范围、租约与 natural-key 列；不新增 migration

## Frozen design / 冻结设计

### Durable enqueue boundary / 持久入队边界

- Add Job type `pipeline.subscription` with closed payload v1 and natural key `sync-job:<sync_job_id>`. / 新增 Job 类型 `pipeline.subscription`，使用封闭 payload v1 与 natural key `sync-job:<sync_job_id>`。
- Enqueue exactly once inside both scheduler normal-success and succeeded-run reconciliation transactions. Scheduler success stops after enqueue; it does not call downloads or Emby export. / 在 scheduler 正常成功与 succeeded-run 恢复事务中各自精确 enqueue 一次；scheduler 成功到入队即止，不调用下载或 Emby 导出。
- Keep the coordinator retry budget at 100 so failures from several independently durable children do not accidentally exhaust a shared five-attempt budget. / 协调器重试预算固定为 100，避免多个独立持久 child 的失败误耗尽共用的五次预算。

### Claim and scope boundary / Claim 与范围边界

- Claim only `pipeline.subscription` rows and inspect at most `scan_limit` candidates per call. Terminalize malformed/stale coordinators with fixed codes, then continue to later candidates. / 只 claim `pipeline.subscription` 行，每次最多检查 `scan_limit` 个候选；畸形/陈旧协调器以固定代码终态化后继续检查后续候选。
- Treat the coordinator's duplicated Subscription, Account, platform, successful Run and source sync Job as authoritative. Recheck mutable Subscription/Account scope before any child side effect. / 以协调器重复保存的 Subscription、Account、平台、成功 Run 与来源 sync Job 为权威；在任何 child 副作用前复核可变 Subscription/Account 范围。
- For MediaCrawler `adapter_refresh` Assets, require an eligible current `asset_refresh_sources` observation for the exact Subscription. / MediaCrawler `adapter_refresh` Asset 必须具有精确 Subscription 的当前合格 `asset_refresh_sources` observation。

### Explicit execution and recovery / 显式执行与恢复

1. An operator runs a bounded coordinator batch; no daemon wakes it automatically. / 操作员显式运行一个有界协调批次；没有 daemon 自动唤醒。
2. Claim/start one coordinator, renew its lease during the handler, and fence finalization by exact token. / Claim/start 一个协调器，在 handler 期间续租，并以精确 token fencing 收尾。
3. Download selected assets sequentially in deterministic order. Existing verified generations return `already_verified`; any failure prevents export. / 按确定性顺序串行下载已选资产；既有 verified generation 返回 `already_verified`，任何失败都阻止导出。
4. Re-read selection and durable asset generations, then export the complete author snapshot through the existing Emby service. / 重新读取选择与持久资产 generation，再通过既有 Emby 服务导出完整作者快照。
5. Mark only the coordinator succeeded. A later explicit invocation re-enumerates durable state and converges after retry delay or process restart. / 只把协调器标为 succeeded；后续显式调用会重新枚举持久状态，并在 retry delay 或进程重启后收敛。

## Operator flow / 操作流程

The scheduler materializer and sync worker remain separate from the pipeline worker:

调度物化器、同步 worker 与 pipeline worker 继续相互分离：

```powershell
uv run media-sync scheduler tick --json
uv run media-sync scheduler run --max-jobs 1 --scan-limit 100 --json
uv run media-sync pipeline run --max-jobs 1 --scan-limit 100 --lease-seconds 3600 --heartbeat-interval-seconds 20 --json
```

For an authorized MediaCrawler runtime, both network-bearing bounded workers remain default-off and require an explicit per-run license acknowledgement:

对于已授权的 MediaCrawler runtime，两个可能产生网络流量的有界 worker 都保持默认关闭，并要求逐次显式确认许可证：

```powershell
uv run media-sync scheduler run --max-jobs 1 --scan-limit 100 --enable-mediacrawler --accept-mediacrawler-license --json
uv run media-sync pipeline run --max-jobs 1 --scan-limit 100 --heartbeat-interval-seconds 20 --enable-mediacrawler --accept-mediacrawler-license --json
```

An XHS pipeline may additionally receive one opaque secret-provider reference such as `--xhs-detail-reference-ref env:MEDIA_SYNC_XHS_NOTE_DETAIL_URL`. The referenced value is an exact note detail URL with required `xsec` authority; it is not copied into documentation, Job payloads or operator output.

小红书 pipeline 可额外接收一个不透明密钥提供方引用，例如 `--xhs-detail-reference-ref env:MEDIA_SYNC_XHS_NOTE_DETAIL_URL`。引用值是带必需 `xsec` 权限的精确 note 详情 URL；该值不会复制到文档、Job payload 或运维输出。

## Implemented sequence / 已完成顺序

1. Pipeline payload/repository and atomic enqueue from both sync-success paths. / Pipeline payload/repository 及两条 sync-success 路径原子 enqueue。
2. Exact Subscription selector and sequential application pipeline using existing download/export services. / 精确 Subscription selector 与复用既有下载/导出服务的串行应用 pipeline。
3. Bounded worker, fixed result vocabulary, independent coordinator budget, invalid/stale queue-head terminalization and bounded scanning. / 有界 worker、固定结果词汇、独立协调器预算、无效/陈旧队首终态化与有界扫描。
4. Exact scope checks, production runtime composition, MediaCrawler lazy refresh binding and CLI wiring. / 精确范围校验、生产 runtime 组合、MediaCrawler 惰性刷新绑定及 CLI 接线。
5. Heartbeat renewal, CLI interval validation and focused concurrency regressions. / Heartbeat 续租、CLI interval 校验及并发专项回归。

## Deferred hardening / 后置强化

- Cooperative cancellation/ownership guards before and during every synchronous child, forced thread/process termination, all cancellation micro-windows and multi-worker/HA stress. / 每个同步 child 前及执行中的协作式取消/权限 guard、强制线程/进程终止、全部取消微窗口与多 worker/HA 压测。
- Resident scheduling/supervision, automatic retry daemon, dependency graph fan-out/fan-in, REST, Docker and production packaging. / 常驻调度/监督、自动重试 daemon、依赖图 fan-out/fan-in、REST、Docker 与生产打包。
- Automatic XHS multi-note detail-authority discovery; additional platform assets and platform-specific derivatives. / 小红书多 note 详情权限自动发现、更多平台 Asset 与平台特有衍生物。
- Authorized live login/creator/CDN qualification, real Emby/Jellyfin scan/playback, exhaustive retained-secret/cancellation matrix and PostgreSQL HA. / 授权真人登录/作者/CDN 验收、真实 Emby/Jellyfin 扫描/播放、完整留存密钥/取消矩阵与 PostgreSQL HA。
