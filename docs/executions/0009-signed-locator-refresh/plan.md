# Execution 0009 plan / 执行 0009 计划

- Status / 状态：Paused — frozen plan with partial implementation checkpoint / 已暂停——冻结计划及部分实现检查点
- Plan date / 计划日期：2026-08-30
- Predecessor / 前置执行：Execution 0008 implementation commit `3889539`
- Network policy / 网络策略：offline fake pinned-upstream modules, local helpers and mock HTTP only / 仅离线 fake 锁定上游模块、本地 helper 与 mock HTTP
- Resume rule / 恢复规则：finish the open execution 0009 sequence and failing gates before execution 0010; do not treat landed slices as capability / 先完成执行 0009 的剩余序列与失败门禁，再开始执行 0010；不得把已落盘切片视为能力交付

## Frozen design / 冻结设计

### Delivery slice / 交付切片

- Execution 0009 implements only explicit manual refresh/download for existing MediaCrawler `adapter_refresh` Assets and successful/recovery attempt terminal cleanup. It does not add automatic downstream Jobs. / 执行 0009 只实现既有 MediaCrawler `adapter_refresh` Asset 的显式手工刷新/下载，以及成功/恢复 attempt 终态清理；不新增自动下游 Job。
- The runtime surface remains default-off and requires both MediaCrawler enablement and license acknowledgement on each CLI invocation. No source, secret or process work occurs before those checks. / 运行面继续默认关闭，每次 CLI 调用都必须同时显式启用 MediaCrawler 并确认许可证；这些检查前不得选择来源、解析密钥或启动进程。
- Cookie and saved-session refresh are the only non-interactive login paths. QR returns a fixed user-interaction-required result without mutation; phone remains unsupported. / Cookie 与保存会话是仅有的非交互刷新登录路径；QR 以零变更返回固定“需要用户交互”结果，手机号继续不支持。

### Relational provenance and migration / 关系来源与迁移

Add Alembic revision `0005_asset_refresh_sources` and ORM model `AssetRefreshSource`. Do not add a single source column to Asset because the same author/asset may be observed by multiple account subscriptions.

新增 Alembic revision `0005_asset_refresh_sources` 与 ORM model `AssetRefreshSource`。不得在 Asset 上新增单一来源列，因为同一作者/资产可能由多个账户订阅观察到。

| Column or rule / 列或规则 | Frozen contract / 冻结契约 |
| --- | --- |
| Primary identity / 主身份 | Composite primary key `(asset_id, subscription_id)` / 复合主键 `(asset_id, subscription_id)` |
| `asset_id` | FK to `assets.id`, `ON DELETE CASCADE` |
| `subscription_id` | FK to `subscriptions.id`, `ON DELETE CASCADE` |
| `last_run_id` | Nullable FK to `sync_runs.id`, `ON DELETE SET NULL`; audit only / 可空 FK，`ON DELETE SET NULL`；只作审计 |
| `observation_kind` | Closed values `ingested` and `legacy_unique_inferred` / 封闭值 `ingested` 与 `legacy_unique_inferred` |
| `observed_generation` | Positive audit value; never the eligibility key / 正数审计值；绝不作为资格 key |
| `observed_semantic_fingerprint` | Exact lower-case SHA-256 copied from current Asset / 当前 Asset 的精确小写 SHA-256 |
| `observed_locator_fingerprint` | Exact lower-case SHA-256 copied from current Asset / 当前 Asset 的精确小写 SHA-256 |
| Timestamps/run / 时间与 run | `first_seen_at` is immutable; `last_seen_at` never decreases; `last_run_id` advances only by total `(SyncRun.created_at, SyncRun.id)` order, so an older replay cannot regress audit state / first 不变、last 不回退；`last_run_id` 只按 `(created_at, id)` 全序推进，旧 run 重放不回退审计状态 |
| Indexes / 索引 | `subscription_id`; `(asset_id, observed_semantic_fingerprint, observed_locator_fingerprint)` / `subscription_id`；`(asset_id, observed_semantic_fingerprint, observed_locator_fingerprint)` |

Eligibility requires both observation fingerprints to equal the current Asset and also checks the current stable locator, Content author, Subscription author, Account platform and `adapter='mediacrawler'`. `observed_generation` is diagnostic only. A verified archive reset may increment generation without changing semantic/locator fingerprints and must retain eligibility. Any persisted semantic- or locator-fingerprint replacement must increment generation and reset downloader state before a new immutable Job source can bind; query-only signed-URL rotation is not a persisted replacement. Other observations remain as ineligible audit rows.

资格要求两个 observation fingerprint 均等于当前 Asset，同时检查当前稳定 locator、Content author、Subscription author、Account platform 及 `adapter='mediacrawler'`。`observed_generation` 只作诊断。已验证归档 reset 可在 semantic/locator fingerprint 不变时增加 generation，此时必须保持 eligible。任何持久 semantic 或 locator fingerprint 替换都必须先增加 generation 并重置下载状态，之后才能绑定新的不可变 Job 来源；纯签名 URL query 轮换不是持久 replacement。其他 observation 保留为不再合格的审计行。

