[English](plan.md) | **中文**

# 执行 0009 计划

- 状态：功能优先 MVP 已实现；其余强化保留为后续计划
- 计划日期：2026-08-30
- 前置执行：Execution 0008 implementation commit `3889539`
- 网络策略：仅离线 fake 锁定上游模块、本地 helper 与 mock HTTP
- 交付优先级：先让本地 refresh/download 与端到端流程可用；完整强化矩阵及授权真人验收明确列入后续工作

## 冻结设计

下列章节保留原始完整强化设计。已实现 MVP 有意选择较小且可用的路径：惰性精确当前来源选择、有界 stdout frame detail helper、显式小红书 note-detail 密钥输入，以及既有 `asset_download` Job 语义。不可变 Job 绑定刷新来源 payload、小红书作者 feed 自动查找、覆盖 CDN 收尾的共用锁及完整留存证据均后置，不宣称完成。

### 交付切片

- 执行 0009 只实现既有 MediaCrawler `adapter_refresh` Asset 的显式手工刷新/下载，以及成功/恢复 attempt 终态清理；不新增自动下游 Job。
- 运行面继续默认关闭，每次 CLI 调用都必须同时显式启用 MediaCrawler 并确认许可证；这些检查前不得选择来源、解析密钥或启动进程。
- Cookie 与保存会话是仅有的非交互刷新登录路径；QR 以零变更返回固定“需要用户交互”结果，手机号继续不支持。

### 关系来源与迁移

新增 Alembic revision `0005_asset_refresh_sources` 与 ORM model `AssetRefreshSource`。不得在 Asset 上新增单一来源列，因为同一作者/资产可能由多个账户订阅观察到。

| 列或规则 | 冻结契约 |
| --- | --- |
| 主身份 | 复合主键 `(asset_id, subscription_id)` |
| `asset_id` | FK to `assets.id`, `ON DELETE CASCADE` |
| `subscription_id` | FK to `subscriptions.id`, `ON DELETE CASCADE` |
| `last_run_id` | 可空 FK，`ON DELETE SET NULL`；只作审计 |
| `observation_kind` | 封闭值 `ingested` 与 `legacy_unique_inferred` |
| `observed_generation` | 正数审计值；绝不作为资格 key |
| `observed_semantic_fingerprint` | 当前 Asset 的精确小写 SHA-256 |
| `observed_locator_fingerprint` | 当前 Asset 的精确小写 SHA-256 |
| 时间与 run | first 不变、last 不回退；`last_run_id` 只按 `(created_at, id)` 全序推进，旧 run 重放不回退审计状态 |
| 索引 | `subscription_id`；`(asset_id, observed_semantic_fingerprint, observed_locator_fingerprint)` |

资格要求两个 observation fingerprint 均等于当前 Asset，同时检查当前稳定 locator、Content author、Subscription author、Account platform 及 `adapter='mediacrawler'`。`observed_generation` 只作诊断。已验证归档 reset 可在 semantic/locator fingerprint 不变时增加 generation，此时必须保持 eligible。任何持久 semantic 或 locator fingerprint 替换都必须先增加 generation 并重置下载状态，之后才能绑定新的不可变 Job 来源；纯签名 URL query 轮换不是持久 replacement。其他 observation 保留为不再合格的审计行。

Migration backfill 只解析 adapter 为 `mediacrawler` 的有效 `adapter_refresh` locator，重算 `stable_asset_key()`，并要求 `Asset.platform == Content.platform == Author.platform == Account.platform`、`Subscription.author_id == Content.author_id`、`Account.adapter == 'mediacrawler'` 全部精确成立。仅当恰有一个 Subscription 满足整条关系链时插入 `legacy_unique_inferred`；绝不从多账户中选择第一个、读取 raw 恢复密钥、解析 secret reference 或重建签名 URL。零候选/歧义/畸形/损坏 case 继续无绑定。Downgrade 只删除本表及其索引/约束。

### 导入 observation

