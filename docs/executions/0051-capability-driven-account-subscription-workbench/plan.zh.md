[English](plan.md) | **中文**

# 执行 0051 计划

- 状态：进行中
- 计划日期：2026-09-04
- 基线：`38e0ebe`
- 数据库迁移：无
- 计划提交：包含本记录的提交（不嵌入自身 SHA）

## 基线决策

Execution 0047 仍是 P0 发布门，但其剩余 Linux 持久性/备份/进程检查和全部真人账户/媒体服务器证据需要操作者基础设施与凭据。本 Windows 编写工作站不会模拟这些证据，它们继续保持开启。Execution 0051 是下一项可独立交付的 P1 切片。

原 0051 设计还提到 SSE、持久登录 Operation 历史和审计事件，但其存储/事件基础被分配给 0052。因此本执行会闭环账户/订阅正确性与工作台，不会暗中提前吞并 0052；延期边界会在目标和收尾中继续明确。

## 交付顺序

1. 恢复锁定的前端依赖图，并运行变更前 Python/Web 基线。
2. 新增类型化 MediaCrawler 平台能力模块和脱敏安全的 `/api/v1/platform-capabilities` 投影，以契约测试完整覆盖七个平台。
3. 新增账户与订阅草稿共用的 application workbench service；让 CLI/API 同时使用它，规范化支持的作者输入，在写入前强制平台特定的全历史确认，并只返回安全摘要。
4. 新增账户登录预检 evaluator 与端点。在分配 Operation 前由登录启动原子复用，并把强制登录检查和无关的下载/导出工具区分开。
5. 新增精确 LoginSession QR 端点；账户兼容端点必须先解析并证明当前 session，才能返回任何图片。前端轮询拿到 session 身份后切换到精确端点。
6. 用能力、组合状态与登录预检面板升级账户 UI；把订阅创建升级为能力驱动的三步向导，并以安全 policy/checkpoint 摘要扩充详情。
7. 增加后端单元/API/CLI 集成测试和前端状态/格式测试，覆盖拒绝零写入、并发、生命周期与 secret 哨兵。
8. 运行专项测试、前端格式/类型/测试/构建、Ruff/format/mypy/compileall/package/docs/upstream 门及完整 Python 套件。没有真实证据时，平台/Docker/真人行继续记为 `NOT_RUN`。
9. 更新双语 progress、verification、status、roadmap 与执行索引；创建双语实现/收尾提交，推送 `main` 并核对本地/远端 SHA。

## 设计约束

- FastAPI 保持浏览器唯一业务入口；前端不直接打开 SQLite，也不直接读取运行时文件。
- Capability 元数据固定、有界、有版本且由后端拥有，不得携带 Cookie、token、签名 URL 或路径。
- 草稿校验必须先于持久化完成。事务回滚只是纵深防御，不是主要校验手段。
- 既有 schema 和 migration 数量不变；本切片读取现有 `Account`、`LoginSession`、`Subscription`、`SyncRun` 与 scheduler 记录。
- 账户级 QR 路由保持兼容，但特定尝试只有 session 级路由具有权威性。
- 没有 SSE 时通过有界轮询保持 UI 可用；0052 前不宣称持久化/重连语义。

## 验证计划

- Python 专项：新增 workbench/capability/preflight 单元、API 契约、CLI workflow、authentication/login repository 和 scheduler 兼容测试。
- 前端：冻结 pnpm 安装、Prettier、`svelte-check`、Vitest 和 adapter-static 生产构建。
- 静态/打包：Ruff、Ruff format、strict mypy、compileall 和 `uv build`。
- 仓库：双语文档检查器、上游锁验证、锁定 checkout 干净性、禁止产物审计和 `git diff --check`。
- 完整套件：运行 Windows 全量并如实报告精确结果，包括已知 completion-receipt/进程族是否复现；Linux 阶段 B 保持权威。

## 提交策略

实现前提交双语目标/计划与初始基线记录。专项门通过后，以双语标题和正文提交实现/测试；适合时另交 progress/verification/status 收尾，再推送 `main` 并比较 `HEAD`、`origin/main` 与 GitHub 广告 ref。绝不暂存 `.mimosa/`、生成的前端产物、`node_modules`、本地数据库、原始 junit XML 或两个锁定上游 checkout。
