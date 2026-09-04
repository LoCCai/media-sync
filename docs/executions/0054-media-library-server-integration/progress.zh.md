[English](progress.md) | **中文**

# 执行 0054 推进结果

- 状态：阶段 A 已交付并完成冻结验证；执行 0054 继续为阶段 B 保持开启
- 收尾日期：2026-09-05
- 基线：`22b5864`
- 计划与加固提交：`793d33b`、`d913537`
- 实现提交：`554277c`、`efdb27c`、`2ad051c`、`1b34632`
- 数据库 revision：`0007_media_server_operations`

## 已交付

1. 恢复推进前先 fetch `origin/main`；本地与远端 `main` 均为 `d913537`，没有待合并的远端变化，也没有覆盖保留中的实现工作树。
2. 新增按作者 UUID 寻址的受管媒体树检查，权威来源是数据库成功发布链加严格 manifest。它使用 existing-only 锁、进程级 single-flight、绑定 manifest 的 HMAC cursor、最多 128 文件的分页、字节/截止时间预算，以及彼此独立的新鲜度/完整性状态，不暴露宿主路径或非受管名称。
3. 加固跨平台文件身份：POSIX 使用稳定目录描述符与 `O_NOFOLLOW`，Windows 持有禁止 delete-share 的句柄。Manifest 与受管文件都要求描述符/名称身份一致及单硬链接；非零末页也不再把局部检查升级为整树 `complete`。
4. 新增全有或全无、由环境变量托管的单个 Emby/Jellyfin 配置，提供安全摘要与默认关闭的操作门。启动校验会规范化 origin/网络策略并隐藏被拒绝的配置输入。
5. 新增 provider-neutral connector：强制全部 DNS 答案符合 CIDR、固定连接 IP、保留 Host/TLS SNI、禁用代理和重定向、固定 probe/定向刷新路由，并实行绝对截止时间与 connector single-flight。API key 只在请求边界解析；动态 `httpx`/`httpcore.*` 日志在请求作用域脱敏，并精确恢复先前 LogRecord factory。
6. 新增持久 `media-server-probe`、`media-server-scan` Operation 及 revision `0007`。Probe/scan 共用配置互斥域；scan 绝不回退 `/Library/Refresh`。取消只能在 dispatch 前胜出；dispatch 后 timeout、取消、断连、清理或响应歧义统一成为 terminal、不可重试的 `media_server_scan_acceptance_unknown`。
7. 完成最终 scan 持久化与取消的线性化。权威最终读取会保留 SQLite writer，并编译为 PostgreSQL `SELECT ... FOR UPDATE`：cancel-first 转为 acceptance-unknown，final-lock-first 则保留成功，后到取消不能改写。重启对账继续保守标为 `interrupted`，且 scan 的中断不可重试。
8. 新增 `GET /api/v1/library/{author_id}`、`GET /api/v1/media-server`、`POST /api/v1/media-server/probe`、`POST /api/v1/media-server/scan` 与 `GET /api/v1/qualifications`。状态和证据只取当前配置作用域，并使用封闭白名单 payload。
9. 升级 Library、Settings 与 Jobs 页面，支持媒体树分页、脱敏配置、资格证据及持久 probe/scan 活动。请求代际阻止迟到响应覆盖当前状态；Settings 使用独立故障域；Jobs 在上一轮请求仍 active 时跳过轮询。
10. 更新部署、架构、运维、安全与能力文档。浏览器 smoke 覆盖未配置服务器时的 Library、Settings、Jobs、禁用 probe/scan、准确 `NOT_RUN`/`NOT_IMPLEMENTED` 标签，以及请求体覆盖远端目标时的 422 拒绝。

## 审查加固

多轮独立审查发现并关闭了分页范围虚高、祖先/manifest 替换竞态、配置错误泄密、反射服务器字段、非绝对 timeout、POST 取消/清理歧义、旧配置证据串用、重启 scan 可重试、动态 logger 泄密、遗留 worker 增长、Web 迟到响应覆盖、Settings 故障域耦合及 Jobs 轮询自我饿死。最终跨数据库审查又发现取消/成功收尾窗口，并通过上述锁定权威读取关闭。Connector 与 CAS 复核在阶段 A 交付范围内没有发现剩余 P0/P1/P2。

首次完整套件暴露了依赖 logger 捕获测试中一个与顺序有关的测试夹具失败：`1 failed, 2617 passed, 3 skipped, 1 warning in 505.38s`；敏感值始终正确脱敏。测试现会保存、显式控制并精确恢复 logger 与全局 logging 状态，定向重跑通过。最终 CAS 加固后，冻结完整套件通过 `2620 passed, 3 skipped, 1 warning in 505.44s`。

## 验证

- Python：Ruff 与格式检查覆盖 213 个文件并通过；strict mypy 通过 101 个源码文件；compileall 干净；完整套件通过 2620 项，3 项为 Windows 不适用 skip，另有一个既有 Starlette/httpx 弃用 warning。
- Web：Prettier 通过；Vitest 的 7 个文件、58 项测试通过；Svelte check 为 0 errors、0 warnings；生产静态构建通过。
- 打包与仓库：wheel/sdist 构建通过；双语文档与两个锁定上游 checkout 通过；tracked-output、宿主路径、secret 模式及空白审计通过。
- Git：四个中英双语实现提交已经推送到 `origin/main`；收尾文档提交就是包含本记录的提交，按约定不嵌入自身 SHA。

## 待实现与外部门

阶段 A 没有剩余实现工作。[执行 0054-B](phase-b/plan.zh.md) 现已冻结有界 provider/path 项目查找与如实的 absent-to-unique-match 刷新后观察。共同 API 不返回持久任务身份，因此该阶段明确不声明 provider task completion。已经实现的连接探测、Library 发现及定向刷新接受，其真人使用在执行 0047 下仍为 `NOT_RUN`。项目查找与刷新后观察在阶段 B 落地前仍为 `NOT_IMPLEMENTED`；provider task completion 在其落地后也继续为 `NOT_IMPLEMENTED`。播放证据写入、浏览器可写设置、多配置、鉴权及破坏性/保留运维继续归 0055。导出后自动扫描是 `NOT_IMPLEMENTED`，且尚无已冻结后续归属。七平台全部真人账户、作者、增量、CDN 及 Linux 持久性/恢复行也继续为 `NOT_RUN`。