- 修改 Asset upsert plumbing 以返回权威 Asset 行；在每个精确 ownership guard 批次中，先证明 SyncRun 属于同一 Subscription 且完整作者/平台/账户关系一致，再使用该 `subscription_id`、`run_id`、Asset generation 与 fingerprint，在 commit/checkpoint 推进前 upsert observation。任一不匹配都一起回滚 observation、Asset 与 checkpoint 变化。
- 重放同一 subscription/run 保持幂等；另一 subscription 可新增第二 observation；semantic 或 locator fingerprint 替换会增加 Asset generation、重置下载状态并更新本次观察 subscription 的行，其他行继续作为审计证据但不再 eligible。
- 空批次或被过滤批次不创建 observation；失败或被 fence 的导入事务既不改变 Asset，也不产生 provenance。

### 只读选择与 Job 绑定

引入不含 ORM 对象或密钥的封闭 source-selection result。它冻结 Asset ID/generation/platform/content remote type 与 ID/kind/position/合成 remote ID、semantic/locator fingerprint、无 query source hint、Author platform/remote ID、Account ID/platform/adapter/login method/credential-reference identity/profile identity/auth status，以及 Subscription ID/account/author/enabled/canonical closed MediaCrawler policy identity。Policy identity 覆盖 creator-secret reference，但不暴露其值。

来源选择分为两个精确模式：

1. **同 generation 无 Job：** 显式 subscription 必须是 eligible observation，否则返回 mismatch；未显式指定时，零行 unavailable、恰一行自动选中、多行 ambiguous。
2. **已有同 generation Job：** 其闭合不可变来源绑定是唯一权威，且必须仍指向一个 current eligible observation；可选 `--subscription-id` 必须等于绑定 subscription。绑定缺失/开放/损坏/过期返回 mismatch；其他后来新增的 eligible observation 不参与歧义判断，也绝不触发 rebind。retry/running/prepared 恢复始终走此模式。
3. 创建/认领 Job 前，从权威 Content/Asset 字段重算 `stable_asset_key()` 并与 parsed locator 比较；在共用账户安全锁内、SQLite 外复核文件系统 cleanup block，随后在 claim 事务内复核 generation、两个 fingerprint 及全部冻结数据库 Author/Account/Subscription/configuration 身份。

保持既有 Job natural key `asset_id:generation`。MediaCrawler refresh Job 填充现有 `subscription_id`、`account_id` 与 `platform` 列，并保持 `run_id = NULL`；新增封闭不可变 `refresh_source` payload，只含 schema version、asset/subscription/account ID、platform 及 semantic/locator fingerprint；拒绝未知字段，绝不保存 observation kind、credential ref、含 creator reference 的 policy、resolved URL、source URL、文件系统根或 profile 路径。Observation kind 从 `legacy_unique_inferred` 升级为 `ingested` 不改变 Job 来源相等性。`AssetRefreshSource.last_run_id` 只作审计；执行 0009 不创建 Job dependency、predecessor、导入 fan-out 或 SyncRun ancestry 推断。

### Preflight 与恢复顺序

- 硬顺序：enable/license → 只读 unresolved-account block fence → 只读分类 already-verified、精确 prepared recovery 或 network-bearing。被 block 的路径对 SecretResolver、run attach、bridge/refresh prepare、child spawn 与 HTTP 的调用数均精确为零。
- 只读 inspection 本身零变更；有效 already-verified archive 不改变 Job/Asset。精确 prepared recovery 只允许对已绑定 Job/Asset generation 做 CAS/lease 接管与成功收尾；不得新建 Job、重绑来源、消耗新 attempt、解析凭据、spawn child 或发起 HTTP。
- 对需要网络的工作，继续按来源/runtime/profile/reference 验证 → 获取共用账户/profile 安全锁 → SQLite 外复核文件系统 cleanup block → SQLite 外解析 Cookie/creator secret → 短事务只复核数据库来源/Asset/Author/Account/Subscription/配置并 claim → 受监督刷新 → 安全下载/收尾 → cleanup → 释放锁。所有可能创建账户 block 的 cleanup 路径使用同一把锁或等价原子 fence，因而二次检查与释放间不能插入 block。
- 若冻结身份在选择/解析密钥与 `_begin` 间变化则 fail closed。Barrier 测试在首次读取后创建 block：取得锁并二次检查必须在 SecretResolver、claim、spawn 前拦截。Secret object 可在 `_begin` 期间暂存可信父内存，但密钥解析、文件系统检查与外部 I/O 绝不进入数据库事务；封闭凭据/配置身份不进入 Job payload 或日志。
- 既有 prepared/retry/running 恢复保持原绑定来源，绝不隐式使用新账户。

