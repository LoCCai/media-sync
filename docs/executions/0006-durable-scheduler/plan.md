# Execution 0006 plan / 执行 0006 计划

- Status / 状态：Frozen before implementation / 实现前冻结
- Plan date / 计划日期：2026-08-30
- Network policy / 网络策略：offline tests only / 仅离线测试

## Frozen design / 冻结设计

### Durable identities / 持久身份

- Add `subscriptions.schedule_revision INTEGER NOT NULL DEFAULT 0 CHECK >= 0`.
- Add nullable `jobs.subscription_id`, `jobs.account_id`, `jobs.platform` and `jobs.scheduled_for`, plus claim/scope indexes and a partial unique index allowing only one active `sync.subscription` Job per subscription. Active is frozen as `queued`, `claimed`, `running`, `retry_wait`, `waiting_auth`, `waiting_user` or `failed_retryable`; terminal is only `succeeded`, `failed_terminal` or `cancelled`.
- Cycle natural key: `subscription:<subscription-id>:schedule:<revision>`.
- `enabled=true AND next_run_at IS NULL` means immediately due; disabled means paused. Materialization is limited and ordered by null-due first, due time, creation time and ID.
- Completion uses fixed delay: `next_run_at = finished_at + interval_seconds`. Success resets `consecutive_failures`; one terminal cycle failure increments it once. Downgrade removes scheduler lanes and all `sync.subscription` Jobs before dropping scheduler columns, so a re-upgrade cannot inherit a natural-key poison; existing execution 0005 Jobs remain byte-identical.

- 新增 `subscriptions.schedule_revision INTEGER NOT NULL DEFAULT 0 CHECK >= 0`。
- 新增可空 `jobs.subscription_id`、`jobs.account_id`、`jobs.platform`、`jobs.scheduled_for`，以及领取/scope 索引与“每个订阅仅一个 active `sync.subscription` Job”的部分唯一索引。active 冻结为 `queued`、`claimed`、`running`、`retry_wait`、`waiting_auth`、`waiting_user`、`failed_retryable`；终态仅为 `succeeded`、`failed_terminal`、`cancelled`。
- 周期 natural key 为 `subscription:<subscription-id>:schedule:<revision>`。
- `enabled=true AND next_run_at IS NULL` 表示立即到期；disabled 表示暂停。物化必须有 limit，并按 null-due、到期时间、创建时间、ID 排序。
- 完成采用 fixed delay：`next_run_at = finished_at + interval_seconds`。成功清零 `consecutive_failures`；一次终态周期失败只增加一次。downgrade 会先删除 scheduler lane 与全部 `sync.subscription` Job，再移除调度列，避免 re-upgrade 继承 natural-key 污染；执行 0005 的既有 Job 保持逐字节一致。

### Retry and lanes / 重试与 lane

- Freeze retry policy into each Job payload: schema v1, base 30 seconds, cap 1,800 seconds, maximum 5 attempts, equal jitter. A valid `Retry-After` is a lower bound.
- Add durable `scheduler_lanes` for platform and account scopes. Fields cover concurrency, start interval, failure threshold, cooldown, next start, consecutive failures, circuit state/open deadline, half-open Job and revision.
- Conservative defaults: platform concurrency 1, account concurrency 1, start interval 5 seconds, and a circuit that opens after 3 classified failures for 15 minutes.
- Claim must satisfy worker-global capacity and both lanes. It scans past blocked candidates to avoid head-of-line starvation. Half-open permits one exact Job.
- Risk/rate-limit/temporary upstream failures affect circuits; account lock contention does not. Authentication and interactive challenges enter explicit waiting states.

- 每个 Job payload 冻结 retry policy：schema v1、30 秒起步、1,800 秒封顶、最多 5 次、equal jitter；合法 `Retry-After` 作为下界。
- 新增平台与账户 scope 的持久 `scheduler_lanes`，字段覆盖并发、启动间隔、失败阈值、冷却、下次启动、连续失败、circuit 状态/开放截止、half-open Job 与 revision。
- 保守默认值：平台并发 1、账户并发 1、启动间隔 5 秒，3 次分类失败后打开 circuit 15 分钟。
- 领取必须同时满足 worker 全局容量和两条 lane，并跳过被阻塞候选，避免队头饥饿；half-open 只允许一个精确 Job。
- 风险/限流/临时上游失败影响 circuit；账户锁竞争不影响。认证与真人交互挑战进入显式等待状态。

### Worker boundary / Worker 边界

