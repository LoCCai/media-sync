# Execution 0012 progress / 执行 0012 推进结果

- Status / 状态：Plan frozen; implementation not started / 计划已冻结；尚未开始实现
- Started / 开始时间：2026-08-31 03:46 +08:00

## Completed / 已完成

- Audited the login runner, LoginSession repository/application flow, generic MediaCrawler parent-control implementation, Windows Job behavior and current bounded scheduler/pipeline CLI surfaces. No source files were changed during the audit. / 已审计登录 runner、LoginSession 仓储/应用流程、通用 MediaCrawler 父进程控制实现、Windows Job 行为及当前有界 scheduler/pipeline CLI；审计期间未修改源码。
- Located the critical persisted-state gap: hard parent death can leave `waiting_user` plus `qr/authenticating`, while current active-session lookup ignores `expires_at`. / 已定位关键持久状态缺口：父进程硬终止可能遗留 `waiting_user` 与 `qr/authenticating`，当前 active-session 查询不会处理 `expires_at`。
- Located the lock/finalization ordering constraint: the runner releases the account lock before the application writes the terminal database transition. Recovery is therefore frozen to `expires_at <= now`, not mere lock availability. / 已定位锁与收尾顺序约束：runner 会在应用写入数据库终态前释放账户锁，因此回收边界冻结为 `expires_at <= now`，不能仅凭锁可获取。
- Re-ran the predecessor process baseline: three generic hard-parent-death plus login timeout/cancellation cases pass. / 已重跑前置进程基线：通用父进程硬终止及登录超时/取消共三项通过。

## Deviations and decisions / 偏差与决策

- The resident loop includes pipeline work for a functional full chain, but shutdown will drain one already-active synchronous attempt under heartbeat instead of claiming that asyncio cancellation stopped its worker thread. / 为交付可用的全链，常驻循环包含 pipeline 工作；但停止时会在 heartbeat 下等待一项已 active 的同步尝试收尾，不会声称 asyncio cancellation 已停止其 worker thread。
- No schema migration or PID ownership column is planned. Exact durable identities, deadline CAS and the existing per-account filesystem lock are sufficient for the frozen single-host boundary. / 不计划 schema migration 或 PID 所有权字段；精确持久身份、截止时间 CAS 与既有逐账户文件锁足以覆盖冻结的单主机边界。
- Real QR/account/platform/CDN/Emby behavior is not inferred from offline process tests. All live qualification remains `NOT_RUN`. / 不用离线进程测试推断真人二维码/账户/平台/CDN/Emby 行为；全部真人资格验证保持 `NOT_RUN`。

## Remaining / 待完成

- Create and record the bilingual local plan commit. / 创建并记录中英双语本地计划提交。
- Implement and verify the login request/control protocol and hard-parent-death cleanup. / 实现并验证登录请求/控制协议与父进程硬终止清理。
- Implement and verify deadline-fenced LoginSession reconciliation. / 实现并验证受截止时间保护的 LoginSession 协调。
- Implement and verify the fair full-chain resident scheduler supervisor and phase-correct cooperative shutdown. / 实现并验证公平的全链常驻调度监督器与分阶段准确停止。
- Run complete gates, update all four records and create bilingual local implementation/closeout commits. / 运行完整门禁，更新四份记录，并创建中英双语本地实现/收尾提交。
