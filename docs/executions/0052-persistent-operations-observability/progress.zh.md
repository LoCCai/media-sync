[English](progress.md) | **中文**

# 执行 0052 推进结果

- 状态：已在本地交付并验证；收尾提交与 GitHub 核对将在本记录之后执行
- 收尾日期：2026-09-05
- 基线：`d64b97b`
- 数据库 migration：`0006_operations_observability`

## 已交付

1. 新增 `operations`、`operation_events`、`operation_subjects` 与 `operation_event_stream_state` 四张持久表，包含受约束生命周期形状、活动范围/幂等唯一性、subject 索引及事务更新的单例 stream cursor。
2. 新增持久 repository 状态机：原子 create-or-replay、claim、heartbeat、进度、subject/event 追加、两阶段取消、不可逆终态、lease-token fencing、有界列表/事件 keyset 分页、stream 边界与保守过期工作协调。
3. 为 `account-login`、`asset-download`、`scheduler-run`、`pipeline-run` 与 `emby-export` 新增封闭请求身份、结果摘要和事件上下文契约。payload 大小/深度/数量边界及禁值检查在持久化前失败关闭。
4. 新增 `OperationCoordinator` 并接通五类工作流。create/replay 与 claim 在 callable 启动前原子提交；worker 身份由服务端派生；heartbeat 与取消监控有界；subject hook 关联持久领域实体；pending 终态意图可在瞬时 SQLite 写竞争后由 monitor 重试。phase 边界发现持久取消时会同步记录观察；若已有 observer，则等待首个 observer 提交后才允许终态 CAS。
5. 修复独立复跑发现的 SQLite WAL deferred-read-to-write `BUSY_SNAPSHOT` 竞态。权威读取现先取得 `BEGIN IMMEDIATE`，最多使用四个新事务重试。shutdown 在取消观察前建立统一 deadline，对已有 observer 的等待使用剩余时间，并在 deadline 到达时停止 monitor 工作。
6. 以持久提交替换 API 进程内 Operation 响应。严格 `Idempotency-Key` 校验支持安全 replay/conflict；私密 reference 只以领域隔离摘要进入指纹；请求 `worker_id` 仅保留为弃用兼容输入，不用于所有权或输出。
7. 新增 `GET /api/v1/operations`、`GET /api/v1/operations/{id}`、单 Operation 事件、`POST .../{id}/cancel` 与全局 `GET /api/v1/operations/events` SSE。协调以非阻塞、单飞后台工作触发。新连接 ready 帧以捕获的 high-water 作为 `initial_cursor`；重连在补发已提交事件前保留调用方 cursor。畸形、未来、已裁剪及超过 signed BIGINT 的 cursor 均以固定码失败；轮询、batch、keepalive 与连接时长均有界。
8. 将 Jobs 路由升级为持久任务中心，包含 Operation 摘要/详情、筛选、进度、安全结果/上下文展示、subject 关联、事件时间线、取消、EventSource 更新与有界轮询回退。
9. 新增 16 KiB、仅聚合的支持包 service 与 `GET /api/v1/support-bundle`。它以 `no-store` 返回规范 JSON，只包含固定 revision/readiness/count 投影，输出字节再次执行泄密扫描，数据库失败映射为固定安全码。
10. 保持领域权威：Operation 不替代 Job、SyncRun 或 LoginSession。登录、资产下载、scheduler、pipeline 与 Emby 导出都会在进入不可中断领域调用前同时检查权威 phase snapshot 与本地信号。scheduler/pipeline 会在领取下一 Job 前停止；归档/导出一旦跨过交接点，领域成功仍如实优先。

## 最终验证

- 持久化/migration/CLI 聚焦门：141 passed。
- coordinator 与相关领域回归门：207 passed。
- Operation payload/repository/coordinator/scheduler/pipeline/API 集成门：241 passed，另有一项已知 Starlette/httpx 弃用 warning。
- 支持包 service 与 HTTP 契约：30 passed。
- 最终 Operation repository/coordinator/API 回归选择：78 passed，另有一项已知 Starlette/httpx 弃用 warning。
- 冻结的 Python 完整套件：`2315 passed, 3 skipped, 1 warning in 555.05s (0:09:15)`。三项 skip 是 Windows 不适用的 POSIX launcher/mode 用例；warning 是既有 Starlette/httpx 弃用。
- Python 全仓门：Ruff 通过；Ruff format 检查 662 个文件；strict mypy 检查 94 个源码文件通过；compileall 通过；`uv build` 产出 sdist 与 wheel。
- Web：Prettier 通过；17 项 Vitest 通过；Svelte/TypeScript 为 0 error、0 warning；adapter-static 生产构建通过。
- 仓库：两个锁定上游 checkout 通过；733 个 tracked 文件的生成/本地状态审计通过；`scripts/check_docs.py` 对 466 个 Markdown 文件通过；`git diff --check` 与本机绝对路径扫描通过。

以上聚焦选择存在重叠，禁止相加。一次冻结前诊断运行得到 2308 passed、3 skipped 及两个 Windows child 15 秒超时；两个超时用例随即单独运行并在 3.24 秒内通过。由于该运行期间 API 仍有修改，它只作为诊断记录。上方结果是全部修复后重新执行的冻结权威运行。

## 发布交接

- 提交 API/SSE/支持包 HTTP 接线与本双语收尾，且不暂存 `.mimosa/` 或任何生成/本地状态输出。
- 推送 `main`，再证明本地 `HEAD`、`origin/main` 与 GitHub `refs/heads/main` 解析为同一 SHA；包含本记录的收尾提交有意不嵌入自身 SHA。
- 在后续质量切片增加任务中心页面的真实浏览器路由交互/E2E。当前 17 项 Web 测试覆盖 Operation 工具/状态/重连/回退，不覆盖实际路由交互。

## 后移范围与外部门

通用文件日志、独立日志浏览器、ZIP 或宽泛主机/配置/进程支持包、统一 supervisor-to-Operation 事件源、后端 retry，以及订阅 pause/resume/delete 审计均未交付。pause/resume/delete 继续置于 Execution 0055 鉴权与保留策略之后。

Execution 0047 仍是 P0。Linux 持久性/备份/进程证据、Bilibili/XHS 金丝雀、其他真人平台及真实 Emby/Jellyfin 重扫/播放继续保持 `NOT_RUN`；0052 的任何离线结果均不能替代这些操作者检查。
