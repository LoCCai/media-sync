# Platform capability matrix / 平台能力矩阵

- Upstream / 上游：MediaCrawler `d6f7c5bb906b6dac40ddf343ef9e26438a3de092`
- Meaning / 含义：✅ reachable implementation / 可达实现；⚠ partial, unreachable or materially incomplete / 部分、不可达或明显不完整；❌ no-op or absent / 空实现或缺失。

## Login paths / 登录路径

| Platform / 平台 | QR | Cookie | Phone in source / 源码手机号 | Phone through main CLI / 主入口手机号 | Saved session / 保存会话 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Xiaohongshu / 小红书 `xhs` | ✅ | ✅ | ⚠ implemented / 有实现 | ❌ core passes empty phone / core 传空号码 | ✅ |
| Douyin / 抖音 `dy` | ✅ | ✅ | ⚠ implemented with SMS cache and slider caveats / 有实现但依赖短信缓存并有滑块限制 | ❌ core passes empty phone / core 传空号码 | ✅ |
| Kuaishou / 快手 `ks` | ✅ | ✅ | ❌ `pass` | ❌ | ✅ |
| Bilibili / 哔哩哔哩 `bili` | ✅ | ✅ | ❌ `pass` | ❌ | ✅ |
| Weibo / 微博 `wb` | ✅ | ✅ | ❌ `pass` | ❌ | ✅ |
| Tieba / 百度贴吧 `tieba` | ✅ | ✅ | ❌ `pass` | ❌ | ✅ |
| Zhihu / 知乎 `zhihu` | ✅ | ✅ | ❌ TODO | ❌ | ✅ |

Evidence / 证据：login enum at `cmd_arg/arg.py:52-57`; XHS call site `media_platform/xhs/core.py:103-113` and implementation `media_platform/xhs/login.py:87-224`; Douyin call site `media_platform/douyin/core.py:100-109` and implementation `media_platform/douyin/login.py:53-89,124-169,266-274`; placeholder implementations in each remaining `media_platform/*/login.py`. The upstream WebUI itself exposes only QR and Cookie (`api/main.py:166-187`).

证据位置：登录枚举位于 `cmd_arg/arg.py:52-57`；小红书调用点与实现分别位于 `media_platform/xhs/core.py:103-113`、`media_platform/xhs/login.py:87-224`；抖音调用点与实现分别位于 `media_platform/douyin/core.py:100-109`、`media_platform/douyin/login.py:53-89,124-169,266-274`；其余平台的占位实现位于各自的 `media_platform/*/login.py`。上游 WebUI 本身只开放二维码与 Cookie（`api/main.py:166-187`）。

### media-sync 0.x exposure / media-sync 0.x 对外能力

Execution 0011's current worktree exposes an explicit, blocking QR-login command for one eligible initial MediaCrawler QR account or one exact `saved_session/expired` account across all seven platform identifiers. Both `--enable-mediacrawler` and `--accept-mediacrawler-license` are required before settings, database or child work. The isolated login-only child forces a headed browser and saved state; reauthentication start atomically becomes `qr/authenticating`, successful durable handoff changes the account to derived per-account `saved_session/authenticated`, and non-success leaves a retryable QR state. Cookie remains a non-interactive secret-reference path, saved sessions are background/headless outside this explicit reauthentication flow, and phone is **not** exposed. This intentionally differs from the overly broad upstream enum.

执行 0011 当前工作树已为七个平台标识开放针对一个合格初始 MediaCrawler QR 账户或精确 `saved_session/expired` 账户的显式阻塞登录命令。在读取设置、数据库或启动 child 前，必须同时提供 `--enable-mediacrawler` 与 `--accept-mediacrawler-license`。隔离的仅登录 child 强制有头浏览器并保存状态；重认证启动时原子变为 `qr/authenticating`，持久成功交接会把账户切换为派生的逐账户 `saved_session/authenticated`，非成功则留在可重试 QR 状态。Cookie 继续走非交互密钥引用，显式重认证之外的 saved session 只允许后台无头使用，且**不开放手机号登录**。这一点有意区别于上游过宽的枚举声明。

The focused offline gate proves the closed seven-identifier protocol, state transitions, process-tree join and redaction behavior; it does not prove a real QR render or login. Every live row remains `NOT_RUN`, and phone remains unsupported rather than untested. / 离线专项门禁证明封闭七标识协议、状态迁移、进程树 join 与脱敏行为，但不证明真人二维码可渲染或可登录。全部真人行保持 `NOT_RUN`；手机号仍为不支持，而不是仅未测试。

