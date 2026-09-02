[English](progress.md) | **中文**

# 执行 0007 推进结果

- 状态：离线范围已实现；验收仍为 `PARTIAL`
- 开始时间：2026-08-30 12:45 +08:00
- 实现：已实现
- 验证：最终自动门禁通过；AC6/AC13 仍为 `PARTIAL`
- 前置执行：Execution 0006 implementation commit `674e510`
- 网络与账户边界：仅离线夹具与仓库自有本地辅助进程

## 已交付实现

- 封闭 MediaCrawler 订阅 policy v1 现只持久化 `schema_version`、可选 `creator_input.secret_ref`、显式 `allow_full_history`、最大为 300 的正数 `request_delay_seconds`，以及 `headless`。许可证确认仍是独立、显式且默认关闭的 worker 授权。原始 Cookie 与签名作者输入不持久化。
- 新产物为 manifest v3 与完成回执 v2。已密封 legacy manifest v2/receipt v1 证据继续通过共享归一化/手工导入实现严格双读、逐字节精确且只读；绝不重新密封或改写。定时重启恢复只信任 v3。
- 重试复用持久 scheduler Job UUID，同时派生唯一 attempt UUID 与受限执行根。旧 attempt 在 cancel/reclaim/ABA 后不能密封、导入、推进 checkpoint 或删除后继根。
- Bridge 准备、checkout/runtime 探测、密钥解析、子进程等待、回执验证与输出归一化均移出事件循环。父进程保留 heartbeat/lease 权限，且进程等待不跨越 SQLite 事务。
- 进程监督现已提供协作取消、进程树终止/join、单向父进程 liveness/control channel、Windows attach/start handshake，以及账户/profile 锁。子进程绝不会获得数据库 URL、worker 身份、lease token 或续租权限。
- 每个 SyncRun 创建/attach/状态变更及每个导入/checkpoint 事务都会先在同一事务应用精确 owner/token/未过期 guard。所有权丢失前已提交批次可以保留，之后的批次不得提交。
- 清理严格收敛为四种状态：`ABSENT`、`REMOVED`、`QUARANTINED` 或 `UNRESOLVED`。`.quarantine` 是操作员控制根目录下明确受限、可能携带凭据的边界；POSIX 上收紧为 `0700`，其他系统预期使用等效受限 ACL，并从零密钥声明中排除。`UNRESOLVED` 会创建固定/脱敏的账户 block，并阻止密钥解析、run attach、准备与 spawn。即使自定义 runtime 位于仓库内，`.quarantine/`、`.cleanup-security-v1/` 与账户 profile 路径也会被 Git 忽略；但 ignore 规则不是访问控制边界。
- 有界 CLI registry 默认保持 fail closed。MediaCrawler 执行必须同时提供 `--enable-mediacrawler` 与逐次运行的 `--accept-mediacrawler-license`；缺少许可证授权及不支持的定时 challenge 会进入保守 waiting 状态且不启动子进程。
- 标准 `uv run pytest` 最初因新 contract helper 需要包导入而在 collection 阶段失败；新增 `tests/__init__.py` 与 `tests/contract/__init__.py` 后关闭了该仓库内 collection 缺陷，同一专项模块命令随后通过。

本执行不需要新增关系型 schema revision；迁移工作是产物协议 v3/v2 writer 与不可变 v2/v1 reader 边界。

## 验收状态

