[English](progress.md) | **中文**

# 执行 0054 推进结果

- 状态：阶段 A 与阶段 B 均已交付并通过本地验证；真人资格保持 `NOT_RUN`
- 收尾日期：2026-09-05
- 基线：`22b5864`
- 计划与加固提交：`793d33b`、`d913537`
- 阶段 A 实现提交：`554277c`、`efdb27c`、`2ad051c`、`1b34632`
- 阶段 B 规划与实现/验证提交：`d7e14c9`；`b4af46d`、`ff5da07`、`88f5ed0`、`22bd9ef`、`48ecbe9`、`d8bbdf7`
- 数据库 revision：`0007_media_server_operations`

## 已交付

阶段 A：

1. 恢复推进前先 fetch `origin/main`；本地与远端 `main` 均为 `d913537`，没有待合并的远端变化，也没有覆盖保留中的实现工作树。
2. 新增按作者 UUID 寻址的受管媒体树检查，权威来源是数据库成功发布链加严格 manifest。它使用 existing-only 锁、进程级 single-flight、绑定 manifest 的 HMAC cursor、最多 128 文件的分页、字节/截止时间预算，以及彼此独立的新鲜度/完整性状态，不暴露宿主路径或非受管名称。
3. 加固跨平台文件身份：POSIX 使用稳定目录描述符与 `O_NOFOLLOW`，Windows 持有禁止 delete-share 的句柄。Manifest 与受管文件都要求描述符/名称身份一致及单硬链接；非零末页也不再把局部检查升级为整树 `complete`。
4. 新增全有或全无、由环境变量托管的单个 Emby/Jellyfin 配置，提供安全摘要与默认关闭的操作门。启动校验会规范化 origin/网络策略并隐藏被拒绝的配置输入。
5. 新增 provider-neutral connector：强制全部 DNS 答案符合 CIDR、固定连接 IP、保留 Host/TLS SNI、禁用代理和重定向、固定 probe/定向刷新路由，并实行绝对截止时间与 connector single-flight。API key 只在请求边界解析；动态 `httpx`/`httpcore.*` 日志在请求作用域脱敏，并精确恢复先前 LogRecord factory。
6. 新增持久 `media-server-probe`、`media-server-scan` Operation 及 revision `0007`。Probe/scan 共用配置互斥域；scan 绝不回退 `/Library/Refresh`。取消只能在 dispatch 前胜出；dispatch 后 timeout、取消、断连、清理或响应歧义统一成为 terminal、不可重试的 `media_server_scan_acceptance_unknown`。
7. 完成最终 scan 持久化与取消的线性化。权威最终读取会保留 SQLite writer，并编译为 PostgreSQL `SELECT ... FOR UPDATE`：cancel-first 转为 acceptance-unknown，final-lock-first 则保留成功，后到取消不能改写。重启对账继续保守标为 `interrupted`，且 scan 的中断不可重试。
8. 新增 `GET /api/v1/library/{author_id}`、`GET /api/v1/media-server`、`POST /api/v1/media-server/probe`、`POST /api/v1/media-server/scan` 与 `GET /api/v1/qualifications`。状态和证据只取当前配置作用域，并使用封闭白名单 payload。
9. 升级 Library、Settings 与 Jobs 页面，支持媒体树分页、脱敏配置、资格证据及持久 probe/scan 活动。请求代际阻止迟到响应覆盖当前状态；Settings 使用独立故障域；Jobs 在上一轮请求仍 active 时跳过轮询。
10. 更新部署、架构、运维、安全与能力文档。阶段 A 浏览器 smoke 覆盖未配置服务器时的 Library、Settings、Jobs、禁用 probe/scan、准确 `NOT_RUN`/`NOT_IMPLEMENTED` 标签，以及请求体覆盖远端目标时的 422 拒绝。

阶段 B：

