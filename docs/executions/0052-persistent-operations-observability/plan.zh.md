[English](plan.md) | **中文**

# 执行 0052 计划

- 状态：交付与本地验证已完成；发布核对将在收尾提交后执行
- 计划日期：2026-09-04
- 基线：`d64b97b`
- 数据库 revision：`0006_operations_observability`
- 收尾提交：包含本记录的提交（不嵌入自身 SHA）

## 基线决策

执行 0051 已消除账户/订阅校验歧义，但按计划保留进程内 Operation 与轮询。因此 Execution 0052 交付可独立测试的控制面切片：持久操作所有权、安全观测与协作取消。Execution 0047 仍是 P0 Linux/真人门；本轮任何离线工作都不会把尚未执行的操作者行改成通过。

一项范围校正现已冻结：订阅 pause/resume 审计和破坏性删除需要已认证的操作者权限及保留/cascade 策略，因此两者都保留到 Execution 0055。本执行只记录五类 API 工作流的取消审计事实，不改变原始七平台订阅与 Emby/Jellyfin 总目标。

## 已执行交付顺序

1. 冻结五类 operation kind、七种状态、十二个生命周期事件码、固定错误码及一份 v1 安全 payload 契约。
2. 新增 `0006` migration，创建 `operations`、`operation_events`、有界 `operation_subjects` 与单例 `operation_event_stream_state`。活动 exclusive scope 与适用的 `(kind, idempotency_key_hash)` 保持唯一；生命周期、进度、target、lease、错误及摘要形状受数据库约束。
3. 实现原子 create-or-replay、claim/start、heartbeat、进度/事件/关联追加、取消请求、终态完成、keyset 分页、stream 边界及过期 lease 协调。lease token 阻止旧 owner 写入，全局事件 cursor 则在事件事务内更新计数器行完成分配。
4. 为每类 Operation 新增封闭请求身份、结果摘要和事件上下文投影器。未知字段或不安全值在持久化前失败关闭；原始请求正文、异常、reference、URL、路径、QR 字节及调用方 worker 身份在 payload 中没有表达方式。
5. 新增 `OperationCoordinator`：在同一事务 create/replay 与 claim，仅在提交后启动 callable；服务端派生 worker 所有权，续租、观察取消，并通过事务 hook 记录 subject。权威读取先取得 SQLite writer reservation，以新事务执行有界重试；pending 终态意图由 monitor 重试。并发 observer 会等待持久取消观察，使事件历史即使跨 coordinator 实例也保持 `requested` → `observed` → `cancelled`。
6. 替换账户登录、资产下载、scheduler run、pipeline run 与 Emby export 的 API 进程内 operation 接线。五类 POST 均接收严格校验的 `Idempotency-Key`；私密 reference 仅以领域隔离摘要进入请求指纹；请求 `worker_id` 不参与持久所有权，也不被序列化。
7. 新增有界列表/详情/单 Operation 事件 API、两阶段取消与全局 SSE。ready 帧始终使用 `event_id=initial_cursor`：新连接捕获当前 high-water，重连则保留传入 cursor，避免跳过两次会话之间提交的事件。重连严格补发该 cursor 后的已提交事件，拒绝畸形/未来 cursor，对已裁剪历史返回固定的 `410 operation_event_cursor_expired`。
8. 将保守的启动与有界读取协调实现为非阻塞、单飞后台工作。有效的其他实例 lease 不受影响；过期 Operation 根据无歧义 Job/LoginSession 事实或 `interrupted` 收敛；失败会释放单飞槽以供重试，shutdown 后不再触发，且不自动恢复内存 callable。
9. 将 Jobs 路由升级为任务中心，包含 200 项有界快照、kind/state/文本筛选、详情与事件时间线、进度、subject 关联、派生动作、取消控制、EventSource 更新、sequence 去重及有界轮询回退。
10. 新增 `GET /api/v1/support-bundle`，以 `application/json` 与 `Cache-Control: no-store` 返回规范 JSON。其固定且仅聚合的形状包含项目/构建/schema readiness、实体计数、Operation 状态/kind 计数及有界近期固定错误码计数；总量上限 16 KiB，输出前再次扫描。数据库失败只返回 `support_bundle_database_failed`。
11. 在领域交接点加固取消。coordinator 刷新权威 phase snapshot，五类工作流都会在进入不可中断领域调用前同时重查持久 `cancel_requested_at` 与本地 cancellation context；调用一旦开始，持久领域成功会如实优先于稍后的取消请求。
12. 已完成最终聚焦、冻结完整套件、静态/打包、Web、上游与 tracked-output 审计。更新双语执行/全局记录后，以中英双语标题/正文提交并推送 `main`，再核对本地、`origin/main` 与 GitHub SHA，不嵌入尚不存在的自身 SHA。

