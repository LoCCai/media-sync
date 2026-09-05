[English](plan.md) | **中文**

# 执行 0055 阶段 A 计划

- 状态：实现前冻结
- 日期：2026-09-05
- 基线：`d0a8cc2`
- 计划 revision：`0008_playback_evidence`

## 交付顺序

1. 先单独提交本次中英双语八文件规划基线，继续排除既有未跟踪 `.mimosa/`。
2. 增加有界操作者鉴权设置并复用类型化 `SecretReference`、`SecretValue` 与本地 resolver。在 API 绑定前解析必需浏览器凭据及可选、独立 Bearer 凭据；值与完整引用不得进入 settings 投影、异常、repr、日志或支持包。
3. 实现小型进程内 auth runtime：常量时间凭据比较、单个轮转的不透明浏览器 session、有界 TTL、仅内存 CSRF、固定码审计日志、确定性的进程全局登录失败限流，以及精确 logout/expiry/restart 语义。时钟与随机源只通过私有测试 seam 注入；生产环境无 bypass。
4. 在 `create_api_app` 最外层安装一个 ASGI 鉴权/Host/Origin 中间件，由它拥有精确公共路由表并在其余 endpoint 工作前拒绝。保留 HEAD、安全/no-store header 及拒绝时不进入 body/stream 的语义。
5. 增加严格的 `/api/v1/operator-auth/login`、`/session`、`/logout` 契约。更新 `media-sync serve` 诊断与部署启动，使鉴权配置缺失或无法解析时在监听前失败。CORS 保持关闭，转发 header 不受信任。
6. 把现有七个 API 测试模块迁移到统一 authenticated-client helper，通过真实 login 与 CSRF 流程访问；不得按测试环境绕过或跳过 middleware。增加路由枚举测试，覆盖 51 条基线路由及每条新增路由。
7. 为 matched 作者 lookup 增加 domain-separated observation fingerprint。它只绑定既有安全 digest 与规范 author UUID；public helper 无法表达原始 provider/path/item。
8. 增加 `PlaybackEvidence` model、revision `0008_playback_evidence` 与专用 repository。表只包含 `id`、`schema_version`、`author_id`、`publication_job_id`、`profile_fingerprint`、`publication_fingerprint`、`selector_fingerprint`、`item_fingerprint`、唯一 `observation_fingerprint`、`observed_at` 与 `confirmed_at`，没有 mutable timestamp、state、raw payload 或 requester 字段。
9. 以自然身份实现 insert/replay。SQLite 在首读前占用 writer；插入使用 nested savepoint。PostgreSQL 由 unique constraint 串行化竞争者。`IntegrityError` 后 expire 并按 fingerprint 重读，只有每个持久字段都精确一致才返回 replay。
10. 实现 `PlaybackEvidenceService.confirm(author_id, observation_fingerprint)`：resolve target A，执行一次完整唯一 lookup，resolve target B，比对 A/B 与重算 fingerprint，最后才开启短 insert transaction。网络/文件系统工作期间不得持有数据库 writer/row lock。
11. 增加只允许已鉴权浏览器 session 的 POST confirmation，以及安全的按作者 evidence 投影。即使 Bearer 有效也拒绝确认。不得接受 `Idempotency-Key`、selector、remote ID、path、profile 值、timestamp 或说明文本。
12. 将 qualification 升级为 schema v3，以有界方式投影 current/stale evidence 且不暴露 selector。`playback_evidence` 转为 `IMPLEMENTED`；没有当前真人记录时保持 `NOT_RUN`，只有当前精确权威才可 `PASS`。Provider task completion 与自动联动保持不变。
13. Web 增加登录壳与 session store、仅内存 CSRF header 注入、集中 401 reset 及 logout。验证 EventSource、直接 archive/media 标签、QR 获取、docs、legacy 与 SPA 深链接可通过 HttpOnly cookie 工作且不使用 URL token。
14. Library 在 matched lookup 后增加播放确认交互，要求显式 modal acknowledgment，只发送 author UUID 与 observation fingerprint，显示 current/stale 安全证据，且不提供假百分比或远端遥测声明。
15. 更新 architecture、deployment、operations/backup/upgrade、security review、status、roadmap、platform capabilities、README/index、0047 真人清单及本执行 progress/verification，继续区分 automated evidence、implementation status 与授权真人 qualification。
16. 运行 auth/evidence/migration/API/Web 专项、SQLite 与真实 PostgreSQL 竞态矩阵、完整 Python 与串行 Web 套件、Ruff/format/mypy/compileall、wheel/sdist 与容器/静态打包检查、docs/upstreams、tracked-output/host-path/private-key/assigned-secret 扫描、冻结 goal/plan diff、空白及 Git 发布对账。

## 鉴权契约

`Settings` 只新增有界不可变输入：`serve` 必需的 `operator_credential_secret_ref`、可选 `operator_api_token_secret_ref`、有界 `operator_allowed_origins` 与默认八小时的有界 `operator_session_ttl_seconds`。回环绑定可派生一个精确本地 HTTP origin；非回环绑定必须显式配置 HTTPS origin。scheme、host、port、Unicode/IDNA 形式、userinfo、path、query、fragment、重复、wildcard、null 与列表边界均在 app 启动前验证。