Migration backfill parses only valid `adapter_refresh` locators with adapter `mediacrawler`, recomputes `stable_asset_key()` and requires exact equality across `Asset.platform == Content.platform == Author.platform == Account.platform`, `Subscription.author_id == Content.author_id`, and `Account.adapter == 'mediacrawler'`. It inserts `legacy_unique_inferred` only when exactly one Subscription satisfies the entire chain. It never chooses the first of multiple accounts, reads raw data to recover secrets, resolves a secret reference or reconstructs a signed URL. Zero/ambiguous/malformed/corrupt cases remain unbound. Downgrade drops only this table and its indexes/constraints.

Migration backfill 只解析 adapter 为 `mediacrawler` 的有效 `adapter_refresh` locator，重算 `stable_asset_key()`，并要求 `Asset.platform == Content.platform == Author.platform == Account.platform`、`Subscription.author_id == Content.author_id`、`Account.adapter == 'mediacrawler'` 全部精确成立。仅当恰有一个 Subscription 满足整条关系链时插入 `legacy_unique_inferred`；绝不从多账户中选择第一个、读取 raw 恢复密钥、解析 secret reference 或重建签名 URL。零候选/歧义/畸形/损坏 case 继续无绑定。Downgrade 只删除本表及其索引/约束。

### Ingestion observation / 导入 observation

- Change Asset upsert plumbing to return the authoritative Asset row. Within every exact ownership-guarded batch, prove the SyncRun belongs to the same Subscription and the full author/platform/account relation, then upsert one observation using that `subscription_id`, `run_id`, Asset generation and fingerprints before commit/checkpoint advancement. Any mismatch rolls back observation, Asset and checkpoint changes together. / 修改 Asset upsert plumbing 以返回权威 Asset 行；在每个精确 ownership guard 批次中，先证明 SyncRun 属于同一 Subscription 且完整作者/平台/账户关系一致，再使用该 `subscription_id`、`run_id`、Asset generation 与 fingerprint，在 commit/checkpoint 推进前 upsert observation。任一不匹配都一起回滚 observation、Asset 与 checkpoint 变化。
- Replaying the same subscription/run is idempotent. Another subscription can add a second observation. A semantic- or locator-fingerprint replacement increments Asset generation, resets downloader state and updates the observing subscription's row; other rows remain audit evidence but no longer qualify. / 重放同一 subscription/run 保持幂等；另一 subscription 可新增第二 observation；semantic 或 locator fingerprint 替换会增加 Asset generation、重置下载状态并更新本次观察 subscription 的行，其他行继续作为审计证据但不再 eligible。
- Empty or filtered batches create no observation. A failed or fenced ingestion transaction creates neither Asset change nor provenance. / 空批次或被过滤批次不创建 observation；失败或被 fence 的导入事务既不改变 Asset，也不产生 provenance。

### Read-only selection and Job binding / 只读选择与 Job 绑定

Introduce a closed source-selection result that contains no ORM object or secret. It freezes Asset ID/generation/platform/content remote type and ID/kind/position/synthetic remote ID, semantic/locator fingerprints, query-free source hint, Author platform/remote ID, Account ID/platform/adapter/login method/credential-reference identity/profile identity/auth status, and Subscription ID/account/author/enabled/canonical closed MediaCrawler policy identity. The policy identity covers the creator-secret reference without exposing it.

引入不含 ORM 对象或密钥的封闭 source-selection result。它冻结 Asset ID/generation/platform/content remote type 与 ID/kind/position/合成 remote ID、semantic/locator fingerprint、无 query source hint、Author platform/remote ID、Account ID/platform/adapter/login method/credential-reference identity/profile identity/auth status，以及 Subscription ID/account/author/enabled/canonical closed MediaCrawler policy identity。Policy identity 覆盖 creator-secret reference，但不暴露其值。

Selection has two exact modes:

来源选择分为两个精确模式：

