# Execution 0009 progress / 执行 0009 推进结果

- Status / 状态：Planned / 已计划
- Started / 开始时间：2026-08-30 20:38 +08:00
- Implementation / 实现：`NOT_RUN` / 未运行
- Verification / 验证：`NOT_RUN` / 未运行
- Predecessor / 前置执行：Execution 0008 implementation commit `3889539`

## Planning baseline / 计划基线

- Execution 0008 closed only the offline cancellation/security evidence. Signed-locator refresh, successful/recovery terminal cleanup and real CDN traffic were still outside its implementation. / 执行 0008 只关闭离线取消/安全证据；签名 locator refresh、成功/恢复终态清理与真实 CDN 流量仍不在其实现内。
- Read-only data-flow review proved that the stable `adapter_refresh.asset_key` is one-way and Asset/Content has no Subscription/Account provenance. An author may have multiple account subscriptions, so choosing the first account would be unsafe. / 只读数据流复核证明稳定 `adapter_refresh.asset_key` 单向不可逆，Asset/Content 也没有 Subscription/Account provenance；同一作者可有多个账户订阅，因此选择第一个账户不安全。
- The frozen design adds many-to-many `asset_refresh_sources`. Eligibility uses semantic/locator fingerprints; generation stays a download fence only, so local archive reset does not destroy a valid source. / 冻结设计新增多对多 `asset_refresh_sources`；资格使用 semantic/locator fingerprint，generation 只作为下载 fence，避免本地归档 reset 破坏有效来源。
- Design audit found that locator-only replacement previously stayed in the same generation and conflicted with immutable Job source binding. The frozen repair advances generation for either persisted semantic or locator replacement, while a generation-only archive reset keeps matching provenance eligible. / 设计审计发现 locator-only 替换此前停留在同一 generation，与不可变 Job 来源绑定冲突；冻结修复要求持久 semantic 或 locator 任一替换都推进 generation，而单纯归档 reset 后匹配 provenance 继续 eligible。
- XHS refresh authority must come from the exact Subscription's creator secret, with strict author/token/source validation and a 4 x 30/120-second bound. The private result channel is a dedicated OS pipe/handle distinct from stdout/stderr, which are redirected before upstream import. / XHS refresh authority 必须来自精确 Subscription 的 creator secret，严格验证作者/token/source，并受 4 x 30/120 秒边界约束；私有结果通道使用与 stdout/stderr 不同的专用 OS pipe/handle，后两者在 import 上游前即重定向。
- Read-only handler review found four post-success gaps: fresh success keeps its root, recovered success loses the source path, already-succeeded restart returns before cleanup, and malformed result/readback errors after a real commit can still mark the succeeded Run failed. Recovered metadata and concurrent cleanup also require stronger identity/race checks. / 只读 handler 复核发现四个成功后缺口：fresh success 保留根、recovered success 丢失来源路径、already-succeeded restart 在清理前返回，且真实提交后的 result/readback 错误仍可能把 succeeded Run 改成失败；恢复 metadata 与并发清理还需要更强身份/竞态检查。
- Pinned-upstream review found in-memory detail entry points before store/JSONL for all platforms. The current normalized Asset surface is only XHS image/video, Douyin image/video/audio/cover, Kuaishou video/cover and Bilibili cover; Weibo/Tieba/Zhihu have no Asset. / 锁定上游复核确认各平台在 store/JSONL 前都有内存 detail 入口；当前已归一化 Asset 只包含 XHS image/video、抖音 image/video/audio/cover、快手 video/cover 与 Bilibili cover；微博/贴吧/知乎没有 Asset。
- No implementation, schema revision, helper process, browser, platform account, CDN request or media-server operation has run. Execution 0010 remains the automatic DAG milestone. / 尚未运行实现、schema revision、helper process、浏览器、平台账户、CDN 请求或媒体服务器操作；执行 0010 继续负责自动 DAG。

## Entry gaps to close / 必须关闭的入口缺口

| Gap / 缺口 | Planned closure / 计划关闭方式 | Status / 状态 |
| --- | --- | --- |
| No exact refresh source / 无精确刷新来源 | `0005_asset_refresh_sources`, conservative backfill and same-transaction observations / 新表、保守 backfill 与同事务 observation | `NOT_RUN` |
| Context-free refresh port / 无上下文 refresh port | Frozen Asset/Content/Subscription/Account context plus stable-key and fingerprint rechecks / 冻结上下文及 stable-key/fingerprint 复核 | `NOT_RUN` |
| No private detail protocol / 无私有 detail 协议 | Supervised detail-only child and one bounded non-relayed frame / 受监督 detail-only child 与单条有界不转发帧 | `NOT_RUN` |
| Short-lived auth URL / 短效认证 URL | Exact one adapter-only 401/403 re-resolution; persistent locator-only partial identity / adapter 专用一次重解析及只持久 locator 的 partial 身份 | `NOT_RUN` |
| Post-success truth and roots / 成功后事实与根 | Exact fresh/recovered/restart cleanup; preserve committed truth across result/readback/cleanup/cancel errors; race-safe four states / 精确三路径清理；result/readback/cleanup/cancel 错误下保留已提交事实；竞态安全四状态 | `NOT_RUN` |
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
| Refresh provenance/migration / 刷新来源/migration | `NOT_RUN` | Frozen design only / 仅冻结设计 |
| Private refresh child / 私有刷新 child | `NOT_RUN` | No protocol or process has run / 尚未运行协议或进程 |
| Manual signed-locator download / 手工签名 locator 下载 | `NOT_RUN` | Existing CLI still returns `locator_refresh_unsupported` / 既有 CLI 仍返回该 fixed code |
| Successful/recovery terminal cleanup / 成功/恢复终态清理 | `NOT_RUN` | Existing temporary credential-bearing boundary remains / 既有可能携带凭据临时边界仍存在 |
| Automatic `sync → download → Emby` DAG / 自动 DAG | Unimplemented / 未实现 | Execution 0010 / 执行 0010 |
| Live login, creator traffic, refresh, CDN and Emby/Jellyfin / 真人登录、作者流量、刷新、CDN 与 Emby/Jellyfin | `NOT_RUN` | No authorized environment supplied / 未提供授权环境 |

## Deferred truthfully / 如实延期

- QR challenge presentation and phone login are not implemented by this plan. / 本计划不实现 QR challenge 展示与手机号登录。
- Bilibili playable video/DASH/multi-part/subtitle/danmaku and Weibo/Tieba/Zhihu Asset discovery remain unavailable. / Bilibili 可播放视频/DASH/多 P/字幕/弹幕及微博/贴吧/知乎 Asset discovery 继续不可用。
- Credential-bearing CDN headers and child-side downloads are deliberately excluded; real URLs requiring them remain unqualified. / 有意排除可能携带凭据的 CDN header 与 child 内下载；需要这些能力的真实 URL 继续未验收。
- Unresolved account cleanup blocks have no automatic clear/bypass path. / Unresolved 账户清理 block 没有自动清除/绕过路径。
- REST, resident supervision, Docker, public deployment and HA/PostgreSQL remain later work. / REST、常驻监督、Docker、公网部署及 HA/PostgreSQL 仍属于后续工作。
