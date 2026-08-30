# Execution 0005 goal / 执行 0005 目标

Deliver a replay-safe asset lifecycle, a resumable and SSRF-resistant media downloader, content-addressed original storage, and a deterministic Emby/Jellyfin library exporter. All acceptance remains offline: mock HTTP, generated media probes and fixture database rows prove local contracts only.

交付可安全重放的资产生命周期、可续传且抵御 SSRF 的媒体下载器、内容寻址原始归档，以及确定性的 Emby/Jellyfin 媒体库导出器。全部验收保持离线：只用 mock HTTP、生成式媒体探测样本与夹具数据库行证明本地契约。

## Acceptance / 验收

- Discovery replay never downgrades `downloaded`/`verified` assets or overwrites downloader-owned local path, actual MIME, byte size or SHA-256 fields when the semantic asset identity is unchanged. A real remote-identity/resource-version change performs an explicit fenced generation reset instead of pairing a new locator with an old blob.
- Asset locator schema v1 is closed and versioned. `direct` contains only a persistable, non-secret HTTP(S) URL; `adapter_refresh` contains stable non-secret keys and returns fixed `locator_refresh_unsupported` until a refresh adapter is implemented. Unknown forms fail closed.
- Sink redaction recognizes composite API/access-key names across snake_case, kebab-case, camelCase and provider-prefixed forms without treating ordinary `key`, `public_key` or `key_id` fields as secrets. Credential-marker URL paths, including encoded and double-encoded forms, are redacted and cannot become a `direct` locator or source hint. The `0003` legacy backfill clears such an unsafe `source_url` and emits only a stable `adapter_refresh` locator.
- A `0003 → 0002 → 0003` schema round trip cannot reuse poisoned generation identities: downgrade clears `assets.download_job_id` and deletes every `asset_download` Job. It preserves succeeded Emby publication-chain Jobs/records and structurally valid closed publication-intent recovery state, while deleting other non-succeeded Emby Jobs/records.
- Download coordination takes a `work_root`/asset OS lock before any database mutation and holds it through finalization. Busy contenders and requests whose hashed work/archive I/O scope differs from the durable job change no asset/job state and consume no attempt. Lifecycle mutations use compare-and-swap plus an exact owner/token lease; an expired but unreclaimed token may renew, while renewal versus reclaim has a single CAS winner.
- Every redirect is independently validated; userinfo, fragments, non-HTTP schemes, loopback/private/link-local/multicast/unspecified/reserved addresses, mixed public/private DNS and environment proxies are rejected. Connections are pinned to the validated address while preserving the origin Host/SNI.
- Streaming enforces redirect, time, line/chunk and byte limits. Resume uses `.part` plus strong ETag or Last-Modified with strict `Range`/`If-Range`/`Content-Range` handling and bounded restart behavior.
- Completed bytes pass SHA-256 plus bounded MIME/container probing before a same-filesystem no-clobber publish to `archive/sha256/<prefix>/<digest>.<verified-ext>`. The lease/generation guard runs after copy, fsync and rehash and immediately before commit, including existing-blob reuse. Existing blobs are revalidated; path escapes, unsafe objects present at operation time and detected leaf replacement fail closed. A committed archive may be recovered after database-finalization failure, and `.part` cleanup occurs best-effort only after atomic asset/job success. For 0.x, configured runtime roots and all ancestors are trusted operator-controlled directories; hostile same-permission parent-directory substitution is outside the threat model.
- Stable, title-independent Emby paths use UTC season years and platform/type-scoped content identities. Repeated export is byte-for-byte deterministic. A successful `export.emby` Job durably anchors publication scope, source/tree/manifest hashes, managed-file count and its exact predecessor Job; the unique predecessor chain, never a manifest discovered only from disk, determines the current publication head and managed ownership.
- Rendering and publication fence the exact database-anchored predecessor and every managed byte. An unexpected first managed manifest, a forged self-consistent manifest, a fork/cycle or a changed predecessor fails closed without adopting or deleting user files. A byte-identical desired tree may roll forward only as recovery for a filesystem publish that committed before database finalization.
- `tvshow.nfo`, episode NFO and allowlisted `source.json` are valid deterministic UTF-8 XML/JSON. XML 1.0-invalid characters, raw envelopes, locators and signed URLs never enter exports.
- Verified video/audio becomes playable episode media; verified covers/images use deterministic poster/backdrop fallback; gallery/text assets remain preserved even when no playable derivative exists.
- Export records have explicit begin/complete/fail lifecycle and canonical source/rendered fingerprints; one asset is not globally marked `exported` because multiple exporter versions may consume it. Empty snapshots remain durable through the publication Job even when no ExportRecord exists; publish intent, record completion and the final Job result provide restart-safe recovery.
- CLI paths cover asset download and Emby export with fixed redacted errors. Missing mandatory `ffprobe` and unsupported `adapter_refresh` preflights report `blocked`/`not_started` plus the unchanged persisted status without creating a job or mutating the asset. Golden-tree, failure injection, restart, package, docs and secret-sentinel gates pass.

