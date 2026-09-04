[English](goal.md) | **中文**

# 执行 0052 目标

- 状态：已规划；尚未开始实现
- 日期：2026-09-04
- 前驱：`d64b97b`（执行 0051 收尾）
- 范围：持久操作、事件流、协作取消与任务中心可观测性
- 数据库迁移：计划新增 revision `0006_operations_observability`
- 计划提交：包含本记录的提交（不嵌入自身 SHA）

## 结果目标

1. 以持久化 `Operation`、只追加 `OperationEvent` 及有界 operation-subject 关联替换进程内 `_OperationRegistry`。保持账户登录、资产下载、调度 worker、pipeline worker 与 Emby 导出五类既有异步流程兼容，同时让历史跨 API 重启保留。
2. 在 SQLite 多写者和多个 API 进程间强制一套封闭状态机、lease-token fencing、原子活动范围互斥及请求幂等键哈希。失效 owner 必须收敛为 `interrupted` 或关联领域结果，不能永久停在运行态。
3. 提供有界的操作列表、详情和事件 API，以及同源 SSE 流；全局单调事件游标支持按 `Last-Event-ID` 无缺口补发，且不形成重复权威。
4. 新增通用取消请求端点。取消必须协作且如实：登录复用既有 cancellation 信号，有界 worker 在安全 Job 边界停止，不可中断的归档/导出临界区可以成功完成，不能被虚假标成已取消。
5. 将 Jobs 页面升级为持久任务中心，支持操作筛选、进度、允许动作、事件时间线、SSE 重连及有界轮询回退。
6. 将操作事件作为结构化安全日志。仅持久化封闭事件码与白名单标量上下文，并提供第一版经二次脱敏扫描的支持包；其中可含诊断与计数，但不得含请求正文、异常文本、秘密、签名 URL、二维码、lease token 或本地路径。

## 验收边界

- `0006` 可从 `0005` 升级，只新增 Operation、Event、有界 subject 关联及单例 stream-sequence 分配器，能在 SQLite 往返，与 metadata 对齐，并进入可执行的 wheel。
- 每个生成的互斥范围至多有一个活动 Operation。带同一合法 `Idempotency-Key` 的重复请求返回同一持久身份，不同请求不能借用该身份。
- 状态、时间戳、lease 所有权、取消与终态转换均由 compare-and-set 约束；终态不可逆，旧 lease token 不能为新 owner 追加事件或完成操作。
- 每个被接受的状态变化在同一事务追加事件，operation 内 sequence 唯一，全局 `stream_sequence` 严格有序。stream cursor 通过一行事务计数器分配，避免 PostgreSQL sequence 的分配顺序与提交顺序不一致而使 SSE 永久漏掉晚提交事件。
- SSE 首次连接发布 ready/high-water 事实并依赖有界 snapshot API；重连补发有序且有界，遵循 `Last-Event-ID`，对畸形或不可用游标返回固定安全码，且绝不序列化私有运行时状态。
- 重启/协调测试证明有效的其他实例 lease 不被触碰，过期且无 owner 的工作会收敛，关联 Job/LoginSession 的充分持久事实优先。
- API 与 Web 测试覆盖五类既有 Operation、取消竞态、多写者、10,000 事件分页、重连/回退及 secret/path/query/QR 哨兵。
- 离线 Operation、Event 或浏览器测试均不改变平台真人或 Emby/Jellyfin 资格；这些行继续在 Execution 0047 下保持 `NOT_RUN`。

## 明确限制

本执行持久化控制面历史，不持久化可执行 Python callable；进程死亡中断的工作会被协调，而不会自动恢复，除非已有持久 Job 本身拥有恢复语义。硬杀进程、分布式 broker、Redis/Kafka、多主机 HA 与已安装 daemon 不在范围内。完整操作者鉴权和破坏性订阅删除保留在 Execution 0055 的授权与保留策略之后。富内容恢复仍归 0053，媒体服务器控制/资格仍归 0054，最终迁移/发布仍归 0056。
