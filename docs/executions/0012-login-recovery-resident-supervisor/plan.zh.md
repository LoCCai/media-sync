[English](plan.md) | **中文**

# 执行 0012 计划

- 状态：已执行；全部冻结验收边界均保留
- 计划日期：2026-08-31
- 完成日期：2026-08-31
- 前置：Execution 0011 closeout commit `11ec5fd`
- 计划提交：`4494226`
- 实现提交：`28655f8`

## 交付顺序

1. **冻结契约与基线**
   - 实现前记录四份中英双语执行文档，并修正路线图中仍要求创建已完成 0011 提交的陈旧内容。
   - 重跑既有通用父进程硬终止测试，以及登录正常超时/取消测试，作为起始基线。
   - 创建中英双语本地计划提交；没有用户新的明确指令不得推送。

2. **让登录持续受父进程控制**
   - 复用或抽取定时 MediaCrawler runner 已成熟的固定控制原语，不定义不兼容协议。
   - 把以 EOF 定界的登录输入改为一个有界请求 frame 加 START/CANCEL/EOF 控制；START 前先附加父侧收容，并在导入上游模块前建立 child 侧收容与控制监视。交付协议还会对结果做长度 framing，从而避免 Windows 在 guardian 仍存活时依赖标准管道 EOF。
   - 保持正常完成、超时、取消路径先 join 再释放锁，并通过真实所属 child/grandchild 契约证明父进程硬终止清理。

3. **增加受截止时间保护的持久协调**
   - 新增一个仓储事务，先验证精确 Account 与 active LoginSession 元组，再原子过期会话并恢复 `qr/required`。
   - 新增应用协调器：只枚举公开候选身份，获取每个精确逐账户锁，并在锁内重复仓储验证，只报告固定、脱敏的计数/状态。
   - 在登录预检/状态决策前及常驻监督器中调用协调器；覆盖截止边界、状态/账户/profile 漂移、重复竞争者、幂等、继任 fencing 与事务回滚。

4. **增加有界全链常驻监督器**
   - 把循环放入可注入时钟/等待原语的应用或服务对象，使 tick、空闲与停止行为在测试中确定可复现。
   - 暴露 `scheduler supervise`，提供有界空闲间隔、物化量、同步量与 pipeline 容量，并沿用 MediaCrawler 与下载/许可证 gate。公平 cycle 依次协调过期登录、tick、运行订阅工作及 pipeline 工作，避免任一 backlog 饿死另一侧。
   - Ctrl+C 或终止时停止后续 tick/claim；进行中的订阅 task 通过 child-control/join 契约取消并等待；若线程型 pipeline 尝试正在运行，则持续 heartbeat，仅等待该项收尾后返回。

5. **验证、记录并提交**
   - 运行仓储、应用、协议、进程、监督器与 CLI 专项门禁，并在本 Windows 主机执行专属 hard-kill 行为。
   - 运行完整 pytest、Ruff lint/格式、mypy、文档与锁定上游检查、构建、`git diff --check`、跟踪/runtime 产物检查及高置信密钥扫描。
   - 用准确命令与结果更新目标/计划/推进/验证文档，全部真人行保持 `NOT_RUN`，再创建中英双语本地实现与收尾提交。

## 实现记录

- Windows 即使在 child 关闭 CRT 描述符 1 后，也会把标准 stdout 管道保留到进程退出。因此结果通道升级为精确 4 字节大端长度加有界 JSON payload。父进程读完一个完整 frame 后立即开始控制/进程树关停，并在 join 后拒绝任何剩余字节；这样无需 guardian 退出即可保留单 frame 契约。
- 审查发现 `(expires_at, id) LIMIT` 枚举可能让一个永久 busy 的早期账户饿死后续候选。交付的协调器为全局 sweep 保留串行化轮转 keyset 游标，到尾部回绕；精确单账户协调不使用该游标。
- 审查还发现：在停止已触发 shield drain 后取消 supervisor task，可能遗留线程型 pipeline 尝试。订阅 cancel/join 与 pipeline drain 现可承受重复 task cancellation，并只在精确 attempt 完成后传播第一次调用方取消。

## 风险与回退点

- Windows stdin 监视必须使用既有原生管道读取方式；竞争性的缓冲读取可能阻塞后代进程启动。
- START 握手只能在父/child 收容前置均就绪后发生；attach/初始化失败必须是关闭的启动失败，绝不能成为启动上游工作的许可。
- 截止时间回收以延迟即时重试换取竞态安全；缩短截止时间或仅凭锁空闲回收不属于冻结契约。
- 既有订阅 worker 的取消是协作式，且其 MediaCrawler handler 具备父进程控制/join 边界。同步 pipeline handler 无法被强停，因此停止时必须在 heartbeat 下等待一项 active attempt 收尾，不能取消其 asyncio wrapper 或立即释放为重复重试。
- 回退方式为移除新增监督器、协调器与控制 framing，同时保留执行 0011 的有界命令与状态机；既有账户、订阅、Job 与 pipeline 记录无需破坏性迁移。
