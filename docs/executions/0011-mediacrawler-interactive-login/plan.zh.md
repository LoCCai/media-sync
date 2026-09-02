[English](plan.md) | **中文**

# 执行 0011 计划

- 状态：离线实现、自动验证、最终只读密钥审计及本地实现提交 `8bb16f6` 已完成；真人验收保持 `NOT_RUN`
- 计划日期：2026-08-31
- 前置：Execution 0010 commit `f2e5899`

## 交付顺序

1. **冻结状态契约 — implemented and focused gate passes / 已实现且专项门禁通过**
   - 新增类型化、封闭的登录请求/结果与固定错误码。
   - 扩展 Account/LoginSession 仓储，提供条件化 start、waiting、success、expiry、failure 与 cancellation 迁移。
   - 允许合格 QR 状态及精确 `saved_session/expired` 重认证；证明其他账户/登录方式/adapter 范围不会产生会话/浏览器副作用。

2. 构建隔离的仅登录集成 — implemented and 42-case focused gate passes / 已实现且 42 项专项门禁通过**
   - 复用锁定 checkout/Python 验证、派生逐账户路径、账户锁与有界进程树监督。
   - 新增私有封闭父子协议，独立于进程退出码报告 authenticated、expired、failed 或 cancelled。
   - 强制有头二维码登录与持久浏览器状态，并配置不会启动作者/内容工作的上游 login-only 模式。
   - 显式捕获上游 `SystemExit`，拒绝缺失、重复、超限或格式错误的结果帧。

3. 组合应用层与 CLI — implemented; application and CLI focused gates pass / 已实现；应用与 CLI 专项门禁通过**
   - 新增阻塞式主机协助命令 `media-sync account login --account-id ... --enable-mediacrawler --accept-mediacrawler-license`。
   - 在 account 命令组下新增脱敏会话/状态查看。
   - 二维码挑战材料只存在于可见上游浏览器，不提取、不序列化。
   - 成功时原子收尾会话并把 Account 登录方式切为 `saved_session`；调度 Job 继续由操作员显式 resume。
   - 对已过期 saved-session 重认证，原子进入 `qr/authenticating`；仅成功时恢复 `saved_session/authenticated`，非成功时保留可重试 QR 状态。

4. 让后台保存会话关闭失败 — implemented; integrated focused gate passes / 已实现；合并专项门禁通过**
   - 移除当前从 saved-session 到 QR 的回退。
   - 在作者流量前验证 profile 存在性；区分 saved-session 不可用状态与普通 bridge 配置错误，并把被阻止的 QR 回退保守映射为需认证状态，但不宣称精确远端原因。
   - 证明后台调度执行绝不打开有头交互挑战。

5. 验证与收尾 — gates, secret review and implementation commit complete / 门禁、密钥复核与实现提交已完成**
   - 新增仓储、登录协议、进程监督、七标识 contract、调度交接、CLI 与密钥落点测试。
   - 覆盖截止时间与 Ctrl+C 收尾、已过期 saved-session 重认证，以及普通配置错误与 auth-expired 分类。
   - 运行专项测试、完整 pytest、Ruff、格式、mypy、文档/上游检查、构建与 `git diff --check`。
   - 用准确命令/结果更新四份执行记录，并保持全部真人账户行 `NOT_RUN`。
   - 完整门禁通过后创建中英双语本地实现提交；在用户再次明确指示前不得推送。

## 管理性收尾

- 已记录中英双语本地实现提交 `8bb16f6`；不宣称已远端推送。
- 在操作员授权并执行真人扫码前，七个平台的真人 QR 与 saved-session 复用行全部保持 `NOT_RUN`。
- 把父进程硬终止后的 LoginSession 回收/parent-liveness 留到下一执行；不得用正常超时、取消或 Ctrl+C 覆盖推断该能力。

## 风险与回退点

- 上游登录失败时可能 `SystemExit(0)`；只有封闭 child 结果才是权威真值。
- saved-session `pong()` 为 false 可能表示失效，也可能包含上游网络异常歧义。`auth_expired` 是保守运维动作，不是精确远端原因诊断；普通本地 bridge 配置错误必须保持 `configuration_invalid`。
- 正常父进程路径会 join 进程树并终结持久状态，但 SIGKILL 无法执行清理；自动回收 stale LoginSession 需要后续 parent-liveness 协议。
- 浏览器登录天然交互，可能等待二维码/CAPTCHA；以硬超时、取消 join 与显式操作员调用限定风险，不计划自动处理 CAPTCHA。
- 初始 MVP 只做本地主机单账户协调，不是跨主机 HA；若既有身份无法 fencing 旧收尾，应停止并新增 migration，不能降低契约。
- 必须针对锁定 SHA 为七个平台证明 login-only 模式；若某平台仍执行内容工作，该平台关闭失败，直到有更窄 wrapper。
- 回退方式为移除新增登录命令/集成并恢复 saved-session 拒绝；既有 Cookie 调度、已存账户及执行 0010 pipeline 不受影响。
