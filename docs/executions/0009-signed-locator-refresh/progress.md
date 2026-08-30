# Execution 0009 progress / 执行 0009 推进结果

- Status / 状态：Function-first MVP implemented locally / 功能优先 MVP 已在本地实现
- Started / 开始时间：2026-08-30 20:38 +08:00
- Paused / 暂停时间：2026-08-31 00:06 +08:00
- Resumed / 恢复时间：2026-08-31 00:39 +08:00
- Implementation / 实现：`MVP COMPLETE; HARDENING DEFERRED` / MVP 完成，强化后置
- Verification / 验证：`PASSING OFFLINE FOCUSED GATES` / 离线专项门禁通过
- Predecessor / 前置执行：Execution 0008 implementation commit `3889539`

## Planning baseline / 计划基线

- Execution 0008 closed only the offline cancellation/security evidence. Signed-locator refresh, successful/recovery terminal cleanup and real CDN traffic were still outside its implementation. / 执行 0008 只关闭离线取消/安全证据；签名 locator refresh、成功/恢复终态清理与真实 CDN 流量仍不在其实现内。
- Read-only data-flow review proved that the stable `adapter_refresh.asset_key` is one-way and Asset/Content has no Subscription/Account provenance. An author may have multiple account subscriptions, so choosing the first account would be unsafe. / 只读数据流复核证明稳定 `adapter_refresh.asset_key` 单向不可逆，Asset/Content 也没有 Subscription/Account provenance；同一作者可有多个账户订阅，因此选择第一个账户不安全。
- The frozen design adds many-to-many `asset_refresh_sources`. Eligibility uses semantic/locator fingerprints; generation stays a download fence only, so local archive reset does not destroy a valid source. / 冻结设计新增多对多 `asset_refresh_sources`；资格使用 semantic/locator fingerprint，generation 只作为下载 fence，避免本地归档 reset 破坏有效来源。
- Design audit found that locator-only replacement previously stayed in the same generation and conflicted with immutable Job source binding. The frozen repair advances generation for either persisted semantic or locator replacement, while a generation-only archive reset keeps matching provenance eligible. / 设计审计发现 locator-only 替换此前停留在同一 generation，与不可变 Job 来源绑定冲突；冻结修复要求持久 semantic 或 locator 任一替换都推进 generation，而单纯归档 reset 后匹配 provenance 继续 eligible。
- XHS refresh authority must come from the exact Subscription's creator secret, with strict author/token/source validation and a 4 x 30/120-second bound. The private result channel is a dedicated OS pipe/handle distinct from stdout/stderr, which are redirected before upstream import. / XHS refresh authority 必须来自精确 Subscription 的 creator secret，严格验证作者/token/source，并受 4 x 30/120 秒边界约束；私有结果通道使用与 stdout/stderr 不同的专用 OS pipe/handle，后两者在 import 上游前即重定向。
- Read-only handler review found four post-success gaps: fresh success keeps its root, recovered success loses the source path, already-succeeded restart returns before cleanup, and malformed result/readback errors after a real commit can still mark the succeeded Run failed. Recovered metadata and concurrent cleanup also require stronger identity/race checks. / 只读 handler 复核发现四个成功后缺口：fresh success 保留根、recovered success 丢失来源路径、already-succeeded restart 在清理前返回，且真实提交后的 result/readback 错误仍可能把 succeeded Run 改成失败；恢复 metadata 与并发清理还需要更强身份/竞态检查。
- Pinned-upstream review found in-memory detail entry points before store/JSONL for all platforms. The current normalized Asset surface is only XHS image/video, Douyin image/video/audio/cover, Kuaishou video/cover and Bilibili cover; Weibo/Tieba/Zhihu have no Asset. / 锁定上游复核确认各平台在 store/JSONL 前都有内存 detail 入口；当前已归一化 Asset 只包含 XHS image/video、抖音 image/video/audio/cover、快手 video/cover 与 Bilibili cover；微博/贴吧/知乎没有 Asset。
- At the planning baseline no implementation had run. A later local worktree checkpoint landed two partial slices only; no helper process, browser, platform account, CDN request, media-server operation or execution 0010 work has run. / 在计划基线时尚未运行实现；之后本地工作树只落盘了两个部分切片，仍未运行 helper 进程、浏览器、平台账户、CDN 请求、媒体服务器操作或执行 0010。

## Pause checkpoint / 暂停检查点