## Creator/content behavior / 作者与内容行为

| Platform / 平台 | Creator reference / 作者输入 | Creator content / 作者内容 | Upstream cap behavior / 上游数量上限 | Profile persisted / 作者资料落库 |
| --- | --- | --- | --- | ---: |
| `xhs` | 24-char ID or profile URL; token parameters may be required / ID 或主页 URL，可能需要 token 参数 | Image/video notes / 图文与视频笔记 | ✅ page loop checks maximum / 分页检查上限 | ❌ |
| `dy` | `sec_user_id` or `/user/...` / ID 或主页 URL | Image/video aweme / 图文与视频作品 | ❌ traverses until `has_more=0` / 遍历到结束 | ❌ |
| `ks` | user ID or `/profile/...` / ID 或主页 URL | Video posts / 视频作品 | ❌ traverses until `no_more` / 遍历到结束 | ❌ |
| `bili` | UID or space URL / UID 或空间 URL | Creator videos / 投稿视频 | ❌ full history, 30 per page / 30 条每页全历史 | ❌ |
| `wb` | numeric user ID / 数字 ID | Weibo notes / 微博内容 | ❌ full mobile-container pagination / 全量分页 | ❌ |
| `tieba` | home URL; CLI also accepts portrait ID / 主页 URL；CLI 可接收 portrait ID | Author threads / 作者主题 | ✅ checks configured maximum / 检查配置上限 | ❌ |
| `zhihu` | `/people/<url_token>` | Answers only by default; article/video calls disabled / 默认只抓回答，文章和视频被关闭 | ❌ ignores cap and traverses answers until end / 忽略上限并遍历全部回答 | ❌ |

Creator-mode dispatch exists for all seven platforms (`media_platform/*/core.py:120-142`). The CLI routes `--creator_id` into six platform lists but omits Zhihu (`cmd_arg/arg.py:388-402`). Most creator stores are deliberately no-ops and content uses an anonymized creator hash (`tools/user_hash.py:11-36`; `store/{xhs,douyin,kuaishou,bilibili,weibo,tieba}/__init__.py`). Zhihu's creator core does not call a creator store, and its JSONL `store_creator` is also a no-op, so no platform in this bridge provides a trustworthy creator profile row.

七个平台均存在 creator-mode 分发（`media_platform/*/core.py:120-142`）。CLI 会把 `--creator_id` 路由到六个平台列表，但遗漏知乎（`cmd_arg/arg.py:388-402`）。多数 creator store 有意为空操作，内容只使用匿名化作者哈希（`tools/user_hash.py:11-36`；`store/{xhs,douyin,kuaishou,bilibili,weibo,tieba}/__init__.py`）。知乎 creator core 不调用 creator store，其 JSONL `store_creator` 也为空操作，因此该桥接中的任何平台都不能提供可信作者资料行。

### Bridge policy / 桥接策略

- Preserve the user-supplied remote creator ID and a user-provided display label in the independent `media-sync` database.
- Give every run a hard wall-clock timeout and output-item watchdog.
- Require an explicit `allow_full_history` acknowledgement for an upstream path known to ignore its item cap until a bounded native adapter exists.
- Stop incremental ingestion at known IDs/publish watermark even if the child emitted older records; never treat downstream truncation as proof that upstream traffic was bounded.
- Work around Zhihu creator input in the external runner without editing the upstream checkout.

- 在独立数据库保存用户输入的远端作者 ID 与用户提供的显示名称。
- 每次任务设置硬超时和输出条数看门狗。
- 对已知忽略数量上限的平台，在原生适配器实现有界分页前，必须显式确认 `allow_full_history`。
- 即使子进程产生旧数据，导入也在已知内容 ID/发布时间水位处停止；但不得把“导入截断”冒充“上游请求已受限”。
- 在外部运行器中兼容知乎作者参数，不修改上游检出。

## Media behavior / 媒体行为