1. **No same-generation Job:** an explicit subscription must be an eligible observation; otherwise return `locator_refresh_source_mismatch`. Without one, zero eligible rows return `locator_refresh_source_unavailable`, exactly one is selected and more than one returns `locator_refresh_source_ambiguous`. / **同 generation 无 Job：** 显式 subscription 必须是 eligible observation，否则返回 mismatch；未显式指定时，零行 unavailable、恰一行自动选中、多行 ambiguous。
2. **Existing same-generation Job:** its closed immutable source binding is authoritative and must still identify one eligible current observation. Optional `--subscription-id` must equal the bound subscription. Missing/open/corrupt/stale binding returns `locator_refresh_source_mismatch`; unrelated newly eligible observations are ignored for ambiguity and never trigger rebind. Retry/running/prepared recovery always follows this mode. / **已有同 generation Job：** 其闭合不可变来源绑定是唯一权威，且必须仍指向一个 current eligible observation；可选 `--subscription-id` 必须等于绑定 subscription。绑定缺失/开放/损坏/过期返回 mismatch；其他后来新增的 eligible observation 不参与歧义判断，也绝不触发 rebind。retry/running/prepared 恢复始终走此模式。
3. Before Job creation/claim, recompute `stable_asset_key()` from authoritative Content/Asset fields and compare it with the parsed locator. Under the shared account security lock, recheck the filesystem cleanup block outside SQLite; then recheck generation, both fingerprints and every frozen database Author/Account/Subscription/configuration identity in the claim transaction. / 创建/认领 Job 前，从权威 Content/Asset 字段重算 `stable_asset_key()` 并与 parsed locator 比较；在共用账户安全锁内、SQLite 外复核文件系统 cleanup block，随后在 claim 事务内复核 generation、两个 fingerprint 及全部冻结数据库 Author/Account/Subscription/configuration 身份。

Keep the existing Job natural key `asset_id:generation`. For MediaCrawler refresh, fill the existing `subscription_id`, `account_id` and `platform` columns and keep `run_id = NULL`. Add a closed immutable `refresh_source` payload containing only schema version, asset/subscription/account IDs, platform and semantic/locator fingerprints; reject unknown fields and never store observation kind, credential refs, policies containing creator references, resolved URLs, source URLs, filesystem roots or profile paths. Observation kind may upgrade from `legacy_unique_inferred` to `ingested` without changing Job source equality. `AssetRefreshSource.last_run_id` is audit only: execution 0009 creates no Job dependency, predecessor, ingestion fan-out or SyncRun ancestry inference.

保持既有 Job natural key `asset_id:generation`。MediaCrawler refresh Job 填充现有 `subscription_id`、`account_id` 与 `platform` 列，并保持 `run_id = NULL`；新增封闭不可变 `refresh_source` payload，只含 schema version、asset/subscription/account ID、platform 及 semantic/locator fingerprint；拒绝未知字段，绝不保存 observation kind、credential ref、含 creator reference 的 policy、resolved URL、source URL、文件系统根或 profile 路径。Observation kind 从 `legacy_unique_inferred` 升级为 `ingested` 不改变 Job 来源相等性。`AssetRefreshSource.last_run_id` 只作审计；执行 0009 不创建 Job dependency、predecessor、导入 fan-out 或 SyncRun ancestry 推断。

### Preflight and recovery ordering / Preflight 与恢复顺序

- Hard order: enable/license -> read-only unresolved-account block fence -> read-only classify already-verified, exact prepared recovery or network-bearing work. Blocked paths call SecretResolver, run attach, bridge/refresh preparation, child spawn and HTTP exactly zero times. / 硬顺序：enable/license → 只读 unresolved-account block fence → 只读分类 already-verified、精确 prepared recovery 或 network-bearing。被 block 的路径对 SecretResolver、run attach、bridge/refresh prepare、child spawn 与 HTTP 的调用数均精确为零。
- Read-only inspection itself is zero-mutation. A valid already-verified archive returns without Job/Asset mutation. Exact prepared recovery may perform only CAS/lease takeover and success finalization of the already-bound Job/Asset generation; it creates no Job, rebinds no source, consumes no new attempt, resolves no credential, spawns no child and issues no HTTP. / 只读 inspection 本身零变更；有效 already-verified archive 不改变 Job/Asset。精确 prepared recovery 只允许对已绑定 Job/Asset generation 做 CAS/lease 接管与成功收尾；不得新建 Job、重绑来源、消耗新 attempt、解析凭据、spawn child 或发起 HTTP。
- For network-bearing work, continue with source/runtime/profile/reference validation -> acquire the shared account/profile security lock -> recheck the filesystem cleanup block outside SQLite -> resolve Cookie/creator secret outside SQLite -> short transaction rechecking only database source/Asset/Author/Account/Subscription/configuration identities and claiming the Job -> supervised refresh -> safe download/finalization -> cleanup -> release lock. Every cleanup path that can create an account block uses this same lock (or an equivalent atomic fence), so no writer can insert a block between the second check and release. / 对需要网络的工作，继续按来源/runtime/profile/reference 验证 → 获取共用账户/profile 安全锁 → SQLite 外复核文件系统 cleanup block → SQLite 外解析 Cookie/creator secret → 短事务只复核数据库来源/Asset/Author/Account/Subscription/配置并 claim → 受监督刷新 → 安全下载/收尾 → cleanup → 释放锁。所有可能创建账户 block 的 cleanup 路径使用同一把锁或等价原子 fence，因而二次检查与释放间不能插入 block。
- If any frozen login method, credential-reference identity, profile identity, auth status, enabled flag, account/author relation or canonical closed-policy identity changes between selection/secret resolution and `_begin`, fail closed. A barrier test creates a block after the first read: lock acquisition plus the second check must stop before SecretResolver, claim and spawn. A secret object may remain in trusted-parent memory during `_begin`, but secret resolution, filesystem checks and external I/O never occur inside a database transaction; closed credential/config identities never enter Job payload or logs. / 若冻结身份在选择/解析密钥与 `_begin` 间变化则 fail closed。Barrier 测试在首次读取后创建 block：取得锁并二次检查必须在 SecretResolver、claim、spawn 前拦截。Secret object 可在 `_begin` 期间暂存可信父内存，但密钥解析、文件系统检查与外部 I/O 绝不进入数据库事务；封闭凭据/配置身份不进入 Job payload 或日志。
- Existing prepared/retry/running recovery keeps its originally bound source and never consumes a new account implicitly. / 既有 prepared/retry/running 恢复保持原绑定来源，绝不隐式使用新账户。

