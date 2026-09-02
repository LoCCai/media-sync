[English](goal.md) | **中文**

# 执行 0007 目标

- 状态：离线范围已实现；验收仍为 `PARTIAL`
- 开始时间：2026-08-30 12:45 +08:00
- 前置执行：Execution 0006 implementation commit `674e510`
- 网络边界：仅离线夹具与本地辅助进程

## 2026-08-30 修订

下方验收标准 13 原文保留，作为已提交计划基线。实现复核证明：在“scrub 被拒绝”的故意负向场景中，若不丢失安全证据或作虚假声明，就无法满足其“整个运行树零密钥”措辞。因此验收契约修订为：正常 active attempt 根必须删除；若原子隔离成功但 no-follow 清理失败，不安全证据只能保留在已忽略的 `.quarantine` 下；若既不能证明删除，也不能证明隔离，handler 必须对账户执行硬 fencing，并在 attempt 根之外只写持久、脱敏的账户/事件标记。账户 browser profile 以及故意保留的 quarantine/unresolved 证据，均属于专用、由操作员控制的根目录及祖先下可能携带凭据的边界。安全产物扫描覆盖 SQLite、成功及正常清理后的 attempt 树、投影和运维输出，并必须逐项列出排除的故意留存负向场景；任何 quarantine 路径或原始清理异常都不得进入运维输出。对于验收标准 3，legacy manifest-v2/receipt-v1 的恢复仅指严格的共享归一化/手工导入读取兼容；它绝不建立 scheduler 所有权，定时重启/reclaim 只接受 manifest v3。

## 结果目标

交付一个显式启用、受许可证约束且经过离线证明的锁定版 MediaCrawler `sync.subscription` handler。它必须隔离每次重试 attempt，把 scheduler 续租权限只留在可信父进程，在取消或父进程死亡时终止完整子进程树，并对每次 SyncRun/checkpoint/content 变更执行 fencing，且不在运维表面暴露凭据、本地根目录或租约权限。

## 验收标准

1. 封闭订阅策略 v1 只保存 `schema_version`、可选不透明作者 `secret_ref`、显式 `allow_full_history`、有界正数 `request_delay_seconds` 与 `headless`。许可证确认是默认关闭的运维授权，并连同锁定许可证身份绑定到每个新 manifest；不得持久化原始 Cookie 或签名作者 URL。
2. Manifest v3 与完成回执 v2 绑定锁定上游 SHA、账户、订阅、scheduler Job、schedule revision、attempt、attempt-scoped execution ID、SyncRun、爬取 checkpoint、forward 模式、登录方式、条数上限、headless/watchdog 策略、作者指纹与请求延迟；新写入只允许 v3/v2。
3. 既有已密封 manifest-v2/receipt-v1 产物保持双读、逐字节精确且只读可恢复。由于旧回执认证精确 manifest 字节，绝不原地重写；未密封或失败的 legacy 产物不会获得可信身份。
4. Scheduler 重试复用持久 Job UUID，但每次 attempt 派生唯一受限 execution root。attempt 1 留下或移除状态后 attempt 2 仍可运行；旧 attempt 在 cancel/reclaim/ABA 后不得密封、导入、推进 checkpoint 或删除后继根目录。
5. 桥接准备、checkout/runtime 探测、secret-provider 读取、子进程等待、回执验证与归一化全部移出事件循环。浏览器/进程/文件系统等待期间不持有 SQLite 事务；可信 scheduler 父进程继续精确 heartbeat。
6. 显式实现协作取消：task 取消会通知同步 runner，终止并 join 完整子/孙进程树，安全清理 attempt-owned 产物，并在 handler 返回或传播 fencing 前释放账户/profile 锁。仅取消 `asyncio.to_thread` task 不能作为验收证据。
7. 父进程 liveness/control channel 防止 worker 硬死亡后遗留爬虫；旧进程树退出前，新 worker 不能使用同一 browser profile。Windows 启动必须关闭 `Popen` 到 Job/control handshake 的窗口；本地 helper-process 硬杀测试证明有界退出与锁释放。
8. 数据库 URL、worker ID、租约 owner/token 与续租权限绝不进入子进程 argv、环境、manifest 或输出。每个 SyncRun 创建/attach/状态变更及每个导入/checkpoint 批次都必须先在同一事务内调用精确 owner/token/未过期 guard。所有权丢失前已提交批次可以保留，之后不得再提交。
9. 忠实的 pinned-shape 测试会在不启动真实爬虫的前提下覆盖上游配置与 `parse_cmd()` 顺序。锁定上游通过 manifest-bound `config.CRAWLER_MAX_SLEEP_SEC` 接收延迟，并设置 `MAX_CONCURRENCY_NUM=1`。这只证明已配置上游 crawl-delay knob，不宣称每次 HTTP 请求都按该间隔执行。
10. 失败映射采用封闭且无密钥的固定表：`ACCOUNT_BUSY → account_busy`、`TIMED_OUT → upstream_timeout`、`START_FAILED → upstream_unavailable`、`CONFIGURATION_FAILED → configuration_invalid`、`UPSTREAM_FAILED → temporary_upstream`、输出/tree/receipt 拒绝 → `output_security_failed`；取消/租约丢失传播 fencing，旧 handler 不得收尾。
11. 缺少许可证授权或 scheduled QR/challenge 展示能力时，不启动子进程并进入显式 `waiting_user`；Cookie 缺失/不可用或 saved-session 认证不可用时进入 `waiting_auth`；两者只有显式 Job resume 才能重试。
12. 七个平台标识均通过 mocked-process、版本化夹具流程：订阅 → tick → v3 prepare → fake child → receipt → guarded forward 导入 → 重启/重试。该流程证明内容/checkpoint 身份幂等，但不宣称真人登录、真实作者流量或上游分页已受限。
13. 已知密钥输出、非零退出、timeout、输出超限、回执拒绝、取消与租约丢失均不得在返回后的运行树保留 attempt-owned 密钥字节。哨兵扫描覆盖 SQLite、manifest/receipt、成功/失败 attempt 根、Job/lane 投影与 scheduler CLI 输出；私有账户 session profile 被如实记录为可能携带凭据的边界，不纳入虚假的零密钥声明。
14. CLI 提供显式 MediaCrawler 启用/许可证确认与封闭策略创建，输出不得包含 payload、secret reference、locator、租约材料或文件系统根；默认未授权时 fail closed。
15. Ruff、格式、严格 mypy、全量分支感知 pytest、v2/v3、取消/父进程死亡、ownership、七平台、重试/重启及保留产物哨兵专项、构建、随包资源、文档、上游锁定、补丁与运行产物未跟踪检查全部通过，并准确记录在 `verification.md`。

## 真实性边界与非目标

- 执行 0007 的 scheduled 模式仅支持 forward。定时 backfill、自动 sync → download → Emby 导出规划及签名 locator 刷新仍属于后续工作。
- QR/challenge 展示 UX 仍是手工/后续工作；scheduled handler 只能安全进入 `waiting_user`。
- 真人二维码/Cookie/保存会话登录、七平台作者扫描、真实 CDN 获取及 Emby/Jellyfin 扫描/播放继续为 `NOT_RUN`，直到用户提供并授权相应环境。
- 逐请求 HTTP 节流、代理池、验证码/平台保护绕过、修改上游源码、REST、常驻生产守护、Docker、分布式 HA/PostgreSQL 与公网部署不属于执行 0007。
- MediaCrawler 二进制下载保持关闭；handler 只导入元数据及稳定 `adapter_refresh` 资产身份。