| Platform / 平台 | Metadata / 元数据 | Upstream binary download / 上游二进制下载 | Qualification / 评价 |
| --- | ---: | --- | --- |
| `xhs` | ✅ | Images and video / 图片与视频 | ⚠ full response in memory, no resume/checksum / 整体读内存，无续传/校验 |
| `dy` | ✅ | Images and video / 图片与视频 | ⚠ same limitations / 同上 |
| `ks` | ✅ | ❌ URL only / 仅 URL | Requires media-sync downloader / 需自有下载器 |
| `bili` | ✅ | ⚠ first CID, one progressive URL only / 仅首 CID 和单个 progressive URL | Missing DASH mux, multi-P, subtitle and danmaku / 缺 DASH 合并、多 P、字幕、弹幕 |
| `wb` | ✅ | ⚠ images only and creator path does not call it / 仅图片且作者路径未调用 | Requires normalized asset discovery / 需自有资产发现 |
| `tieba` | ✅ | ❌ | Requires attachment discovery / 需附件发现 |
| `zhihu` | ⚠ answers by default | ❌ | Article/video creator flow disabled / 作者文章与视频流程关闭 |

Media download is disabled by the misspelled non-CLI switch `ENABLE_GET_MEIDAS` (`config/base_config.py:107-108`). Implementations are under `store/*/*_store_media.py`; current HTTP clients buffer complete responses and lack `.part`, Range resume, MIME/probe and checksum validation.

媒体下载由拼写错误且不对 CLI 开放的开关 `ENABLE_GET_MEIDAS` 禁用（`config/base_config.py:107-108`）。实现位于 `store/*/*_store_media.py`；当前 HTTP 客户端会把完整响应读入内存，并缺少 `.part`、Range 续传、MIME/探测与校验和验证。

### media-sync downloader/export status / media-sync 下载与导出状态

Execution 0005 implements an offline-qualified, platform-independent downloader and Emby/Jellyfin layout v1. Query-free `direct` locators use per-hop public-DNS validation, address-pinned connections, manual redirects, strict resumable Range semantics, byte/time limits, MIME/container probing, mandatory bounded `ffprobe` structural validation for video/audio, SHA-256 and immutable content-addressed publication. Download orchestration adds a per-asset OS lock, a non-disclosing work/archive scope fingerprint, exact lease/reclaim CAS and restart recovery after archive commit but before database finalization. In 0.x, these filesystem guarantees assume dedicated operator-controlled runtime roots and ancestors; hostile same-permission parent-directory substitution is outside the threat model.

执行 0005 实现了通过离线验收的平台无关下载器与 Emby/Jellyfin layout v1。无 query 的 `direct` locator 会执行逐跳公网 DNS 验证、固定地址连接、手动重定向、严格断点续传语义、字节/时间限制、MIME/容器探测、音视频强制且有界的 `ffprobe` 结构验证、SHA-256 与不可变内容寻址发布。下载编排还提供逐资产 OS 锁、不披露路径的 work/archive scope 指纹、精确租约/reclaim CAS，以及归档提交后、数据库收尾前的重启恢复。0.x 的这些文件系统保证以运行根目录及祖先是操作员控制的专用目录为前提；同权限恶意进程替换父目录不在威胁模型内。

Export uses deterministic creator/content identities, NFO and allowlisted provenance, an author lock, staging and a filesystem manifest/file CAS. Managed ownership does not come from the disk manifest alone: succeeded `export.emby` Job results form a unique predecessor chain and anchor exact source/tree/manifest hashes. Publication and interrupted roll-forward revalidate the complete desired managed tree before success or journal cleanup. Pre-publish intent supports exact database-finalization recovery, including empty snapshots; `A → B → A` is valid, a forged or unexpected manifest is rejected, and concurrent siblings leave one winner without deleting user-modified or unmanaged files.

导出使用稳定作者/内容身份、NFO 与白名单来源、作者锁、staging 及文件系统 manifest/file CAS。受管所有权不由磁盘 manifest 单独决定：succeeded `export.emby` Job result 组成唯一 predecessor chain，并锚定精确 source/tree/manifest 哈希。发布及中断 roll-forward 会在成功或清理 journal 前复核完整 desired 受管树。发布前 intent 支持精确数据库收尾恢复，包括空快照；允许 `A → B → A`，拒绝伪造或意外 manifest，并发 sibling 只留下一个胜者，且不会删除用户修改或非受管文件。