- 语义资产身份未变化时，发现重放不得把 `downloaded`/`verified` 资产降级，也不得覆盖下载器拥有的本地路径、实际 MIME、字节数或 SHA-256；真实远端身份/资源版本变化时必须执行显式 fenced generation reset，不能把新 locator 与旧 blob 错配。
- 资产 locator v1 是封闭且版本化的契约。`direct` 只含可持久化、非机密的 HTTP(S) URL；`adapter_refresh` 只含稳定非密钥键，在刷新适配器实现前固定返回 `locator_refresh_unsupported`；未知形式默认拒绝。
- 落点脱敏会识别 snake_case、kebab-case、camelCase 及带提供商前缀的组合 API/access-key 名称，不会把普通 `key`、`public_key` 或 `key_id` 字段误当密钥。带凭据标记的 URL 路径（包括编码与双重编码形式）会被脱敏，且不能成为 `direct` locator 或 source hint。`0003` legacy 回填会清空这类不安全 `source_url`，只产生稳定 `adapter_refresh` locator。
- `0003 → 0002 → 0003` schema 往返不得复用被污染的 generation 身份：downgrade 会清空 `assets.download_job_id` 并删除全部 `asset_download` Job。已成功的 Emby 发布链 Job/record 及结构严格有效的封闭发布 intent 恢复状态必须保留，其他未成功的 Emby Job/record 必须删除。
- 下载协调在任何数据库变更前获取 `work_root`/资产 OS 锁，并持有至最终收尾。锁忙竞争者及 work/archive I/O scope 哈希与持久 job 不一致的请求不会改变资产/job，也不消耗 attempt。生命周期使用 CAS 与精确 owner/token 租约；已到期但未被 reclaim 的 token 可以续期，续期与 reclaim 只能有一个 CAS 胜者。
- 每次重定向独立校验；拒绝 userinfo、fragment、非 HTTP 协议、本机/私网/link-local/组播/未指定/保留地址、混合公私 DNS 及环境代理。连接固定到已验证地址，同时保留源站 Host/SNI。
- 流式下载限制重定向、总时长、分块及字节数；续传使用 `.part`，并以强 ETag 或 Last-Modified 配合严格的 `Range`/`If-Range`/`Content-Range` 与有界重启。
- 完整字节在发布前通过 SHA-256 与有界 MIME/容器探测，再以 no-clobber 方式写入 `archive/sha256/<prefix>/<digest>.<verified-ext>`。租约/generation guard 位于复制、fsync、重哈希之后和最终提交之前，复用既有 blob 也必须执行。既有 blob 必须复核；路径逃逸、操作时已存在的不安全对象及可检测的叶节点替换默认拒绝。归档已提交但数据库收尾失败时可以恢复；`.part` 只在资产/job 原子成功后做 best-effort 清理。0.x 把已配置运行根目录及全部祖先视为操作员控制的可信目录；同权限恶意进程替换父目录不在威胁模型内。
- Emby 路径稳定且不依赖可变标题，使用 UTC 年份 season 和带平台/类型命名空间的内容身份；重复导出逐字节确定。每个成功 `export.emby` Job 持久锚定 publication scope、source/tree/manifest 哈希、受管文件数量及精确前序 Job；当前发布 head 与受管所有权只由唯一前序链确定，绝不由仅从磁盘发现的 manifest 自证。
- 渲染与发布会 fence 数据库锚定的精确 predecessor 及每个受管字节。首次发布遇到意外 managed manifest、自洽伪造 manifest、分叉/环或 predecessor 变化时默认拒绝，不接管或删除用户文件。只有在文件系统已发布而数据库尚未收尾的恢复场景中，逐字节一致的 desired tree 才允许 roll forward。
- `tvshow.nfo`、episode NFO 与白名单 `source.json` 是确定性 UTF-8 XML/JSON；XML 1.0 非法字符、raw envelope、locator 与签名 URL 不得进入导出。
- 已验证视频/音频成为可播放 episode；已验证封面/图片按确定规则选择 poster/backdrop；没有可播放衍生物时仍保留图集/文本资产。
- ExportRecord 具有显式 begin/complete/fail 生命周期及规范 source/rendered 指纹；同一资产不会被全局标成 `exported`，因为多个 exporter/version 都可能消费它。即使空快照没有任何 ExportRecord，publication Job 仍提供持久锚点；publish intent、record 完成与最终 Job result 共同提供可重启恢复。
- CLI 覆盖资产下载与 Emby 导出，并只给出固定脱敏错误。缺少强制 `ffprobe` 或不支持 `adapter_refresh` 时，preflight 返回 `blocked`/`not_started` 和未改变的持久状态，不创建 job、不修改资产；黄金目录、故障注入、重启、打包、文档与密钥哨兵门禁全部通过。

## Truth boundary / 真实性边界

Current normalized media coverage is incomplete: XHS/Douyin/Kuaishou expose some binary URLs, Bilibili currently exposes covers, and Weibo/Tieba/Zhihu fixtures expose no downloadable asset. Therefore this execution proves a generic offline download/export contract, not seven-platform live media or an actual Emby/Jellyfin rescan. All live rows remain `NOT_RUN`.

当前归一化媒体覆盖并不完整：小红书/抖音/快手暴露部分二进制 URL，B 站当前只有封面，微博/贴吧/知乎夹具没有可下载资产。因此本执行只证明通用离线下载/导出契约，不证明七平台真人媒体可用，也不冒充真实 Emby/Jellyfin 重扫；所有线上项继续保持 `NOT_RUN`。

`NOT_RUN` applies to authorized live QR/Cookie/saved-session login, creator sync, signed-locator refresh/CDN retrieval and Emby/Jellyfin scan/playback. Phone login exposure, MediaCrawler refresh, platform-specific derivatives, scheduler/API and production packaging are unsupported, unavailable or deferred implementation scope rather than unexecuted qualification rows. Automated mock/fixture success can never promote a live row.

`NOT_RUN` 适用于授权真人二维码/Cookie/保存会话登录、作者同步、签名 locator refresh/CDN 下载及 Emby/Jellyfin 扫描/播放。手机号登录对外能力、MediaCrawler refresh、平台特有衍生物、调度/API 与生产打包属于不支持、不可用或延期实现范围，而不是尚未执行的验收行。自动 mock/fixture 成功永远不能提升真人行。
