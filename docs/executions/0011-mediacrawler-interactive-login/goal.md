# Execution 0011 goal / 执行 0011 目标

- Status / 状态：Planned / 计划中
- Started / 开始时间：2026-08-31 02:17 +08:00
- Predecessor / 前置：Execution 0010 commit `f2e5899`

## Outcome / 结果

Deliver an explicit host-assisted MediaCrawler QR-login command for one exact account. The command must open a headed, account-isolated upstream browser only after the operator enables MediaCrawler and acknowledges its license for that invocation. It records redaction-safe `LoginSession` and Account authentication states, performs no creator/content crawl, and atomically hands a successful QR account over to `saved_session` for later scheduler runs.

为一个精确账户交付显式、由主机用户协助的 MediaCrawler 二维码登录命令。只有操作员在本次调用中启用 MediaCrawler 并确认许可证后，命令才可打开使用账户隔离 profile 的有头上游浏览器。该流程只记录可脱敏观察的 `LoginSession` 与账户认证状态，不抓取作者/内容，并在成功后把二维码账户原子交接为供后续调度使用的 `saved_session`。

## Acceptance / 验收

1. **Default-off exact scope / 默认关闭与精确范围** — no child is started unless both MediaCrawler gates are present. The account must exist, use the MediaCrawler adapter and currently use QR login. Cookie, phone, saved-session and foreign-adapter accounts are rejected before a browser or session mutation. / 未同时提供两个 MediaCrawler gate 时不启动 child；账户必须存在、使用 MediaCrawler adapter 且当前为二维码登录。Cookie、手机号、saved-session 及其他 adapter 账户在浏览器或会话变更前拒绝。
2. **Login-only headed child / 仅登录的有头 child** — the pinned checkout and Python runtime are verified, the browser profile and account lock are derived from platform plus account UUID, and the upstream child is forced headed with saved login state. Its contract performs zero creator/search/detail/comment/media/store/ingestion work for all seven platform identifiers. / 验证锁定 checkout 与 Python runtime；浏览器 profile 与账户锁仅由平台及账户 UUID 派生；上游 child 强制有头并保存登录状态。七个平台标识的协议测试证明作者/search/detail/comment/media/store/ingestion 工作均为零。
3. **Durable observable state / 持久可观察状态** — `LoginSession` follows `pending → waiting_user → succeeded|expired|failed|cancelled`; Account follows `unknown|required → authenticating → authenticated`, with conservative failure states. Fixed-state CLI output exposes IDs, statuses and timestamps only. / `LoginSession` 遵循 `pending → waiting_user → succeeded|expired|failed|cancelled`；Account 遵循 `unknown|required → authenticating → authenticated`，失败时保守落入失败/需认证状态。CLI 固定输出只暴露 ID、状态与时间。
4. **Fenced handoff / 受保护的交接** — one local account login is active at a time. Completion is accepted only for the still-current session while the per-account lock is held. Success preserves only the derived stable profile, changes QR to `saved_session` atomically, and lets an existing `qr_required` scheduler Job continue through the existing explicit resume control without another QR challenge. / 同一本地账户同一时刻只允许一个登录；仅在持有账户锁且会话仍为当前会话时接受收尾。成功只保留派生的稳定 profile，原子地把 QR 改为 `saved_session`，并允许既有 `qr_required` 调度 Job 经现有显式 resume 控制继续，而不再次要求二维码。
5. **Saved-session fail-closed / 保存会话失效时关闭失败** — a missing profile or failed authenticated-session probe maps to fixed `auth_expired`/`waiting_auth`; a background scheduler run never silently falls back to QR or opens an interactive browser. / profile 缺失或已认证会话探测失败时映射为固定 `auth_expired`/`waiting_auth`；后台调度绝不静默回退二维码或打开交互浏览器。
6. **Explicit child truth / 显式 child 真值** — the login child emits a closed result protocol. Upstream `SystemExit`, including exit code zero on a login failure, cannot be mistaken for success. / 登录 child 输出封闭结果协议；上游 `SystemExit`（包括登录失败却返回零退出码）不得被误判为成功。
7. **Cancellation and secrecy / 取消与保密** — timeout/cancellation terminates and joins the child process tree before releasing the account lock and records a recoverable fixed state. QR bytes/tokens, Cookies, raw child stdout/stderr and local profile paths never enter SQLite, CLI output, logs, docs or Git. / 超时或取消会在释放账户锁前终止并 join child 进程树，并记录可恢复的固定状态。二维码字节/token、Cookie、原始 child stdout/stderr 与本地 profile 路径不得进入 SQLite、CLI 输出、日志、文档或 Git。
8. **Truthful qualification / 真实验收边界** — offline fake-child coverage may qualify the local protocol for all seven identifiers, but every real-account QR row remains `NOT_RUN` until the user performs an authorized scan. Phone login, CAPTCHA bypass, REST, daemon, Docker, content sync and platform media expansion are outside this execution. / 离线 fake-child 可验收七个平台标识的本地协议，但在用户授权扫码前，所有真人账户二维码行保持 `NOT_RUN`。手机号登录、验证码绕过、REST、daemon、Docker、内容同步及平台媒体扩展不属于本执行。

## Schema decision / Schema 决策

Start by reusing the existing `accounts` and `login_sessions` columns. Local single-account exclusion is owned by the existing per-account filesystem lock, while repository transitions use conditional current-state updates. Add a migration only if implementation proves that the required fencing cannot be expressed safely with these existing identities. / 初始复用既有 `accounts` 与 `login_sessions` 列；本地单账户排他由既有逐账户文件锁承担，仓储状态迁移使用基于当前状态的条件更新。仅当实现证明现有身份无法安全表达所需 fencing 时才新增 migration。
