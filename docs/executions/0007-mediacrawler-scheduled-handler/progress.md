# Execution 0007 progress / 执行 0007 推进结果

- Status / 状态：Planned / 已计划
- Started / 开始时间：2026-08-30 12:45 +08:00
- Implementation / 实现：NOT_RUN / 未运行
- Verification / 验证：NOT_RUN / 未运行
- Predecessor / 前置执行：Execution 0006 implementation commit `674e510`

## Planning baseline / 计划基线

- The goal and frozen plan define an opt-in MediaCrawler scheduled handler without changing the execution 0006 Fake-only implementation truth. No source, database schema, migration or runtime configuration has been changed for execution 0007.
- 目标与冻结计划定义了显式启用的 MediaCrawler 定时 handler，但不改变执行 0006 “仅 Fake handler”的实现事实；执行 0007 尚未修改源码、数据库 schema、迁移或运行配置。
- Read-only design review identified the mandatory boundaries: attempt-scoped execution identity, cooperative cancellation, parent-death process control, same-transaction ingestion fencing, strict durable policy and safe cleanup of unsealed/secret-bearing attempt output.
- 只读设计审查识别出必须关闭的边界：attempt-scoped 执行身份、协作取消、父进程死亡控制、同事务导入 fencing、严格持久策略，以及未密封/含密钥 attempt 输出的安全清理。
- The migration decision is frozen as “no initial Alembic revision”: existing columns can represent the planned state. Manifest v3/receipt v2 with strict legacy dual-read is the required artifact-protocol migration. Any need for a relational schema change must first revise the plan.
- 迁移决定冻结为“初始不新增 Alembic revision”：既有列可以表达计划状态。必需迁移是 manifest v3/receipt v2 及严格 legacy 双读；若需要关系型 schema 变更，必须先修订计划。
- All automated acceptance is restricted to generated sentinels, versioned fixtures, temporary SQLite/filesystems and repository-owned helper processes. No browser, real account, platform/CDN endpoint or Emby/Jellyfin server is authorized.
- 全部自动验收仅限生成哨兵、版本化夹具、临时 SQLite/文件系统及仓库自有辅助进程；不授权浏览器、真人账户、平台/CDN 端点或 Emby/Jellyfin 服务器。
- The planning baseline passed the documentation-link checker for 44 Markdown files, verified both locked upstream checkouts and passed `git diff --check`. These checks validate only the plan commit; implementation and execution 0007 behavior remain `NOT_RUN`.
- 计划基线通过了 44 个 Markdown 文件的文档链接检查、两个锁定上游 checkout 的校验及 `git diff --check`。这些检查只验证计划提交；执行 0007 的实现与行为仍为 `NOT_RUN`。

## Entry findings to close / 实现前必须关闭的问题

| Finding / 问题 | Planned closure / 计划关闭方式 | Status / 状态 |
| --- | --- | --- |
| Retry reuses one scheduler Job path / 重试复用同一 scheduler Job 路径 | Split durable Job and attempt execution identity; unique confined roots / 分离持久 Job 与 attempt 执行身份；使用唯一受限根 | `NOT_RUN` |
| Cancelling `asyncio.to_thread` does not stop runner/processes / 取消 `asyncio.to_thread` 不会停止 runner/进程 | Explicit cancel signal, shielded join and confirmed tree exit / 显式取消信号、shielded join 与整树退出确认 | `NOT_RUN` |
| Batch ingestion lacks scheduler ownership fencing / 分批导入缺少 scheduler ownership fencing | Same-session exact guard before every mutation / 每次变更前在同 session 执行精确 guard | `NOT_RUN` |
| Hard parent death can orphan POSIX child and release profile lock / 父进程硬死亡可能遗留 POSIX child 并释放 profile lock | One-way liveness/control, lock lifetime and helper-process hard-kill tests / 单向 liveness/control、锁生命周期及 helper 硬杀测试 | `NOT_RUN` |
| Scheduled policy is not yet strict or durable / 定时策略尚未严格持久化 | Closed policy v1 plus default-off operator license authorization / 封闭 policy v1 及默认关闭的许可证运维授权 | `NOT_RUN` |
| Secret-bearing output remains after sealing failure / 密钥输出在 sealing 失败后仍会保留 | Safe cleanup of all unsealed/failed attempt-owned artifacts / 安全清理全部未密封/失败的 attempt-owned 产物 | `NOT_RUN` |

## Planned implementation sequence / 计划实现顺序

1. Policy v1 and v3/v2 artifact protocol with immutable legacy readers. / Policy v1 与 v3/v2 产物协议及不可变 legacy reader。
2. Pinned-shape configuration/delay tests and attempt-scoped paths. / Pinned-shape 配置/延迟测试与 attempt-scoped 路径。
3. Cancellable, parent-death-safe process supervision and owned cleanup. / 可取消、父死亡安全的进程监督与受管清理。
4. Reusable MediaCrawler application orchestration and exact database guards. / 可复用 MediaCrawler 应用编排与精确数据库 guard。
5. Closed scheduler handler, waiting/status mapping and explicit CLI enablement. / 封闭 scheduler handler、等待/状态映射及显式 CLI 启用。
6. Offline seven-platform/retry/restart/cancel/ABA/secret acceptance and final gates. / 七平台离线、重试/重启、取消/ABA/密钥验收及最终门禁。

## Current qualification / 当前验收状态

| Scope / 范围 | Status / 状态 | Truth / 真实性说明 |
| --- | --- | --- |
| MediaCrawler scheduled handler implementation / MediaCrawler 定时 handler 实现 | `NOT_RUN` | Execution 0006 remains Fake-only / 执行 0006 仍仅支持 Fake |
| Manifest v3 and receipt v2 / Manifest v3 与 receipt v2 | `NOT_RUN` | Existing writer remains manifest v2/receipt v1 / 既有 writer 仍为 manifest v2/receipt v1 |
| Cooperative cancel and parent-death supervision / 协作取消与父死亡监督 | `NOT_RUN` | Existing runner has no scheduler cancellation contract / 既有 runner 没有 scheduler 取消契约 |
| Same-session MediaCrawler ingestion guard / MediaCrawler 同 session 导入 guard | `NOT_RUN` | Existing ingestion batches have no scheduler guard / 既有导入批次没有 scheduler guard |
| Seven-platform offline scheduled fixture flow / 七平台离线定时夹具流程 | `NOT_RUN` | Planned tests have not run / 计划测试尚未运行 |
| Live login, creator traffic, CDN and Emby/Jellyfin / 真人登录、作者流量、CDN 与 Emby/Jellyfin | `NOT_RUN` | No authorization or environment was supplied / 未提供授权或环境 |

## Deferred truthfully / 如实延期

- Scheduled backfill, signed-locator refresh, real CDN retrieval and automatic downstream DAG planning are not execution 0007 acceptance. / 定时 backfill、签名 locator refresh、真实 CDN 获取及自动下游 DAG 不属于执行 0007 验收。
- Per-request HTTP throttling is not implied by `CRAWLER_MAX_SLEEP_SEC`; proxy/CAPTCHA/protection-bypass work is excluded. / `CRAWLER_MAX_SLEEP_SEC` 不代表逐请求 HTTP 节流；代理/验证码/平台保护绕过均排除。
- REST, resident supervision, Docker/production packaging, distributed HA and live Emby/Jellyfin operations remain later work. / REST、常驻守护、Docker/生产打包、分布式 HA 与真人 Emby/Jellyfin 运维仍属于后续工作。
