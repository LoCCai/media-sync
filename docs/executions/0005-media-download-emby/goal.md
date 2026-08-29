# Execution 0005 goal / 执行 0005 目标

Deliver a replay-safe asset lifecycle, a resumable and SSRF-resistant media downloader, content-addressed original storage, and a deterministic Emby/Jellyfin library exporter. All acceptance remains offline: mock HTTP, generated media probes and fixture database rows prove local contracts only.

交付可安全重放的资产生命周期、可续传且抵御 SSRF 的媒体下载器、内容寻址原始归档，以及确定性的 Emby/Jellyfin 媒体库导出器。全部验收保持离线：只用 mock HTTP、生成式媒体探测样本与夹具数据库行证明本地契约。

## Acceptance / 验收

- Discovery replay never downgrades `downloaded`/`verified` assets or overwrites downloader-owned local path, actual MIME, byte size or SHA-256 fields when the semantic asset identity is unchanged. A real remote-identity/resource-version change performs an explicit fenced generation reset instead of pairing a new locator with an old blob.
- Asset locator schema v1 is closed and versioned. `direct` contains only a persistable, non-secret HTTP(S) URL; `adapter_refresh` contains stable non-secret keys and returns fixed `locator_refresh_unsupported` until a refresh adapter is implemented. Unknown forms fail closed.
- Download lifecycle mutations use compare-and-swap plus an owned job lease. DNS/network/file I/O holds no SQLite transaction; final asset verification and job completion commit atomically.
- Every redirect is independently validated; userinfo, fragments, non-HTTP schemes, loopback/private/link-local/multicast/unspecified/reserved addresses, mixed public/private DNS and environment proxies are rejected. Connections are pinned to the validated address while preserving the origin Host/SNI.
- Streaming enforces redirect, time, line/chunk and byte limits. Resume uses `.part` plus strong ETag or Last-Modified with strict `Range`/`If-Range`/`Content-Range` handling and bounded restart behavior.
- Completed bytes pass SHA-256 plus bounded MIME/container probing before a same-filesystem atomic publish to `archive/sha256/<prefix>/<digest>.<verified-ext>`. Existing blobs are revalidated; paths, symlinks and reparse points fail closed.
- Stable, title-independent Emby paths use UTC season years and platform/type-scoped content identities. Repeated export is byte-for-byte deterministic; a versioned managed-file manifest allows only unchanged prior managed files to be replaced or removed, never unmanaged or user-modified files.
- `tvshow.nfo`, episode NFO and allowlisted `source.json` are valid deterministic UTF-8 XML/JSON. XML 1.0-invalid characters, raw envelopes, locators and signed URLs never enter exports.
- Verified video/audio becomes playable episode media; verified covers/images use deterministic poster/backdrop fallback; gallery/text assets remain preserved even when no playable derivative exists.
- Export records have explicit begin/complete/fail lifecycle and canonical source/rendered fingerprints; one asset is not globally marked `exported` because multiple exporter versions may consume it.
- CLI paths cover asset download and Emby export with fixed redacted errors. Golden-tree, failure injection, restart, package, docs and secret-sentinel gates pass.

- 语义资产身份未变化时，发现重放不得把 `downloaded`/`verified` 资产降级，也不得覆盖下载器拥有的本地路径、实际 MIME、字节数或 SHA-256；真实远端身份/资源版本变化时必须执行显式 fenced generation reset，不能把新 locator 与旧 blob 错配。
- 资产 locator v1 是封闭且版本化的契约。`direct` 只含可持久化、非机密的 HTTP(S) URL；`adapter_refresh` 只含稳定非密钥键，在刷新适配器实现前固定返回 `locator_refresh_unsupported`；未知形式默认拒绝。
- 下载生命周期使用 CAS 与任务租约所有权；DNS/网络/文件 I/O 期间不持有 SQLite 事务；最终资产验证与 job 完成原子提交。
- 每次重定向独立校验；拒绝 userinfo、fragment、非 HTTP 协议、本机/私网/link-local/组播/未指定/保留地址、混合公私 DNS 及环境代理。连接固定到已验证地址，同时保留源站 Host/SNI。
- 流式下载限制重定向、总时长、分块及字节数；续传使用 `.part`，并以强 ETag 或 Last-Modified 配合严格的 `Range`/`If-Range`/`Content-Range` 与有界重启。
- 完整字节在发布前通过 SHA-256 与有界 MIME/容器探测，再原子写入 `archive/sha256/<prefix>/<digest>.<verified-ext>`；既有 blob 必须复核，路径、符号链接与 reparse 默认拒绝。
- Emby 路径稳定且不依赖可变标题，使用 UTC 年份 season 和带平台/类型命名空间的内容身份；重复导出逐字节确定，版本化受管文件 manifest 只允许替换/删除未被用户修改的旧受管文件，绝不处理非受管文件。
- `tvshow.nfo`、episode NFO 与白名单 `source.json` 是确定性 UTF-8 XML/JSON；XML 1.0 非法字符、raw envelope、locator 与签名 URL 不得进入导出。
- 已验证视频/音频成为可播放 episode；已验证封面/图片按确定规则选择 poster/backdrop；没有可播放衍生物时仍保留图集/文本资产。
- ExportRecord 具有显式 begin/complete/fail 生命周期及规范 source/rendered 指纹；同一资产不会被全局标成 `exported`，因为多个 exporter/version 都可能消费它。
- CLI 覆盖资产下载与 Emby 导出，并只给出固定脱敏错误；黄金目录、故障注入、重启、打包、文档与密钥哨兵门禁全部通过。

## Truth boundary / 真实性边界

Current normalized media coverage is incomplete: XHS/Douyin/Kuaishou expose some binary URLs, Bilibili currently exposes covers, and Weibo/Tieba/Zhihu fixtures expose no downloadable asset. Therefore this execution proves a generic offline download/export contract, not seven-platform live media or an actual Emby/Jellyfin rescan. All live rows remain `NOT_RUN`.

当前归一化媒体覆盖并不完整：小红书/抖音/快手暴露部分二进制 URL，B 站当前只有封面，微博/贴吧/知乎夹具没有可下载资产。因此本执行只证明通用离线下载/导出契约，不证明七平台真人媒体可用，也不冒充真实 Emby/Jellyfin 重扫；所有线上项继续保持 `NOT_RUN`。
