# media-sync

`media-sync` is a local-first author subscription and media archiving service. It is being designed around the platform coverage of [MediaCrawler](https://github.com/NanmiCoder/MediaCrawler) and the media-library workflow of [bili-sync-up](https://github.com/NeeYoonc/bili-sync-up).

`media-sync` 是一个本地优先的作者订阅与媒体归档服务。项目目标是覆盖 MediaCrawler 所支持的平台登录与创作者内容抓取，并将图文、视频和元数据整理为 Emby/Jellyfin 可识别的媒体库结构。

## Current status / 当前状态

The core foundation, credential-safe MediaCrawler bridge, and offline-qualified media pipeline are runnable. Execution 0005 adds replay-safe asset generations, resumable SSRF-resistant retrieval, immutable content-addressed archives, and deterministic Emby/Jellyfin layout v1 export. Its final offline gate passed 540 tests with 79% branch-aware coverage, plus build, packaged-migration and retained-artifact secret scans. These media claims are proven only with mock HTTP, generated files, fixture database rows, and temporary export trees. The MediaCrawler `adapter_refresh` path for expiring platform/CDN URLs is not implemented, and scheduler/API plus all user-authorized live platform and Emby/Jellyfin qualification remain outstanding. Requirements, capability truth, progress, and exact verification evidence are tracked in [`docs/`](docs/README.md).

核心基线、安全凭据的 MediaCrawler 桥接和通过离线验收的媒体流水线已可运行。执行 0005 新增可安全重放的资产 generation、可续传且抵御 SSRF 的下载、不可变内容寻址归档，以及确定性的 Emby/Jellyfin layout v1 导出；最终离线门禁通过 540 项测试，分支感知覆盖率为 79%，并通过构建、随包迁移及保留产物密钥扫描。这些媒体能力只由 mock HTTP、生成文件、数据库夹具和临时导出树证明。用于刷新平台/CDN 过期地址的 MediaCrawler `adapter_refresh` 尚未实现；调度/API，以及全部需要用户授权的真人平台和 Emby/Jellyfin 验收仍待完成。需求、真实能力、进展及准确验证证据均保存在 [`docs/`](docs/README.md)。

## Foundation quickstart / 基线快速开始

The commands below are network-free and use the deterministic Fake adapter. They do not log in to a real platform or prove live platform compatibility.

以下命令无需网络并使用确定性 Fake 适配器；它们不会登录真实平台，也不能作为线上平台兼容性证明。

```powershell
uv sync --all-groups --locked
uv run media-sync db init
uv run media-sync account add --platform bili --display-name local-demo --login-method cookie --json
uv run media-sync account list --json
```

Use the account UUID returned above to create and run the fixture subscription:

使用上一步返回的账户 UUID 创建并运行测试订阅：

```powershell
uv run media-sync subscription add --account-id <ACCOUNT_UUID> --platform bili --creator-remote-id creator-001 --display-name "Fixture Creator" --max-items 30 --json
uv run media-sync subscription list --json
uv run media-sync sync run --subscription-id <SUBSCRIPTION_UUID> --json
```

Only opaque secret references such as `env:MEDIA_SYNC_BILI_COOKIE` or `keyring:media-sync/bili-demo` may be passed to `--credential-ref`; raw Cookie/password values are rejected. Run the complete offline test suite with `uv run pytest`; the complete quality gate also includes lint, format, strict types, build/package, documentation, pinned-upstream, patch and secret-sentinel checks. See [`docs/executions/0005-media-download-emby/verification.md`](docs/executions/0005-media-download-emby/verification.md) for the exact closeout commands and results after they are recorded.

OS-keyring lookup is optional; install it with `uv sync --extra keyring` before using a `keyring:` reference. Confined `file:<relative-path>` references resolve below `MEDIA_SYNC_SECRET_FILE_DIR` (or the private state-directory default).

`--credential-ref` 只接受 `env:MEDIA_SYNC_BILI_COOKIE`、`keyring:media-sync/bili-demo` 等不透明引用；原始 Cookie/密码会被拒绝。`uv run pytest` 会运行完整离线测试套件；完整质量门禁还包括 lint、格式、严格类型、构建/打包、文档、锁定上游、补丁与密钥哨兵检查。准确收尾命令及实际结果记录后位于 [`docs/executions/0005-media-download-emby/verification.md`](docs/executions/0005-media-download-emby/verification.md)。

系统钥匙串是可选能力；使用 `keyring:` 引用前请运行 `uv sync --extra keyring`。`file:<relative-path>` 只会在 `MEDIA_SYNC_SECRET_FILE_DIR` 下解析；未配置时使用私有状态目录中的默认位置。

## Media download and Emby quickstart / 媒体下载与 Emby 快速开始

First run the deterministic offline contract. It uses temporary SQLite/filesystem roots, a mock transport, and generated media bytes; it does not contact a platform/CDN or start Emby/Jellyfin.

先运行确定性的离线契约。它只使用临时 SQLite/文件系统目录、mock transport 和生成的媒体字节，不访问平台/CDN，也不会启动 Emby/Jellyfin。

```powershell
uv run pytest tests/integration/test_offline_media_pipeline.py tests/contract/test_emby_export_contract.py
```

For a local database that already contains discovered assets, list redaction-safe IDs, download one eligible asset, and publish one complete author snapshot with:

对于已经含有发现资产的本地数据库，可先列出脱敏后的稳定 ID，再下载一个符合条件的资产，并发布一个完整作者快照：

```powershell
uv run media-sync doctor
uv run media-sync asset list --json
uv run media-sync asset list --status discovered --json
uv run media-sync asset download --asset-id <ASSET_UUID> --json
uv run media-sync emby export --author-id <AUTHOR_UUID> --json
```

`asset list` deliberately omits locators, source URLs, archive paths, and raw metadata. `asset download` performs network access for an eligible query-free `direct` locator and writes verified blobs below `MEDIA_SYNC_ARCHIVE_DIR` (default `archive/`). Video and audio are accepted only after mandatory structural probing by `ffprobe`; install FFmpeg/ffprobe and confirm `media-sync doctor` reports it ready. `emby export` is local filesystem work and writes layout v1 below `MEDIA_SYNC_EXPORT_DIR` (default `exports/`), but it requires a complete exportable author snapshot.

`asset list` 会主动隐藏 locator、来源 URL、归档路径和原始元数据。`asset download` 会为符合条件、无 query 的 `direct` locator 发起网络请求，并把已验证文件写到 `MEDIA_SYNC_ARCHIVE_DIR`（默认 `archive/`）下。视频和音频必须通过 `ffprobe` 的结构探测才能接收；请安装 FFmpeg/ffprobe，并确认 `media-sync doctor` 报告 ready。`emby export` 只操作本地文件系统，把 layout v1 写到 `MEDIA_SYNC_EXPORT_DIR`（默认 `exports/`）下，但要求该作者快照完整且可导出。

MediaCrawler-discovered assets currently use only the stable, secret-free `adapter_refresh` locator. Because its refresh adapter is not implemented yet, `asset download` reports `blocked` / `not_started` with the fixed redacted code `locator_refresh_unsupported`, without creating a job or changing the persisted asset status; do not treat the Fake/mock path as proof of real CDN retrieval. A missing mandatory `ffprobe` capability is reported with the same non-mutating disposition and code `media_probe_unavailable`. Real login/sync/download for XHS, Douyin, Kuaishou, Bilibili, Weibo, Tieba, and Zhihu, plus an actual Emby/Jellyfin rescan, all remain `NOT_RUN`.

MediaCrawler 发现的资产目前只使用稳定且不含密钥的 `adapter_refresh` locator。由于刷新适配器尚未实现，`asset download` 会报告 `blocked` / `not_started` 和固定脱敏代码 `locator_refresh_unsupported`，不创建任务也不修改持久化资产状态；不能把 Fake/mock 链路当作真实 CDN 下载证明。缺少强制的 `ffprobe` 能力时也会以相同的非变更 disposition 和 `media_probe_unavailable` 代码报告。小红书、抖音、快手、哔哩哔哩、微博、贴吧、知乎的真人登录/同步/下载，以及真实 Emby/Jellyfin 重扫，全部继续标记为 `NOT_RUN`。

Secret-sink handling recognizes explicit composite credential keys such as `api_key`, `access_key`, provider-prefixed and camelCase/kebab-case variants, while preserving ordinary fields such as `key`, `public_key` and `key_id`. Credential-marker URL paths such as `/token/<value>/video.mp4`, including percent-encoded and double-encoded forms, are redacted in operator/database sinks and rejected as durable `direct` locators or source hints. Discovery therefore falls back to a stable `adapter_refresh` locator. The `0003` upgrade applies the same path rule while backfilling legacy assets: it clears an unsafe legacy `source_url` and does not copy the credential path into the replacement locator.

密钥落点处理会识别 `api_key`、`access_key`、带提供商前缀及 camelCase/kebab-case 变体等明确组合密钥键，同时保留 `key`、`public_key`、`key_id` 等普通字段。`/token/<value>/video.mp4` 等带凭据标记的 URL 路径（包括百分号编码及双重编码形式）会在运维/数据库落点被脱敏，且不得作为持久 `direct` locator 或 source hint；发现阶段因此回退为稳定的 `adapter_refresh` locator。`0003` 升级在回填 legacy 资产时也执行同一路径规则：清空不安全的 legacy `source_url`，且不把凭据路径复制到替换 locator 中。

Keep `MEDIA_SYNC_JOB_DIR` and `MEDIA_SYNC_ARCHIVE_DIR` stable for a durable asset generation. A download Job stores only a hash of those canonical roots; a request from a different I/O scope fails safely before reclaiming the job or consuming an attempt. A local per-asset OS lock is held from before database mutation through finalization. If archive publication succeeds before the final database commit, the generation-bound partial evidence permits exact recovery without another network request; partial cleanup happens only after verification succeeds.

同一持久资产 generation 应保持 `MEDIA_SYNC_JOB_DIR` 与 `MEDIA_SYNC_ARCHIVE_DIR` 稳定。下载 Job 只保存这些规范根目录的哈希；来自不同 I/O scope 的请求会在回收 job 或消耗 attempt 前安全失败。逐资产本地 OS 锁从数据库变更前一直持有到收尾。若归档发布先于最终数据库提交成功，绑定 generation 的 partial 证据可以在不再次请求网络的情况下精确恢复；partial 只在验证成功后清理。

Filesystem threat boundary for the 0.x line: the configured state, job, archive, staging and export roots—and their ancestors—must be dedicated, operator-controlled directories that are not writable by an untrusted same-permission process. The path guards reject escapes, links/reparse points/hardlinks present at operation time and detected leaf replacement, but path-based operations do not claim to survive an attacker swapping a parent directory between checks. Do not place these roots in a shared adversarial directory.

0.x 的文件系统威胁边界：配置的 state、job、archive、staging、export 根目录及其祖先必须是专用、由操作员控制且不允许不可信同权限进程写入的目录。路径 guard 会拒绝操作时已存在的逃逸、符号链接/reparse、硬链接及可检测的叶节点替换，但基于路径的操作不宣称能抵御攻击者在检查间隙替换父目录。请勿把这些根目录放在对抗性共享目录中。

Emby managed ownership comes from a durable database Job predecessor chain, not from `.media-sync-managed-v1.json` alone. The disk manifest remains a byte-checked description of the database-anchored predecessor. An unexpected or forged manifest is preserved and rejected; an empty author snapshot still receives a Job anchor, and a publish that committed before database finalization can be recovered only when the exact intended source, tree, manifest and managed bytes match.

Emby 受管所有权来自持久数据库 Job predecessor chain，而不是单独依赖 `.media-sync-managed-v1.json`。磁盘 manifest 只是数据库锚定 predecessor 的逐字节校验描述。意外或伪造 manifest 会被保留并拒绝；空作者快照仍会获得 Job 锚点；只有 intended source、tree、manifest 与全部受管字节精确匹配时，才能恢复“发布已提交但数据库尚未收尾”的任务。

Schema round trips deliberately clean generation-bound identities. Downgrading `0003` to `0002` first clears every `assets.download_job_id`, then removes all `asset_download` Jobs because `0002` cannot represent their generation. Succeeded Emby Jobs/records remain as the publication chain. Other non-succeeded Emby Jobs/records are removed as identity poison unless a Job carries a structurally valid closed publication intent; that Job and the records named by its intent are retained only for exact byte-validated recovery after re-upgrade.

Schema 往返会主动清理与 generation 绑定的身份。从 `0003` 降级到 `0002` 时，先清空所有 `assets.download_job_id`，再删除全部 `asset_download` Job，因为 `0002` 无法表达其 generation。已成功的 Emby Job/record 作为发布链保留；其他未成功的 Emby Job/record 作为可能的身份污染会被删除，除非 Job 携带结构严格有效的封闭发布 intent；该 Job 及 intent 点名的 records 只为重新升级后的精确逐字节校验恢复而保留。

## Scope / 范围

- Platforms / 平台：小红书、抖音、快手、哔哩哔哩、微博、百度贴吧、知乎。
- Authentication / 登录：当前桥接按锁定源码的可达路径支持二维码、Cookie 与已保存浏览器会话；不宣称手机号登录可用。
- Subscription / 订阅: currently stores author identity, subscription policy, incremental watermarks and deduplication state; scheduled runs, unified backoff and rate limiting belong to Phase 4. / 当前保存作者身份、订阅策略、增量水位与去重状态；定时调度、统一退避和限流属于后续 Phase 4。
- Content / 内容：归一化图文、视频、图片及相关元数据。
- Media library / 媒体库：输出稳定目录、媒体文件、海报/封面和 Emby/Jellyfin NFO。

## Important license boundary / 重要许可证边界

MediaCrawler uses a custom non-commercial learning license. Its checkout is treated as an optional external runtime and is not vendored into this repository. See [`docs/decisions/0001-upstream-boundary.md`](docs/decisions/0001-upstream-boundary.md) before distributing or using this project commercially.

MediaCrawler 使用定制的“非商业学习使用许可证”。本仓库只把它视为可选外部运行时，不把其源码纳入版本历史。分发或商业使用前，请先阅读 [`docs/decisions/0001-upstream-boundary.md`](docs/decisions/0001-upstream-boundary.md)。