MediaCrawler-discovered assets intentionally persist only a stable `adapter_refresh` locator because platform/CDN URLs may contain expiring signatures. Execution 0009 commit `98cf387` implements a default-off lazy refresh path bound to the exact current Asset/Subscription observation. `asset download` requires both `--enable-mediacrawler` and `--accept-mediacrawler-license`, plus `--subscription-id` when an exact source must be selected; XHS additionally accepts one ephemeral `--xhs-detail-reference-ref` for the exact note URL. Refreshed signed URLs remain in the private result/memory/HTTP boundary and are not written back to SQLite.

MediaCrawler 发现的资产只持久化稳定的 `adapter_refresh` locator，因为平台/CDN URL 可能包含过期签名。执行 0009 提交 `98cf387` 已实现默认关闭、绑定精确当前 Asset/Subscription observation 的惰性刷新路径。`asset download` 必须同时传入 `--enable-mediacrawler` 与 `--accept-mediacrawler-license`；需要选择精确来源时再传 `--subscription-id`；小红书另接受一个一次性精确 note URL 的 `--xhs-detail-reference-ref`。刷新的签名 URL 只存在于私有结果/内存/HTTP 边界，不写回 SQLite。

Before a network-bearing pipeline creates or mutates any child Job/Asset lifecycle state, production preflight validates the pinned MediaCrawler lock, checkout and Python runtime and verifies that mandatory `ffprobe` is actually launchable. Missing and invalid-but-present configurations both fail before child lifecycle side effects. This is offline configuration coverage, not live CDN qualification.

在可能产生网络流量的 pipeline 创建或修改任何 child Job/Asset 生命周期状态前，生产 preflight 会校验锁定的 MediaCrawler lock、checkout、Python runtime，并验证强制 `ffprobe` 实际可启动。缺失配置与无效但非空的配置都会在 child 生命周期副作用前失败。这是离线配置覆盖，不是真人 CDN 验收。

The offline-qualified refresh shapes are XHS image/video, Douyin image/video/audio/cover, Kuaishou video/cover and Bilibili cover. XHS still needs an operator-supplied exact-note detail reference and does not discover authority for multiple notes automatically. Weibo, Tieba and Zhihu have no normalized downloadable Asset; Bilibili playable video/DASH/multi-part/subtitle/danmaku remains unsupported. Query-free `direct` locators continue to use the platform-independent downloader without enabling MediaCrawler.

通过离线验收的刷新形状为小红书 image/video、抖音 image/video/audio/cover、快手 video/cover 与 Bilibili cover。小红书仍需操作员提供精确 note 详情引用，不能自动发现多个 note 的权限。微博、贴吧、知乎没有已归一化的可下载 Asset；Bilibili 可播放视频/DASH/多 P/字幕/弹幕仍不支持。无 query 的 `direct` locator 继续使用平台无关下载器，无需启用 MediaCrawler。

Execution 0010 composes the durable local workflow without broadening platform support. Scheduler success only enqueues one `pipeline.subscription` coordinator. A separate explicit bounded `pipeline run` scans at most `--scan-limit` candidates per claim, renews the coordinator lease, downloads the exact Subscription's eligible assets sequentially and calls Emby export only after a durable recheck. MediaCrawler refresh stays default-off and license-gated in this second worker too. This is a one-shot control surface, not a daemon.

执行 0010 在不扩大平台支持的前提下组合持久本地工作流。Scheduler 成功只 enqueue 一个 `pipeline.subscription` 协调器；另一个显式有界 `pipeline run` 每次 claim 最多扫描 `--scan-limit` 个候选，续租协调器，串行下载精确 Subscription 的合格资产，并仅在持久复核后调用 Emby 导出。第二个 worker 中的 MediaCrawler refresh 同样保持默认关闭并受许可证 gate 约束。它是一次性控制面，不是 daemon。

Composite API/access-key mapping names are redacted across snake_case, kebab-case, camelCase and provider-prefixed forms without erasing ordinary `key`, `public_key` or `key_id` fields. Credential-marker URL paths, including encoded and double-encoded variants, are redacted at sinks and rejected by both `direct` locators and source-hint derivation. Current ingestion and the `0003` legacy backfill therefore persist only a stable `adapter_refresh` identity for such an asset; the legacy unsafe `source_url` is cleared. On downgrade, `0003` also clears all asset download FKs and generation-bound Jobs, removes non-recoverable non-succeeded Emby identities, and preserves the succeeded publication chain plus structurally valid publication-intent recovery state.