### Refresh port 与私有 child 协议

把无上下文 `resolve(AdapterRefreshLocator)` 调用替换为冻结的 `RefreshRequest`/`RefreshContext`。Subscription UUID 保持在全局持久 locator 之外。Resolver 返回从 `repr` 隐藏 URL 的 `ResolvedLocator`；执行 0009 有意保持 CDN 契约仅 URL，不新增可能携带凭据的请求 header。

实现专用 detail-only child 与父 runner，复用或抽取既有账户/profile 锁、checkout/runtime/license 校验、start handshake、父死亡监督、取消、后代 join 及有界 timeout。可信父进程绝不 import MediaCrawler。

- 私有输入复用既有“最先 pop”的密钥 envelope，绝不进入 argv、manifest 或运维输出。
- 创建与 fd 1/2 完全不同的专用继承 OS result pipe/handle；import 任何上游模块前在 OS 层把普通 stdout/stderr 指向 null。父进程并发 drain 至多 16 KiB 加 overflow probe 到 EOF，绝不转发 bytes，并在成功、失败、timeout、取消时关闭全部本地/继承 handle。
- 只允许一帧，最大 16 KiB，使用 canonical UTF-8 JSON 加换行。成功帧为含版本、固定状态、精确 request-identity fingerprint 与 URL 的封闭 schema；失败帧只含 version、固定 status 及 allowlist code。退出状态、单帧、EOF 与 handle closure 必须一致。Watchdog timeout 固定映射 temporary；非零退出、无帧、退出/帧不一致及全部无效帧固定映射 result_invalid；取消沿用既有取消结果。
- 拒绝重复/未知 key、无效 UTF-8、多帧/尾随、overflow、截断、身份不匹配及不符合 `ResolvedLocator` 的 URL 语法，且不回显原始 bytes。
- Child 在上游 store/JSONL 前于内存提取 detail dict，绝不调用 store 或写 attempt/output 文件。Child code 负责候选语义验证；父进程验证覆盖完整冻结 request 的 fingerprint、封闭 hint contract 与 URL syntax，而不是帧无法独立证明的 candidate echo。

### 离线平台 selector 矩阵

| 平台 | 支持的当前 Asset | 冻结 selector | 明确边界 |
| --- | --- | --- | --- |
| `xhs` | 带精确 stored hint 的 image、video | 严格解析精确 Subscription creator URL，要求 HTTPS XHS host、作者 ID 一致、token/source 非空；120 秒内最多 4 x 30 条，再取 detail 与精确 hint 选择 | 固定 disposition；绝不重建/持久化 xsec |
| `dy` | image, video, audio, cover | `get_video_by_id`；复现当前图片优先/抑制 video 语义及精确候选匹配 | browser 状态只在 child 内生成 API 签名材料 |
| `ks` | video, cover | 精确一个 video/cover 候选 | 不宣称真人 CDN |
| `bili` | cover only | detail 接口及精确 cover 匹配 | 绝不调用 playurl；不宣称可播放视频/DASH/多 P |
| `wb`, `tieba`, `zhihu` | 无 | 固定 unsupported；不 spawn | Asset discovery 仍未实现 |

每个受支持 Asset 都必须有精确 stored query-free hint。合成 `Asset.remote_id` 与数字 position 不是持久平台 variant ID。在可信 child 内，只有当前归一化语义及 hint 已产生唯一候选集合后，position 才可参与验证；它自身不能消除同 kind 歧义。Child 只在完成该检查后发出完整 request fingerprint。Hint 缺失或不能继续精确选择唯一候选时返回 `locator_refresh_asset_mismatch`。

### 固定错误分类

