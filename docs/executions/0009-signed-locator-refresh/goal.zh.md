[English](goal.md) | **中文**

# 执行 0009 目标

- 状态：功能优先 MVP 已在本地实现；真人验收与强化后置
- 开始时间：2026-08-30 20:38 +08:00
- 前置执行：Execution 0008 implementation commit `3889539`
- 网络边界：仅离线 fake 锁定上游模块、本地 helper process 与 mock HTTP
- 检查点事实：migration/来源、终态清理、有界 detail 刷新、CLI 接线及一次 401/403 续签均通过离线专项门禁

## 结果目标

为手工选择的既有 Asset 交付显式启用、默认关闭的 MediaCrawler 签名 locator 刷新路径，同时把刷新权限绑定到观察到当前资产身份的精确 Subscription 与 Account。刷新 URL 只能存在于私有 child 结果通道、可信父进程内存及 `SafeHttpClient` 请求边界，绝不能进入持久状态或运维输出。在向外返回成功前删除或安全隔离精确来源根，关闭 MediaCrawler 成功/恢复 attempt 产物边界。

## 功能优先完成裁定

本地 MVP 按以下已实现边界验收。下方更长的验收矩阵继续作为原始强化目标，不代表所有对抗、留存产物或真人账户项目都已执行。

- `media-sync asset download` 的 adapter refresh 默认关闭，必须同时传入两个显式开关；可选 `--subscription-id` 用于选择多个当前合格来源。
- 惰性运行时把 Asset 绑定到当前 Content、Author、Subscription 与 Account，仅在确需网络刷新时解析 Cookie/保存会话上下文并调用锁定的 MediaCrawler detail child；已验证及 prepared recovery 路径可不触发刷新直接收尾。
- 离线支持形状为小红书 image/video、抖音 image/video/audio/cover、快手 video/cover 与 Bilibili cover。小红书当前需要一次性详情链接密钥引用；自动作者 feed 查找继续后置。
- detail 结果有界、以内存返回、复用导入 normalizer，并按精确 content/kind/position/无 query 来源提示选择；返回前删除 UUID attempt root，签名 URL 绝不写回 SQLite。
- adapter refresh 在 HTTP 401/403 后只重新解析一次；第二次认证失败返回可重试固定码，direct locator 绝不刷新。
- 自动下游执行属于 0010；真人平台/CDN/Emby 验收、小红书自动详情引导、完整取消/安全矩阵、留存哨兵、完整构建/wheel 及公网/HA 运行均明确后置。

## 验收标准