组合 API/access-key 映射名会在 snake_case、kebab-case、camelCase 及带提供商前缀的形式下脱敏，但不会删除普通 `key`、`public_key` 或 `key_id` 字段。带凭据标记的 URL 路径（包括编码及双重编码变体）会在落点脱敏，并被 `direct` locator 与 source-hint 派生同时拒绝。当前导入与 `0003` legacy 回填因此只为此类资产持久稳定 `adapter_refresh` 身份，并清空 legacy 不安全 `source_url`。`0003` downgrade 还会清空所有资产下载 FK 与 generation-bound Job，移除不可恢复的未成功 Emby 身份，同时保留已成功发布链与结构有效的发布 intent 恢复状态。

## Storage and scheduling / 存储与调度

| Capability / 能力 | Upstream state / 上游现状 | media-sync response / media-sync 方案 |
| --- | --- | --- |
| Subscription table / 订阅表 | Absent / 缺失 | Independent normalized schema / 独立统一模型 |
| Run history / 任务历史 | One in-memory WebUI process / WebUI 单个内存进程 | Durable `sync_runs` and events / 持久任务与事件 |
| Incremental cursor / 增量水位 | Absent / 缺失 | Known-ID + publish watermark + optional cursor / 已知 ID + 发布时间水位 + 可选 cursor |
| Idempotent upsert / 幂等写入 | SQL path does select-then-write / SQL 先查后写 | Database unique constraints and atomic upsert / 唯一约束与原子 upsert |
| JSONL isolation / JSONL 隔离 | Per-day append / 按日追加 | Unique output root per run / 每任务独立输出根目录 |
| Multi-account profile / 多账户 profile | Per platform only / 仅按平台 | Per platform and account / 按平台与账户 |
| Interactive authentication / 交互认证 | Platform login code may exit or fall back to QR implicitly / 平台登录代码可能退出或隐式回退二维码 | Execution 0011 adds an explicit double-gated QR command, closed child truth, durable LoginSession state and atomic `saved_session` handoff. Focused and complete offline gates pass; live qualification remains open / 执行 0011 新增显式双 gate QR 命令、封闭 child 真值、持久 LoginSession 状态及原子 `saved_session` 交接；专项与完整离线门禁通过，真人验收仍待完成 |
| Durable scheduling / 持久调度 | In-memory WebUI queue only / 仅内存 WebUI 队列 | Execution 0006 provides durable due cycles, retry policy and platform/account launch lanes; execution 0007 adds the default-off, license-gated MediaCrawler forward handler with attempt roots, parent heartbeat/supervision and exact ingestion fencing. Its historical AC6/AC13 records remain `PARTIAL`; execution 0008 now passes their successor offline closeout with both remaining cancellation barriers and the exact 33-cell failure/sink matrix / 执行 0006 提供持久到期周期、重试策略与平台/账户启动 lane；执行 0007 新增默认关闭、受许可证约束的 MediaCrawler forward handler，包含 attempt 根、父进程 heartbeat/监督与精确导入 fencing。其历史 AC6/AC13 记录继续为 `PARTIAL`；执行 0008 现以两个剩余取消 barrier 与精确 33-cell 失败/落点矩阵通过继任离线收口 |
| Automatic downstream handoff / 自动下游衔接 | Absent / 缺失 | Execution 0010 atomically enqueues `pipeline.subscription` on sync success; an explicit bounded `pipeline run` performs sequential download then Emby export. No resident daemon or HA supervisor is implemented / 执行 0010 在 sync 成功时原子 enqueue；显式有界 `pipeline run` 串行下载后执行 Emby 导出；未实现常驻 daemon 或 HA supervisor |

## Qualification status / 验收状态

Execution 0007 supplies automated offline evidence for all seven identifiers: subscribe → tick → manifest-v3 write/load → a real local fake child writes versioned JSONL → receipt-v2 write/read → guarded ingestion → retry/restart → idempotent replay. This proves the media-sync/child filesystem protocol and durable identities only. It does not use a browser, platform account, creator endpoint, CDN or media server, and it does not prove bounded upstream pagination or live compatibility.

执行 0007 已为七个平台标识提供自动化离线证据：“订阅 → tick → manifest-v3 写入/读取 → 真实本地 fake child 写入版本化 JSONL → receipt-v2 写入/读取 → 受保护导入 → 重试/重启 → 幂等重放”。这只证明 media-sync/子进程文件系统协议与持久身份；没有使用浏览器、平台账户、作者端点、CDN 或媒体服务器，也不证明上游分页有界或真人兼容。

