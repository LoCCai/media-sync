# Execution 0007 goal / 执行 0007 目标

- Status / 状态：Planned / 已计划
- Started / 开始时间：2026-08-30 12:45 +08:00
- Predecessor / 前置执行：Execution 0006 implementation commit `674e510`
- Network boundary / 网络边界：offline fixtures and local helper processes only / 仅离线夹具与本地辅助进程

## Outcome / 结果目标

Deliver an opt-in, license-gated and offline-proven MediaCrawler `sync.subscription` handler for the pinned upstream. It must isolate every retry attempt, keep scheduler renewal authority in the trusted parent, terminate the complete child tree on cancellation or parent death, and fence every SyncRun/checkpoint/content mutation without exposing credentials, local roots in operator surfaces, or lease authority.

交付一个显式启用、受许可证约束且经过离线证明的锁定版 MediaCrawler `sync.subscription` handler。它必须隔离每次重试 attempt，把 scheduler 续租权限只留在可信父进程，在取消或父进程死亡时终止完整子进程树，并对每次 SyncRun/checkpoint/content 变更执行 fencing，且不在运维表面暴露凭据、本地根目录或租约权限。

## Acceptance criteria / 验收标准

1. A closed subscription policy v1 stores only `schema_version`, optional opaque creator `secret_ref`, explicit `allow_full_history`, bounded positive `request_delay_seconds` and `headless`. License acknowledgement is a default-off operator authorization and is bound into every new manifest with the pinned license identity; no raw Cookie or signed creator URL is persisted.
2. Manifest v3 and completion receipt v2 bind the pinned upstream SHA, account, subscription, scheduler Job, schedule revision, attempt, attempt-scoped execution ID, SyncRun, crawl checkpoint, forward mode, login method, item cap, headless/watchdog policy, creator fingerprints and request delay. Newly written artifacts are v3/v2 only.
3. Previously sealed manifest-v2/receipt-v1 artifacts remain dual-read, byte-exact and read-only recoverable. They are never rewritten in place because the existing receipt authenticates the exact manifest bytes. Unsealed or failed legacy artifacts do not gain trust.
4. Scheduler retries reuse the durable Job UUID but derive a unique, confined execution root for every attempt. Attempt 2 can run after attempt 1 leaves or removes state; stale attempts cannot seal output, ingest, advance checkpoints or delete a successor's root after cancel/reclaim/ABA.
5. Bridge preparation, checkout/runtime probes, secret-provider reads, child waiting, receipt validation and normalization run off the event loop. No SQLite transaction spans browser/process/filesystem waits, while the trusted scheduler parent continues exact lease heartbeat.
6. Cooperative cancellation is explicit: task cancellation signals the synchronous runner, terminates and joins the complete child/grandchild tree, safely removes attempt-owned artifacts and releases the account/profile lock before the handler returns or propagates fencing. A plain cancelled `asyncio.to_thread` task is not accepted as evidence.
7. A parent-liveness/control channel prevents orphan crawlers after a hard worker-process death. A fresh worker cannot use the same browser profile until the old child tree has exited; Windows startup must close the `Popen`-to-Job/control-handshake gap. Local helper-process hard-kill tests prove bounded exit and lock release.
8. The database URL, worker ID, lease owner/token and renewal authority never enter child argv, environment, manifest or output. Every SyncRun create/attach/status mutation and every ingestion/checkpoint batch invokes the exact owner/token/unexpired guard first in the same transaction. Batches committed before ownership loss may remain; no batch commits afterward.
9. A faithful pinned-shape test exercises the upstream configuration and `parse_cmd()` ordering without launching the real crawler. The pinned upstream receives the manifest-bound delay through `config.CRAWLER_MAX_SLEEP_SEC` and receives `MAX_CONCURRENCY_NUM=1`. This proves a configured upstream crawl-delay knob only, not spacing for every HTTP request.
10. Closed status mapping is fixed and secret-free: `ACCOUNT_BUSY → account_busy`, `TIMED_OUT → upstream_timeout`, `START_FAILED → upstream_unavailable`, `CONFIGURATION_FAILED → configuration_invalid`, `UPSTREAM_FAILED → temporary_upstream`, output/tree/receipt rejection → `output_security_failed`; cancellation/lease loss propagates fencing and the stale handler never finalizes.
11. Missing license authorization or scheduled QR/challenge presentation enters explicit `waiting_user` without spawning. Missing/unavailable Cookie or saved-session authentication enters `waiting_auth`. Only explicit Job resume can retry either state.
12. All seven platform identifiers pass a mocked-process, versioned-fixture flow: subscribe → tick → v3 prepare → fake child → receipt → guarded forward ingestion → restart/retry. The flow proves idempotent content/checkpoint identity but does not claim live login, live creator traffic or bounded upstream pagination.
13. Known-secret output, nonzero exit, timeout, output-limit failure, receipt rejection, cancel and lease loss all leave no attempt-owned secret bytes in the returned runtime tree. Sentinel scans cover SQLite, manifests/receipts, successful and failed attempt roots, Job/lane projections and scheduler CLI output; the private account session profile is documented as a credential-bearing boundary, not included in a false zero-secret claim.
14. CLI exposes explicit MediaCrawler enablement/license acknowledgement and closed policy creation without returning payloads, secret references, locators, lease material or filesystem roots. The default without authorization is fail-closed.
15. Ruff, format, strict mypy, full branch-aware pytest, focused v2/v3, cancellation/parent-death, ownership, seven-platform, retry/restart and retained-artifact sentinel suites, build, packaged resources, documentation, upstream pins, patch and untracked-runtime checks all pass and are recorded exactly in `verification.md`.

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

## Truth boundary and non-goals / 真实性边界与非目标

- Scheduled mode is forward-only in execution 0007. Scheduled backfill, automatic sync → download → Emby export planning and signed-locator refresh remain later work.
- QR/challenge presentation UX remains manual/later work; the scheduled handler may only enter `waiting_user` safely.
- Live QR/Cookie/saved-session login, seven-platform creator scans, real CDN retrieval and Emby/Jellyfin scan/playback remain `NOT_RUN` until the user supplies and authorizes those environments.
- Per-request HTTP throttling, proxy pools, CAPTCHA/protection bypass, upstream source modification, REST, resident production supervision, Docker, distributed HA/PostgreSQL and public-network deployment are outside execution 0007.
- MediaCrawler binary downloading stays disabled; the handler ingests metadata and stable `adapter_refresh` asset identities only.

- 执行 0007 的 scheduled 模式仅支持 forward。定时 backfill、自动 sync → download → Emby 导出规划及签名 locator 刷新仍属于后续工作。
- QR/challenge 展示 UX 仍是手工/后续工作；scheduled handler 只能安全进入 `waiting_user`。
- 真人二维码/Cookie/保存会话登录、七平台作者扫描、真实 CDN 获取及 Emby/Jellyfin 扫描/播放继续为 `NOT_RUN`，直到用户提供并授权相应环境。
- 逐请求 HTTP 节流、代理池、验证码/平台保护绕过、修改上游源码、REST、常驻生产守护、Docker、分布式 HA/PostgreSQL 与公网部署不属于执行 0007。
- MediaCrawler 二进制下载保持关闭；handler 只导入元数据及稳定 `adapter_refresh` 资产身份。