### Refresh port and private child protocol / Refresh port 与私有 child 协议

Replace the context-free `resolve(AdapterRefreshLocator)` call with a frozen `RefreshRequest`/`RefreshContext`. Subscription UUIDs remain outside the globally persisted locator. The resolver returns `ResolvedLocator` with URL hidden from `repr`; execution 0009 deliberately keeps the CDN contract URL-only and does not add credential-bearing request headers.

把无上下文 `resolve(AdapterRefreshLocator)` 调用替换为冻结的 `RefreshRequest`/`RefreshContext`。Subscription UUID 保持在全局持久 locator 之外。Resolver 返回从 `repr` 隐藏 URL 的 `ResolvedLocator`；执行 0009 有意保持 CDN 契约仅 URL，不新增可能携带凭据的请求 header。

Implement a dedicated detail-only child and parent runner, reusing or extracting the existing account/profile lock, checkout/runtime/license verification, start handshake, parent-death supervision, cancellation, descendant join and bounded timeout. The trusted parent never imports MediaCrawler.

实现专用 detail-only child 与父 runner，复用或抽取既有账户/profile 锁、checkout/runtime/license 校验、start handshake、父死亡监督、取消、后代 join 及有界 timeout。可信父进程绝不 import MediaCrawler。

- Private inputs use the existing early-pop secret envelope and never appear in argv, manifest or operator output. / 私有输入复用既有“最先 pop”的密钥 envelope，绝不进入 argv、manifest 或运维输出。
- Create a dedicated inherited OS result pipe/handle that is distinct from fd 1/2; before importing any upstream module, redirect ordinary stdout/stderr to null at OS level. The parent concurrently drains at most 16 KiB plus the overflow probe to EOF, never relays bytes, and closes every local/inherited handle on success, failure, timeout and cancellation. / 创建与 fd 1/2 完全不同的专用继承 OS result pipe/handle；import 任何上游模块前在 OS 层把普通 stdout/stderr 指向 null。父进程并发 drain 至多 16 KiB 加 overflow probe 到 EOF，绝不转发 bytes，并在成功、失败、timeout、取消时关闭全部本地/继承 handle。
- One frame, maximum 16 KiB, canonical UTF-8 JSON plus newline. Success uses a closed schema with version, fixed status, exact request-identity fingerprint and URL; failure contains only version, fixed status and allowlisted code. Exit status, one frame, EOF and handle closure must agree. Watchdog timeout maps to retryable `locator_refresh_temporary`; nonzero exit, no frame, exit/frame disagreement and every invalid-frame shape map to terminal `locator_refresh_result_invalid`; cancellation preserves the existing cancellation result. / 只允许一帧，最大 16 KiB，使用 canonical UTF-8 JSON 加换行。成功帧为含版本、固定状态、精确 request-identity fingerprint 与 URL 的封闭 schema；失败帧只含 version、固定 status 及 allowlist code。退出状态、单帧、EOF 与 handle closure 必须一致。Watchdog timeout 固定映射 temporary；非零退出、无帧、退出/帧不一致及全部无效帧固定映射 result_invalid；取消沿用既有取消结果。
- Reject duplicate/unknown keys, invalid UTF-8, multiple/trailing frames, overflow, truncation, identity mismatch and non-`ResolvedLocator` URL syntax without echoing bytes. / 拒绝重复/未知 key、无效 UTF-8、多帧/尾随、overflow、截断、身份不匹配及不符合 `ResolvedLocator` 的 URL 语法，且不回显原始 bytes。
- Child extracts detail dictionaries in memory before upstream store/JSONL. It never invokes store or writes an attempt/output file. Child code owns semantic candidate validation; the parent validates the fingerprint covering the full frozen request, closed hint contract and URL syntax, not a candidate echo that the frame cannot independently prove. / Child 在上游 store/JSONL 前于内存提取 detail dict，绝不调用 store 或写 attempt/output 文件。Child code 负责候选语义验证；父进程验证覆盖完整冻结 request 的 fingerprint、封闭 hint contract 与 URL syntax，而不是帧无法独立证明的 candidate echo。

### Offline platform selector matrix / 离线平台 selector 矩阵

