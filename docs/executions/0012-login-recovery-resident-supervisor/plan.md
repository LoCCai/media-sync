# Execution 0012 plan / 执行 0012 计划

- Status / 状态：Frozen before implementation / 实现前已冻结
- Plan date / 计划日期：2026-08-31
- Predecessor / 前置：Execution 0011 closeout commit `11ec5fd`

## Delivery sequence / 交付顺序

1. **Freeze contracts and baseline / 冻结契约与基线**
   - Record all four bilingual execution files before implementation and correct the roadmap entry that still asks for the already-created 0011 commit. / 实现前记录四份中英双语执行文档，并修正路线图中仍要求创建已完成 0011 提交的陈旧内容。
   - Re-run the existing generic hard-parent-death and login normal timeout/cancellation tests as the starting baseline. / 重跑既有通用父进程硬终止测试，以及登录正常超时/取消测试，作为起始基线。
   - Create a bilingual local plan commit; do not push without a new explicit user instruction. / 创建中英双语本地计划提交；没有用户新的明确指令不得推送。

2. **Keep login under continuing parent control / 让登录持续受父进程控制**
   - Reuse or extract the mature fixed control primitives from the scheduled MediaCrawler runner rather than defining an incompatible protocol. / 复用或抽取定时 MediaCrawler runner 已成熟的固定控制原语，不定义不兼容协议。
   - Replace EOF-delimited login input with one bounded request frame plus START/CANCEL/EOF control. Attach parent-side containment before START and establish child-side containment/control watching before importing upstream modules. / 把以 EOF 定界的登录输入改为一个有界请求 frame 加 START/CANCEL/EOF 控制；START 前先附加父侧收容，并在导入上游模块前建立 child 侧收容与控制监视。
   - Preserve join-before-lock-release for normal completion, timeout and cancellation, and prove true hard-parent-death cleanup with an owned child/grandchild contract. / 保持正常完成、超时、取消路径先 join 再释放锁，并通过真实所属 child/grandchild 契约证明父进程硬终止清理。

3. **Add deadline-fenced durable reconciliation / 增加受截止时间保护的持久协调**
   - Add one repository transaction that validates the exact Account and active LoginSession tuple before atomically expiring the session and restoring `qr/required`. / 新增一个仓储事务，先验证精确 Account 与 active LoginSession 元组，再原子过期会话并恢复 `qr/required`。
   - Add an application reconciler that enumerates only public candidate identities, acquires each exact per-account lock, repeats repository validation inside the lock, and reports fixed redaction-safe counts/states. / 新增应用协调器：只枚举公开候选身份，获取每个精确逐账户锁，并在锁内重复仓储验证，只报告固定、脱敏的计数/状态。
   - Invoke the reconciler before login preflight/status decisions and from the resident supervisor. Cover deadline edges, state/account/profile drift, duplicate contenders, idempotency, successor fencing and transaction rollback. / 在登录预检/状态决策前及常驻监督器中调用协调器；覆盖截止边界、状态/账户/profile 漂移、重复竞争者、幂等、继任 fencing 与事务回滚。

4. **Add the bounded full-chain resident supervisor / 增加有界全链常驻监督器**
   - Put the loop in an application/service object with an injected clock/wait primitive so tick, idle and shutdown behavior are deterministic in tests. / 把循环放入可注入时钟/等待原语的应用或服务对象，使 tick、空闲与停止行为在测试中确定可复现。
   - Expose `scheduler supervise` with bounded idle interval/materialization/sync/pipeline capacities and the existing MediaCrawler plus download/license gates. Fair cycles reconcile expired logins, tick, run subscription work and then pipeline work so either backlog cannot starve the other. / 暴露 `scheduler supervise`，提供有界空闲间隔、物化量、同步量与 pipeline 容量，并沿用 MediaCrawler 与下载/许可证 gate。公平 cycle 依次协调过期登录、tick、运行订阅工作及 pipeline 工作，避免任一 backlog 饿死另一侧。
   - On Ctrl+C or termination, stop later ticks/claims. Cancel and await an active subscription task through its child-control/join contract; if the thread-backed pipeline attempt is active, continue its heartbeat and drain only that attempt before returning. / Ctrl+C 或终止时停止后续 tick/claim；进行中的订阅 task 通过 child-control/join 契约取消并等待；若线程型 pipeline 尝试正在运行，则持续 heartbeat，仅等待该项收尾后返回。

5. **Verify, document and commit / 验证、记录并提交**
   - Run focused repository/application/protocol/process/supervisor/CLI gates and exercise Windows-specific hard-kill behavior on this host. / 运行仓储、应用、协议、进程、监督器与 CLI 专项门禁，并在本 Windows 主机执行专属 hard-kill 行为。
   - Run full pytest, Ruff lint/format, mypy, documentation and pinned-upstream checks, build, `git diff --check`, tracked/runtime artifact checks and a high-confidence secret scan. / 运行完整 pytest、Ruff lint/格式、mypy、文档与锁定上游检查、构建、`git diff --check`、跟踪/runtime 产物检查及高置信密钥扫描。
   - Update goal/plan/progress/verification with exact commands and results, retain every live row as `NOT_RUN`, then create bilingual local implementation and closeout commits. / 用准确命令与结果更新目标/计划/推进/验证文档，全部真人行保持 `NOT_RUN`，再创建中英双语本地实现与收尾提交。

## Risks and rollback points / 风险与回退点

- Windows stdin monitoring must use the existing native pipe-read approach; competing buffered reads can block descendant spawning. / Windows stdin 监视必须使用既有原生管道读取方式；竞争性的缓冲读取可能阻塞后代进程启动。
- A START handshake must occur only after all parent and child containment prerequisites are ready. Attach/setup failure is a closed start failure, never permission to launch upstream work. / START 握手只能在父/child 收容前置均就绪后发生；attach/初始化失败必须是关闭的启动失败，绝不能成为启动上游工作的许可。
- Deadline recovery deliberately trades immediate retry for race safety. Shortening the deadline or reclaiming merely because a lock is free is outside the frozen contract. / 截止时间回收以延迟即时重试换取竞态安全；缩短截止时间或仅凭锁空闲回收不属于冻结契约。
- Cancellation of the existing subscription worker is cooperative and its MediaCrawler handler owns a parent-control/join boundary. A synchronous pipeline handler cannot be force-stopped, so shutdown must drain one active attempt under heartbeat instead of cancelling its asyncio wrapper or releasing an immediate duplicate retry. / 既有订阅 worker 的取消是协作式，且其 MediaCrawler handler 具备父进程控制/join 边界。同步 pipeline handler 无法被强停，因此停止时必须在 heartbeat 下等待一项 active attempt 收尾，不能取消其 asyncio wrapper 或立即释放为重复重试。
- Rollback is removal of the new supervisor/reconciler/control framing while retaining execution 0011 bounded commands and state machine. Existing accounts, subscriptions, Jobs and pipeline records require no destructive migration. / 回退方式为移除新增监督器、协调器与控制 framing，同时保留执行 0011 的有界命令与状态机；既有账户、订阅、Job 与 pipeline 记录无需破坏性迁移。
