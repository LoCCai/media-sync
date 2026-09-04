[English](verification.md) | **中文**

# 执行 0052 验证

- 状态：本地实现与全部冻结收尾门均通过；发布核对将在包含本记录的提交后执行
- 收尾日期：2026-09-05
- 基线：`d64b97b`
- 数据库 migration：`0006_operations_observability`

## 自动化证据

| 检查 | 过程 | 结果 |
| --- | --- | --- |
| 持久化/migration/CLI 聚焦 | Repository、SQLite 多写者、migration 升降级/包及 CLI 选择 | `PASS` — 141 passed |
| Coordinator/领域回归 | Coordinator 加登录/下载/scheduler/pipeline/Emby subject 与取消选择 | `PASS` — 207 passed |
| Operation/API 集成 | Operation payload、repository、coordinator、scheduler、pipeline 与 API/SSE 选择 | `PASS` — 241 passed；一项已知 Starlette/httpx 弃用 warning |
| 支持包 | `uv run --frozen pytest -q -p no:cacheprovider tests/unit/test_support_bundle.py tests/unit/test_api_support_bundle.py` | `PASS` — 30 passed |
| 最终 Operation 回归 | 取消与 cursor 加固后的 Operation repository/coordinator/API/server/support 选择 | `PASS` — 78 passed；一项已知 Starlette/httpx 弃用 warning |
| Web 单元 | 在 `web/` 运行 `pnpm test` | `PASS` — 17 tests |
| Web 格式 | 在 `web/` 运行 `pnpm format:check` | `PASS` |
| Svelte/TypeScript | 在 `web/` 运行 `pnpm check` | `PASS` — 0 errors，0 warnings |
| 静态生产包 | 在 `web/` 运行 `pnpm build` | `PASS` — adapter-static 构建完成 |
| Python 质量 | 全仓 Ruff、Ruff format、strict mypy 与 compileall | `PASS` — 662 个格式化文件；94 个类型化源码文件 |
| 分发包 | `uv build` | `PASS` — sdist 与 wheel |
| 文档 | 双语收尾编辑后运行 `uv run --frozen python scripts/check_docs.py` | `PASS` — 466 个 Markdown 文件 |
| 锁定上游 | `uv run --frozen python scripts/check_upstreams.py` | `PASS` — 2 个锁定且干净的 checkout |
| tracked 产物审计 | 对 `git ls-files` 执行生成/本地状态 denylist | `PASS` — 733 个 tracked 文件，无禁入产物 |
| 仓库空白 | 双语收尾编辑后运行 `git diff --check` | `PASS` |
| Python 完整套件 | `uv run --frozen pytest -q` | `PASS` — 2315 passed, 3 skipped, 1 warning in 555.05s (0:09:15) |
| Git 推送核对 | 推送包含本记录的收尾提交后比较本地 `HEAD`、`origin/main` 与 GitHub `refs/heads/main` | 提交后执行；有意不嵌入自身 SHA |

以上聚焦选择存在重叠，禁止相加。一次冻结前诊断运行得到 2308 passed、3 skipped 和两个 Windows child 超时；两个超时用例随即单独执行并在 3.24 秒内通过。该运行期间 API 仍有修改，因此只有随后冻结的 `2315 passed` 结果具有权威性。最终三项 skip 是既有 Windows 不适用 POSIX launcher/mode 测试，warning 是既有 Starlette/httpx 弃用。

## 需求证据

| 需求 | 已验证证据 |
| --- | --- |
| Migration 与持久历史 | `0006` 测试覆盖升降级、metadata/包对齐及四张 Operation 表；repository/API 测试使用新 session 并让历史跨 coordinator/app 实例保留 |
| 活动范围与请求幂等 | SQLite 并发测试强制一个活动 exclusive key；同摘要/指纹 replay 同一身份，变化的指纹及畸形/重复 header 返回固定错误且不回显 |
| 状态与 lease fencing | Repository/coordinator 测试覆盖合法转换、终态不可逆、ABA/旧 token 拒绝、heartbeat、四事务有界竞争重试及 pending 终态意图重试 |
| 提交有序事件 | 并发 repository 测试覆盖 operation 内/全局 sequence 原子性、事务计数器分配、keyset 分页及 10,000 事件有界路径 |
| 五类工作流接线 | API 与 coordinator 回归覆盖账户登录、资产下载、scheduler run、pipeline run 与 Emby export，包含领域 subject 关联和封闭结果摘要 |
| 如实取消与恢复 | 测试覆盖请求与观察、五类领域交接前的跨 coordinator 持久取消、并发 observer 顺序、有界 shutdown 等待、成功/取消竞态、有效其他实例 lease 保留，以及基于 Job/LoginSession 或 `interrupted` 的保守收敛 |
| 有界公开 API | 列表/详情/事件/取消测试覆盖分页/筛选错误，并证明 revision、指纹、requester、lease 状态、worker 身份及原始幂等数据均不序列化 |
| SSE 重连 | ready 帧携带 `initial_cursor`；覆盖新连接 high-water、严格重连 replay、无效/未来/过期/超过 signed BIGINT 的 cursor、batch 边界、keepalive/disconnect 与跨 session 可见性 |
| 安全支持响应 | Service 与 HTTP 测试验证固定聚合 JSON 形状、16 KiB 上限、规范字节、`application/json`、`no-store`、数据库失败码及输出后二次 secret/path/query/QR/exception 扫描 |
| 任务中心状态 | 17 项 Web 单元覆盖筛选、排序、快照/事件合并、cursor 去重、重连与轮询回退；Svelte check 与生产编译通过 |

## 残余与后移证据

- 当前 Web 单元没有在浏览器中挂载并交互真实 Jobs 路由。路由 interaction/E2E 覆盖属于后续质量债，不能静默视为通过。
- 任务中心按设计不展示内部 requester、lease、revision 或 idempotency/fingerprint 状态，也不提供 retry 端点或订阅 pause/resume/delete 审计。
- Operation Event 不是通用文件日志子系统，支持端点也不是 ZIP 或宽泛环境导出。既有 supervisor Job 不声明已统一为 API Operation。
- API lifespan 在 Operation 数据库暂不可用时允许 health 启动；Operation 读取与提交随后返回固定安全可用性错误码。这是可用性行为，不代表任务执行成功。

## 证据口径

这些聚焦门未使用真人浏览器账户、作者端点、平台 API/CDN、下载的作者媒体、Linux 持久性/备份/进程演练或 Emby/Jellyfin 服务。所有此类行继续在 Execution 0047 下保持 `NOT_RUN`。离线测试、本地静态构建或支持包响应均不会改变真人资格。
