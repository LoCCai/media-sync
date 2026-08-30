# media-sync project journal / 项目工作日志

This directory is the durable audit trail for the project. Every execution milestone has four records: goal, plan, progress, and verification.

本目录是项目的长期审计记录。每个执行里程碑固定保存四类文件：目标、计划、推进结果和验证过程。

## Navigation / 导航

- [`roadmap.md`](roadmap.md): overall delivery phases and acceptance criteria / 总体阶段与验收标准。
- [`requirements.md`](requirements.md): functional, safety and quality contract / 功能、安全与质量契约。
- [`architecture.md`](architecture.md): component boundaries, data model and workflow / 组件边界、数据模型与工作流。
- [`platform-capabilities.md`](platform-capabilities.md): source-backed platform truth matrix / 基于源码证据的平台真实能力矩阵。
- [`upstreams.md`](upstreams.md): pinned source repositories and capability baseline / 上游锁定与能力基线。
- [`research/`](research/): detailed source research / 详细源码调研。
- [`decisions/`](decisions/): architecture decision records / 架构决策记录。
- [`executions/`](executions/): per-milestone goal, plan, progress and verification evidence / 每个里程碑的四件套记录。
- [`templates/`](templates/): templates for all future executions / 后续执行模板。

## Execution index / 执行索引

| ID | Milestone / 里程碑 | Status / 状态 | Commit / 提交 |
| --- | --- | --- | --- |
| 0001 | Bootstrap and pin upstreams / 初始化并锁定上游 | Complete / 已完成 | `59da120` |
| 0002 | Upstream analysis and architecture / 上游分析与架构 | Complete / 已完成 | `af813bd`, `201fbbf` |
| 0003 | Core domain, persistence and offline CLI / 核心领域、持久化与离线 CLI | Complete / 已完成 | `564cdb8` |
| 0004 | Credential-safe MediaCrawler bridge / 安全凭据与 MediaCrawler 桥接 | Complete / 已完成 | `0c27ad6`, `13664b5` |
| 0005 | Media download and Emby/Jellyfin export / 媒体下载与 Emby/Jellyfin 导出 | Complete for offline scope; live rows remain `NOT_RUN` / 离线范围完成；真人行保持 `NOT_RUN` | Plan `096b815`; implementation `8d5b48a` / 计划 `096b815`；实现 `8d5b48a` |
| 0006 | Durable scheduler and throttled workers / 持久调度与限流工作器 | Complete for the offline/Fake scope; live rows remain `NOT_RUN` / 离线/Fake 范围完成；真人行保持 `NOT_RUN` | Plan `c8c4e54`; implementation `674e510` / 计划 `c8c4e54`；实现 `674e510` |
| 0007 | MediaCrawler scheduled handler / MediaCrawler 定时 handler | Implemented for the offline scope; AC6/AC13 `PARTIAL`; every live row `NOT_RUN` / 离线范围已实现；AC6/AC13 为 `PARTIAL`；全部真人行保持 `NOT_RUN` | This bilingual implementation commit / 本次双语实现提交 |

Execution 0005 qualifies only mock/fixture/local-filesystem contracts. Its downloader coordinates one asset generation with a hashed I/O scope, a local OS lock and lease/generation CAS, and can recover an archive commit that preceded database finalization. Composite API/access-key variants and credential-bearing URL paths are removed at sinks without classifying ordinary `key` fields as secrets; direct/source-hint persistence and the `0003` legacy backfill also reject those paths. Its Emby publisher derives managed ownership from a durable database Job predecessor chain with exact source/tree/manifest identities; the disk manifest cannot establish ownership by itself. A `0003 → 0002 → 0003` round trip removes generation-bound download identities and non-recoverable non-succeeded Emby identities while preserving the succeeded chain and structurally valid publication-intent recovery state. The final root run passed 540 tests with 79% branch-aware coverage, all focused gates, build/package checks and a zero-match scan over retained SQLite/archive/export/operator artifacts. At the 0005 boundary, scheduler/API and production packaging were deferred; execution 0006 now closes only the scheduler's offline/Fake slice. Seven-platform live login/sync/CDN download and real Emby/Jellyfin scan/playback remain `NOT_RUN`; unavailable refresh, platform derivatives, API and production packaging remain unimplemented or deferred rather than `NOT_RUN`.

执行 0005 只验收 mock、夹具与本地文件系统契约。下载器以 I/O scope 哈希、本地 OS 锁及租约/generation CAS 协调单个资产 generation，并能恢复先于数据库收尾完成的归档提交。组合 API/access key 变体及带凭据的 URL 路径会在落点被移除，但普通 `key` 字段不会被误判；direct/source hint 持久化与 `0003` legacy 回填同样拒绝这类路径。Emby 发布器通过持久数据库 Job predecessor chain 及精确 source/tree/manifest 身份确定受管所有权；磁盘 manifest 不能自行建立所有权。`0003 → 0002 → 0003` 往返会移除 generation-bound 下载身份及不可恢复的未成功 Emby 身份，同时保留已成功发布链与结构有效的发布 intent 恢复状态。最终根任务通过 540 项测试，分支感知覆盖率为 79%，全部专项、构建/打包检查及保留 SQLite/归档/导出/运维产物的零匹配扫描均通过。在 0005 边界，调度/API 与生产打包均处于延期状态；执行 0006 现在只补齐调度器的离线/Fake 切片。七平台真人登录/同步/CDN 下载及真实 Emby/Jellyfin 扫描/播放继续为 `NOT_RUN`；不可用的 refresh、平台衍生物、API 与生产打包属于未实现或延期范围，而不是 `NOT_RUN`。

