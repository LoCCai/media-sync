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

The MediaCrawler bridge exposes QR, Cookie and a previously saved per-account browser session. It does **not** claim phone support. A future native adapter may expose phone login only after an interactive end-to-end qualification. This intentionally differs from the overly broad upstream enum.

MediaCrawler 桥接器只开放二维码、Cookie 和已保存的账户级浏览器会话，**不宣称支持手机号登录**。未来原生适配器只有通过交互式端到端验收后才能开放手机号登录。这一点有意区别于上游过宽的枚举声明。

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

MediaCrawler-discovered assets intentionally persist only a stable `adapter_refresh` locator because platform/CDN URLs may contain expiring signatures. The refresh adapter remains unimplemented through 0008, so CLI preflight reports `blocked`/`not_started`, the unchanged `persisted_status` and fixed code `locator_refresh_unsupported` without creating a Job or mutating the Asset; this prevents accidental persistence of signed URLs. Real CDN retrieval and an Emby/Jellyfin rescan therefore remain `NOT_RUN` for every platform until an authorized account and refresh path are qualified.

MediaCrawler 发现的资产只持久化稳定的 `adapter_refresh` locator，因为平台/CDN URL 可能包含过期签名。截至 0008 仍未实现 refresh adapter，因此 CLI preflight 返回 `blocked`/`not_started`、未改变的 `persisted_status` 及固定代码 `locator_refresh_unsupported`，不创建 Job、不修改 Asset，避免误存签名 URL。七个平台的真实 CDN 获取及 Emby/Jellyfin 重扫仍保持 `NOT_RUN`，直到在用户授权账户与 refresh 路径上完成验收。

Execution 0009 currently adds only a frozen contract, not runtime capability: a many-to-many Asset/Subscription observation, immutable generation-bound Job source, a dedicated child result pipe distinct from stdout/stderr, child-owned exact candidate selection, URL-only parent download, and fresh/recovered/restart terminal cleanup. Any semantic or persisted locator replacement must start a new generation; a generation-only archive reset keeps matching provenance eligible. The network path is hard-fenced by enable/license and unresolved cleanup state before secrets, Job attachment or child spawn. Implementation and offline behavior evidence remain `NOT_RUN`.

执行 0009 当前只新增冻结契约，不新增运行能力：多对多 Asset/Subscription observation、generation-bound 不可变 Job 来源、与 stdout/stderr 分离的专用 child 结果 pipe、child 内精确候选选择、父进程仅 URL 下载，以及 fresh/recovered/restart 终态清理。任何 semantic 或持久 locator 替换都必须开启新 generation；单纯归档 reset 后匹配来源仍 eligible。网络路径必须在密钥解析、Job attach 或 child spawn 前先通过 enable/license 与 unresolved cleanup 硬 fence。实现与离线行为证据继续为 `NOT_RUN`。

Successful sealed v3 attempt output remains a separate temporary boundary: its JSONL may contain an unknown signed query that the parent could not pre-register as a known secret. Execution 0008 does not broaden its failure-artifact zero-match proof to that recovery root. Execution 0009 must implement refresh together with successful/recovery terminal cleanup or isolation before automatic network-bearing work is enabled.

成功密封的 v3 attempt 输出仍是独立临时边界：其 JSONL 可能含父进程无法预先登记的未知签名 query。执行 0008 不会把失败产物零匹配证明扩大到该恢复根；执行 0009 必须在启用自动网络工作前，把 refresh 与成功/恢复终态清理或隔离一并实现。

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
| Durable scheduling / 持久调度 | In-memory WebUI queue only / 仅内存 WebUI 队列 | Execution 0006 provides durable due cycles, retry policy and platform/account launch lanes; execution 0007 adds the default-off, license-gated MediaCrawler forward handler with attempt roots, parent heartbeat/supervision and exact ingestion fencing. Its historical AC6/AC13 records remain `PARTIAL`; execution 0008 now passes their successor offline closeout with both remaining cancellation barriers and the exact 33-cell failure/sink matrix / 执行 0006 提供持久到期周期、重试策略与平台/账户启动 lane；执行 0007 新增默认关闭、受许可证约束的 MediaCrawler forward handler，包含 attempt 根、父进程 heartbeat/监督与精确导入 fencing。其历史 AC6/AC13 记录继续为 `PARTIAL`；执行 0008 现以两个剩余取消 barrier 与精确 33-cell 失败/落点矩阵通过继任离线收口 |