1. 新增 publication-target resolver，只授权当前唯一成功 publication head 与完整严格 manifest，并在不暴露 selector 的前提下派生精确服务器 provider/path。
2. 新增有界精确 item lookup：Emby 使用有文档的过滤器，Jellyfin 使用有界完整分页；两者最终都执行本地 provider/path 精确相等与唯一性核验。未完成遍历绝不降级为 `not_found`。
3. 在 lease/revision fencing 下新增 accepted/observed running checkpoint，封闭取消/最终收尾竞态，并实现保守的 phase-aware 重启恢复；不改变 Alembic revision `0007`，也不新增 Event kind。
4. 保留 legacy `POST /api/v1/media-server/scan {}` 的 targetless acceptance-only 语义。作者模式只接受 `{"author_id":"<uuid>"}`，要求 absent baseline，至多发送一次 provider-specific refresh，保留 accepted 证据，并且只有间隔后连续两次观察到同一唯一 item 才成功。
5. 新增安全作者 item-lookup API 与 qualification schema v2。`item_lookup`、`post_refresh_item_observation` 为实现状态 `IMPLEMENTED`、真人状态 `NOT_RUN`；`provider_task_completion` 保持 `NOT_IMPLEMENTED`，原因是 `provider_api_unsupported`。
6. `48ecbe9` 更新 Library 与 Jobs：顶部动作继续发送严格 `{}`，作者刷新并核验只发送作者 UUID，lookup 只返回白名单事实，作者观察进度不显示百分比，固定文案明确区分 acceptance、observation、provider completion 与 playback。
7. `d8bbdf7` 增加真实 PostgreSQL Operation 竞态门禁，并让普通取消与 shutdown 在写入取消前获取权威行锁。11 个非 skip 双连接用例通过可观察的数据库锁等待覆盖 accepted/observed checkpoint、cancel/final 双顺序、shutdown、coordinator fallback、lease loss 与 duplicate final。

## 阶段 A 审查加固

多轮独立审查发现并关闭了分页范围虚高、祖先/manifest 替换竞态、配置错误泄密、反射服务器字段、非绝对 timeout、POST 取消/清理歧义、旧配置证据串用、重启 scan 可重试、动态 logger 泄密、遗留 worker 增长、Web 迟到响应覆盖、Settings 故障域耦合及 Jobs 轮询自我饿死。最终跨数据库审查又发现取消/成功收尾窗口，并通过上述锁定权威读取关闭。Connector 与 CAS 复核在阶段 A 交付范围内没有发现剩余 P0/P1/P2。

首次完整套件暴露了依赖 logger 捕获测试中一个与顺序有关的测试夹具失败：`1 failed, 2617 passed, 3 skipped, 1 warning in 505.38s`；敏感值始终正确脱敏。测试现会保存、显式控制并精确恢复 logger 与全局 logging 状态，定向重跑通过。最终 CAS 加固后，冻结完整套件通过 `2620 passed, 3 skipped, 1 warning in 505.44s`。

## 验证

- Python：阶段 A 历史完整套件通过 2620 项；启用隔离真实 PostgreSQL 服务后，阶段 B 冻结套件通过 `2763 passed, 3 skipped, 1 warning in 544.08s`，其中 11 项 PostgreSQL 竞态用例均实际运行。Ruff、219 个文件的格式检查、103 个源码文件的 strict mypy、compileall、lock consistency、wheel 与 sdist 构建全部通过。PostgreSQL 首次 10 项开发诊断为 7 PASS/3 FAIL，原因是普通取消与 shutdown 在等待行锁前读取了旧 revision；加入权威 `require_for_update()` 读取后最终 11/11 通过。
- Web：阶段 A 历史门禁通过 58 项测试。阶段 B 从 `web/` 运行 `pnpm test`（69 项测试）、`pnpm format:check`、`pnpm check`（0 errors、0 warnings）与 `pnpm build` 并全部通过。首次并发尝试中，只有生产 build 因与其他 Web 命令争用 `.svelte-kit` 中间产物而失败；随后四条命令串行执行均通过。本轮没有单独执行阶段 B 浏览器 smoke。
- 仓库：490 份 Markdown 与两个锁定 upstream checkout 均通过验证；787 个 tracked 文件没有禁入的 generated/runtime output；拟提交 diff 没有工作站路径、private key 或赋值形式 secret 命中，且通过 `git diff --check`。冻结的阶段 B goal/plan 未变化，`.mimosa/` 继续保持未跟踪并排除。PostgreSQL fixture 只在隔离 schema 中创建生产 Operation/Event/Subject/StreamState 四张 metadata 表；默认数据库仍为 SQLite，不声明全 schema PostgreSQL 部署支持。
- Git：阶段 B 截至 `d8bbdf7` 的提交均已推送到 `origin/main`；收尾文档提交就是包含本记录的提交，按约定不嵌入自身 SHA。

## 待实现与外部门

执行 0054 没有剩余本地实现工作。已实现的连接探测、Library 发现、定向刷新接受、item lookup 与刷新后 item observation，其真人使用在执行 0047 下仍为 `NOT_RUN`。共同 API 不返回可关联的持久 task identity，因此 provider task completion 为 `NOT_IMPLEMENTED`。播放证据写入、浏览器可写设置、多配置、鉴权及破坏性/保留运维继续归 0055。导出后自动扫描是 `NOT_IMPLEMENTED`，且尚无已冻结后续归属。七平台全部真人账户、作者、增量、CDN 及 Linux 持久性/恢复行也继续为 `NOT_RUN`。