| Platform / 平台 | Supported current Asset / 支持的当前 Asset | Frozen selector / 冻结 selector | Explicit boundary / 明确边界 |
| --- | --- | --- | --- |
| `xhs` | image, video with exact stored query-free hint / 带精确 stored hint 的 image、video | Strictly parse exact Subscription creator URL; require HTTPS XHS host, matching author ID and non-empty token/source; scan at most 4 x 30 feed items in a 120-second child watchdog, then detail and exact hint selection / 严格解析精确 Subscription creator URL，要求 HTTPS XHS host、作者 ID 一致、token/source 非空；120 秒内最多 4 x 30 条，再取 detail 与精确 hint 选择 | Invalid/mismatched authority=`configuration_invalid`; expired=`auth_expired`; absent after 120=`asset_not_found`; malformed/repeating pagination=`schema_changed`; watchdog=`temporary`; never reconstruct/persist xsec / 固定 disposition；绝不重建/持久化 xsec |
| `dy` | image, video, audio, cover | `get_video_by_id`; reproduce current image-first/video-suppression semantics and exact candidate matching / `get_video_by_id`；复现当前图片优先/抑制 video 语义及精确候选匹配 | Browser state may generate API signing material only inside child / browser 状态只在 child 内生成 API 签名材料 |
| `ks` | video, cover | GraphQL `visionVideoDetail(photoId)`; exact one video/cover candidate / 精确一个 video/cover 候选 | No live CDN claim / 不宣称真人 CDN |
| `bili` | cover only | `/x/web-interface/view/detail` and exact cover match / detail 接口及精确 cover 匹配 | Never call playurl; no playable video/DASH/multi-part claim / 绝不调用 playurl；不宣称可播放视频/DASH/多 P |
| `wb`, `tieba`, `zhihu` | none / 无 | Fixed `locator_refresh_platform_unsupported`; no child spawn / 固定 unsupported；不 spawn | Asset discovery remains unimplemented / Asset discovery 仍未实现 |

Every supported Asset must have an exact stored query-free hint. The synthetic `Asset.remote_id` and numeric position are not durable platform variant IDs. Inside the trusted child, position may only participate after current normalization semantics and the hint have produced a unique candidate set; it cannot break same-kind ambiguity by itself. The child emits only the full-request fingerprint after that check. A missing hint or a hint that no longer chooses exactly one candidate returns `locator_refresh_asset_mismatch`.

每个受支持 Asset 都必须有精确 stored query-free hint。合成 `Asset.remote_id` 与数字 position 不是持久平台 variant ID。在可信 child 内，只有当前归一化语义及 hint 已产生唯一候选集合后，position 才可参与验证；它自身不能消除同 kind 歧义。Child 只在完成该检查后发出完整 request fingerprint。Hint 缺失或不能继续精确选择唯一候选时返回 `locator_refresh_asset_mismatch`。

### Fixed error taxonomy / 固定错误分类

| Phase / 阶段 | Fixed codes / 固定 code | Disposition / 处置 |
| --- | --- | --- |
| Zero-mutation preflight / 零变更 preflight | `locator_refresh_disabled`, `license_acknowledgement_required`, `locator_refresh_source_unavailable`, `locator_refresh_source_ambiguous`, `locator_refresh_source_mismatch`, `locator_refresh_platform_unsupported`, `locator_refresh_kind_unsupported`, `locator_refresh_qr_required`, `locator_refresh_credentials_unavailable`, `locator_refresh_configuration_invalid` | No Job/Asset mutation / 不变更 Job/Asset |
| Retryable attempt / 可重试 attempt | `locator_refresh_account_busy`, `locator_refresh_auth_expired`, `locator_refresh_rate_limited`, `locator_refresh_temporary` | Fixed redacted retryable failure under existing attempt limits / 在既有 attempt 上限下固定脱敏可重试失败 |
| Terminal/security / 终态/安全 | `locator_refresh_asset_not_found`, `locator_refresh_schema_changed`, `locator_refresh_asset_mismatch`, `locator_refresh_result_invalid` | Fixed terminal failure; no raw child bytes / 固定终态失败；无原始 child bytes |

Retain `locator_refresh_unsupported` as the generic media-layer code when no refresher is supplied; the MediaCrawler CLI preflight must normally prevent reaching it. All public messages remain fixed in the error registry.

未提供 refresher 时，媒体层继续使用通用 `locator_refresh_unsupported`；MediaCrawler CLI preflight 正常情况下必须在到达该分支前阻止。全部公开消息在错误 registry 中保持固定。

### Downloader re-resolution / 下载器重新解析