No live account or interactive challenge has been used. All seven live QR/Cookie/saved-session login, creator traffic and scheduled-run entries remain `NOT_RUN`; phone login remains unsupported rather than merely untested. No live signed-locator refresh/CDN retrieval or real Emby/Jellyfin scan/playback has run. Execution 0007's own AC6/AC13 records remain historical `PARTIAL` evidence.

仍未使用真人账户或交互挑战。七个平台的真人二维码/Cookie/保存会话登录、作者流量及定时运行全部保持 `NOT_RUN`；手机号登录仍属于不支持，而不是仅未测试。没有运行真实签名 locator 刷新/CDN 获取或真实 Emby/Jellyfin 扫描/播放。执行 0007 自身的 AC6/AC13 记录继续作为历史 `PARTIAL` 证据。

Execution 0011's current worktree completes the offline-qualified state and process boundaries for explicit QR login, expired saved-session reauthentication and non-interactive saved-session reuse. The final focused gate passes 274 tests and the full suite passes 1080 with one Windows-inapplicable skip. The local child outcome is closed and independent of exit code, but a false upstream saved-session probe may include network ambiguity, so `auth_expired` is conservative rather than an exact remote-cause diagnosis. Missing profile state is distinguished from ordinary `configuration_invalid`. Normal parent paths join the complete process tree and detail fallback runs `async_cleanup`; hard-parent-death LoginSession recovery remains future work. Implementation commit pending; this evidence changes no live qualification row. / 执行 0011 当前工作树已完成通过离线验收的显式 QR 登录、已过期 saved-session 重认证及非交互 saved-session 复用状态/进程边界。最终专项门禁通过 274 项，完整套件通过 1080 项并有 1 项 Windows 不适用的跳过。本地 child 结果封闭且独立于退出码，但上游 saved-session 探测为 false 可能包含网络异常歧义，因此 `auth_expired` 是保守动作而非精确远端原因诊断。profile 缺失状态与普通 `configuration_invalid` 已区分。正常父进程路径会 join 完整进程树，detail fallback 会执行 `async_cleanup`；父进程硬终止后的 LoginSession 回收仍属于未来工作。实现提交待创建；这些证据不会改变任何真人资格行。

Execution 0009's refresh MVP and execution 0010's explicit bounded downstream pipeline are implemented and pass their focused offline gates. This evidence proves repository selection, private fake-detail refresh, deterministic/mock download, durable child recovery and local Emby layout publication; it does not prove any live platform/CDN/media-server row. The production pipeline handler is synchronous and runs through `asyncio.to_thread`; cancelling its asyncio task cannot forcibly terminate the underlying thread, so cooperative cancellation and multi-worker HA remain unqualified.

执行 0009 刷新 MVP 与执行 0010 显式有界下游 pipeline 已实现并通过各自离线专项门禁。这些证据证明 repository 选择、私有 fake-detail 刷新、确定性/mock 下载、持久 child 恢复及本地 Emby 布局发布，不证明任何真人平台/CDN/媒体服务器行。生产 pipeline handler 为同步函数并通过 `asyncio.to_thread` 运行；取消 asyncio task 不能强制终止底层线程，因此协作式取消与多 worker HA 尚未验收。

Platform-specific DASH/multi-part/subtitle/danmaku and slideshow/mux derivatives, XHS multi-note authority discovery, per-request HTTP spacing, resident downstream supervision, cooperative cancellation/HA, REST operations, Docker and production operations remain unavailable or deferred implementation scope, not `NOT_RUN` qualification outcomes. The only upstream pacing evidence is configuration of `CRAWLER_MAX_SLEEP_SEC` together with `MAX_CONCURRENCY_NUM=1`; it is not a guarantee for every HTTP request.

平台特有 DASH/多 P/字幕/弹幕及幻灯片/mux 衍生物、小红书多 note 权限发现、逐 HTTP 请求间隔、常驻下游监督、协作式取消/HA、REST 运维、Docker 与生产运维继续属于不可用或延期实现范围，不是 `NOT_RUN` 验收结果。上游节奏方面唯一已有证据是同时配置 `CRAWLER_MAX_SLEEP_SEC` 与 `MAX_CONCURRENCY_NUM=1`；这不是每次 HTTP 请求的间隔保证。
