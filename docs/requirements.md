**English** | [中文](requirements.zh.md)

# Product requirements

- Status: Architecture baseline
- Applies to: `media-sync` 0.x
- Upstream scope: [`upstreams.lock.json`](../upstreams.lock.json)

## 1. Product statement

`media-sync` is a self-hosted, local-first service for archiving content from explicitly subscribed creators. It coordinates user-authorized platform sessions, performs polite incremental collection, preserves original content and normalized metadata, and renders a deterministic Emby/Jellyfin media library.

## 2. Functional requirements

### Accounts and authentication

- **AUTH-001** — Represent separate accounts for `xhs`, `dy`, `ks`, `bili`, `wb`, `tieba` and `zhihu`.
- **AUTH-002** — Advertise only login methods actually implemented by the selected adapter and platform.
- **AUTH-003** — Support interactive QR login, Cookie login and saved browser state where upstream behavior permits it; support phone login only on qualified platforms.
- **AUTH-004** — Never persist a raw Cookie in SQLite, configuration files, logs, command-line arguments or Git. Store only a credential reference and resolve secrets at process start.
- **AUTH-005** — Isolate browser profiles by platform and account, and make login expiry observable.

### Creator subscriptions

- **SUB-001** — Add a subscription from a platform creator ID or canonical profile URL.
- **SUB-002** — Enforce uniqueness by platform plus stable remote creator ID while allowing multiple accounts to access the same author.
- **SUB-003** — Enable, pause, run-now and delete a subscription without deleting already archived content by default.
- **SUB-004** — Configure per-subscription interval, maximum items per scan and optional publish-time cutoff.
- **SUB-005** — Persist cursor/watermark and next-run state so restart remains idempotent.

### Collection and normalization

- **SYNC-001** — Execute one isolated job directory per sync run and retain a redacted manifest plus bounded logs.
- **SYNC-002** — Ingest JSON and JSONL incrementally, tolerate a truncated final JSONL line, and quarantine malformed records.
- **SYNC-003** — Upsert creator and content records by stable platform keys; never duplicate content when a run is retried.
- **SYNC-004** — Normalize video, image/gallery, text/article and mixed posts while preserving the complete raw record for forward-compatible reprocessing.
- **SYNC-005** — Discover ordered media assets, canonical source URL, publish time, title/body, creator identity and available engagement fields.
- **SYNC-006** — Apply bounded concurrency, configurable request intervals, exponential retry with jitter and a circuit breaker for repeated risk-control/login failures.

### Media and Emby/Jellyfin

- **MEDIA-001** — Download assets atomically through a temporary file with resume support where HTTP permits it.
- **MEDIA-002** — Validate scheme, redirect target, content type and configured size limit; structurally probe audio/video, use bounded FFmpeg stream-copy when separate components require muxing, and calculate SHA-256 only after final validation.
- **MEDIA-003** — Keep original assets and record provenance, download state and failure reason.
- **EMBY-001** — Export each creator as an Emby/Jellyfin TV show with `tvshow.nfo`, creator poster and year-based seasons.
- **EMBY-002** — Export playable video posts as episodes with stable `SyyyyE...` names and matching episode NFO.
- **EMBY-003** — Preserve galleries/text beside their NFO and optionally render an FFmpeg slideshow MP4 so image/text posts are playable in an Emby video library.
- **EMBY-004** — Use XML-safe values, platform-scoped unique IDs, source links, publish dates, plot text, tags, studio/platform and creator actor metadata.
- **EMBY-005** — Render to a staging path and atomically replace changed sidecars; repeated export must be deterministic.

### Interfaces and operations

- **OPS-001** — Provide one CLI for database setup, account/subscription management, sync, ingest, export, doctor and server startup.
- **OPS-002** — Provide a versioned local REST API with equivalent core operations and health/readiness endpoints.
- **OPS-003** — Emit structured, redacted logs and expose run/item failure state without exposing credentials.
- **OPS-004** — Support SQLite backup/restore and schema migration; use WAL mode and a single-writer transaction policy.
- **OPS-005** — Provide Docker and native setup instructions, while interactive browser login remains a host-assisted workflow.

## 3. Safety and compliance requirements

- **SAFE-001** — Users must explicitly acknowledge the selected crawler adapter's license and platform terms before its first live run.
- **SAFE-002** — Default to one concurrent crawler per account, comments disabled, a small item cap and a nonzero delay.
- **SAFE-003** — Do not bypass CAPTCHA, paywalls, private-account controls or platform access restrictions.
- **SAFE-004** — Refuse non-HTTP(S) remote asset URLs and prevent download paths escaping configured roots.
- **SAFE-005** — Redact common Cookie/token names and user-provided secret values from errors and subprocess output.

## 4. Quality requirements

- Python 3.11+ on Windows, Linux and macOS; UTF-8 paths and non-ASCII creator titles are first-class.
- Core operations have type checks, linting and unit tests; database, bridge ingestion and Emby output have integration tests.
- A clean checkout can run deterministic tests without network access, accounts, browsers or MediaCrawler.
- Live tests are opt-in, never run in CI, and record only redacted evidence.
- Database and output schemas are versioned; upstream-specific raw payloads never leak into public domain interfaces without a versioned envelope.

## 5. Explicit non-goals for 0.x

- Bulk keyword scraping, comment warehousing or unrestricted site crawling.
- Circumventing platform protection or automating CAPTCHA solutions.
- Claiming commercial-use rights to MediaCrawler or redistributing its source.
- Cloud multi-tenancy, public Internet exposure or shared secret storage.
- Byte-for-byte parity with every advanced bili-sync-up Bilibili feature.

## 6. Release acceptance

Automated acceptance is necessary but not sufficient. Each platform must also have a user-authorized qualification record for login, one creator scan, incremental rerun, media retrieval and Emby rescan. Any unavailable account or interactive challenge is reported as `NOT_RUN` or `BLOCKED_EXTERNAL`, never `PASS`.
