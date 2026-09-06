[English](plan.md) | **中文**

# 计划

## 1. 冻结权威范围

- 把 `run-now` 明确保留为调度控制兼容路由，并在 UI 改成更准确的文案。
- 新增独立的精确交付路由和 Operation kind；使用逐订阅 exclusive key，并用 expected schedule revision、MediaCrawler 启用/许可证开关及有界 lease 参数构成封闭请求身份。
- 明确下游当前选择范围为 `author_active_snapshot`，不声称只处理本轮新发现行。

## 2. 数据库与持久契约

- 新增 migration `0013_exact_subscription_delivery`：用新封闭集合替换数据库 Operation-kind check，并创建 `(subscription_id, feed)` 唯一扫描进度表。
- SQLite batch 重建和 PostgreSQL constraint 替换必须保留全部 Operation、event 与 subject；若存在新 kind Operation 或扫描进度历史，downgrade 必须拒绝。
- 为 `subscription-delivery` 增加封闭 payload/result schema、target 映射、路由、摘要、诊断及支持包计数。

## 3. 精确 scheduler 与 pipeline 所有权

- 把当前物化/认领谓词重构为共享 helper，再增加具备相同 lease、容量、lane 与 reconciliation 规则的精确 ID 变体。
- 只物化一个已启用、未删除的订阅，且不改变其周期调度语义；遇到既有当前周期时复用或冲突，不能重复入队。
- 两个 worker 新增精确入口，并复用现有 start、heartbeat、handler 与 finalize 实现。
- pipeline coordinator 只能从精确成功 sync Job 及其 attached succeeded Run 解析，再只认领该 Job，不能扫描到另一队列行。

## 4. 强类型执行回执

- 新增应用编排器，逐阶段推进，并在身份产生后立即关联持久 subjects。
- 让脱敏 pipeline 回执穿过 handler/worker 边界，不再丢弃 `SubscriptionPipelineOutcome`。
- 成功前重新读取精确 Job/Run/export 状态；busy、drift、发现失败、coordinator 缺失、pipeline 失败和目录验证失败使用固定错误码。
- 按 adapter 命名发现计数语义；未支持的更新行数保持空值。归档 disposition 与受管文件数不能称为网络下载数或内容数。

## 5. 扫描进度证据

- B 站投稿/动态 coverage 更新必须与 ingestion、checkpoint CAS 和 Run 成功在同一事务提交。
- 只持久化固定 feed/state/stop-reason、有界计数、upstream/contract generation 与精确 source-end Run 身份；新表不得复制 opaque source cursor，API/UI 也不得暴露。
- 把进度投影加入订阅详情；本执行中全部非 B 站内容流保持 `unproven`。

## 6. API 与 Web 工作流

- 新增精确 execute 请求/响应、202 Operation 跟踪及固定冲突响应。
- 在订阅工作台增加显式确认与阶段显示，链接精确 Operation、Jobs 与日志过滤。
- 保留 response generation/abort 防护，避免过期响应替换当前选中订阅状态。

## 7. Windows 目录 pin

- 只在 exporter 的目录 opener 中把零 DesiredAccess 改为具名常量 `FILE_LIST_DIRECTORY = 0x0001`。保留 `FILE_SHARE_READ | FILE_SHARE_WRITE`、不共享 `FILE_SHARE_DELETE`，并保留 reparse/open-directory flags。
- 增加真实 Windows 祖先 rename 回归以及非 Windows/静态契约覆盖。

## 8. 验证与发布

- 各层先跑专项测试，再跑 Python unit/integration/contract、Web test/typecheck/lint/build、API→TypeScript 契约、打包 migration/源码一致性及 secret/path 扫描。
- 在 `verification(.zh).md` 记录精确命令、数量、skip、失败与修复；更新 progress、status、roadmap 及部署说明。
- 实现与收尾分别使用中英双语提交说明并推送 `main`。不会自动部署、恢复 supervisor、发起真人登录或启动生产下载。