- Direct locator behavior is byte-for-byte unchanged. Adapter refresh resolves once immediately before HTTP. / Direct locator 行为逐字节保持不变；adapter refresh 在 HTTP 前解析一次。
- Only an HTTP 401/403 from an adapter-refresh request can consume one additional resolution. Reuse the exact frozen source/context. A second 401/403 raises `locator_refresh_auth_expired`; other statuses retain existing classification. / 只有 adapter-refresh 请求的 HTTP 401/403 可再消耗一次解析；复用精确冻结来源/context。第二次 401/403 抛 `locator_refresh_auth_expired`；其他状态保持既有分类。
- `.part` metadata and recovery identity use only the canonical persistent locator fingerprint. A refreshed query, expiry, API header or Cookie never reaches metadata, archive names or result payloads. / `.part` metadata 与恢复身份只使用 canonical 持久 locator fingerprint；刷新 query、过期时间、API header 或 Cookie 绝不进入 metadata、archive 名或结果 payload。
- Range/If-Range remains safe. If a new signed URL answers a resumed request with `200`, the existing bounded restart logic discards/restarts rather than appending incompatible bytes. / Range/If-Range 继续保持安全；若新签名 URL 对续传请求返回 `200`，既有有界重启逻辑会丢弃/重启，而不是追加不兼容字节。
- No Cookie, Origin or Referer is added to `SafeHttpClient` redirects. If a real CDN requires such credentials, that live row remains unsupported/`NOT_RUN`; execution 0009 does not bypass DNS pinning, redirect, Range, size or probe contracts by downloading inside the child. / 不向 `SafeHttpClient` redirect 添加 Cookie、Origin 或 Referer；若真实 CDN 需要这类凭据，该真人行继续 unsupported/`NOT_RUN`。执行 0009 不在 child 内下载以绕过 DNS pinning、redirect、Range、大小或 probe 契约。

### Successful/recovery terminal cleanup / 成功与恢复终态清理

Repair four existing gaps: fresh `_ingest()` success currently returns with its root; recovered success drops source paths; already-succeeded restart returns before cleanup; and malformed in-memory result or authoritative readback failure after a committed success can still reach `_set_run_failure()`.

修复现有四个缺口：fresh `_ingest()` 成功当前会保留根；recovered success 丢失 source paths；already-succeeded restart 会在清理前返回；成功提交后的内存 result 畸形或权威 readback 失败仍可能到达 `_set_run_failure()`。

1. Extend `_RecoveredOutput` with exact `source_paths`. Recovered ingestion cleans that source root, never the new successor path. / 为 `_RecoveredOutput` 增加精确 `source_paths`；恢复导入清理来源根，绝不清理新 successor path。
2. After authoritative DB success and before outward success, run terminal cleanup through the repeated-cancellation-safe join helper. Lease loss/cancellation does not let the caller unwind before cleanup reaches a secured/unresolved verdict. / 权威 DB 成功后、向外成功前，通过可抵御重复取消的 join helper 执行终态清理；lease loss/取消不得让调用方在清理得到 secured/unresolved 结论前 unwind。
3. For an already-succeeded restart, validate a closed run-metadata schema. Fresh cleanup uses top-level attempt/execution identity. Recovered cleanup uses `recovered_artifact` source attempt/execution/run identity and proves `execution_id == uuid5(job_id, "media-sync/mediacrawler/attempt/{source_attempt}")`. Never trust an open path or successor execution ID. / already-succeeded 重启验证封闭 run metadata schema；fresh 使用顶层 attempt/execution 身份；recovered 使用 `recovered_artifact` 来源 attempt/execution/run 身份，并证明确定性 UUID；绝不信任开放路径或 successor execution ID。
4. Make `cleanup_attempt_root()` concurrency-idempotent. After every no-follow/scope check and rename/remove transition, disappearance caused by a concurrent exact cleanup converges to safe `ABSENT`/`REMOVED`; it must not become false `UNRESOLVED`. Unsafe replacement, escape or unverifiable metadata still fails closed. / 使 `cleanup_attempt_root()` 并发幂等；每个 no-follow/scope 检查及 rename/remove 迁移后，另一精确清理导致的消失都收敛为安全 `ABSENT`/`REMOVED`，不得成为虚假 `UNRESOLVED`；不安全替换、逃逸或不可验证 metadata 仍 fail closed。
5. Introduce an explicit post-commit-success boundary. Once authoritative Run/checkpoint/content success exists, malformed result objects, readback mismatch/error, all four cleanup states, cancellation and lease loss may only produce fixed control outcomes while preserving database truth. They never call `_set_run_failure()`, re-ingest or roll back; repeated restart performs exact cleanup only. / 新增显式“成功提交后”边界。一旦权威 Run/checkpoint/content 成功存在，result 畸形、readback mismatch/error、四种 cleanup 状态、取消与 lease loss 都只能在保留数据库事实的前提下产生固定 control outcome；不得调用 `_set_run_failure()`、重复导入或回滚；重复 restart 只做精确 cleanup。

Terminal state mapping is fixed:

终态映射固定如下：

