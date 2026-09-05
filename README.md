**English** | [中文](README.zh.md)

# media-sync

`media-sync` is a local-first author subscription and media archiving service. It combines the platform coverage of [MediaCrawler](https://github.com/NanmiCoder/MediaCrawler) (as a license-gated external crawling runtime) with the media-library workflow of [bili-sync-up](https://github.com/NeeYoonc/bili-sync-up): authenticated creator subscriptions, incremental collection, resumable verified downloads, a SHA-256 archive and a deterministic Emby/Jellyfin library — behind one Python modular monolith with SQLite.

## Current status

The single source of truth is [`docs/status.md`](docs/status.md). Summary at the current execution 0055 incremental implementation checkpoint:

| Dimension | State |
| --- | --- |
| Offline implementation | Authentication, revision `0008`/ledger, browser confirmation and author evidence/qualification v3 are published (projection `2e1949f`); secure Web login/session/CSRF and pre-migration checks are implemented and verified with local synthetic-browser fixtures. Playback confirmation UI remains pending |
| Offline verification | Current Python: 3155 passed, 22 skipped, one existing warning in 670.16s; Web: 114 tests in 9 files, Svelte check 0 errors/warnings and build passed; exact results are in [secure-console verification](docs/executions/0055-operator-auth-playback-evidence/secure-console/verification.md); the 2999-test projection result is historical for `2e1949f`. Docker/Linux UID and real PostgreSQL remain unexecuted on this workstation |
| REST API + web console | Safe console and startup preflight are implemented and locally verified, including synthetic-browser checks; serialized session bootstrap, memory-only CSRF, logout/expiry/401 and QR/SSE wiring are implemented. Private pages mount only after successful session bootstrap; `/legacy` is a protected migration notice, and a missing v2 build leaves a build/CLI notice at root. Local video evidence is loading/decoding only, with no play click or live-playback qualification |
| Docker packaging | The example Compose deployment mounts a host-provided operator credential as a Docker secret and explicitly permits only the host-loopback browser origin while binding `0.0.0.0` inside the container. The 0047 Linux restart/restore/process evidence remains `NOT_RUN` |
| Live qualification | **Every implemented live platform/CDN/media-server row remains `NOT_RUN`**. Schema v3 marks playback evidence IMPLEMENTED and evaluates one explicitly requested author. Only revalidated durable attestation yields scoped PASS; provider completion and automatic scan remain NOT_IMPLEMENTED |
| Release blockers | The exact current Linux image and authorized Bilibili/XHS canaries; P1 confirmation UI does not block CLI live workflows. See [current verification](docs/executions/0055-operator-auth-playback-evidence/secure-console/verification.md) and [status](docs/status.md) |

Per-execution detail, evidence and exact commands live in [`docs/executions/`](docs/README.md) — this README intentionally does not stack execution narratives.

## Offline quickstart (Fake adapter, no network)

```powershell
uv sync --all-groups --locked
uv run media-sync db init
uv run media-sync account add --platform bili --display-name local-demo --login-method cookie --json
uv run media-sync subscription add --account-id <ACCOUNT_UUID> --platform bili --creator-remote-id creator-001 --display-name "Fixture Creator" --max-items 30 --json
uv run media-sync scheduler tick --json
uv run media-sync scheduler run --max-jobs 1 --json
uv run media-sync pipeline run --max-jobs 1 --json
```

Quality gates: `uv run ruff check . && uv run ruff format --check .`, `uv run mypy --strict src`, `uv run pytest -q`, `uv run python scripts/check_docs.py`, `uv run python scripts/check_upstreams.py` (needs `.upstream/` checkouts per [`docs/upstreams.md`](docs/upstreams.md)).

## Deployment and live verification

Docker deployment and the seven-platform qualification procedure are documented in [`docs/deployment.md`](docs/deployment.md) (build/run), [`docs/operations.md`](docs/operations.md) (backup/restore/upgrade) and [`docs/executions/0047-seven-platform-live-qualification/`](docs/executions/0047-seven-platform-live-qualification/) (the acceptance plan with support tiers). `media-sync serve` now requires an externally resolved operator credential before it binds. Keep the example port on host loopback; non-loopback browser origins require HTTPS. Web authentication is now wired and has passed local synthetic-browser verification in the [checkpoint record](docs/executions/0055-operator-auth-playback-evidence/secure-console/verification.md); the CLI and resident supervisor remain available. Configuration preflight does not substitute for current Linux-image, platform-account or media-server live qualification.

## Scope

- Platforms: Xiaohongshu, Douyin, Kuaishou, Bilibili, Weibo, Tieba, Zhihu (adapter framework; per-platform live status is tracked in the qualification matrix, not implied).
- Authentication: platform accounts retain explicit double-gated QR login, opaque Cookie references and background-only saved sessions. The administration backend additionally has one process-local operator session plus optional distinct Bearer automation; its Web login client is implemented and verified with local synthetic-browser fixtures. Phone login is unsupported.
- Non-goals: comments/keyword crawling, bangumi/live media, multi-user/public-network deployment.

## License boundary

MediaCrawler uses a custom non-commercial learning license. Its checkout is an optional external runtime and is never vendored here. Docker images embedding it are for personal local use only — do not publish or redistribute them. See [`docs/decisions/0001-upstream-boundary.md`](docs/decisions/0001-upstream-boundary.md).