The user requested a pause before execution 0009 acceptance. The following code is preserved in one local WIP commit as incomplete work, not as delivered capability. The manual signed-locator path is still unavailable and the CLI still returns `locator_refresh_unsupported`. / 用户要求在执行 0009 验收前暂停。以下代码将作为未完成工作保存在一个本地 WIP 提交中，不代表能力已交付；手工签名 locator 路径仍不可用，CLI 仍返回 `locator_refresh_unsupported`。

### Partial code landed / 已落盘的部分代码

- Added `AssetRefreshSource` ORM relationships, composite identity, constraints and indexes, plus migration `0005_asset_refresh_sources` with conservative unique legacy-source backfill and downgrade. / 新增 `AssetRefreshSource` ORM 关系、复合身份、约束与索引，以及包含保守唯一 legacy 来源回填和 downgrade 的 `0005_asset_refresh_sources` migration。
- Added repository APIs for observation upsert, monotonic `(created_at, id)` run audit ordering and eligible-source lookup. Semantic or persisted-locator replacement advances generation and resets download state; generation-only archive reset does not rewrite provenance. / 新增 observation upsert、单调 `(created_at, id)` run 审计顺序及 eligible 来源查询；semantic 或持久 locator 替换会推进 generation 并重置下载状态，单纯 generation archive reset 不改写来源。
- Added exact recovered `source_paths`; fresh, recovered and already-succeeded paths now attempt terminal cleanup. Closed metadata checks bind attempt/execution/run identity with deterministic `uuid5`, and post-commit database truth is protected from contradictory failure mutation. `UNRESOLVED` remains a hard fence. / 新增精确 recovered `source_paths`；fresh、recovered 与 already-succeeded 路径现会尝试终态清理。封闭 metadata 校验以确定性 `uuid5` 绑定 attempt/execution/run 身份，并保护成功提交后的数据库事实不被矛盾失败变更覆盖；`UNRESOLVED` 继续作为硬 fence。

### Still to implement / 待实现

- Exact 0/1/N and existing-Job-bound source selection; immutable Job source with `run_id = NULL`. / 精确 0/1/N 与既有 Job 绑定来源选择；`run_id = NULL` 的不可变 Job 来源。
- Shared account lock, filesystem-block second check and TOCTOU barrier before secret resolution/claim/spawn. / 共用账户锁、文件系统 block 二次检查及密钥解析/claim/spawn 前的 TOCTOU barrier。
- Private refresh protocol, dedicated pipe/handle, detail child and runner; XHS/Douyin/Kuaishou/Bilibili selectors; fixed no-spawn Weibo/Tieba/Zhihu paths. / 私有 refresh 协议、专用 pipe/handle、detail child 与 runner；四个平台 selector；微博/贴吧/知乎固定不 spawn 路径。
- Context-aware refresh and exact one 401/403 re-resolution; CLI `--enable-mediacrawler`, license and `--subscription-id` wiring. / 有上下文 refresh 与精确一次 401/403 重解析；CLI 启用、许可证及订阅参数接线。
- Functional refresh/download CLI, platform detail selection and automatic workflow integration. / 功能性 refresh/download CLI、平台 detail 选择及自动工作流集成。
- Full hardening matrix, authorized live rows and retained sentinel are explicitly deferred until the functional path is complete. Execution 0010 automatic DAG remains not started. / 完整强化矩阵、授权真人行与留存哨兵明确后置到功能路径完成之后；执行 0010 自动 DAG 仍未开始。

## Resumed implementation tranche / 恢复后的实现批次

- Promoted `0005_asset_refresh_sources` to the CLI/package head and added `0004 → 0005 → 0004 → 0005` coverage for schema constraints, foreign keys, indexes and conservative 0/1/N legacy backfill. / 将 `0005_asset_refresh_sources` 提升为 CLI/包当前 head，并新增 schema 约束、外键、索引及保守 0/1/N legacy 回填的往返覆盖。
- Wired exact Asset/Subscription observation into the same ingestion transaction before checkpoint publication. Wrong run/relation rolls back the entire batch; replay ordering, multi-account replacement and archive-reset eligibility are covered. / 在 checkpoint 发布前把精确 Asset/Subscription observation 接入同一导入事务；错误 run/关系回滚整批，并覆盖重放顺序、多账户替换及 archive reset 资格。
- Closed fresh, recovered and already-succeeded cleanup behavior, preserved committed success truth and made concurrent disappearance of the exact root converge safely. / 收口 fresh、recovered 与 already-succeeded 清理行为，保留已提交成功事实，并让精确根的并发消失安全收敛。
- Merged verification: Ruff PASS, strict mypy PASS for 65 source files, and `87 passed, 1 skipped` across migration/ingestion/handler/supervision focused gates. / 合并验证：Ruff 通过、65 个源码文件严格 mypy 通过，migration/ingestion/handler/supervision 专项共 `87 passed, 1 skipped`。
- Added one automatic re-resolution after an adapter-refresh HTTP 401/403. A second auth failure returns fixed retryable `locator_refresh_auth_expired`; direct locators never invoke refresh. / adapter-refresh HTTP 401/403 后自动重新解析一次；第二次认证失败返回固定可重试 `locator_refresh_auth_expired`，direct locator 绝不触发 refresh。

