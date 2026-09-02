[English](goal.md) | **中文**

# 执行 0011 目标

- 状态：离线实现与自动验证范围已在本地提交 `8bb16f6` 完成；全部真人行保持 `NOT_RUN`
- 开始时间：2026-08-31 02:17 +08:00
- 前置：Execution 0010 commit `f2e5899`

## 结果

为一个精确的初始 QR 账户或已过期 saved-session 账户交付显式、由主机用户协助的 MediaCrawler 二维码登录命令。只有操作员在本次调用中启用 MediaCrawler 并确认许可证后，命令才可打开使用账户隔离 profile 的有头上游浏览器。该流程只记录可脱敏观察的 `LoginSession` 与账户认证状态，不抓取作者/内容，并在成功后把本次尝试原子交接为供后续调度使用的 `saved_session`。

## 当前证据边界

实现已记录在中英双语本地提交 `8bb16f6`。当前离线专项证据覆盖仓储状态机（`32 passed`）、应用编排（`33 passed`）、仓储/应用/登录模型组合（`83 passed`）、仅登录集成（`42 passed`）、saved-session 审计（`25 passed`）、CLI 控制面（`77 passed`），以及登录/saved-session/调度/下载合并切片（`274 passed`）。完整套件通过 `1080` 项，另有 1 项 Windows 不适用的 POSIX mode-bit 测试跳过；不宣称运行过覆盖率。这些检查没有使用浏览器、真人平台账户、作者端点、CDN 或媒体服务器。

## 验收

1. **默认关闭与精确范围** 未同时提供两个 MediaCrawler gate 时不启动 child；账户必须存在、使用 MediaCrawler adapter，且为合格 QR 账户或精确的 `saved_session/expired`。Cookie、手机号、已认证/未过期 saved-session 及其他 adapter 账户在浏览器或会话变更前拒绝。
2. **仅登录的有头 child** 验证锁定 checkout 与 Python runtime；浏览器 profile 与账户锁仅由平台及账户 UUID 派生；上游 child 强制有头并保存登录状态。七个平台标识的协议测试证明作者/search/detail/comment/media/store/ingestion 工作均为零。
3. **持久可观察状态** `LoginSession` 遵循 `pending → waiting_user → succeeded|expired|failed|cancelled`；初始 QR 状态与精确 `saved_session/expired` 重认证会原子进入 `qr/authenticating`。成功变为 `saved_session/authenticated`；过期/取消/失败会终结 session，并让账户保持可重试 QR 状态。CLI 固定输出只暴露 ID、状态与时间。
4. **受保护的交接** runner 持有逐账户锁期间，同一本地账户只允许一个登录进程树；数据库收尾通过仓储 CAS 仅接受仍为当前的会话。成功只保留派生的稳定 profile，原子地把 QR 改为 `saved_session`，并允许既有 `qr_required` 调度 Job 经现有显式 resume 控制继续，而不再次要求二维码。截止时间与 Ctrl+C 路径会终结仍归本次尝试所有的 session，不留下正常路径僵尸状态。执行 0012 审计更正了此前措辞：runner 会先 join 进程树并释放锁，再由应用写入数据库终态；执行 0011 未在该间隔实现 stale 回收。
5. **保存会话失效时关闭失败** 派生 profile 缺失或认证探测进入被阻止的 QR 回退时，会保守映射为固定 `auth_expired`/`waiting_auth`；普通 bridge 配置错误保持 `configuration_invalid`。上游 `pong() == false` 可能包含网络异常歧义，因此不宣称精确远端原因。后台调度绝不静默打开交互浏览器。
6. **显式 child 真值** 登录 child 输出封闭结果协议；上游 `SystemExit`（包括登录失败却返回零退出码）不得被误判为成功。
7. **取消与保密** 在父进程仍存活时，超时/取消/Ctrl+C 会在释放账户锁前终止并 join child 进程树，并记录可恢复的固定状态。二维码字节/token、Cookie、原始 child stdout/stderr 与本地 profile 路径不得进入 SQLite、CLI 输出、日志、文档或 Git。本执行不宣称能自动回收 SIGKILL 等父进程硬终止。
8. **真实验收边界** 离线 fake-child 可验收七个平台标识的本地协议，但在用户授权扫码前，所有真人账户二维码行保持 `NOT_RUN`。手机号登录、验证码绕过、REST、daemon、Docker、父进程硬终止后的登录回收、内容同步及平台媒体扩展不属于本执行。

## Schema 决策

初始复用既有 `accounts` 与 `login_sessions` 列；本地单账户排他由既有逐账户文件锁承担，仓储状态迁移使用基于当前状态的条件更新。仅当实现证明现有身份无法安全表达所需 fencing 时才新增 migration。
