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
| 0005 | Media download and Emby/Jellyfin export / 媒体下载与 Emby/Jellyfin 导出 | Complete for offline scope; live rows remain `NOT_RUN` / 离线范围完成；真人行保持 `NOT_RUN` | Plan `096b815`; bilingual closeout implementation commit / 计划 `096b815`；双语收尾实现提交 |
| 0006 | Durable scheduler and throttled workers / 持久调度与限流工作器 | Planned; implementation not started / 已计划；实现尚未开始 | Goal and plan frozen after `8d5b48a` / 在 `8d5b48a` 后冻结目标与计划 |

Execution 0005 qualifies only mock/fixture/local-filesystem contracts. Its downloader coordinates one asset generation with a hashed I/O scope, a local OS lock and lease/generation CAS, and can recover an archive commit that preceded database finalization. Composite API/access-key variants and credential-bearing URL paths are removed at sinks without classifying ordinary `key` fields as secrets; direct/source-hint persistence and the `0003` legacy backfill also reject those paths. Its Emby publisher derives managed ownership from a durable database Job predecessor chain with exact source/tree/manifest identities; the disk manifest cannot establish ownership by itself. A `0003 → 0002 → 0003` round trip removes generation-bound download identities and non-recoverable non-succeeded Emby identities while preserving the succeeded chain and structurally valid publication-intent recovery state. The final root run passed 540 tests with 79% branch-aware coverage, all focused gates, build/package checks and a zero-match scan over retained SQLite/archive/export/operator artifacts. Seven-platform live login/sync/CDN download and real Emby/Jellyfin scan/playback remain `NOT_RUN`; unavailable refresh, platform derivatives, scheduler/API and production packaging remain unimplemented or deferred rather than `NOT_RUN`.

执行 0005 只验收 mock、夹具与本地文件系统契约。下载器以 I/O scope 哈希、本地 OS 锁及租约/generation CAS 协调单个资产 generation，并能恢复先于数据库收尾完成的归档提交。组合 API/access key 变体及带凭据的 URL 路径会在落点被移除，但普通 `key` 字段不会被误判；direct/source hint 持久化与 `0003` legacy 回填同样拒绝这类路径。Emby 发布器通过持久数据库 Job predecessor chain 及精确 source/tree/manifest 身份确定受管所有权；磁盘 manifest 不能自行建立所有权。`0003 → 0002 → 0003` 往返会移除 generation-bound 下载身份及不可恢复的未成功 Emby 身份，同时保留已成功发布链与结构有效的发布 intent 恢复状态。最终根任务通过 540 项测试，分支感知覆盖率为 79%，全部专项、构建/打包检查及保留 SQLite/归档/导出/运维产物的零匹配扫描均通过。七平台真人登录/同步/CDN 下载及真实 Emby/Jellyfin 扫描/播放继续为 `NOT_RUN`；不可用的 refresh、平台衍生物、调度/API 与生产打包属于未实现或延期范围，而不是 `NOT_RUN`。

## Documentation rule / 文档规则

Before a milestone starts, create its `goal.md` and `plan.md`. During implementation, update `progress.md`. Before committing, record exact commands, exit codes and important output in `verification.md`. Secrets, cookies and personal account data must never be copied into these records.

每个里程碑开始前创建 `goal.md` 和 `plan.md`；实现期间持续更新 `progress.md`；提交前把准确命令、退出码和关键输出写入 `verification.md`。任何密钥、Cookie 或个人账户数据都不得进入文档。