| Cleanup / 清理 | Database truth / 数据库事实 | Outward behavior / 向外行为 |
| --- | --- | --- |
| `ABSENT`, `REMOVED` | Preserve succeeded Run/checkpoint/content / 保留 succeeded Run/checkpoint/content | Success / 成功 |
| `QUARANTINED` | Preserve success; isolated root remains an enumerated credential-bearing boundary / 保留成功；隔离根继续为枚举的可能携带凭据边界 | Success with only fixed internal disposition; no path / 仅固定内部 disposition 的成功；无路径 |
| `UNRESOLVED` | Preserve success, attempt fixed marker persistence and hard-fence account / 保留成功，尝试固定 marker 并硬 fence 账户 | Raise fixed cleanup-blocked control result; never stale-fail/reingest / 抛固定 cleanup-blocked 控制结果；绝不 stale-fail/重复导入 |

The persistent unresolved account block has no automatic clear path in execution 0009. No restart, refresh or manual download silently bypasses it.

执行 0009 不提供持久 unresolved account block 的自动清除路径；任何重启、刷新或手工下载都不得静默绕过。

### Security and retained evidence / 安全与留存证据

- A signed-URL sentinel is generated after collection and inserted into the private child frame. A private-pipe observer proves injection before parent consumption; mock HTTP proves the exact URL reached only the request boundary. Separate dynamic sentinels are injected after collection into fresh- and recovered-success JSONL roots, proved non-empty before cleanup, then the exact source roots are proved removed/secured; already-succeeded restart proves the same source identity. / 签名 URL 哨兵在 collection 后生成并写入私有 child 帧；私有 pipe observer 在父进程消费前证明注入，mock HTTP 证明精确 URL 只到请求边界。另在 collection 后把动态哨兵注入 fresh/recovered 成功 JSONL 根，清理前证明非空，随后证明精确来源根已 removed/secured；already-succeeded restart 证明相同来源身份。
- Scan every logical SQLite text/JSON value and all database/WAL/SHM bytes; Job/Asset locators, raw/source fields, payloads and results must be query-free and secret-free. / 扫描全部 SQLite 逻辑文本/JSON 值及数据库/WAL/SHM bytes；Job/Asset locator、raw/source 字段、payload 与结果必须无 query/密钥。
- Scan safe attempt/download/archive/sidecar/operator/JUnit trees, hidden and ignored files and path names fail-closed. No scan exclusion inside a declared safe root. / 对安全 attempt/download/archive/sidecar/operator/JUnit 树、隐藏/忽略文件及路径名执行 fail-closed 扫描；声明为安全的根内不设排除。
- Persistent profile, deliberate quarantine and unresolved cleanup evidence are a separately named negative set. Never delete or rewrite them to satisfy a scan; never expose their paths. / 持久 profile、故意 quarantine 与 unresolved 清理证据属于单独命名负向集合；不得为扫描通过而删除/改写，也不得暴露其路径。
- Use a fresh ignored `.media-sync/verification/0009-refresh-sentinel-root` exactly once. It must not exist before the authoritative run and must never be deleted/recreated afterward. The 0007 and 0008 retained roots are read-only and untouched. / 全新忽略根 `.media-sync/verification/0009-refresh-sentinel-root` 只运行一次；权威运行前不得存在，之后不得删除/重建；0007 与 0008 留存根只读且不触碰。

## Implementation sequence / 实现顺序

1. Add red tests for fresh/recovered/already-succeeded terminal cleanup and concurrent exact-root cleanup; implement the minimal cleanup/state repair first. / 先为 fresh/recovered/already-succeeded 终态清理及并发精确根清理新增红测，再实现最小清理/状态修复。
2. Add `0005_asset_refresh_sources`, ORM/repository APIs, conservative backfill and packaged migration round-trip tests. / 新增 `0005_asset_refresh_sources`、ORM/repository API、保守 backfill 及随包 migration 往返测试。
3. Integrate exact observation upsert into fenced MediaCrawler ingestion and prove replay/replacement/generation-reset semantics. / 把精确 observation upsert 集成进受保护 MediaCrawler 导入，并证明重放/替换/generation-reset 语义。
4. Add read-only source selection, immutable Job source payload/columns and zero-mutation CLI preflight. / 新增只读来源选择、不可变 Job 来源 payload/列及零变更 CLI preflight。
5. Define the context-aware refresh port, fixed error taxonomy and strict private child frame. / 定义有上下文 refresh port、固定错误分类及严格私有 child 帧。
6. Implement supervised fake-detail shapes for XHS/Douyin/Kuaishou/Bilibili and fixed no-spawn unsupported paths for the remaining platforms. / 实现 XHS/抖音/快手/Bilibili 受监督 fake detail 形状，以及其余平台固定不 spawn unsupported 路径。
7. Integrate one-time 401/403 re-resolution into the existing secure downloader and wire the explicit CLI. / 把一次性 401/403 re-resolution 接入既有安全下载器，并连接显式 CLI。
8. Run focused platform/supervision/migration/cleanup/security gates, the full suite, build/package checks and the one-shot retained sentinel; update capability truth without promoting live rows. / 运行平台/监督/migration/清理/安全专项、完整套件、构建/打包及一次性留存哨兵；更新真实能力但不提升真人行。

