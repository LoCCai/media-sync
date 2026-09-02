[English](plan.md) | **中文**

# 执行 0006 计划

- 状态：实现前冻结
- 执行结果：由本次双语收尾提交完成
- 计划日期：2026-08-30
- 网络策略：仅离线测试

## 冻结设计

### 持久身份

- 新增 `subscriptions.schedule_revision INTEGER NOT NULL DEFAULT 0 CHECK >= 0`。
- 新增可空 `jobs.subscription_id`、`jobs.account_id`、`jobs.platform`、`jobs.scheduled_for`，以及领取/scope 索引与“每个订阅仅一个 active `sync.subscription` Job”的部分唯一索引。active 冻结为 `queued`、`claimed`、`running`、`retry_wait`、`waiting_auth`、`waiting_user`、`failed_retryable`；终态仅为 `succeeded`、`failed_terminal`、`cancelled`。
- 周期 natural key 为 `subscription:<subscription-id>:schedule:<revision>`。
- `enabled=true AND next_run_at IS NULL` 表示立即到期；disabled 表示暂停。物化必须有 limit，并按 null-due、到期时间、创建时间、ID 排序。
- 完成采用 fixed delay：`next_run_at = finished_at + interval_seconds`。成功清零 `consecutive_failures`；一次终态周期失败只增加一次。downgrade 会先删除 scheduler lane 与全部 `sync.subscription` Job，再移除调度列，避免 re-upgrade 继承 natural-key 污染。`0003` 可表达的执行 0005 Job 证据保持逐字段一致，包括 JSON 存储类型；这不是 SQLite 物理字节一致声明。

### 重试与 lane

- 每个 Job payload 冻结 retry policy：schema v1、30 秒起步、1,800 秒封顶、最多 5 次、equal jitter；合法 `Retry-After` 作为下界。
- 新增平台与账户 scope 的持久 `scheduler_lanes`，字段覆盖并发、启动间隔、失败阈值、冷却、下次启动、连续失败、circuit 状态/开放截止、half-open Job 与 revision。
- 保守默认值：平台并发 1、账户并发 1、启动间隔 5 秒，3 次分类失败后打开 circuit 15 分钟。
- 领取必须同时满足 worker 全局容量和两条 lane，并跳过被阻塞候选，避免队头饥饿；half-open 只允许一个精确 Job。
- 风险/限流/临时上游失败影响 circuit；账户锁竞争不影响。认证与真人交互挑战进入显式等待状态。

### Worker 边界

- 新增封闭的 `sync.subscription` handler registry，以及短事务 worker 生命周期：claim、start、heartbeat、finalize；执行 0006 交付确定性 Fake handler。
- reclaim 与重新排队谓词在变更前按 Job 类型限定。`asset_download` 与 `export.emby` 继续只由执行 0005 服务内部 enqueue 并精确 claim。
- Fake handler 复用应用同步服务。MediaCrawler 保持执行 0004 的手工 CLI run/ingest 路径；其 scheduler 应用 handler、manifest v3 及子进程监督作为后续独立执行记录。
- 密钥/凭据值、不可信真实路径及原始 handler 错误不得进入 `sync.subscription` 调度 Job/lane payload；既有资产/导出记录可按设计保存经验证的归档/输出路径。

## 实现顺序

1. 新增 retry/circuit 纯策略类型及完整数字/时间测试。
2. 新增迁移 `0004_scheduler_control_plane`、ORM 模型，以及源码/wheel upgrade、downgrade 保留测试。
3. 修复通用 Job reclaim/排队的类型 scope，再新增到期物化、lane 策略/CAS、等待恢复及周期收尾仓储。
4. 新增注入时钟/RNG 的 scheduler、worker 应用服务与 handler 协议。
5. 交付 Fake handler 及可重启离线周期测试。
6. 新增离线验收 harness，在 scheduled Fake sync 后显式调用执行 0005 的既有下载/导出服务；不新增通用下游 planner，也不预领其 Job。
7. 新增脱敏 CLI 控制面与运维文档。
8. 执行并发、退避、circuit、迁移、端到端及哨兵审查，关闭全部 P0/P1。
9. 运行准确最终门禁，更新四份执行文档并创建中英双语本地实现提交；绝不推送。

## 必需测试

- 使用独立 SQLite session 的并发到期 tick；disabled/future/null due、run-now、pause/resume 及无追赶风暴。
- 退避边界、equal jitter、Retry-After、NaN/infinity、datetime overflow 及最大尝试次数。
- 全局/平台/账户并发、启动间隔、队列扫描公平、open/冷却/唯一 half-open/成功关闭/失败重开 circuit。
- 过期/ABA heartbeat 与取消；sync reclaim 证明不会修改过期 download/export prepared-result 或发布 intent Job。
- waiting auth/user 在显式 resume 前保持休眠。
- Fake handler 生命周期、重试/等待结果及无长 I/O 事务。
- 离线重启 E2E，以及 SQLite、Job/lane、运行输出、归档和导出的字节级密钥哨兵。
- 空库、真实 `0003` upgrade、downgrade、源码包及解包 wheel 迁移。
