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
| 0001 | Bootstrap and pin upstreams / 初始化并锁定上游 | Complete / 已完成 | Baseline commit / 基线提交 |
| 0002 | Upstream analysis and architecture / 上游分析与架构 | Complete / 已完成 | Research commit / 调研提交 |
| 0003 | Core domain, persistence and offline CLI / 核心领域、持久化与离线 CLI | Complete / 已完成 | Core foundation commit / 核心基线提交 |
| 0004 | Credential-safe MediaCrawler bridge / 安全凭据与 MediaCrawler 桥接 | In progress / 进行中 | Planning commit / 计划提交 |

## Documentation rule / 文档规则

Before a milestone starts, create its `goal.md` and `plan.md`. During implementation, update `progress.md`. Before committing, record exact commands, exit codes and important output in `verification.md`. Secrets, cookies and personal account data must never be copied into these records.

每个里程碑开始前创建 `goal.md` 和 `plan.md`；实现期间持续更新 `progress.md`；提交前把准确命令、退出码和关键输出写入 `verification.md`。任何密钥、Cookie 或个人账户数据都不得进入文档。
