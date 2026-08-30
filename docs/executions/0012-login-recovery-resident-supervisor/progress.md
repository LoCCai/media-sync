# Execution 0012 progress / 执行 0012 推进结果

- Status / 状态：Implementation and offline closeout complete / 实现与离线收尾已完成
- Started / 开始时间：2026-08-31 03:46 +08:00
- Completed / 完成时间：2026-08-31 04:54 +08:00
- Plan commit / 计划提交：`4494226`
- Implementation commit / 实现提交：`28655f8`

## Completed / 已完成

- Audited the login runner, LoginSession repository/application flow, generic MediaCrawler parent-control implementation, Windows Job behavior and current bounded scheduler/pipeline CLI surfaces. No source files were changed during the audit. / 已审计登录 runner、LoginSession 仓储/应用流程、通用 MediaCrawler 父进程控制实现、Windows Job 行为及当前有界 scheduler/pipeline CLI；审计期间未修改源码。
- Located the critical persisted-state gap: hard parent death can leave `waiting_user` plus `qr/authenticating`, while current active-session lookup ignores `expires_at`. / 已定位关键持久状态缺口：父进程硬终止可能遗留 `waiting_user` 与 `qr/authenticating`，当前 active-session 查询不会处理 `expires_at`。
- Located the lock/finalization ordering constraint: the runner releases the account lock before the application writes the terminal database transition. Recovery is therefore frozen to `expires_at <= now`, not mere lock availability. / 已定位锁与收尾顺序约束：runner 会在应用写入数据库终态前释放账户锁，因此回收边界冻结为 `expires_at <= now`，不能仅凭锁可获取。
- Re-ran the predecessor process baseline: three generic hard-parent-death plus login timeout/cancellation cases pass. / 已重跑前置进程基线：通用父进程硬终止及登录超时/取消共三项通过。
- Replaced EOF-delimited login input with a 4-byte big-endian request length, bounded payload and independent START/CANCEL/EOF control. Parent containment attaches before START; child containment and control watching exist before upstream import. / 已把 EOF 定界登录输入替换为 4 字节大端请求长度、有界 payload 及独立 START/CANCEL/EOF 控制；父侧收容在 START 前附加，child 收容与控制监听在导入上游前建立。
- Added the corresponding bounded result length frame. The parent can receive the authoritative result while the child guardian remains alive, then close control, join the entire tree and reject any appended bytes. This avoids the Windows standard-pipe EOF dependency and removes exit-code authority from an authenticated result. / 已增加对应的有界结果长度 frame。父进程可在 child guardian 仍存活时收到权威结果，再关闭控制通道、join 完整树并拒绝追加字节；这避免依赖 Windows 标准管道 EOF，也移除了进程退出码对已认证结果的权威性。
- Added child-owned Windows Job/POSIX process-group supervision plus a post-result guardian. A deterministic real child/grandchild contract hard-kills the parent after result receipt but before control close and proves the complete tree exits before the inherited account lock can be reacquired. / 已增加 child 自持 Windows Job/POSIX 进程组监督及结果 guardian。确定性的真实 child/grandchild 契约会在父进程收到结果但尚未关闭控制通道时硬杀父进程，并证明完整树会先退出，继承账户锁才可重新获取。
- Added exact expired-session candidate enumeration and atomic recovery. Repository CAS revalidates session identity/status/method/challenge/deadline, Account adapter/platform/login/auth/credential/profile state and active siblings, rolling back both rows on any drift. / 已增加精确过期会话候选枚举与原子回收。仓储 CAS 会重新验证会话身份/状态/method/challenge/截止时间、Account adapter/平台/登录/认证/credential/profile 状态及 active sibling；任一漂移都会回滚两行。
- Added the public `MediaCrawlerAccountLock` boundary and application reconciler. Global sweeps use a serialized rotating `(expires_at, id)` cursor so busy/conflicted early candidates cannot starve later accounts; exact account reconciliation does not share that cursor. Login start, login status and the resident supervisor all reach the reconciler. / 已增加公共 `MediaCrawlerAccountLock` 边界与应用协调器。全局 sweep 使用串行化轮转 `(expires_at, id)` 游标，避免 busy/conflicted 早期候选饿死后续账户；精确账户协调不共享该游标。登录启动、登录状态及常驻监督器均可到达协调器。
- Added `media-sync scheduler supervise` with bounded configuration and stable per-process worker identities. Each fair cycle runs stale-login sweep, scheduler tick, subscription sync and pipeline work. The Fake SQLite integration reaches succeeded sync and pipeline Jobs in one cycle without separate bounded worker commands. / 已增加具备有界配置与稳定逐进程 worker 身份的 `media-sync scheduler supervise`。每个公平 cycle 依次运行 stale-login sweep、scheduler tick、订阅同步与 pipeline 工作。Fake SQLite 集成无需单独调用有界 worker 命令，即可在一个 cycle 内得到成功的 sync 与 pipeline Job。
- Implemented phase-correct shutdown. The first signal requests cooperative stop; a repeated signal force-exits with `128 + signal`. Subscription work is cancelled and joined; one already-active thread-backed pipeline attempt stays heartbeat-protected and drains exactly. Both joins tolerate repeated task cancellation and propagate the first caller cancellation only after the exact attempt is done. / 已实现分阶段准确关停。第一次信号请求协作停止；重复信号以 `128 + signal` 强制退出。订阅工作会取消并 join；一项已经 active 的线程型 pipeline 尝试会保持 heartbeat 并精确等待结束。两条 join 都可承受重复 task cancellation，只在精确 attempt 完成后传播第一次调用方取消。
- Completed the root integrated focused gate, full suite, Ruff, format, mypy, documentation/upstream checks, build, patch check and retained artifact/secret audits. Exact evidence is in `verification.md`. / 已完成根任务合并专项、完整套件、Ruff、格式、mypy、文档/上游检查、构建、补丁检查及保留产物/密钥审计；准确证据见 `verification.md`。