## Qualification status / 验收状态

Execution 0007 supplies automated offline evidence for all seven identifiers: subscribe → tick → manifest-v3 write/load → a real local fake child writes versioned JSONL → receipt-v2 write/read → guarded ingestion → retry/restart → idempotent replay. This proves the media-sync/child filesystem protocol and durable identities only. It does not use a browser, platform account, creator endpoint, CDN or media server, and it does not prove bounded upstream pagination or live compatibility.

执行 0007 已为七个平台标识提供自动化离线证据：“订阅 → tick → manifest-v3 写入/读取 → 真实本地 fake child 写入版本化 JSONL → receipt-v2 写入/读取 → 受保护导入 → 重试/重启 → 幂等重放”。这只证明 media-sync/子进程文件系统协议与持久身份；没有使用浏览器、平台账户、作者端点、CDN 或媒体服务器，也不证明上游分页有界或真人兼容。

No live account or interactive challenge has been used. All seven live QR/Cookie/saved-session login, creator traffic and scheduled-run entries remain `NOT_RUN`; phone login remains unsupported rather than merely untested. No live signed-locator refresh/CDN retrieval or real Emby/Jellyfin scan/playback has run. Execution 0007's own AC6/AC13 records remain historical `PARTIAL` evidence.

仍未使用真人账户或交互挑战。七个平台的真人二维码/Cookie/保存会话登录、作者流量及定时运行全部保持 `NOT_RUN`；手机号登录仍属于不支持，而不是仅未测试。没有运行真实签名 locator 刷新/CDN 获取或真实 Emby/Jellyfin 扫描/播放。执行 0007 自身的 AC6/AC13 记录继续作为历史 `PARTIAL` 证据。

Execution 0008 now closes only those two gaps as successor offline evidence. The deterministic child-exit/pre-seal and single/repeated post-seal/pre-ingest barriers pass, and the exact eleven-failure × three-sink matrix proves 33 cells with fail-closed retained-filesystem/SQLite scans and fixed operator authority. The full suite passes 837 tests with one Windows-inapplicable skip and 79% branch-aware coverage. Execution 0009 has frozen the signed-locator refresh/terminal-cleanup plan only; implementation remains `NOT_RUN`. Durable automatic downstream planning remains execution 0010.

执行 0008 现只以继任离线证据关闭上述两个缺口。确定性 child-exit/pre-seal 及单次/重复 post-seal/pre-ingest barrier 通过；精确“11 种失败 × 3 类落点”矩阵以 fail-closed 留存文件系统/SQLite 扫描及固定运维权限证明 33 个 cell。完整套件通过 837 项测试、1 项 Windows 不适用的 skip，分支感知覆盖率 79%。执行 0009 目前只冻结签名 locator refresh/终态清理计划，实现保持 `NOT_RUN`；持久自动下游规划仍属于执行 0010。

Platform-specific DASH/multi-part/subtitle/danmaku and slideshow/mux derivatives, MediaCrawler refresh, per-request HTTP spacing, automatic downstream planning, REST operations, Docker and production operations remain unavailable or deferred implementation scope, not `NOT_RUN` qualification outcomes. The only upstream pacing evidence is configuration of `CRAWLER_MAX_SLEEP_SEC` together with `MAX_CONCURRENCY_NUM=1`; it is not a guarantee for every HTTP request.

平台特有 DASH/多 P/字幕/弹幕及幻灯片/mux 衍生物、MediaCrawler refresh、逐 HTTP 请求间隔、自动下游规划、REST 运维、Docker 与生产运维继续属于不可用或延期实现范围，不是 `NOT_RUN` 验收结果。上游节奏方面唯一已有证据是同时配置 `CRAWLER_MAX_SLEEP_SEC` 与 `MAX_CONCURRENCY_NUM=1`；这不是每次 HTTP 请求的间隔保证。
