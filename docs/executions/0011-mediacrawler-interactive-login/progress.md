# Execution 0011 progress / 执行 0011 推进结果

- Status / 状态：Complete for the offline implementation and automated verification scope in local commit `8bb16f6`; live qualification `NOT_RUN` / 离线实现与自动验证范围已在本地提交 `8bb16f6` 完成；真人验收为 `NOT_RUN`
- Started / 开始时间：2026-08-31 02:17 +08:00
- Predecessor / 前置：Execution 0010 commit `f2e5899`

## Implemented in the current worktree / 已在当前工作树实现

### Durable state and application orchestration / 持久状态与应用编排

- Added conditional Account authentication CAS and a redaction-safe `LoginSessionState` projection. The repository enforces `pending → waiting_user → terminal`, one active local session, deadline fences and stale/sibling rejection. Initial QR states and exact `saved_session/expired` reauthentication atomically enter `qr/authenticating`; success changes that state to `saved_session/authenticated`, while non-success leaves a retryable QR state. / 新增 Account 认证状态条件 CAS 与脱敏的 `LoginSessionState` 投影。仓储强制 `pending → waiting_user → terminal`、本地单一活动会话、deadline fencing 及 stale/sibling 拒绝。初始 QR 状态与精确 `saved_session/expired` 重认证会原子进入 `qr/authenticating`；成功后切到 `saved_session/authenticated`，非成功则留在可重试 QR 状态。
- Reused the existing schema. Savepoints make duplicate, stale and sibling conflicts zero-half-write even if a caller catches the fixed conflict and continues its outer transaction. / 复用既有 schema；savepoint 保证重复、过期及 sibling 冲突即使被调用方捕获并继续外层事务，也不会留下半写入。
- Added `MediaCrawlerQrLoginService` with strict pre-run eligibility: a MediaCrawler QR account in `unknown|required|expired|failed`, or exactly a `saved_session/expired` account, may reach the runner only when persisted credential/profile references are absent. Authenticated/non-expired saved sessions, Cookie/phone/foreign accounts and missing accounts create no session and do not invoke the integration. / 新增 `MediaCrawlerQrLoginService` 严格前置资格检查：处于 `unknown|required|expired|failed` 的 MediaCrawler QR 账户或精确的 `saved_session/expired` 账户，且未持久化 credential/profile 引用时才可进入 runner。已认证/未过期 saved session、Cookie/手机号/其他 adapter 账户及不存在账户不会创建 session，也不会调用集成层。
- Added fixed redaction-safe application errors for not-found, ineligible, busy, invalid configuration, start failure, invalid result, conflict and unexpected failure. Runner-controlled exception text is never operator output; post-hook invalid/exceptional outcomes attempt a conservative `failed` closeout. / 新增 not-found、ineligible、busy、配置无效、启动失败、结果无效、冲突及意外失败的固定脱敏应用错误；runner 控制的异常文本绝不进入运维输出，hook 后的非法结果或异常会尽力保守收尾为 `failed`。

### Login-only process boundary and CLI / 仅登录进程边界与 CLI