Auth runtime 只在进程内保留已解析 `SecretValue` 与随机 session/CSRF 材料。同一时刻只接受一个浏览器 session；新登录轮转旧 session。Session cookie 与 CSRF 均以常量时间比较。登录失败具有确定性最短耗时和不保留客户端标识的进程全局有界 limiter。固定日志码为 `operator_login_succeeded`、`operator_login_failed`、`operator_login_rate_limited`、`operator_logout_succeeded`、`operator_session_expired`、`playback_evidence_created`、`playback_evidence_replayed`，上下文不含请求派生文本。

中间件公共表同时匹配 method 与精确 path，或匹配 `/_app/immutable/` 下已经解析的普通静态文件。绝不放行全部 `/api`、全部非 API path、SPA fallback 或任意文件系统 prefix。鉴权优先级为：有效浏览器 cookie；否则对允许自动化的路由接受有效 Bearer；否则 401。使用 cookie 的不安全请求随后校验精确 Origin 与 CSRF；login 在无 session 时也要求精确 Origin。所有请求最先经过 Host 门。

## 播放证据身份

Observation fingerprint 使用规范 length-prefixed payload 与专用 `media-sync:media-server-playback-observation:v1` domain，绑定规范 author UUID、profile fingerprint、publication fingerprint、selector fingerprint 与 item fingerprint。它不包含 `observed_at`，因此同一未变身份的重复完整 lookup 只会对应一条自然 evidence；表中 `observed_at` 来自确认时服务端 lookup。

公共 lookup 只在 `matched` 时返回 fingerprint。Confirmation 重做全部权威工作并以 `hmac.compare_digest` 比较；没有已鉴权浏览器 session 与 CSRF 时，响应本身不能充当 bearer capability。表中四个 digest 是为了有界 current/stale 查询与精确冲突校验而复制安全身份组件，并非复制原始 selector。

## Migration 与回滚

Revision 0008 新增一张表、`observation_fingerprint` unique constraint、`(author_id, confirmed_at, id)` 索引、UUID/digest/schema/timestamp check，以及关联 `authors.id` 与 `jobs.id` 的 RESTRICT 外键；不修改任何既有 row 或 vocabulary。Metadata/create-all 与 Alembic schema 必须等价。

Downgrade 仅允许 online。先审计 evidence；非空表抛出 `playback_evidence_rows_prevent_downgrade`，且不改变 revision、table 或 row。空表才可删除索引/表并回到 0007。未来 Author/Job 删除必须显式处理 RESTRICT evidence，禁止 cascade 删除。

由于旧 API 没有鉴权，应用回滚本身也是安全边界：停止流量、保留 revision 0008 数据库、部署兼容鉴权 binary 或另行评审的外部鉴权层，再恢复流量。绝不能删除 evidence 或强改 Alembic revision 来让旧 binary 启动。

## 验证矩阵

- 配置：缺失/无效/无法解析/弱/重复 secret ref、回环派生、非回环 HTTPS origin、恶意 Host 与 forwarded header、有界 TTL/list/text、repr/error/support-bundle 脱敏。
- Auth：正确/错误凭据、常量时间比较 seam、轮转、登出、过期、重启、固定 401/403/429、GET/HEAD、cookie flags、Bearer grammar、凭据/Bearer 分离、限流恢复及零 secret 留存。
- 路由清单：每个 `app.routes` entry 的匿名请求；精确公共 method 通过，其余在 dependency/DB/file/stream 前拒绝，包括 OpenAPI/docs/redoc、SPA fallback、`/legacy`、QR、archive GET/HEAD/Range、support bundle、deep readiness 与 SSE。
- CSRF/origin：缺失/null/重复/错误/过期 header、缺失/错误 Origin、跨域 form/JSON、精确允许 Origin、Bearer 行为及零 query token。
- Evidence identity：仅 matched 返回 fingerprint、domain separation、canonicalization、每个上下文组件漂移、无原始 selector 泄漏、repr/redaction 与未变 lookup 稳定性。
- Service TOCTOU：not-found/ambiguous/incomplete、target A/B 的 publication/profile/selector/item 漂移、伪造 fingerprint、数据库失败、重复确认返回原 `confirmed_at`，且数据库锁内无网络/文件工作。
- SQLite persistence：fresh 与 populated 0007→0008、schema parity、全部 constraint/FK、串行与双线程 replay、outer rollback、RESTRICT 删除、空/非空 downgrade、foreign-key check 与 packaged-wheel upgrade。
- PostgreSQL persistence：同身份 unique-lock wait 后 replay、winner rollback 后创建、字段冲突、不同身份、insert 与 parent delete 双顺序、timeout/retry、无 orphan 与单行。
- Qualification：schema v3 无证据 `IMPLEMENTED/NOT_RUN`、当前精确证据 PASS、stale 保留但不 PASS、provider completion/automatic scan 不变，checked-in 状态不得从 mock 升级为真人。
- Web：login/session/logout、CSRF 注入、session 过期 reset、无 localStorage/token URL、EventSource reconnect、QR/blob、archive media/new-tab、docs/legacy、deep link、仅 matched 确认、modal focus/keyboard 及如实文案。

## 提交边界

1. 规划基线。
2. 操作者鉴权配置/runtime/middleware 与后端测试。
3. 播放 fingerprint、revision 0008、repository 与跨数据库持久化测试。
4. Confirmation service/API 与 qualification v3。
5. Web 登录与播放确认表面。
6. 评审修复、完整验证、文档收尾与推送对账。

每个提交使用中英双语 subject，只包含已评审边界，并排除 `.mimosa/` 与全部 runtime/generated output。