| 阶段 | 固定 code | 处置 |
| --- | --- | --- |
| 零变更 preflight | `locator_refresh_disabled`, `license_acknowledgement_required`, `locator_refresh_source_unavailable`, `locator_refresh_source_ambiguous`, `locator_refresh_source_mismatch`, `locator_refresh_platform_unsupported`, `locator_refresh_kind_unsupported`, `locator_refresh_qr_required`, `locator_refresh_credentials_unavailable`, `locator_refresh_configuration_invalid` | 不变更 Job/Asset |
| 可重试 attempt | `locator_refresh_account_busy`, `locator_refresh_auth_expired`, `locator_refresh_rate_limited`, `locator_refresh_temporary` | 在既有 attempt 上限下固定脱敏可重试失败 |
| 终态/安全 | `locator_refresh_asset_not_found`, `locator_refresh_schema_changed`, `locator_refresh_asset_mismatch`, `locator_refresh_result_invalid` | 固定终态失败；无原始 child bytes |

未提供 refresher 时，媒体层继续使用通用 `locator_refresh_unsupported`；MediaCrawler CLI preflight 正常情况下必须在到达该分支前阻止。全部公开消息在错误 registry 中保持固定。

### 下载器重新解析

- Direct locator 行为逐字节保持不变；adapter refresh 在 HTTP 前解析一次。
- 只有 adapter-refresh 请求的 HTTP 401/403 可再消耗一次解析；复用精确冻结来源/context。第二次 401/403 抛 `locator_refresh_auth_expired`；其他状态保持既有分类。
- `.part` metadata 与恢复身份只使用 canonical 持久 locator fingerprint；刷新 query、过期时间、API header 或 Cookie 绝不进入 metadata、archive 名或结果 payload。
- Range/If-Range 继续保持安全；若新签名 URL 对续传请求返回 `200`，既有有界重启逻辑会丢弃/重启，而不是追加不兼容字节。
- 不向 `SafeHttpClient` redirect 添加 Cookie、Origin 或 Referer；若真实 CDN 需要这类凭据，该真人行继续 unsupported/`NOT_RUN`。执行 0009 不在 child 内下载以绕过 DNS pinning、redirect、Range、大小或 probe 契约。

### 成功与恢复终态清理

修复现有四个缺口：fresh `_ingest()` 成功当前会保留根；recovered success 丢失 source paths；already-succeeded restart 会在清理前返回；成功提交后的内存 result 畸形或权威 readback 失败仍可能到达 `_set_run_failure()`。

1. 为 `_RecoveredOutput` 增加精确 `source_paths`；恢复导入清理来源根，绝不清理新 successor path。
2. 权威 DB 成功后、向外成功前，通过可抵御重复取消的 join helper 执行终态清理；lease loss/取消不得让调用方在清理得到 secured/unresolved 结论前 unwind。
3. already-succeeded 重启验证封闭 run metadata schema；fresh 使用顶层 attempt/execution 身份；recovered 使用 `recovered_artifact` 来源 attempt/execution/run 身份，并证明确定性 UUID；绝不信任开放路径或 successor execution ID。
4. 使 `cleanup_attempt_root()` 并发幂等；每个 no-follow/scope 检查及 rename/remove 迁移后，另一精确清理导致的消失都收敛为安全 `ABSENT`/`REMOVED`，不得成为虚假 `UNRESOLVED`；不安全替换、逃逸或不可验证 metadata 仍 fail closed。
5. 新增显式“成功提交后”边界。一旦权威 Run/checkpoint/content 成功存在，result 畸形、readback mismatch/error、四种 cleanup 状态、取消与 lease loss 都只能在保留数据库事实的前提下产生固定 control outcome；不得调用 `_set_run_failure()`、重复导入或回滚；重复 restart 只做精确 cleanup。

终态映射固定如下：

| 清理 | 数据库事实 | 向外行为 |
| --- | --- | --- |
| `ABSENT`, `REMOVED` | 保留 succeeded Run/checkpoint/content | 成功 |
| `QUARANTINED` | 保留成功；隔离根继续为枚举的可能携带凭据边界 | 仅固定内部 disposition 的成功；无路径 |
| `UNRESOLVED` | 保留成功，尝试固定 marker 并硬 fence 账户 | 抛固定 cleanup-blocked 控制结果；绝不 stale-fail/重复导入 |

执行 0009 不提供持久 unresolved account block 的自动清除路径；任何重启、刷新或手工下载都不得静默绕过。

### 安全与留存证据