- Added a closed typed request/result protocol and an isolated process runner for `interactive_qr` and `saved_session_probe`. The runner verifies the pinned checkout and Python runtime, derives account-scoped paths, owns the per-account lock through process-tree join and accepts only one bounded exact child frame. / 新增封闭类型化请求/结果协议，以及支持 `interactive_qr` 与 `saved_session_probe` 的隔离进程 runner。Runner 验证锁定 checkout 与 Python runtime，派生账户级路径，从锁后 hook 一直持有逐账户锁至进程树 join，并且只接受一个有界、精确的 child frame。
- Interactive mode forces a headed QR browser and saved login state while clearing creator/search/detail/comment/media/store work for all seven platform identifiers. QR bytes remain inside the visible browser, and upstream output is silenced rather than persisted. / 交互模式强制有头二维码浏览器并保存登录状态，同时为七个平台标识清空作者/search/detail/comment/media/store 工作。二维码字节只存在于可见浏览器，上游输出被静默而非持久化。
- Saved-session probe mode is headless and rejects the upstream QR fallback before interaction. `SystemExit`, including code zero, malformed/duplicate/oversized results, timeout and cancellation cannot authenticate. Under a live parent, timeout/cancellation closes and joins the complete process tree before lock release; detail fallback also guarantees `async_cleanup`. / saved-session probe 模式强制无头，并在交互前拒绝上游二维码回退。`SystemExit`（包括零退出码）、畸形/重复/超限结果、超时及取消均不能认证。在父进程仍存活时，超时/取消会在释放锁前关闭并 join 完整进程树；detail fallback 也保证执行 `async_cleanup`。
- Added explicit `media-sync account login` double gates and `account login-status`. Output contains only fixed IDs, statuses and timestamps; it omits credential references, profile paths, challenge material and child output. / 新增显式 `media-sync account login` 双 gate 与 `account login-status`；输出仅含固定 ID、状态与时间戳，不含 credential 引用、profile 路径、挑战材料或 child 输出。
- Background forward/detail paths now force saved sessions headless and block QR fallback. A missing derived profile uses the dedicated saved-session-unavailable boundary and maps to fixed `auth_expired`; ordinary `BridgeConfigurationError` remains `configuration_invalid`. A probe that reaches the blocked QR fallback also maps conservatively to `auth_expired`, but upstream `pong() == false` may contain network ambiguity, so this is not an exact remote-cause claim. Scheduler/download paths persist Account `expired` only for the fixed auth-expired outcome. No background path silently opens an interactive browser. / 后台 forward/detail 路径现会强制 saved session 无头并阻止 QR 回退。派生 profile 缺失使用专用 saved-session-unavailable 边界并映射固定 `auth_expired`；普通 `BridgeConfigurationError` 保持 `configuration_invalid`。探测进入被阻止的 QR 回退时也会保守映射为 `auth_expired`，但上游 `pong() == false` 可能包含网络异常歧义，因此这不是精确远端原因声明。调度/下载路径只为固定 auth-expired 结果持久化 Account `expired`。后台路径不会静默打开交互浏览器。

## Verified so far / 当前已验证

- Repository state-machine focused gate: `32 passed in 6.55s`. / 仓储状态机专项门禁：`32 passed in 6.55s`。
- Application orchestration focused gate: `33 passed in 6.64s`; repository/application/login-model composition: `83 passed in 13.13s`. / 应用编排专项门禁：`33 passed in 6.64s`；仓储/应用/登录模型组合：`83 passed in 13.13s`。
- Login-only runner/unit/contract gate: `42 passed in 23.57s`; its targeted Ruff, format, mypy, package-export import and whitespace checks pass. / 仅登录 runner/unit/contract 门禁：`42 passed in 23.57s`；对应专项 Ruff、格式、mypy、包导出导入及空白检查通过。
- Saved-session forward/detail/scheduler audit: `25 passed in 0.97s`; its test Ruff/format and five-source mypy checks pass. / saved-session forward/detail/调度审计：`25 passed in 0.97s`；对应测试 Ruff/格式及五个源码文件 mypy 检查通过。
- CLI gate: `77 passed in 13.36s`. / CLI 门禁：`77 passed in 13.36s`。
- Integrated repository/application/login-only/CLI/saved-session/download/scheduler gate: `274 passed in 70.73s`. / 仓储/应用/仅登录/CLI/saved-session/下载/调度合并门禁：`274 passed in 70.73s`。
- A later exact closure test proves that a successful QR login can resume the pre-existing `qr_required` Job under `saved_session` without creating a second Job or interactive fallback: `1 passed in 0.82s`. / 后续精确闭环测试证明：成功 QR 登录后，可在 `saved_session` 下恢复既有 `qr_required` Job，不创建第二个 Job，也不发生交互回退：`1 passed in 0.82s`。
- Deadline and Ctrl+C regressions terminalize the still-owned durable LoginSession instead of leaving a normal-path zombie; the final integrated gate includes them and passes `274` tests. / 截止时间与 Ctrl+C 回归会终结仍归本次尝试所有的持久 LoginSession，不再留下正常路径僵尸；最终合并门禁已覆盖并通过 `274` 项测试。
- Complete suite: `1080 passed, 1 skipped in 226.92s`; the sole skip is `tests/contract/test_mediacrawler_supervision.py:556`, whose POSIX mode-bit assertion is not the Windows ACL boundary. No coverage run was performed or claimed. / 完整套件：`1080 passed, 1 skipped in 226.92s`；唯一跳过项为 `tests/contract/test_mediacrawler_supervision.py:556`，其 POSIX mode-bit 断言不适用于 Windows ACL 边界。未运行也不宣称覆盖率结果。
- Project-wide Ruff, format, mypy, documentation, pinned-upstream and sdist/wheel build gates all pass. / 全项目 Ruff、格式、mypy、文档、锁定上游及 sdist/wheel 构建门禁全部通过。
- These automated results complete the offline implementation scope; they are not evidence of live platform compatibility. / 这些自动化结果完成离线实现范围，但不是真人平台兼容性证据。