## Verification plan / 验证计划

| Gate / 门禁 | Required coverage / 必需覆盖 |
| --- | --- |
| Migration / 迁移 | New DB head; constraints/FKs/indexes; exact relation/stable-key legacy backfill; ambiguous/corrupt unbound; upgrade/downgrade/re-upgrade; packaged inventory / 新库 head、约束/FK/索引、精确关系/stable-key legacy backfill、歧义/损坏不绑定、往返及随包清单 |
| Provenance / 来源 | Same-transaction observation; wrong-run/cross-relation rollback; older-run replay cannot regress `(created_at,id)` audit order; multi-account; semantic- and locator-only replacement advance generation; archive reset alone retains eligibility / 同事务 observation、错误关系回滚、旧 run 重放不回退审计全序、多账户、两类替换推进 generation、单独归档 reset 保持资格 |
| Selection/Job / 选择与 Job | No-Job 0/1/N; existing-Job authority; explicit source; audit upgrade; shared-lock second block check catches a barrier writer before SecretResolver/claim/spawn; no filesystem I/O in transaction; config race; `run_id = NULL` / 两种来源模式、共用锁二次 block 检查在密钥/claim/spawn 前拦截 barrier writer、事务无文件 I/O、配置竞态、空 `run_id` |
| Recovery ordering / 恢复顺序 | Verified succeeds with no source/profile/credential/mutation; exact prepared recovery permits only bound CAS/finalization; both make zero SecretResolver/child/HTTP calls / verified 无来源/profile/凭据/变更即可成功；prepared 只允许已绑定 CAS/收尾；两者 SecretResolver/child/HTTP 调用均为零 |
| Child/platform / Child/平台 | Dedicated fd/handle; pre-import null redirection; bounded drain/EOF/closure; strict frame/error matrix; shared account lock held through child tree, download finalization and cleanup; every block writer uses same fence; parent death/cancel; selectors / 专用 handle、严格帧/错误矩阵、共用账户锁覆盖 child tree/下载收尾/cleanup 且 block writer 同 fence、父死亡/取消、selector |
| Downloader / 下载器 | Signed URL reaches mock HTTP; exact one 401/403 re-resolve; direct unchanged; partial resume; no URL/query in metadata; redirect headers unchanged / 签名 URL 到 mock HTTP、精确一次重解析、direct 不变、续传、metadata 无 URL/query、redirect header 不变 |
| Cleanup / 清理 | Non-empty fresh/recovered sentinels; exact restart identity; after real success commit inject malformed result, readback failure/mismatch, four states, repeated cancel/lease loss and restart; assert no failure mutation/reingest; marker failure and concurrent disappearance / 非空来源哨兵、精确重启身份、真实成功提交后注入 result/readback/四状态/取消/重启并断言无 failure mutation/重复导入、marker 失败与并发消失 |
| Secret sinks / 密钥落点 | Private-pipe and mock-transport proof plus exact post-cleanup filesystem/SQLite/operator/JUnit zero-match; named negative exclusions / 私有 pipe 与 mock transport 证明，加清理后文件系统/SQLite/运维/JUnit 精确零匹配及命名负向排除 |
| Root quality / 根质量 | Locked sync; Ruff/format/mypy; full branch-aware pytest; build and wheel smoke; packaged migrations; docs/upstreams/diff/Git checks; fresh retained root / 锁定同步、Ruff/format/mypy、完整分支感知 pytest、构建与 wheel smoke、随包迁移、docs/upstream/diff/Git、全新留存根 |

## Explicit non-goals / 明确非目标

- No durable automatic `sync → download → Emby` DAG, dependency table, fan-out/fan-in or shared-child cancellation semantics; execution 0010 owns them. / 不实现持久自动 DAG、依赖表、fan-out/fan-in 或共享 child 取消语义；这些属于执行 0010。
- No real platform/CDN/Emby traffic or capability promotion. / 不执行真实平台/CDN/Emby 流量，也不提升真人能力。
- No Bilibili playable video/DASH/multi-part/subtitle/danmaku, no Weibo/Tieba/Zhihu Asset discovery and no XHS variant identity redesign beyond fail-closed current-hint matching. / 不实现 Bilibili 可播放视频/DASH/多 P/字幕/弹幕、Weibo/Tieba/Zhihu Asset discovery，也不在 fail-closed 当前 hint 匹配之外重设计 XHS variant 身份。
- No credential-bearing CDN headers, child-side media download, QR presentation UX, phone login, REST, resident supervisor, Docker or HA/PostgreSQL. / 不实现可能携带凭据的 CDN header、child 内媒体下载、QR 展示 UX、手机号登录、REST、常驻监督、Docker 或 HA/PostgreSQL。
- No automatic clearing of unresolved cleanup blocks and no silent source rebind. / 不自动清除 unresolved 清理 block，也不静默重绑来源。
