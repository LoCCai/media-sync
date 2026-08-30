# Execution 0011 plan / 执行 0011 计划

- Status / 状态：Offline implementation, automated verification and final read-only secret audit complete; implementation commit pending; live qualification remains `NOT_RUN` / 离线实现、自动验证与最终只读密钥审计已完成；实现提交待创建；真人验收保持 `NOT_RUN`
- Plan date / 计划日期：2026-08-31
- Predecessor / 前置：Execution 0010 commit `f2e5899`

## Delivery sequence / 交付顺序

1. **Freeze state contracts / 冻结状态契约 — implemented and focused gate passes / 已实现且专项门禁通过**
   - Add typed, closed login requests/results and fixed error codes. / 新增类型化、封闭的登录请求/结果与固定错误码。
   - Extend Account/LoginSession repositories with conditional start, waiting, success, expiry, failure and cancellation transitions. / 扩展 Account/LoginSession 仓储，提供条件化 start、waiting、success、expiry、failure 与 cancellation 迁移。
   - Admit eligible QR states plus exact `saved_session/expired` reauthentication; prove every other account/method/adapter scope has zero session/browser side effects. / 允许合格 QR 状态及精确 `saved_session/expired` 重认证；证明其他账户/登录方式/adapter 范围不会产生会话/浏览器副作用。

2. **Build an isolated login-only integration / 构建隔离的仅登录集成 — implemented and 42-case focused gate passes / 已实现且 42 项专项门禁通过**
   - Reuse pinned checkout/Python verification, derived per-account paths, the account lock and bounded process-tree supervision. / 复用锁定 checkout/Python 验证、派生逐账户路径、账户锁与有界进程树监督。
   - Add a private closed parent/child protocol that reports authenticated, expired, failed or cancelled independently of process exit code. / 新增私有封闭父子协议，独立于进程退出码报告 authenticated、expired、failed 或 cancelled。
   - Force headed QR login and persistent browser state while configuring a login-only upstream mode that cannot start creator/content work. / 强制有头二维码登录与持久浏览器状态，并配置不会启动作者/内容工作的上游 login-only 模式。
   - Catch upstream `SystemExit` explicitly and reject missing, duplicate, oversized or malformed result frames. / 显式捕获上游 `SystemExit`，拒绝缺失、重复、超限或格式错误的结果帧。

3. **Compose the application and CLI / 组合应用层与 CLI — implemented; application and CLI focused gates pass / 已实现；应用与 CLI 专项门禁通过**
   - Add `media-sync account login --account-id ... --enable-mediacrawler --accept-mediacrawler-license` as a blocking host-assisted command. / 新增阻塞式主机协助命令 `media-sync account login --account-id ... --enable-mediacrawler --accept-mediacrawler-license`。
   - Add redaction-safe session/status inspection under the account command group. / 在 account 命令组下新增脱敏会话/状态查看。
   - Keep QR challenge material inside the visible upstream browser; do not extract or serialize it. / 二维码挑战材料只存在于可见上游浏览器，不提取、不序列化。
   - On success, atomically finalize the session and switch Account login method to `saved_session`; leave scheduler Job resume explicit. / 成功时原子收尾会话并把 Account 登录方式切为 `saved_session`；调度 Job 继续由操作员显式 resume。
   - For expired saved-session reauthentication, atomically enter `qr/authenticating`; restore `saved_session/authenticated` only on success and retain a retryable QR state on non-success. / 对已过期 saved-session 重认证，原子进入 `qr/authenticating`；仅成功时恢复 `saved_session/authenticated`，非成功时保留可重试 QR 状态。

4. **Make scheduled saved sessions fail closed / 让后台保存会话关闭失败 — implemented; integrated focused gate passes / 已实现；合并专项门禁通过**
   - Remove the current saved-session-to-QR fallback from the bridge. / 移除当前从 saved-session 到 QR 的回退。
   - Validate profile presence before creator traffic; distinguish unavailable saved-session state from ordinary bridge configuration errors, and conservatively map a blocked QR fallback to auth-required state without claiming an exact remote cause. / 在作者流量前验证 profile 存在性；区分 saved-session 不可用状态与普通 bridge 配置错误，并把被阻止的 QR 回退保守映射为需认证状态，但不宣称精确远端原因。
   - Prove background scheduler execution never opens a headed interactive challenge. / 证明后台调度执行绝不打开有头交互挑战。

