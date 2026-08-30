# Execution 0010 plan / 执行 0010 计划

- Status / 状态：In progress — frozen functional MVP / 推进中——已冻结功能 MVP
- Plan date / 计划日期：2026-08-31
- Schema decision / Schema 决策：reuse existing `jobs` scope/lease/natural-key columns; no migration for MVP / MVP 复用既有 `jobs` 范围、租约及 natural-key 列；无需 migration

## Design / 设计

### Durable coordinator / 持久协调器

- Add Job type `pipeline.subscription` with natural key `sync-job:<sync_job_id>`. / 新增 Job 类型，natural key 为 `sync-job:<sync_job_id>`。
- Closed payload v1 contains only `schema_version`, `sync_job_id`, `subscription_id` and `run_id`; author identity is re-read from Subscription. / 封闭 payload v1 只含上述四项；作者身份从 Subscription 重新读取。
- Enqueue inside both scheduler normal-success and succeeded-attachment reconciliation transactions. Unique identity makes repeated finalization safe. / 在调度器正常成功与 succeeded attachment 恢复事务中均 enqueue；唯一身份保证重复收尾安全。

### Exact work selection / 精确工作选择

- Resolve Subscription → Account/Author and enumerate non-tombstoned Content for that author. / 解析 Subscription → Account/Author，并枚举该作者未 tombstone 的 Content。
- For MediaCrawler `adapter_refresh` Assets, require a current `asset_refresh_sources` row for the exact Subscription whose fingerprints equal the Asset. / MediaCrawler `adapter_refresh` Asset 必须存在精确 Subscription 的当前来源行，且指纹与 Asset 相等。
- Include every current unverified eligible asset needed by the complete author snapshot, not only rows last seen by the triggering run. / 包含完整作者快照需要的全部当前未验证合格资产，不只处理触发 run 最后观察的行。

### Execution and recovery / 执行与恢复

1. Claim one coordinator Job with existing lease semantics. / 使用既有租约语义 claim 一个协调 Job。
2. Download assets sequentially in deterministic order; verified assets return `already_verified`. / 按确定性顺序下载；已验证资产返回 `already_verified`。
3. Stop before export on any download failure and classify the coordinator result retryably/terminally. / 任一下载失败即在导出前停止，并分类协调 Job 结果。
4. Export the author through the existing Emby service after all blockers are verified. / 全部阻塞资产验证后调用既有 Emby 服务导出作者。
5. Mark the coordinator succeeded with fixed, non-URL summary fields. Restart simply re-enumerates durable state. / 以固定、无 URL 摘要字段标记成功；重启重新枚举持久状态即可。

## Implementation sequence / 实现顺序

1. Pipeline Job payload/repository plus atomic enqueue from the two sync-success paths. / Pipeline Job payload/repository 及两条 sync-success 路径原子 enqueue。
2. Exact subscription asset selector and application coordinator using existing download/export services. / 精确 Subscription Asset selector 及复用下载/导出服务的应用协调器。
3. Dedicated bounded worker/handler with lease heartbeat and fixed result mapping. / 专用有界 worker/handler、租约 heartbeat 与固定结果映射。
4. CLI wiring and Fake/direct end-to-end regression. / CLI 接线及 Fake/direct 端到端回归。
5. MediaCrawler refresh integration, documentation truth and local bilingual commits. / MediaCrawler refresh 集成、文档事实及本地双语提交。

## Deferred hardening / 后置强化

- Dependency graph tables, concurrent child fan-out, multi-worker stress/HA, every cancellation micro-window, full retained-secret gate, live platform/CDN and real media-server qualification. / 依赖图表、并发 child fan-out、多 worker 压测/HA、全部取消微窗口、完整留存密钥门禁、真人平台/CDN 与真实媒体服务器验收。