## Function-first delivery completed / 功能优先交付已完成

### Implemented / 已实现

- Added `MediaCrawlerDetailProcessRunner`: it validates the pinned checkout and explicit Python runtime, reuses the exact account profile, runs bounded detail mode, returns content JSONL in memory and removes only the UUID-scoped attempt root. / 新增 detail runner：校验锁定 checkout 与显式 Python，复用精确账户 profile，有界运行 detail 模式，内存返回 content JSONL，并只删除 UUID attempt 根。
- Added `MediaCrawlerRefreshContext` and `MediaCrawlerLocatorRefresher`: they recompute the stable Asset identity, reuse the normal ingestion normalizer and select exactly one URL by content/type/id, kind, position and query-free source hint. / 新增刷新上下文与 refresher：重算稳定 Asset 身份、复用正常导入 normalizer，并按 content/type/id、kind、position 与无 query 来源提示精确选一。
- Added `LazyMediaCrawlerLocatorRefresher`: it selects the exact current `AssetRefreshSource`, Subscription and Account only if the downloader actually needs a locator; Cookie secrets remain transient. / 新增惰性 refresher：仅在下载器确需 locator 时选择精确当前来源、Subscription 与 Account；Cookie 密钥保持瞬态。
- Wired `asset download --enable-mediacrawler --accept-mediacrawler-license [--subscription-id]`. XHS also accepts `--xhs-detail-reference-ref`; missing runtime/license/XHS detail authority is blocked before download orchestration. / 接通资产下载显式开关与可选订阅选择；小红书另支持详情链接密钥引用；缺少 runtime/许可证/XHS 详情权限时在下载编排前拦截。
- Added fixed source errors for unavailable, ambiguous and mismatched observations plus unavailable credentials. Operator-correctable source errors remain retryable. / 新增来源缺失、歧义、不匹配及凭据不可用固定错误；可由操作员修正的来源错误保持可重试。
- Offline fake-child, normalizer selection, cleanup and downloader renewal regressions pass; no real platform, CDN, credential or media-server traffic ran. / 离线 fake child、normalizer 选择、清理与下载器续签回归通过；未运行真人平台、CDN、凭据或媒体服务器流量。

### Pending / 待实现

- Execution 0010 automatic `sync → download → Emby` coordinator and worker. / 执行 0010 的自动协调器与 worker。
- Automatic XHS creator-feed lookup for a fresh note-specific `xsec` detail URL; the MVP uses an ephemeral operator-supplied secret reference. / 自动从小红书作者 feed 获取新的 note 专用 `xsec` 详情链接；MVP 使用操作员一次性密钥引用。
- Live Cookie/saved-session/QR qualification, real CDN download and real Emby/Jellyfin scan. / 真人 Cookie/保存会话/QR、真实 CDN 下载与真实 Emby/Jellyfin 扫描验收。
- Exhaustive hardening/retained-sentinel/full-suite/build/wheel/public deployment matrices. / 完整强化、留存哨兵、全套测试、构建/wheel 与公网部署矩阵。

## Entry gaps to close / 必须关闭的入口缺口

