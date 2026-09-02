[English](goal.md) | **中文**

# 执行 0012 目标

- 状态：离线单机前台范围已完成；真人验收保持 `NOT_RUN`
- 开始时间：2026-08-31 03:46 +08:00
- 完成时间：2026-08-31 04:54 +08:00
- 前置：Execution 0011 closeout commit `11ec5fd`
- 计划提交：`4494226`
- 实现提交：`28655f8`

## 结果

交付一个本机常驻、单主机的前台监督器，同时补齐 MediaCrawler 交互登录在父进程硬终止时的进程树收容，以及按截止时间回收遗留 LoginSession 状态。登录父进程被强杀后不得留下仍运行的 child/浏览器进程树；超过截止时间的遗留尝试必须无需人工修改 SQLite 即可恢复重试；一个常驻循环必须把到期调度推进到订阅同步及既有持久下载/Emby pipeline，并在停止时按当前阶段采取准确策略。

## 已交付证据边界

执行 0012 已在文档声明的本地边界内关闭前置缺口。登录 child 现使用有界请求/结果长度 frame、持续 START/CANCEL/EOF 控制及结果 guardian。Windows 与 POSIX 父进程硬终止契约证明所属 child/grandchild 树会先退出，继承账户锁才可复用；其中包括“父进程已读完结果、尚未关闭控制通道”的精确窗口。超过截止时间的持久状态可在同一账户锁与精确仓储 CAS 下协调；有界轮转枚举避免早期 busy 候选饿死后续账户。显式 `scheduler supervise` 命令公平运行协调、tick、订阅与 pipeline 阶段，并提供可承受重复取消的精确 join。

自动证据均为离线证据。Fake supervisor 集成证明持久 sync 与 pipeline Job 可在一个 cycle 内成功，但不证明真人作者流量、签名 CDN 下载、FFmpeg 对真实媒体的处理或 Emby/Jellyfin 重扫/播放。该进程仍是本地前台命令，不是 daemon 化、自动重启、操作系统服务、Docker 或跨主机 HA。

## 验收

1. **启动受控的父子协议** 登录 child 仅接受一个有界、带版本的请求 frame，并在导入上游代码或产生浏览器/profile 副作用前等待独立 START 控制。父进程持续保持控制流；显式 CANCEL、意外 EOF、非法控制与初始化失败均关闭失败。
2. **父进程硬终止收容** 在 POSIX 与 Windows 上，父进程死亡后，其拥有的登录 child 及后代树会在有界时间内退出。Windows 保留外层 kill-on-close Job 并增加 child 自持的后代收容；POSIX 不得误杀环境进程组。所属进程树存活时账户锁不可获取，完整退出后才可复用。
3. **精确截止时间回收** 仅当前 MediaCrawler `pending|waiting_user` 会话在 `expires_at <= now` 且精确 Account 仍为 `qr/authenticating` 时，才可原子改为 `expired` 与 `qr/required`。回收只能在持有同一个逐账户文件锁时运行，必须幂等并受 CAS fencing 保护，拒绝状态/账户/兄弟会话漂移，不依赖 PID 信任，也不要求 schema migration。
4. **可达的自愈路径** 登录启动与脱敏登录状态查询会先协调合格的过期尝试；常驻监督器也会扫描合格账户。之后新登录只能创建一个继任会话，旧尝试的迟到收尾不得覆盖继任者。本执行明确不宣称在持久截止时间前回收。
5. **常驻全链边界** 新增一个显式本地前台监督命令，公平循环执行 stale-login 协调、有界 schedule 物化、有界订阅同步及有界 `pipeline.subscription` 工作，并沿用 MediaCrawler/下载启用与许可证 gate。Fake 端到端路径无需另行调用 `scheduler run` 或 `pipeline run` 即可到达 pipeline 成功。循环限制与间隔必须有界且经过校验。
6. **分阶段准确停止** 停止请求会阻止之后全部 tick 与 claim。进行中的订阅 task 会被取消并等待，使其 MediaCrawler 父进程控制路径完整 join child 树。进行中的线程型 pipeline 尝试不会被虚假取消：heartbeat 持续，监督器等待这一项尝试得到权威结果后退出，不再领取下一项。操作员第二次强制中断及硬杀后的恢复继续由 lease fencing 处理，不冒充优雅完成。
7. **真实排除项** 该命令是本地前台进程，不包含自动重启、daemon 化、Windows Service/systemd 集成、Docker 或跨主机 HA。REST 及真人浏览器/账户/平台/CDN/Emby/Jellyfin 验收均不属于本执行；七个平台真人行保持 `NOT_RUN`。
8. **封闭可观察性与验证** CLI 输出、SQLite、日志、文档与 Git 不得包含二维码字节、Cookie、上游原始输出、token 或 profile 路径。只有专项竞态/进程/CLI 测试、完整套件、lint、格式、类型、文档/上游检查、构建及保留产物/密钥审计均通过后，才能宣称完成。

## 回收时机决策

保留的登录顺序会先释放账户锁，再由应用层写入 LoginSession/Account 最终迁移。因此执行 0012 使用持久会话截止时间作为回收权威，绝不把“当前锁可获取”当作遗弃证明。错过持久截止时间的认证结果仍按超时处理，不会因 child 已完成而获得额外权威。
