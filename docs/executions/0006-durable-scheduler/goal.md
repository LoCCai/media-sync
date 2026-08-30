# Execution 0006 goal / 执行 0006 目标

- Status / 状态：Complete for the offline/Fake scope / 离线/Fake 范围完成
- Started / 开始时间：2026-08-30 10:48 +08:00
- Predecessor / 前置执行：Execution 0005 implementation commit `8d5b48a`

## Outcome / 结果目标

Deliver a restart-safe, multi-process-safe single-host scheduler for creator subscriptions. It must materialize due subscription cycles into durable Jobs, run supported sync handlers with bounded retries, and enforce global worker capacity plus persistent platform/account launch throttling without weakening the exact-claim download and Emby protocols delivered by execution 0005.

交付可重启、可由多个进程安全竞争的单机作者订阅调度器。它必须把到期订阅周期物化为持久 Job，以有界重试运行受支持的同步 handler，并执行全局 worker 容量及持久平台/账户启动节流，同时不得削弱执行 0005 已交付的下载与 Emby 精确领取协议。

## Acceptance criteria / 验收标准

1. Migration `0004_scheduler_control_plane` adds scheduler identity and lane state without changing the payload, status, attempt, lease or recovery evidence of existing `asset_download` and `export.emby` Jobs.
2. A bounded scheduler tick atomically materializes every selected due subscription as one `sync.subscription` Job. Concurrent ticks create at most one non-terminal cycle per subscription; a completed cycle advances by fixed delay instead of producing a catch-up storm.
3. `claim_next` reclaim/queue mutation is scoped by accepted Job type before it changes any row. Generic sync workers never claim or reclaim execution 0005 download/export Jobs.
4. Claiming obeys injected global capacity and persistent platform/account lanes: maximum concurrency, minimum start interval, closed/open/half-open circuit state and one half-open probe winner. Independent SQLite connections prove the CAS behavior.
5. Retry policy implements bounded exponential backoff, equal jitter, `Retry-After` as a lower bound, maximum attempts and fixed error classes. Invalid numeric/time inputs fail closed; tests inject the clock and RNG and never sleep.
6. `waiting_auth` and `waiting_user` never retry automatically. Only an explicit safe resume operation may make them claimable again.
7. A closed handler registry ships with the deterministic Fake subscription handler. MediaCrawler keeps its execution 0004 manual run/ingest boundary unchanged in this execution; scheduler integration, manifest v3 and child-process heartbeat/cancellation are explicitly deferred.
8. The offline acceptance test explicitly invokes execution 0005 download/export services after a scheduled Fake sync. Execution 0006 does not claim an automatic downstream DAG/planner, and the generic worker never preclaims download/export Jobs.
9. CLI surfaces pause/resume/run-now, bounded tick/run, redaction-safe Job listing/resume, lane policy inspection/update and circuit reset. Output omits payloads, lease tokens, credentials, locators and filesystem roots.
10. An offline restart test covers subscribe → tick → Fake sync → mock secure download → Emby export → reconstruct services → rerun without duplicate cycle, archive or publication identities.
11. Ruff, format, strict mypy, full pytest/coverage, focused scheduler/concurrency/restart/sentinel suites, build, source and unpacked-wheel migrations, documentation, upstream pins, patch checks and untracked-runtime checks all pass and are recorded exactly in `verification.md`.

1. 迁移 `0004_scheduler_control_plane` 新增调度身份与 lane 状态，但不得改变既有 `asset_download`、`export.emby` Job 的 payload、状态、attempt、租约或恢复证据。
2. 有界 scheduler tick 会把选中的每个到期订阅原子物化为一个 `sync.subscription` Job。并发 tick 对同一订阅最多产生一个非终态周期；周期完成后采用 fixed-delay 推进，不能形成追赶风暴。
3. `claim_next` 必须先按接受的 Job 类型限定 reclaim/排队变更范围。通用同步 worker 绝不领取或回收执行 0005 的下载/导出 Job。
4. 领取必须同时满足注入的全局容量及持久平台/账户 lane：最大并发、最小启动间隔、closed/open/half-open circuit 及唯一 half-open 探针胜者；使用独立 SQLite 连接证明 CAS 行为。
5. 重试策略实现有界指数退避、equal jitter、作为下界的 `Retry-After`、最大尝试次数与固定错误分类。非法数字/时间输入默认拒绝；测试注入时钟与 RNG，禁止真实 sleep。
6. `waiting_auth` 与 `waiting_user` 不自动重试，只有显式安全 resume 才能重新进入可领取状态。
7. 封闭 handler registry 随确定性 Fake 订阅 handler 交付。MediaCrawler 在本执行中保持执行 0004 的手工 run/ingest 边界不变；scheduler 集成、manifest v3 与子进程 heartbeat/cancel 明确延期。
8. 离线验收在 scheduled Fake sync 后显式调用执行 0005 的下载/导出服务。执行 0006 不宣称已有自动下游 DAG/planner，通用 worker 绝不预领下载/导出 Job。
9. CLI 提供 pause/resume/run-now、有界 tick/run、脱敏 Job list/resume、lane policy 查看/修改及 circuit reset；输出不得含 payload、租约 token、凭据、locator 或文件系统根目录。
10. 离线重启测试覆盖订阅 → tick → Fake 同步 → mock 安全下载 → Emby 导出 → 重建服务 → 重跑，且不重复周期、归档或发布身份。
11. Ruff、格式、严格 mypy、全量 pytest/覆盖率、调度/并发/重启/哨兵专项、构建、源码与解包 wheel 迁移、文档、上游锁定、补丁及运行产物未跟踪检查全部通过，并把准确证据写入 `verification.md`。

## Truth boundary and non-goals / 真实性边界与非目标

- All automated acceptance is offline and uses Fake adapters/handlers, mock transports, generated media and temporary SQLite/filesystem roots.
- Live QR/Cookie/saved-session login, real platform scheduling behavior, signed-locator refresh/CDN retrieval and Emby/Jellyfin scan/playback remain `NOT_RUN` until the user supplies and authorizes those environments.
- MediaCrawler scheduler integration, manifest v3 request-delay binding, long-child heartbeat/cancellation and automatic download/export DAG planning are deferred to a later execution.
- REST API, Docker/production supervision, public-network binding, distributed HA/PostgreSQL locking, proxy pools, CAPTCHA automation and platform-protection bypass are outside execution 0006.
- Platform concurrency and start intervals qualify scheduler launch throttling only; this execution makes no claim about every upstream HTTP request.

- 全部自动验收保持离线，只使用 Fake adapter/handler、mock transport、生成媒体及临时 SQLite/文件系统根目录。
- 真人二维码/Cookie/保存会话登录、真实平台调度效果、签名 locator refresh/CDN 下载及 Emby/Jellyfin 扫描/播放继续为 `NOT_RUN`，直到用户提供并授权相应环境。
- MediaCrawler scheduler 集成、manifest v3 请求延迟绑定、长子进程 heartbeat/cancel 及自动下载/导出 DAG 规划延期到后续执行。
- REST API、Docker/生产守护、公网绑定、分布式 HA/PostgreSQL 锁、代理池、验证码自动化及平台保护绕过不属于执行 0006。
- 平台并发与启动间隔只验收 scheduler 启动节流；本执行不宣称覆盖每次上游 HTTP 请求。