## Deviations and decisions / 偏差与决策

- Prioritize an explicit host-assisted `account login` control surface before a resident daemon or REST API because it unlocks the user-facing authentication path while keeping interactive authority visible. / 在常驻 daemon 或 REST API 前优先交付显式主机协助 `account login` 控制面，以解锁用户可用认证链，同时保持交互授权可见。
- The login command handles only eligible initial QR states or exact `saved_session/expired` reauthentication. Start atomically becomes `qr/authenticating`; success returns to `saved_session/authenticated`, while failure/timeout/cancellation remains retryable QR state. Cookie, phone, active/non-expired saved-session, foreign-adapter, credential-bearing and persisted-profile-path accounts are rejected before integration. / 登录命令只处理合格初始 QR 状态或精确 `saved_session/expired` 重认证。启动时原子变为 `qr/authenticating`；成功回到 `saved_session/authenticated`，失败/超时/取消则保持可重试 QR 状态。Cookie、手机号、活动/未过期 saved-session、其他 adapter、带 credential 或已持久化 profile path 的账户都会在集成层前拒绝。
- Do not serialize QR images or tokens. The user scans the upstream headed browser directly. / 不序列化二维码图片或 token；用户直接扫描上游有头浏览器。
- No migration was required for the local-host model. Coordination relies on one derived runtime root plus its per-account filesystem lock and repository CAS; cross-host HA is not claimed. / 本地主机模型无需 migration；协调依赖一个派生 runtime root、逐账户文件锁及仓储 CAS，不宣称跨主机 HA。
- Treat a saved profile as derived runtime state rather than a database path or credential. Success changes the login method to `saved_session`; scheduled reuse derives the same account-scoped profile and fails closed if it is unavailable or reaches the blocked QR fallback. This conservative state does not distinguish expiry from every upstream network ambiguity. / 把保存的 profile 视为派生运行时状态，而不是数据库路径或凭据；成功后登录方式切为 `saved_session`，定时复用会派生同一账户级 profile，若不可用或进入被阻止的 QR 回退则关闭失败。该保守状态不能区分失效与所有上游网络异常歧义。

## Remaining outside the completed offline scope / 已完成离线范围之外的待办

- Bilingual implementation commit `8bb16f6` created; remote push remains unclaimed. / 已创建中英双语实现提交 `8bb16f6`；不宣称远端已推送。
- Real-account QR scans for all platforms remain `NOT_RUN`. / 所有平台真人账户二维码扫码保持 `NOT_RUN`。
- Hard-parent-death LoginSession recovery and a parent-liveness protocol remain for the next execution; normal timeout/cancellation/Ctrl+C coverage does not prove SIGKILL recovery. / 父进程硬终止后的 LoginSession 回收与 parent-liveness 协议留待下一执行；正常超时/取消/Ctrl+C 覆盖不证明 SIGKILL 回收。