| AC | 范围 | 状态 | 证据与剩余边界 |
| ---: | --- | --- | --- |
| 1 | 封闭策略与授权 | `PASS` | 严格 v1 字段/边界、可选不透明作者 ref、独立且默认关闭的许可证授权 |
| 2 | Manifest v3/回执 v2 | `PASS` | 新 writer 同时绑定持久 Job 与 attempt-specific 身份 |
| 3 | Legacy v2/v1 兼容 | `PASS` | 共享归一化/手工导入逐字节精确且只读；定时恢复拒绝 legacy |
| 4 | 重试与 attempt 隔离 | `PASS` | 复用持久 Job UUID；attempt UUID/根唯一；旧根受 fencing |
| 5 | 移出事件循环与 heartbeat | `PASS` | 真实长运行本地 child 加并发 heartbeat 与独立 SQLite writer |
| 6 | 确定性取消 barrier | `PARTIAL` | spawn 前/运行中取消、lease fencing、重复 runner 取消及真实批次间 guard barrier 均通过；两条重复取消路径均证明先 join 再 unwind，第二批被 fencing，已提交首批保留。仍缺少 child 退出后/seal 前及 seal 后/导入前的确定性 barrier。 |
| 7 | 父死亡与 profile 排他 | `PASS` | 使用本地 helper 验证 liveness/control handshake、整树硬停止及账户/profile 锁 |
| 8 | 精确所有权 fencing | `PASS` | 每个 SyncRun 与导入/checkpoint 事务前均执行精确 owner/token/未过期 guard |
| 9 | 锁定上游配置 | `PASS` | 忠实 `parse_cmd()` 形状保留 Cookie，并设置 `CRAWLER_MAX_SLEEP_SEC` 与 `MAX_CONCURRENCY_NUM=1`；不宣称逐请求间隔 |
| 10 | 封闭状态映射 | `PASS` | 固定映射如左；取消/lease 丢失传播 fencing |
| 11 | Waiting 恢复 | `PASS` | 许可证/challenge 使用 `waiting_user`；缺失/不可用认证使用 `waiting_auth`；必须显式 resume |
| 12 | 七平台离线协议 | `PASS` | 七个平台均通过真实本地 fake-child 重试/重启/重放链 |
| 13 | 完整失败密钥落点矩阵 | `PARTIAL` | 清理、脱敏与哨兵覆盖较充分，但完整“失败类型 × 保留文件系统/SQLite/运维落点”交叉矩阵尚不完整 |
| 14 | 显式脱敏 CLI | `PASS` | 启用与许可证是独立开关；输出省略 payload、ref、locator、lease 材料与根目录 |
| 15 | 最终质量门禁 | `PASS` | 最终全量：819 项通过、1 项 Windows 边界 skip、分支感知覆盖率 79%；专项：320 项通过、1 项跳过。构建/打包/文档/上游/补丁/运行产物及安全留存哨兵也通过；准确证据见 `verification.md`。 |

## 七平台离线证据

七个平台标识均通过同一真实本地协议链：

`subscribe → tick → manifest-v3 write/load → local fake child writes versioned JSONL → receipt-v2 write/read → guarded ingestion → retry/restart → idempotent replay`

这只是离线协议证据，不证明二维码/Cookie/保存会话真人登录、真实作者流量、真实 CDN 获取、真实 Emby/Jellyfin 扫描/播放，也不证明上游分页有界。

## 最终自动化证据

- 修复后的最终代码树通过 819 项测试，另有 1 项仅 Windows 的 POSIX mode skip，耗时 212.99 秒，分支感知覆盖率 79%；执行 0007 专项通过 320 项，仍是同一项 skip，耗时 128.64 秒。
- 安全留存产物门禁在 `.media-sync/verification/0007-closeout-sentinel-root` 下通过 29 个精确 case，耗时 40.90 秒；8 个生成密钥/签名 query 哨兵均零匹配，21 个 SQLite 数据库逻辑上不存在 Job 租约权限，19 个 pytest `current` 别名均证明指向留存根内同父真实目录；共保留 279 个文件、364 个目录、5,958,937 字节且均被忽略，供后续审计。
- 依赖锁、Ruff、格式、严格源码 mypy、构建、随包迁移、文档链接、两个上游锁定、补丁空白、自定义运行根 ignore 与运行产物未跟踪检查均通过；准确命令及故意排除的留存负向测试记录在 `verification.md`。

## 如实延期

- 定时 backfill、签名 locator 刷新、真实 CDN 获取及自动 sync → download → export 规划不属于执行 0007。
- `CRAWLER_MAX_SLEEP_SEC` 与 `MAX_CONCURRENCY_NUM=1` 是已证明的配置边界，不是逐 HTTP 请求间隔证据；代理/验证码/平台保护绕过仍被排除。
- REST、常驻守护、Docker/生产打包、分布式 HA/PostgreSQL 与真人 Emby/Jellyfin 运维仍属于后续工作。
