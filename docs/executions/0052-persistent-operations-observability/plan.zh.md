[English](plan.md) | **中文**

# 执行 0052 计划

- 状态：进行中
- 计划日期：2026-09-04
- 基线：`d64b97b`
- 计划数据库 revision：`0006_operations_observability`
- 计划提交：包含本记录的提交（不嵌入自身 SHA）

## 基线决策

执行 0051 已消除账户/订阅校验歧义，但按计划保留进程内 Operation 与轮询。下一个可独立交付的控制面切片是持久操作所有权与观测。执行 0047 仍是 P0 Linux/真人门；0052 与其并行推进，但不会把任何未执行的操作者行改成通过。

这里明确校正一项边界：0051 收尾将订阅删除归入 0052，但硬删除需要已认证的操作者权限及保留/cascade 策略。因此 0052 会记录 pause/resume 与操作审计事实，而破坏性删除保留到 0055。该收窄减少权限，不改变原始七平台订阅与 Emby 总目标。

## 交付顺序

1. 记录干净基线，盘点五类进程内操作流程，冻结安全 operation kind、错误码、事件码与版本化公开 payload。
2. 新增 `0006` migration，创建 `operations`、`operation_events`、有界 `operation_subjects` 关联与单例 `operation_event_stream_state` 计数器。每个可选幂等键哈希旁保存规范请求指纹，防止复用 key 授权不同请求。在事件事务内锁定并更新计数器行以分配 `stream_sequence`，因为 PostgreSQL sequence 值不代表提交顺序。活动互斥范围与 `(kind, idempotency_key_hash)` 使用部分唯一索引；状态、时间戳、进度、subject 与 lease 形状受约束。
3. 新增类型化持久化/application service，支持原子 create-or-replay、claim/start、heartbeat、进度、事件追加、取消请求、成功/失败/取消收尾、列表/详情分页和过期 lease 协调。所有变更均使用 expected state/revision 与 lease-token fencing。
4. 按 operation kind 新增封闭的 result summary 与 event context 投影器。未知 key 或不安全值在持久化前失败关闭；通用脱敏仅作为纵深防御。
5. 在 API 中替换 `_OperationRegistry`。五类异步 POST 支持 `Idempotency-Key`，返回 replay/conflict 事实但不泄露内部 key；后台 owner 持续 heartbeat，领域 Job/LoginSession 仍为权威。Job worker owner 由 Operation UUID 生成；请求中的 `worker_id` 仅作为弃用兼容输入保留，绝不用于持久所有权或日志上下文。
6. 新增 `GET /api/v1/operations`、精确详情和分页事件接口、`POST /api/v1/operations/{id}/cancel` 及 `GET /api/v1/operations/events` SSE。首次连接先发布 ready/high-water 并由客户端读取有界 snapshot；重连严格补发全局 cursor 之后的事件再 tail。限制 batch、keepalive、连接时长和输入尺寸，并轮询数据库以接收其他 API 进程的事件。
7. 接入协作取消：账户登录直接传递信号；有界 scheduler/pipeline worker 在下一项前停止；资产/Emby 工作在安全边界观察。完成与取消竞态以持久领域事实而不是到达先后决定。
8. 在应用启动和有界读取时协调过期 Operation。有效的其他实例 lease 不受影响；存在无歧义的 Job/LoginSession 证据时派生终态，否则记录 `interrupted`；绝不自动恢复内存 callable。
9. 将 Jobs 页面升级为任务中心，增加类型化事件流、筛选、详情时间线、进度、允许动作、取消控制，并在 SSE 不可用时使用有界轮询回退。
10. 新增安全支持包端点或命令，仅由白名单项目/构建/schema/readiness/计数/近期错误码投影组成，并在返回字节前强制执行第二遍禁值扫描。
11. 运行聚焦并发/状态/migration/SSE/API/Web/安全测试，再运行 Ruff/format/strict mypy/compileall/build、文档/上游/仓库审计与完整 Python 套件。除非得到真实操作者证据，Linux/真人/媒体服务器行一律记录为 `NOT_RUN`。
12. 更新双语 progress、verification、status、roadmap 与执行索引；以中英双语标题/正文提交实现和收尾，推送 `main`，并核对本地与 GitHub SHA。

## 设计约束

- Operation、Job、SyncRun 与 LoginSession 是不同事实。Operation 表示操作者请求；有界 `operation_subjects` 与事件 subject 可关联多个持久身份，不能假装单个 Job 就代表整个有界 worker 调用，也不能把关联藏入 result JSON。
- 只保存合法 `Idempotency-Key` 的 SHA-256 摘要，并用规范请求指纹证明 replay 具有相同 method、route、target 与规范化 body，而不保留 body 本身。exclusive key 由服务端按封闭 kind/UUID 映射生成，不接受请求正文传入。
- `retryable` 与 `allowed_actions` 从状态和固定错误分类派生，不形成可独立写入的双重事实。
- 取消请求不是终态转换；只有当前 fenced owner 或重启协调器才能在工作抵达安全边界后发布最终状态。
- SSE cursor 使用事务分配的全局 `stream_sequence`；operation 内 sequence 与任意 row identity 是独立不变量。禁止以自增/sequence 主键或墙钟时间作为重连 cursor。
- event/result JSON 必须小、浅且白名单化。通用字典、请求正文或异常字符串不得跨越持久化边界。
- SQLite 仍是默认单主机数据库。DDL 保持 PostgreSQL 兼容，但不声明多主机 HA 或外部消息 broker。

## 验证计划

- 持久化：metadata/DDL 对齐、migration 升降级/wheel、约束/索引/FK、并发写者下全局 cursor 与提交顺序一致，以及 10,000 事件 keyset 分页。
- 并发：SQLite 多连接活动互斥、幂等 replay/conflict、事件 sequence 分配、cancel-versus-finish 与 lease-token ABA/fencing。
- 恢复：有效其他实例 lease 保留、过期 Operation 收敛及 Job/LoginSession 权威终态映射。
- API/SSE：五类流程兼容、列表/详情/筛选分页、精确取消语义、补发/tail/重连/keepalive/disconnect 与固定无效 cursor 错误。
- 安全：在数据库、JSON、SSE、UI 和支持包字节中扫描凭据、签名 query、二维码、异常文本、路径、owner ID、lease token 与原始幂等键哨兵。
- 前端：类型检查、状态 reducer、SSE 重连与轮询回退、筛选、时间线、进度和动作门禁。

## 提交策略

实现前先提交本双语 goal/plan/baseline。优先将 migration/repository、API/runtime、Web 任务中心及最终文档拆成独立双语提交。禁止暂存 `.mimosa/`、`.upstream`、本地数据库、含哨兵的支持包 fixture、JUnit XML、`node_modules`、`web/build`、`.svelte-kit` 或分发产物。