## Deviations and decisions / 偏差与决策

- The resident loop includes pipeline work for a functional full chain, but shutdown will drain one already-active synchronous attempt under heartbeat instead of claiming that asyncio cancellation stopped its worker thread. / 为交付可用的全链，常驻循环包含 pipeline 工作；但停止时会在 heartbeat 下等待一项已 active 的同步尝试收尾，不会声称 asyncio cancellation 已停止其 worker thread。
- No schema migration or PID ownership column is planned. Exact durable identities, deadline CAS and the existing per-account filesystem lock are sufficient for the frozen single-host boundary. / 不计划 schema migration 或 PID 所有权字段；精确持久身份、截止时间 CAS 与既有逐账户文件锁足以覆盖冻结的单主机边界。
- Windows does not deliver EOF for its standard stdout pipe while the guardian process remains alive, even after CRT descriptor 1 closes. The result protocol therefore uses explicit bounded length framing; process exit and standard-pipe EOF are not result boundaries. / Windows 在 guardian 进程仍存活时，即使关闭 CRT 描述符 1，也不会为标准 stdout 管道交付 EOF。因此结果协议使用显式有界长度 framing；进程退出与标准管道 EOF 都不是结果边界。
- Recovery authority remains strictly `expires_at <= now`. A missing runtime account directory is unavailable rather than auto-created, and lock availability by itself never proves abandonment. / 回收权威严格保持为 `expires_at <= now`。缺失的 runtime 账户目录会保持不可用而不是自动创建；仅凭锁可获取绝不证明遗弃。
- Real QR/account/platform/CDN/Emby behavior is not inferred from offline process tests. All live qualification remains `NOT_RUN`. / 不用离线进程测试推断真人二维码/账户/平台/CDN/Emby 行为；全部真人资格验证保持 `NOT_RUN`。

## Remaining outside execution 0012 / 执行 0012 范围外待完成

- Real QR/account/creator/CDN and Emby/Jellyfin qualification for all seven platforms remains `NOT_RUN` and requires user-authorized accounts plus human interaction where applicable. / 七个平台的真人二维码/账户/作者/CDN 与 Emby/Jellyfin 验收保持 `NOT_RUN`，需要用户授权账户，并在适用时进行真人交互。
- Automatic restart, Windows Service/systemd integration, Docker, REST, distributed HA and forced termination of synchronous pipeline threads remain future product work. / 自动重启、Windows Service/systemd 集成、Docker、REST、分布式 HA 及同步 pipeline 线程强制终止仍属于后续产品工作。
- Additional playable media shapes—especially Bilibili video beyond the currently supported cover—remain later functional slices. / 更多可播放媒体形状，尤其是当前仅支持封面的 Bilibili 视频，仍属于后续功能切片。
