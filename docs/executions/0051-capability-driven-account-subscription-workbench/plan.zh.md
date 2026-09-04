[English](plan.md) | **中文**

# 执行 0051 计划

- 状态：离线工作台范围已执行并验证
- 计划日期：2026-09-04
- 基线：`38e0ebe`
- 数据库迁移：无
- 实现提交：后端 `6ed7ab3`；Web `178e557`
- 收尾提交：包含最终记录的提交（不嵌入自身 SHA）

## 基线决策

Execution 0047 仍是 P0 发布门，但其剩余 Linux 持久性/备份/进程检查和全部真人账户/媒体服务器证据需要操作者基础设施与凭据。本 Windows 编写工作站未模拟这些证据。因此 Execution 0051 交付可独立测试的 P1 账户/订阅工作台，不宣称任何真人资格。

原后续设计还提到 SSE、持久登录 Operation 历史和审计事件。其存储与跨进程协调基础归 0052，所以本执行保留有界轮询和进程内 Operation，同时闭环 capability、草稿、预检、QR 所有权和 UI 切片。

## 已执行顺序

1. 恢复锁定的前端依赖图，并保留已记录的变更前 Python/仓库基线。
2. 新增类型化 MediaCrawler v1 能力模块和 `GET /api/v1/platform-capabilities`，以闭合字段和完整七平台测试覆盖。
3. 新增账户/订阅共用 application workbench，负责校验、预览、幂等创建、固定错误和脱敏安全结果投影；CLI 与 REST 均已接入。
4. 集中保守的 MediaCrawler 作者 ID 规范化，只允许 XHS 使用作者 secret reference，并在变更前强制四个已审计平台的全历史确认。
5. 新增 `GET /api/v1/accounts/{account_id}/login-preflight`；登录启动在分配进程内 Operation 前运行同一 evaluator，并排除无关下载/导出工具。
6. 新增 `GET /api/v1/login-sessions/{login_session_id}/qr.png`，加固旧图片清理，并让账户兼容路由解析到精确 session 路径。
7. Accounts 以服务端能力、组合状态、预检事实和 session 绑定 QR 轮询升级；Subscriptions 以账户选择、作者/策略输入、服务端预览/确认阶段和安全详情摘要升级。
8. 增加后端 capability/workbench/preflight/API/CLI/login 契约与前端工作台状态测试，覆盖并发收敛、拒绝零写入以及 secret/路径/cursor 哨兵。
9. 运行 Python 全量、Web、静态、打包、文档和上游锁门，并保持全部真人账户/媒体服务器行不变。

## 设计约束

- FastAPI 保持浏览器唯一业务入口；Svelte 前端不直接打开 SQLite，也不直接读取运行时文件。
- Capability 元数据固定、有界、有版本且由后端拥有，不携带凭据值、作者权限、签名 URL 或本地路径。
- 校验先于持久化。SQLite immediate-writer reservation 是本地幂等/并发机制，不是 schema 变更，也不宣称分布式锁。
- QR 字节保持为短生命周期的账户运行时材料。返回前必须证明精确 QR session 所有权与活动状态，执行有界同文件读取并在读取后复查持久状态。
- 既有 `/api/v1` 账户 QR 行为保持兼容，但特定尝试以精确 session 身份为权威。
- 无 SSE 时通过有界轮询保持 UI 可用；0051 不宣称持久重连/历史语义。

## 已记录偏差

预检与登录启动共用一个 evaluator，但通过的预检结果只是快照。它向进程内 Operation registry 和后台 application service 的转换在多个 API 进程间并不原子。随后的持久 LoginSession compare-and-set 与账户 OS 锁会安全拒绝落败者，因此不阻塞 0051 离线边界。消除短暂的落败 Operation，并提供跨进程幂等操作所有权，需要 0052 规划的持久 Operation/Event 基础。

## 验证结果

- Python 完整套件：`2135 passed, 3 skipped`。
- Web：Prettier、`svelte-check`、七项 Vitest 和 adapter-static 生产构建全部通过。
- 静态/打包：Ruff、Ruff format、90 个源码文件 strict mypy、compileall 和 `uv build` 全部通过。
- 仓库：双语文档及两个锁定上游的 SHA/remote/干净 checkout 门通过；`.upstream` 与 `.mimosa/` 保持未触碰。
- 真人：未使用浏览器真人账户、作者端点、CDN 字节或 Emby/Jellyfin 服务器；全部对应行仍在 0047 下保持 `NOT_RUN`。

## 提交策略

原目标/计划基线保持为首个双语 checkpoint。后端实现/测试已提交为 `6ed7ab3`，Web 实现/测试已提交为 `178e557`；本收尾以双语标题和正文单独提交。生成的前端输出、`node_modules`、本地数据库、原始 junit XML、`.mimosa/` 和两个锁定上游 checkout 均不进入提交。只有收尾提交存在后才推送并核对本地/远端 SHA。