## 冻结契约校正

- 只持久化已校验 `Idempotency-Key` 的 SHA-256 摘要与规范请求指纹；绝不保存或返回原始 key。
- `requested_by` 是固定的内部来源标签，不是调用方可控请求数据，也不会出现在公开 API/SSE/Web payload 中。
- lease owner、token、expiry、repository revision 及指纹均为私有 fencing 状态。Web 任务中心显示 phase/progress/subjects 与派生 `allowed_actions`，不显示 lease 控制。
- Operation Event 是 0052 的结构化诊断面。不实现或声明通用应用文件日志、异常文本日志、日志文件选择/跟随/下载或独立 Logs 页面。
- 支持包是小型 JSON 聚合，不是 ZIP，也不是宽泛的主机/配置/进程/事件导出。
- 既有 scheduler/supervisor Job 继续作为独立持久事实。Execution 0052 不声明覆盖所有非 API 任务的统一 supervisor、broker 或 Operation stream。
- 订阅 pause/resume 审计与删除继续后移到 0055。后端 retry 端点也未交付；`retryable` 只提供信息，当前 `allowed_actions` 只为合格的活动 Operation 开放安全取消。

## 验证与收尾结果

- 最终 Operation/API 聚焦回归选择通过 78 项测试，只有一项已知 Starlette/httpx 弃用 warning。此前实现阶段的 141 项持久化/migration/CLI、207 项 coordinator/领域、241 项集成及 30 项支持包选择只作为开发检查点保留；这些集合重叠，禁止相加。
- 冻结的完整套件结果为 `2315 passed, 3 skipped, 1 warning in 555.05s (0:09:15)`。三项 skip 均为 Windows 不适用的 POSIX 虚拟环境/权限用例；warning 是同一项既有 Starlette/httpx 弃用。
- 全仓 Ruff 通过；Ruff format 覆盖 662 个文件；strict mypy 对 94 个源文件通过；compileall 通过；`uv build` 成功生成 sdist 与 wheel。
- Web Prettier 通过；Vitest 通过 17 项测试；Svelte/TypeScript 为 0 error、0 warning；adapter-static 生产构建通过。当前 Web 测试覆盖类型化 Operation 状态/reducer/重连/回退，不覆盖真实浏览器路由交互；路由级 interaction/E2E 继续作为后续质量债。
- 两个锁定上游均通过锁定且干净校验；tracked generated/local-output 审计对 733 个文件通过；文档与 `git diff --check` 通过。`.mimosa/`、`.upstream`、数据库、XML 报告、`node_modules`、`web/build`、`.svelte-kit` 与 `dist` 继续排除在提交外。
- 证据口径：除非真实产生操作者证据，否则 Linux 持久性/进程/备份检查、所有真人平台行及真实 Emby/Jellyfin 重扫/播放继续在 Execution 0047 下保持 `NOT_RUN`。

## 提交策略

实现按双语提交拆分为 Web 状态基础、安全 payload、取消边界、任务中心、migration/repository、支持包与 coordinator。API/SSE 集成和本收尾另以中英双语标题/正文提交。禁止暂存上列生成或本地状态路径。