Execution 0006 materializes bounded due cycles, applies fixed-delay completion, bounded retry/backoff and persistent platform/account launch lanes, and runs `sync.subscription` Jobs behind exact lease/heartbeat/cancellation fencing. Its closed registry intentionally ships only the deterministic Fake handler. The restart acceptance path explicitly invokes the existing secure downloader and Emby exporter after scheduled Fake sync; it does not claim an automatic downstream DAG. The final root gate passed 686 tests in 152.40 seconds with 80% branch-aware coverage. MediaCrawler scheduled execution, per-request upstream throttling, signed-locator refresh, REST, resident supervision and production packaging remain later work. Exact offline verification is recorded in [`executions/0006-durable-scheduler/verification.md`](executions/0006-durable-scheduler/verification.md).

执行 0006 会有界物化到期周期，执行 fixed-delay 收尾、有界重试/退避及持久平台/账户启动 lane，并以精确租约、heartbeat 与取消 fencing 运行 `sync.subscription` Job。其封闭 registry 有意只随附确定性 Fake handler。重启验收会在 scheduled Fake sync 后显式调用既有安全下载器与 Emby 导出器；不宣称已有自动下游 DAG。最终根任务门禁通过 686 项测试，耗时 152.40 秒，分支感知总覆盖率 80%。MediaCrawler 定时执行、逐请求上游节流、签名 locator 刷新、REST、常驻守护及生产打包仍属于后续工作。准确离线验证记录在 [`executions/0006-durable-scheduler/verification.md`](executions/0006-durable-scheduler/verification.md)。

Execution 0007 now ships an opt-in, license-gated MediaCrawler scheduled handler. Closed policy v1, new manifest v3/receipt v2 artifacts, attempt-scoped execution identity, parent-owned heartbeat/process supervision, exact same-transaction ingestion fencing, conservative waiting/failure mapping and four-state failed-artifact cleanup are implemented. Sealed manifest v2/receipt v1 evidence remains strict, byte-exact and read-only through shared normalization/manual ingest; scheduled restart recovery trusts v3 only. A real offline fake-child protocol proves subscribe → tick → v3 write/load → versioned JSONL → v2 receipt → guarded ingestion → retry/restart → idempotent replay for all seven platform identifiers. Repeated cancellation now joins both runner and between-batch ingestion before unwind; AC6 remains `PARTIAL` only because deterministic post-child/pre-seal and post-seal/pre-ingest barriers are incomplete. AC13 remains `PARTIAL` because the complete failure/secret-sink cross-product is incomplete. Live login, creator traffic, CDN retrieval and Emby/Jellyfin scan/playback remain `NOT_RUN`. Exact evidence is in [`executions/0007-mediacrawler-scheduled-handler/`](executions/0007-mediacrawler-scheduled-handler/).

执行 0007 现已随附显式启用、受许可证约束的 MediaCrawler 定时 handler。封闭 policy v1、新写 manifest v3/receipt v2、attempt-scoped 执行身份、父进程拥有的 heartbeat/进程监督、精确同事务导入 fencing、保守 waiting/失败映射，以及四状态失败产物清理均已实现。已密封 manifest v2/receipt v1 证据继续通过共享归一化/手工导入实现严格、逐字节精确的只读兼容；定时重启恢复只信任 v3。真实离线 fake-child 协议已为七个平台标识证明“订阅 → tick → v3 写入/读取 → 版本化 JSONL → v2 回执 → 受保护导入 → 重试/重启 → 幂等重放”。重复取消现在会先 join runner 与批次间导入，再向外 unwind；AC6 仍为 `PARTIAL`，仅因为 child 退出后/seal 前及 seal 后/导入前的确定性 barrier 尚不完整。AC13 仍为 `PARTIAL`，因为完整失败/密钥落点交叉矩阵尚不完整。真人登录、作者流量、CDN 获取及 Emby/Jellyfin 扫描/播放继续为 `NOT_RUN`。准确证据位于 [`executions/0007-mediacrawler-scheduled-handler/`](executions/0007-mediacrawler-scheduled-handler/)。

## Documentation rule / 文档规则

Before a milestone starts, create its `goal.md` and `plan.md`. During implementation, update `progress.md`. Before committing, record exact commands, exit codes and important output in `verification.md`. Secrets, cookies and personal account data must never be copied into these records.

每个里程碑开始前创建 `goal.md` 和 `plan.md`；实现期间持续更新 `progress.md`；提交前把准确命令、退出码和关键输出写入 `verification.md`。任何密钥、Cookie 或个人账户数据都不得进入文档。
