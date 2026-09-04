[English](goal.md) | **中文**

# 执行 0052 目标

- 状态：已在本地交付并验证；收尾提交与 GitHub 核对将在本记录之后执行
- 日期：2026-09-04
- 前驱：`d64b97b`（执行 0051 收尾）
- 范围：持久操作、事件流、协作取消与任务中心可观测性
- 数据库迁移：已实现 revision `0006_operations_observability`
- 收尾提交：包含本记录的提交（不嵌入自身 SHA）

## 结果目标

1. 以持久化 `Operation`、只追加 `OperationEvent`、有界 operation-subject 关联及事务 stream clock 替换进程内 `_OperationRegistry`。保持账户登录、资产下载、调度 worker、pipeline worker 与 Emby 导出五类异步流程，同时让其控制面历史跨 API 重启保留。
2. 在 SQLite 多写者和多个 API 进程间强制一套封闭状态机、lease-token fencing、原子活动范围互斥及请求幂等键哈希。失效工作必须收敛为 `interrupted` 或无歧义的关联领域终态，不能永久停在运行态。
3. 提供有界的操作列表、详情和事件 API，以及同源 SSE 流。新连接发布 ready/high-water 事实；`Last-Event-ID` 重连严格补发事务已提交全局 cursor 之后的事件，并以固定语义处理畸形、未来及已裁剪 cursor。
4. 提供协作式两阶段取消。请求先记录取消意图，再由当前 fenced owner 在安全边界观察并得出如实终态。登录接收取消信号；scheduler/pipeline worker 在 Job 之间停止；不可中断的归档/导出工作仍可成功完成。
5. 将 Jobs 路由升级为持久任务中心，支持 kind/state/文本筛选、进度、安全结果摘要、subject 关联、事件时间线、取消控制、SSE 重连与有界轮询回退。
6. 将 Operation Event 作为结构化安全诊断面。只持久化封闭事件码和白名单标量上下文，并提供窄化、仅聚合的 JSON 支持包；支持包只含 schema/readiness、实体计数及近期固定错误码计数，返回前必须再次执行泄密扫描。

## 验收边界

- `0006` 可从 `0005` 升级，只创建 `operations`、`operation_events`、`operation_subjects` 与 `operation_event_stream_state`，能在 SQLite 往返，与 metadata 对齐，并进入可执行的 wheel。
- 每个生成的互斥范围至多有一个活动 Operation。带同一合法 `Idempotency-Key` 与指纹的重复请求返回同一持久身份；将其复用于不同请求会失败关闭。只持久化 key 的 SHA-256 摘要与规范请求指纹。
- 状态、时间戳、lease 所有权、取消与终态转换均受 compare-and-set 约束；终态不可逆，旧 lease token 不能为新 owner 追加事件、关联或终态结果。
- 每个被接受的生命周期变化都会追加事件，operation 内 sequence 唯一，全局 `stream_sequence` 在事务内分配。单例计数器保持提交顺序，不依赖数据库 sequence 或墙钟时间。
- 公开 Operation JSON、SSE 与任务中心绝不暴露 `requested_by`、revision、请求指纹、原始幂等键或摘要、lease owner/token/expiry、调用方传入的 worker ID、异常文本、二维码、秘密、签名 URL 或本地路径。
- 启动与有界读取协调保留有效的其他实例 lease，保守协调过期工作，并且仅在无歧义时采用关联 Job/LoginSession 权威事实。两类触发均为非阻塞、单飞后台工作；中断的内存 callable 不会自动恢复。
- 取消使用 repository 的权威 phase snapshot，而不是过期的进程内 phase。五类工作流都会在从可中断段进入不可中断段之前再次检查安全边界；跨 coordinator observer 保证审计顺序为 `requested` → `observed` → `cancelled`。
- 最终聚焦回归选择通过 78 项测试，只有一项已知 Starlette/httpx 弃用 warning。冻结的完整套件结果为 `2315 passed, 3 skipped, 1 warning in 555.05s (0:09:15)`，全套仓库质量、打包、Web、上游与产物门均通过。
- 离线 Operation、Event、API 或浏览器测试均不改变平台真人或 Emby/Jellyfin 资格；这些行继续在 Execution 0047 下保持 `NOT_RUN`。

## 明确限制

本执行持久化 API 控制面历史，不持久化 Python callable，也不把所有既有 supervisor Job 统一改造成 Operation。scheduler supervisor 继续使用既有 Job/RunEvent 权威事实；不声明通用 broker 或 supervisor 到 Operation 的统一事件源。通用文件日志、独立日志文件浏览器、归档下载、系统/进程清单及配置键导出均不属于本支持包。

订阅 pause/resume 审计与破坏性删除继续后移到 Execution 0055 的鉴权权限与保留策略设计。富内容恢复仍归 0053，媒体服务器控制/资格仍归 0054，最终迁移/发布仍归 0056。Jobs 页面真实浏览器路由交互/E2E 覆盖属于后续质量债；当前 Web 证据覆盖类型化状态/reducer、静态检查与生产编译。硬杀进程、分布式 broker、Redis/Kafka、多主机 HA 与已安装 daemon 仍不在范围内。

编辑这份自指收尾记录时，发布 SHA 尚不存在。root 收尾会提交并推送 `main`，随后比较本地 `HEAD`、`origin/main` 与 GitHub `refs/heads/main`；本记录不会虚构未来 SHA。