1. 全部实现验证保持离线。测试可使用仓库自有 helper process、fake 锁定上游模块形状及 mock HTTP transport，但不得使用连接真实平台的 browser session、真实凭据、平台/CDN 端点、Emby/Jellyfin 服务器或 Git 远端。
2. Alembic revision `0005_asset_refresh_sources` 新增多对多 `asset_refresh_sources` observation 表。来源以 `asset_id + subscription_id` 绑定观察到的 semantic/locator fingerprint；generation 只作审计；区分精确导入与保守 legacy 推断；可选按单调 `(created_at, id)` 顺序指向最新观察 SyncRun，重放旧 run 不得回退 `last_run_id` 或时间戳；不得保存凭据、作者 secret、签名 URL 或运行路径。
3. 来源资格要求当前 Asset semantic/locator fingerprint、稳定 `adapter_refresh` 身份、Content/Author/Subscription 关系、Account platform/adapter 与 observation 全部一致。Asset generation 继续作为 download Job fence，但不作为来源资格：`reset_verified_archive()` 可以在 observation 仍完全相同的情况下增加 generation。任何持久 semantic **或 locator** fingerprint 替换都必须开启新 generation 并重置下载状态，避免不可变 Job 来源污染同一 generation；签名 query 轮换因绝不持久化而不在此列。
4. Migration backfill 只在精确 `Asset.platform == Content.platform == Author.platform == Account.platform`、Subscription-author、MediaCrawler adapter、parsed-locator adapter、重算 stable asset key 全链一致，且当前 Content 作者恰有一个这样的 Subscription 时建立来源。候选为零或多个、任一不匹配、locator 畸形或 stable key 损坏时继续无绑定。Downgrade 只删除新 observation 表；upgrade/downgrade/re-upgrade 保留既有下载与 Emby 恢复身份。
5. MediaCrawler ingestion 在 Asset upsert 与 checkpoint 推进的同一受保护事务中，使用精确 subscription/run upsert observation，并证明 `last_run_id` 属于该 Subscription 且完整作者/平台/账户链一致；任一不匹配都回滚 observation、Asset 变化与 checkpoint。重放保持幂等；semantic 或 locator fingerprint 替换会推进 generation、更新本次观察来源，并保留其他旧 observation 作为不再合格的审计行。
6. 手工 CLI 刷新必须同时提供 `--enable-mediacrawler` 与 `--accept-mediacrawler-license`，可选 `--subscription-id`。同 generation 无 Job 时，零 eligible source 返回 `locator_refresh_source_unavailable`，一项自动选择，多项返回 `locator_refresh_source_ambiguous`。已有同 generation Job 时，其闭合绑定来源是唯一权威且必须仍 current/eligible；可选显式来源必须等于它，其他后来新增的 eligible 来源既不制造歧义，也不允许 rebind。绑定缺失/开放/损坏/不合格或显式来源不同均返回 `locator_refresh_source_mismatch`。全部 preflight 失败保持 SQLite 零变更。
7. 来源选择与下载 begin 在一个事务中重新验证 generation、fingerprint、重算 stable asset key、Content/Author/Subscription/Account 关系及精确选中或 Job 绑定来源。`asset_download` Job 保持既有 `asset_id:generation` natural key，填充既有 subscription/account/platform scope，保持 `run_id = NULL`，并保存由 ID/platform 加 semantic/locator fingerprint 组成的不可变封闭非密钥 key。Observation kind 只作 provenance 审计，绝不参与 Job 来源相等性，避免 `legacy_unique_inferred -> ingested` 卡住既有 Job。`AssetRefreshSource.last_run_id` 只作 observation 审计，绝不是 predecessor 或 dependency。
8. 每次手工调用的硬顺序为 enable/license → 只读 unresolved-account block fence → 只读分类 already-verified、精确 prepared recovery 或 network-bearing。Inspection 本身零变更；有效 already-verified archive 不改变 Job/Asset，精确 prepared recovery 只可对已绑定 generation 做 CAS/lease 接管与成功收尾；两者都不要求 eligible source、profile、凭据、child 或 HTTP。需要网络时先验证来源/runtime/reference 身份，再取得所有 cleanup-block writer 共用的账户/profile 安全锁；在锁内且 SQLite 外二次检查文件系统 block 并解析 Cookie/creator secret，随后用短事务只复核冻结数据库 Account（`id`、platform、adapter、login method、credential-ref identity、profile identity、auth status）、Subscription（`id`、account、author、enabled、canonical closed-policy identity）、Author（platform/remote ID）、observation 与 Asset/Job 身份并 claim。该锁持续持有到 child tree join、安全下载收尾及任何 cleanup 完成。Block 或不匹配按阶段在 SecretResolver/claim、run attach、bridge prepare、child spawn、HTTP 前 fail closed；SQLite 事务内不做文件系统 I/O，封闭凭据身份不得进入 Job payload 或日志。
9. Refresh port 接收冻结的 Asset 与来源上下文，而不只接收单向 locator key。专用受监督 detail-only child 导入锁定外部 runtime，使用精确账户/profile 锁，继承父死亡/取消/进程树 fencing，并通过与 fd 1/2 完全不同的专用继承 OS pipe/handle 返回一条有界严格帧。在 import 任何上游模块前，普通 stdout/stderr 已在 OS 层指向 null；父进程并发有界 drain 结果 pipe 到 EOF 并关闭全部继承 handle。URL 不得进入 argv、普通环境、磁盘、JSONL、stdout/stderr 转发或异常消息。
10. 私有帧拒绝重复 key、未知字段、多帧、尾随内容、无效身份回显、overflow、畸形/截断数据。进程退出状态、精确一帧、EOF 与 handle closure 必须一致；stdout/stderr 注入不能污染帧或运维落点。Watchdog timeout 映射为可重试 `locator_refresh_temporary`；非零退出、缺帧、退出/帧不一致或无效帧映射为终态 `locator_refresh_result_invalid`；取消保持既有取消结果。父进程结果与错误只含固定 allowlist 状态码，不含 child 控制文本。
11. 离线平台形状只覆盖带精确 stored query-free source hint 的 eligible 当前 Asset：XHS image/video、Douyin image/video/audio/cover、Kuaishou video/cover 及 Bilibili cover。XHS creator feed 只能使用精确 Subscription 刚解析出的 `creator_input.secret_ref` 启动：严格解析必须证明 HTTPS 小红书 creator URL、`user_id == Author.remote_id` 及非空 `xsec_token`/`xsec_source`，不得从 Asset/raw/position 重建；在 120 秒 refresh-child watchdog 内最多搜索 4 页、每页 30 条（120 个候选）再取 detail。authority 缺失/畸形/作者不匹配返回 `locator_refresh_configuration_invalid`，过期返回 `locator_refresh_auth_expired`，120 个候选内无目标返回 `locator_refresh_asset_not_found`，分页畸形/游标重复返回 `locator_refresh_schema_changed`，watchdog 超时返回 `locator_refresh_temporary`。Bilibili 不调用 `playurl`。Weibo、Tieba、Zhihu 当前不归一化 Asset，因此不 spawn，返回固定 unsupported code。
12. 可信 child 在发出成功帧前验证精确 platform/content/kind/position/remote request identity，应用当前归一化语义，并证明必需的 query-free source hint 精确选择一个候选。成功帧只回显覆盖完整冻结 request 的 fingerprint 与 URL；父进程验证该 fingerprint、封闭 hint contract 与 URL syntax，而不验证不可证明的 child candidate echo。当前合成 `Asset.remote_id` 不是平台 variant 身份；hint 缺失、同 kind 多候选或不能唯一选择时 fail closed，不得信任 position 或上游列表顺序。不匹配返回 `locator_refresh_asset_mismatch`，绝不向当前 generation 下载。
13. Adapter-refresh 下载最多只允许在 HTTP 401/403 后重新解析一次；第二次认证失败使用固定 refresh-specific retryable code。Direct locator 永不重新解析。续传 metadata 继续只保存持久 locator fingerprint，不保存 resolved URL/query 或平台凭据；不得把 Cookie/Origin/Referer header 转发到 CDN redirect chain。
14. Fresh success、recovered success 及 already-succeeded restart 均在向外返回成功前推导并清理精确来源 attempt。Recovered metadata 必须闭合证明来源 attempt/execution/run 身份，包括确定性 execution UUID。不得从不可信开放 JSON 字段派生路径；不得删除 successor/current attempt 根或持久 browser profile。
15. 终态清理具备取消屏蔽、重复取消安全及并发幂等性。一旦 Run/checkpoint/content 成功已提交，内存 result 畸形、权威 readback mismatch/error、全部 cleanup 状态、取消与 lease loss 都必须保留该数据库事实，只返回固定 control outcome；任何分支都不得调用 failure mutation、重复导入或改写 succeeded SyncRun，restart 只做精确 cleanup。`ABSENT`/`REMOVED` 干净完成；`QUARANTINED` 是已收口但明确可能携带凭据的隔离边界；`UNRESOLVED` 尝试写固定脱敏持久 block 并硬 fence 账户。另一 worker 已收口同一根后的 `FileNotFoundError` 属于安全 absent/removed，不得造成虚假永久 block。
16. 生成签名哨兵必须先被证明穿过私有帧与 mock HTTP 请求。另把动态哨兵注入 fresh/recovered 成功 JSONL 来源根，清理前证明存在，随后证明精确来源身份已 removed 或 secured；already-succeeded restart 也证明相同的精确来源身份。全部哨兵随后在保留安全运行树、download work/archive/sidecar、全部 SQLite 文本/JSON 值与数据库/WAL/SHM、manifest/receipt/JSONL、Job/Asset 状态、CLI/捕获输出、JUnit 及异常/结果 `str`/`repr` 中精确零匹配。Quarantine、unresolved 根与 browser profile 继续作为单独枚举的可能携带凭据负向边界。
17. Ruff、格式、严格 mypy、完整分支感知套件、refresh/cleanup/platform/migration 专项、构建、随包迁移/资源、文档、上游锁定、补丁、忽略/未跟踪运行产物及全新留存产物哨兵全部通过，并准确记录结果。