- 签名 URL 哨兵在 collection 后生成并写入私有 child 帧；私有 pipe observer 在父进程消费前证明注入，mock HTTP 证明精确 URL 只到请求边界。另在 collection 后把动态哨兵注入 fresh/recovered 成功 JSONL 根，清理前证明非空，随后证明精确来源根已 removed/secured；already-succeeded restart 证明相同来源身份。
- 扫描全部 SQLite 逻辑文本/JSON 值及数据库/WAL/SHM bytes；Job/Asset locator、raw/source 字段、payload 与结果必须无 query/密钥。
- 对安全 attempt/download/archive/sidecar/operator/JUnit 树、隐藏/忽略文件及路径名执行 fail-closed 扫描；声明为安全的根内不设排除。
- 持久 profile、故意 quarantine 与 unresolved 清理证据属于单独命名负向集合；不得为扫描通过而删除/改写，也不得暴露其路径。
- 全新忽略根 `.media-sync/verification/0009-refresh-sentinel-root` 只运行一次；权威运行前不得存在，之后不得删除/重建；0007 与 0008 留存根只读且不触碰。

## 实现顺序

1. 先为 fresh/recovered/already-succeeded 终态清理及并发精确根清理新增红测，再实现最小清理/状态修复。
2. 新增 `0005_asset_refresh_sources`、ORM/repository API、保守 backfill 及随包 migration 往返测试。
3. 把精确 observation upsert 集成进受保护 MediaCrawler 导入，并证明重放/替换/generation-reset 语义。
4. 新增只读来源选择、不可变 Job 来源 payload/列及零变更 CLI preflight。
5. 定义有上下文 refresh port、固定错误分类及严格私有 child 帧。
6. 实现 XHS/抖音/快手/Bilibili 受监督 fake detail 形状，以及其余平台固定不 spawn unsupported 路径。
7. 把一次性 401/403 re-resolution 接入既有安全下载器，并连接显式 CLI。
8. 运行平台/监督/migration/清理/安全专项、完整套件、构建/打包及一次性留存哨兵；更新真实能力但不提升真人行。

## 验证计划

| 门禁 | 必需覆盖 |
| --- | --- |
| 迁移 | 新库 head、约束/FK/索引、精确关系/stable-key legacy backfill、歧义/损坏不绑定、往返及随包清单 |
| 来源 | 同事务 observation、错误关系回滚、旧 run 重放不回退审计全序、多账户、两类替换推进 generation、单独归档 reset 保持资格 |
| 选择与 Job | 两种来源模式、共用锁二次 block 检查在密钥/claim/spawn 前拦截 barrier writer、事务无文件 I/O、配置竞态、空 `run_id` |
| 恢复顺序 | verified 无来源/profile/凭据/变更即可成功；prepared 只允许已绑定 CAS/收尾；两者 SecretResolver/child/HTTP 调用均为零 |
| Child/平台 | 专用 handle、严格帧/错误矩阵、共用账户锁覆盖 child tree/下载收尾/cleanup 且 block writer 同 fence、父死亡/取消、selector |
| 下载器 | 签名 URL 到 mock HTTP、精确一次重解析、direct 不变、续传、metadata 无 URL/query、redirect header 不变 |
| 清理 | 非空来源哨兵、精确重启身份、真实成功提交后注入 result/readback/四状态/取消/重启并断言无 failure mutation/重复导入、marker 失败与并发消失 |
| 密钥落点 | 私有 pipe 与 mock transport 证明，加清理后文件系统/SQLite/运维/JUnit 精确零匹配及命名负向排除 |
| 根质量 | 锁定同步、Ruff/format/mypy、完整分支感知 pytest、构建与 wheel smoke、随包迁移、docs/upstream/diff/Git、全新留存根 |

## 明确非目标

- 不实现持久自动 DAG、依赖表、fan-out/fan-in 或共享 child 取消语义；这些属于执行 0010。
- 不执行真实平台/CDN/Emby 流量，也不提升真人能力。
- 不实现 Bilibili 可播放视频/DASH/多 P/字幕/弹幕、Weibo/Tieba/Zhihu Asset discovery，也不在 fail-closed 当前 hint 匹配之外重设计 XHS variant 身份。
- 不实现可能携带凭据的 CDN header、child 内媒体下载、QR 展示 UX、手机号登录、REST、常驻监督、Docker 或 HA/PostgreSQL。
- 不自动清除 unresolved 清理 block，也不静默重绑来源。