5. **Verify and close out / 验证与收尾 — gates and secret review complete; implementation commit pending / 门禁与密钥复核已完成；实现提交待创建**
   - Add repository, login protocol, process supervision, seven-identifier contract, scheduler handoff, CLI and secret-sink tests. / 新增仓储、登录协议、进程监督、七标识 contract、调度交接、CLI 与密钥落点测试。
   - Cover deadline and Ctrl+C terminalization, expired saved-session reauthentication and ordinary-configuration versus auth-expired classification. / 覆盖截止时间与 Ctrl+C 收尾、已过期 saved-session 重认证，以及普通配置错误与 auth-expired 分类。
   - Run focused tests, full pytest, Ruff, format, mypy, docs/upstream checks, build and `git diff --check`. / 运行专项测试、完整 pytest、Ruff、格式、mypy、文档/上游检查、构建与 `git diff --check`。
   - Update all four execution records with exact commands/results and keep every live-account row `NOT_RUN`. / 用准确命令/结果更新四份执行记录，并保持全部真人账户行 `NOT_RUN`。
   - Create a bilingual local implementation commit after the complete gate. Do not push until the user gives a new explicit instruction. / 完整门禁通过后创建中英双语本地实现提交；在用户再次明确指示前不得推送。

## Administrative closeout still pending / 仍待管理性收尾

- Create and record the bilingual local implementation commit; do not claim a remote push. / 创建并记录中英双语本地实现提交；不得宣称已远端推送。
- Keep all seven live QR and saved-session reuse rows `NOT_RUN` until an operator authorizes and performs the real scan. / 在操作员授权并执行真人扫码前，七个平台的真人 QR 与 saved-session 复用行全部保持 `NOT_RUN`。
- Carry hard-parent-death LoginSession recovery/parent-liveness into the next execution; do not infer it from normal timeout, cancellation or Ctrl+C coverage. / 把父进程硬终止后的 LoginSession 回收/parent-liveness 留到下一执行；不得用正常超时、取消或 Ctrl+C 覆盖推断该能力。

## Risks and rollback points / 风险与回退点

- The upstream login implementations may terminate with `SystemExit(0)` on failure; only the closed child result is authoritative. / 上游登录失败时可能 `SystemExit(0)`；只有封闭 child 结果才是权威真值。
- A false saved-session `pong()` may reflect expiry or an upstream network ambiguity. `auth_expired` is a conservative operator action, not an exact remote-cause diagnosis; ordinary local bridge misconfiguration must remain `configuration_invalid`. / saved-session `pong()` 为 false 可能表示失效，也可能包含上游网络异常歧义。`auth_expired` 是保守运维动作，不是精确远端原因诊断；普通本地 bridge 配置错误必须保持 `configuration_invalid`。
- Normal parent paths join the process tree and terminalize durable state, but SIGKILL cannot run cleanup. Automatic stale LoginSession recovery requires a future parent-liveness protocol. / 正常父进程路径会 join 进程树并终结持久状态，但 SIGKILL 无法执行清理；自动回收 stale LoginSession 需要后续 parent-liveness 协议。
- A browser login is necessarily interactive and may wait on QR/CAPTCHA. A hard timeout, cancellation join and explicit operator invocation bound that risk; no automated CAPTCHA work is planned. / 浏览器登录天然交互，可能等待二维码/CAPTCHA；以硬超时、取消 join 与显式操作员调用限定风险，不计划自动处理 CAPTCHA。
- The initial MVP is local-host single-account coordination, not cross-host HA. If existing identities cannot fence stale completion, stop and add a migration rather than weakening the contract. / 初始 MVP 只做本地主机单账户协调，不是跨主机 HA；若既有身份无法 fencing 旧收尾，应停止并新增 migration，不能降低契约。
- A login-only upstream mode must be proven against the pinned SHA for all seven identifiers. If any platform performs content work, that platform fails closed until a narrower wrapper exists. / 必须针对锁定 SHA 为七个平台证明 login-only 模式；若某平台仍执行内容工作，该平台关闭失败，直到有更窄 wrapper。
- Rollback is deletion of the new login command/integration and restoration of saved-session rejection; existing Cookie scheduling, stored accounts and execution 0010 pipeline remain untouched. / 回退方式为移除新增登录命令/集成并恢复 saved-session 拒绝；既有 Cookie 调度、已存账户及执行 0010 pipeline 不受影响。
