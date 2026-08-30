# Execution 0011 progress / 执行 0011 推进结果

- Status / 状态：Planned / 计划中
- Started / 开始时间：2026-08-31 02:17 +08:00
- Predecessor / 前置：Execution 0010 commit `f2e5899`

## Completed / 已完成

- Audited requirements AUTH-003/AUTH-005 and the current QR/saved-session scheduler path. / 已审计需求 AUTH-003/AUTH-005 与当前 QR/saved-session 调度路径。
- Confirmed the current scheduler deliberately returns `qr_required` before launching a QR child, so no real QR login entry point exists yet. / 已确认当前调度器会在启动 QR child 前直接返回 `qr_required`，因此尚无真实二维码登录入口。
- Confirmed the existing Account/LoginSession schema, per-account profile derivation, account lock, checkout/Python verification and process-tree supervision are reusable starting points. / 已确认既有 Account/LoginSession schema、逐账户 profile 派生、账户锁、checkout/Python 验证及进程树监督可作为复用起点。
- Identified two fail-closed requirements: upstream login failure may use `SystemExit(0)`, and saved-session currently maps to QR fallback. / 已识别两项关闭失败要求：上游登录失败可能使用 `SystemExit(0)`，且 saved-session 当前映射到 QR 回退。

## Deviations and decisions / 偏差与决策

- Prioritize an explicit host-assisted `account login` control surface before a resident daemon or REST API because it unlocks the user-facing authentication path while keeping interactive authority visible. / 在常驻 daemon 或 REST API 前优先交付显式主机协助 `account login` 控制面，以解锁用户可用认证链，同时保持交互授权可见。
- The login command handles QR accounts only. Cookie references already have a non-interactive path; phone remains unsupported; saved sessions are consumed by scheduling rather than recreated through this command. / 登录命令只处理二维码账户；Cookie 引用已有非交互路径；手机号仍不支持；saved session 由调度消费，而不是通过本命令重建。
- Do not serialize QR images or tokens. The user scans the upstream headed browser directly. / 不序列化二维码图片或 token；用户直接扫描上游有头浏览器。

## Remaining / 待完成

- Implement repository state transitions and application service. / 实现仓储状态迁移与应用服务。
- Implement login-only child protocol and supervised runner. / 实现仅登录 child 协议与受监督 runner。
- Wire CLI, saved-session handoff and fail-closed scheduler behavior. / 接通 CLI、saved-session 交接与调度关闭失败行为。
- Run focused/full gates and record exact evidence. / 运行专项/完整门禁并记录准确证据。
- Real-account QR scans for all platforms remain `NOT_RUN`. / 所有平台真人账户二维码扫码保持 `NOT_RUN`。
