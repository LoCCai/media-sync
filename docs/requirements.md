# Product requirements / 产品需求

- Status / 状态：Architecture baseline / 架构基线
- Applies to / 适用版本：`media-sync` 0.x
- Upstream scope / 上游范围：[`upstreams.lock.json`](../upstreams.lock.json)

## 1. Product statement / 产品说明

`media-sync` is a self-hosted, local-first service for archiving content from explicitly subscribed creators. It coordinates user-authorized platform sessions, performs polite incremental collection, preserves original content and normalized metadata, and renders a deterministic Emby/Jellyfin media library.

`media-sync` 是一个可自托管、本地优先的创作者内容归档服务。它协调用户授权的平台登录会话，以克制的频率进行增量采集，保存原始内容及归一化元数据，并生成确定性的 Emby/Jellyfin 媒体库。

## 2. Functional requirements / 功能需求

### Accounts and authentication / 账户与登录

- **AUTH-001** — Represent separate accounts for `xhs`, `dy`, `ks`, `bili`, `wb`, `tieba` and `zhihu`.
- **AUTH-002** — Advertise only login methods actually implemented by the selected adapter and platform.
- **AUTH-003** — Support interactive QR login, Cookie login and saved browser state where upstream behavior permits it; support phone login only on qualified platforms.
- **AUTH-004** — Never persist a raw Cookie in SQLite, configuration files, logs, command-line arguments or Git. Store only a credential reference and resolve secrets at process start.
- **AUTH-005** — Isolate browser profiles by platform and account, and make login expiry observable.

- **AUTH-001** — 为七个平台分别建模账户。
- **AUTH-002** — 只展示当前适配器和平台真正实现的登录方式。
- **AUTH-003** — 在上游能力允许时支持交互式二维码、Cookie 和已保存浏览器会话；手机号登录只对验收过的平台开放。
- **AUTH-004** — 原始 Cookie 不得进入 SQLite、配置文件、日志、命令行参数或 Git，只保存凭据引用并在进程启动时解析。
- **AUTH-005** — 浏览器配置按“平台 + 账户”隔离，登录过期状态可观察。

### Creator subscriptions / 创作者订阅

- **SUB-001** — Add a subscription from a platform creator ID or canonical profile URL.
- **SUB-002** — Enforce uniqueness by platform plus stable remote creator ID while allowing multiple accounts to access the same author.
- **SUB-003** — Enable, pause, run-now and delete a subscription without deleting already archived content by default.
- **SUB-004** — Configure per-subscription interval, maximum items per scan and optional publish-time cutoff.
- **SUB-005** — Persist cursor/watermark and next-run state so restart remains idempotent.

### Collection and normalization / 采集与归一化

- **SYNC-001** — Execute one isolated job directory per sync run and retain a redacted manifest plus bounded logs.
- **SYNC-002** — Ingest JSON and JSONL incrementally, tolerate a truncated final JSONL line, and quarantine malformed records.
- **SYNC-003** — Upsert creator and content records by stable platform keys; never duplicate content when a run is retried.
- **SYNC-004** — Normalize video, image/gallery, text/article and mixed posts while preserving the complete raw record for forward-compatible reprocessing.
- **SYNC-005** — Discover ordered media assets, canonical source URL, publish time, title/body, creator identity and available engagement fields.
- **SYNC-006** — Apply bounded concurrency, configurable request intervals, exponential retry with jitter and a circuit breaker for repeated risk-control/login failures.

### Media and Emby/Jellyfin / 媒体与 Emby/Jellyfin