## 真实性边界与非目标

- 本计划提交不改变任何运行能力；在实现提交记录准确证据前，签名 locator refresh 及成功/恢复终态清理均保持 `NOT_RUN`。
- 自动持久 `sync → download → Emby` 规划仍属于执行 0010；执行 0009 不创建下游 DAG Job，也不改变 scheduler fan-out/fan-in 语义。
- 离线 fake detail 支持不代表真人验收；在提供用户授权环境前，七个平台的真人二维码/Cookie/保存会话登录、作者流量、签名刷新、CDN 获取及 Emby/Jellyfin 扫描/播放均保持 `NOT_RUN`；手机号登录仍不支持。
- QR 刷新继续返回固定“需要用户交互”结果；执行 0009 只实现非交互 Cookie 与保存会话路径。平台 API 凭据/header 保持在 child 内，绝不转发到 CDN redirect。
- Bilibili 可播放视频/DASH/多 P/字幕/弹幕、Weibo/Tieba/Zhihu Asset discovery、平台衍生物、逐请求上游间隔、REST、常驻监督、Docker、公网部署及 HA/PostgreSQL 仍未实现或延期。
- 执行 0008 的安全失败产物结论继续有效；成功密封 v3 输出仍是明确的可能携带凭据临时边界，直到执行 0009 实现及其留存产物门禁通过。
- `UNRESOLVED` 清理账户 block 是持久安全状态；执行 0009 不静默清除或绕过它，操作员修复/确认仍需后续显式控制面。