| Gap / 缺口 | Planned closure / 计划关闭方式 | Status / 状态 |
| --- | --- | --- |
| No exact refresh source / 无精确刷新来源 | `0005_asset_refresh_sources`, conservative backfill and same-transaction observations / 新表、保守 backfill 与同事务 observation | `PASS (focused)` — schema, backfill, repository and ingestion wired / schema、回填、repository 与导入已接通 |
| Context-free refresh port / 无上下文 refresh port | Frozen Asset/Content/Subscription/Account context plus stable-key and fingerprint rechecks / 冻结上下文及 stable-key/fingerprint 复核 | `PASS (offline focused)` |
| No private detail protocol / 无私有 detail 协议 | Supervised detail-only child and one bounded non-relayed frame / 受监督 detail-only child 与单条有界不转发帧 | `PASS (offline fake child)` |
| Short-lived auth URL / 短效认证 URL | Exact one adapter-only 401/403 re-resolution; persistent locator-only partial identity / adapter 专用一次重解析及只持久 locator 的 partial 身份 | `PASS (offline focused)` — resolver and CLI wired / resolver 与 CLI 已接通 |
| Post-success truth and roots / 成功后事实与根 | Exact fresh/recovered/restart cleanup; preserve committed truth across result/readback/cleanup/cancel errors; race-safe four states / 精确三路径清理；result/readback/cleanup/cancel 错误下保留已提交事实；竞态安全四状态 | `PASS (focused)` — handler and concurrent cleanup regressions pass / handler 与并发清理回归通过 |
| Signed data sink risk / 签名数据落点风险 | Injection/transport proof and fail-closed filesystem/SQLite/operator/JUnit scans / 注入/transport 证明与 fail-closed 多落点扫描 | `NOT_RUN` |
| Configuration/block TOCTOU / 配置与 block 竞态 | Shared account lock; filesystem block recheck outside SQLite before secrets/claim/spawn; transactional DB identity recheck; all block writers share fence / 共用账户锁；SQLite 外二次检查 block 后再解析密钥/claim/spawn；事务复核 DB 身份；block writer 共用 fence | `NOT_RUN` |

## Planned implementation sequence / 计划实现顺序

1. Terminal cleanup red tests and minimal race/identity repair. / 终态清理红测与最小竞态/身份修复。
2. Migration, ORM/repository provenance and conservative backfill. / Migration、ORM/repository 来源及保守 backfill。
3. Same-transaction ingestion observations and exact selector/Job binding. / 同事务导入 observation 与精确 selector/Job 绑定。
4. Context-aware refresh port, supervised private child and fixed errors. / 有上下文 refresh port、受监督私有 child 及固定错误。
5. Four supported fake platform shapes, three fixed no-spawn paths and downloader re-resolution. / 四个平台 fake 形状、三个固定不 spawn 路径及下载器重解析。
6. CLI wiring, adversarial security gates, full suite, build/package and one-shot retained evidence. / CLI 连接、对抗安全门禁、完整套件、构建/打包及一次性留存证据。

## Current qualification / 当前验收状态

| Scope / 范围 | Status / 状态 | Truth / 真实性说明 |
| --- | --- | --- |
| Refresh provenance/migration / 刷新来源/migration | `PASS (focused)` | Migration/repository/ingestion focused gates pass / migration/repository/ingestion 专项通过 |
| Private refresh child / 私有刷新 child | `PASS (offline fake child)` | Detail-mode helper ran against a fake pinned checkout and cleaned its exact attempt root / detail helper 已对 fake 锁定 checkout 运行并清理精确 attempt 根 |
| Manual signed-locator download / 手工签名 locator 下载 | `PASS (offline wiring)` | Explicit CLI flags construct the lazy exact-source refresher; real traffic remains unqualified / 显式 CLI 开关已构造惰性精确来源 refresher；真实流量未验收 |
| Successful/recovery terminal cleanup / 成功/恢复终态清理 | `PASS (focused)` | Handler `53 passed`; supervision `14 passed, 1 skipped` / handler 53 项通过；supervision 14 项通过、1 项跳过 |
| Automatic `sync → download → Emby` DAG / 自动 DAG | Unimplemented / 未实现 | Execution 0010 / 执行 0010 |
| Live login, creator traffic, refresh, CDN and Emby/Jellyfin / 真人登录、作者流量、刷新、CDN 与 Emby/Jellyfin | `NOT_RUN` | No authorized environment supplied / 未提供授权环境 |

## Deferred truthfully / 如实延期

- QR challenge presentation and phone login are not implemented by this plan. / 本计划不实现 QR challenge 展示与手机号登录。
- Bilibili playable video/DASH/multi-part/subtitle/danmaku and Weibo/Tieba/Zhihu Asset discovery remain unavailable. / Bilibili 可播放视频/DASH/多 P/字幕/弹幕及微博/贴吧/知乎 Asset discovery 继续不可用。
- Credential-bearing CDN headers and child-side downloads are deliberately excluded; real URLs requiring them remain unqualified. / 有意排除可能携带凭据的 CDN header 与 child 内下载；需要这些能力的真实 URL 继续未验收。
- Unresolved account cleanup blocks have no automatic clear/bypass path. / Unresolved 账户清理 block 没有自动清除/绕过路径。
- REST, resident supervision, Docker, public deployment and HA/PostgreSQL remain later work. / REST、常驻监督、Docker、公网部署及 HA/PostgreSQL 仍属于后续工作。