- Introduce a closed `sync.subscription` handler registry and short-transaction worker lifecycle: claim, start, heartbeat, finalize. Execution 0006 ships the deterministic Fake handler.
- Reclaim and requeue predicates are Job-type scoped before mutation. `asset_download` and `export.emby` continue to enqueue and exact-claim only inside their execution 0005 services.
- Fake handler reuses the application sync service. MediaCrawler remains on the execution 0004 manual CLI run/ingest path; its scheduler application handler, manifest v3 and child-process supervision are a separately documented later execution.
- Secret/credential values, real paths and raw handler errors never enter Job/lane payloads.

- 新增封闭的 `sync.subscription` handler registry，以及短事务 worker 生命周期：claim、start、heartbeat、finalize；执行 0006 交付确定性 Fake handler。
- reclaim 与重新排队谓词在变更前按 Job 类型限定。`asset_download` 与 `export.emby` 继续只由执行 0005 服务内部 enqueue 并精确 claim。
- Fake handler 复用应用同步服务。MediaCrawler 保持执行 0004 的手工 CLI run/ingest 路径；其 scheduler 应用 handler、manifest v3 及子进程监督作为后续独立执行记录。
- 密钥/凭据值、真实路径及原始 handler 错误不得进入 Job/lane payload。

## Implementation sequence / 实现顺序

1. Add retry/circuit pure policy types and exhaustive numeric/time tests.
2. Add migration `0004_scheduler_control_plane`, ORM models, source/wheel upgrade and downgrade preservation tests.
3. Fix generic Job reclaim/queue scoping, then add scheduler repositories for due materialization, lane policy/CAS, waiting resume and cycle finalization.
4. Add scheduler and worker application services with injected clock/RNG and handler protocol.
5. Deliver Fake handler and restart-safe offline cycle tests.
6. Add an offline acceptance harness that explicitly invokes existing execution 0005 download/export services after scheduled Fake sync; do not add a generic downstream planner or preclaim their Jobs.
7. Add redaction-safe CLI control surfaces and operations documentation.
8. Run concurrency, retry, circuit, migration, end-to-end and sentinel review; close every P0/P1 finding.
9. Run the exact final gates, update all four execution documents and create a bilingual local implementation commit. Never push.

1. 新增 retry/circuit 纯策略类型及完整数字/时间测试。
2. 新增迁移 `0004_scheduler_control_plane`、ORM 模型，以及源码/wheel upgrade、downgrade 保留测试。
3. 修复通用 Job reclaim/排队的类型 scope，再新增到期物化、lane 策略/CAS、等待恢复及周期收尾仓储。
4. 新增注入时钟/RNG 的 scheduler、worker 应用服务与 handler 协议。
5. 交付 Fake handler 及可重启离线周期测试。
6. 新增离线验收 harness，在 scheduled Fake sync 后显式调用执行 0005 的既有下载/导出服务；不新增通用下游 planner，也不预领其 Job。
7. 新增脱敏 CLI 控制面与运维文档。
8. 执行并发、退避、circuit、迁移、端到端及哨兵审查，关闭全部 P0/P1。
9. 运行准确最终门禁，更新四份执行文档并创建中英双语本地实现提交；绝不推送。

## Required tests / 必需测试

- Concurrent due ticks with independent SQLite sessions; disabled/future/null due, run-now, pause/resume and no catch-up storm.
- Backoff boundaries, equal jitter, Retry-After, NaN/infinity, datetime overflow and max attempts.
- Global/platform/account concurrency, start intervals, queue scan fairness, open/cooldown/single-half-open/success-close/failure-reopen circuits.
- Expiry/ABA heartbeat and cancellation; sync reclaim proves zero mutation of expired download/export prepared-result or publication-intent Jobs.
- Waiting auth/user remains dormant until explicit resume.
- Fake handler lifecycle, retry/wait outcomes and no long I/O transaction.
- Offline restart E2E and byte-level secret sentinel across SQLite, Job/lane state, runtime output, archive and export.
- Empty database, real `0003` upgrade, downgrade, source package and unpacked-wheel migrations.

- 使用独立 SQLite session 的并发到期 tick；disabled/future/null due、run-now、pause/resume 及无追赶风暴。
- 退避边界、equal jitter、Retry-After、NaN/infinity、datetime overflow 及最大尝试次数。
- 全局/平台/账户并发、启动间隔、队列扫描公平、open/冷却/唯一 half-open/成功关闭/失败重开 circuit。
- 过期/ABA heartbeat 与取消；sync reclaim 证明不会修改过期 download/export prepared-result 或发布 intent Job。
- waiting auth/user 在显式 resume 前保持休眠。
- Fake handler 生命周期、重试/等待结果及无长 I/O 事务。
- 离线重启 E2E，以及 SQLite、Job/lane、运行输出、归档和导出的字节级密钥哨兵。
- 空库、真实 `0003` upgrade、downgrade、源码包及解包 wheel 迁移。