- **MEDIA-001** — Download assets atomically through a temporary file with resume support where HTTP permits it.
- **MEDIA-002** — Validate scheme, redirect target, content type and configured size limit; structurally probe audio/video, use bounded FFmpeg stream-copy when separate components require muxing, and calculate SHA-256 only after final validation.
- **MEDIA-003** — Keep original assets and record provenance, download state and failure reason.
- **EMBY-001** — Export each creator as an Emby/Jellyfin TV show with `tvshow.nfo`, creator poster and year-based seasons.
- **EMBY-002** — Export playable video posts as episodes with stable `SyyyyE...` names and matching episode NFO.
- **EMBY-003** — Preserve galleries/text beside their NFO and optionally render an FFmpeg slideshow MP4 so image/text posts are playable in an Emby video library.
- **EMBY-004** — Use XML-safe values, platform-scoped unique IDs, source links, publish dates, plot text, tags, studio/platform and creator actor metadata.
- **EMBY-005** — Render to a staging path and atomically replace changed sidecars; repeated export must be deterministic.

### Interfaces and operations / 接口与运维

- **OPS-001** — Provide one CLI for database setup, account/subscription management, sync, ingest, export, doctor and server startup.
- **OPS-002** — Provide a versioned local REST API with equivalent core operations and health/readiness endpoints.
- **OPS-003** — Emit structured, redacted logs and expose run/item failure state without exposing credentials.
- **OPS-004** — Support SQLite backup/restore and schema migration; use WAL mode and a single-writer transaction policy.
- **OPS-005** — Provide Docker and native setup instructions, while interactive browser login remains a host-assisted workflow.

## 3. Safety and compliance requirements / 安全与合规需求

- **SAFE-001** — Users must explicitly acknowledge the selected crawler adapter's license and platform terms before its first live run.
- **SAFE-002** — Default to one concurrent crawler per account, comments disabled, a small item cap and a nonzero delay.
- **SAFE-003** — Do not bypass CAPTCHA, paywalls, private-account controls or platform access restrictions.
- **SAFE-004** — Refuse non-HTTP(S) remote asset URLs and prevent download paths escaping configured roots.
- **SAFE-005** — Redact common Cookie/token names and user-provided secret values from errors and subprocess output.

## 4. Quality requirements / 质量需求

- Python 3.11+ on Windows, Linux and macOS; UTF-8 paths and non-ASCII creator titles are first-class.
- Core operations have type checks, linting and unit tests; database, bridge ingestion and Emby output have integration tests.
- A clean checkout can run deterministic tests without network access, accounts, browsers or MediaCrawler.
- Live tests are opt-in, never run in CI, and record only redacted evidence.
- Database and output schemas are versioned; upstream-specific raw payloads never leak into public domain interfaces without a versioned envelope.

## 5. Explicit non-goals for 0.x / 0.x 明确不做

- Bulk keyword scraping, comment warehousing or unrestricted site crawling.
- Circumventing platform protection or automating CAPTCHA solutions.
- Claiming commercial-use rights to MediaCrawler or redistributing its source.
- Cloud multi-tenancy, public Internet exposure or shared secret storage.
- Byte-for-byte parity with every advanced bili-sync-up Bilibili feature.

- 不做大规模关键词抓取、评论仓库或无限制站点爬取。
- 不绕过平台保护或自动破解验证码。
- 不宣称拥有 MediaCrawler 商业使用权，也不再分发其源码。
- 不做云端多租户、直接暴露公网或共享密钥存储。
- 不追求与 bili-sync-up 全部高级 B 站功能逐字节一致。

## 6. Release acceptance / 发布验收

Automated acceptance is necessary but not sufficient. Each platform must also have a user-authorized qualification record for login, one creator scan, incremental rerun, media retrieval and Emby rescan. Any unavailable account or interactive challenge is reported as `NOT_RUN` or `BLOCKED_EXTERNAL`, never `PASS`.

自动化验收是必要条件但不是充分条件。每个平台还必须在用户授权账户下记录登录、一次作者扫描、增量重跑、媒体获取和 Emby 重扫结果。缺少账户或遇到真人交互挑战时必须标为 `NOT_RUN` 或 `BLOCKED_EXTERNAL`，不得记为 `PASS`。
