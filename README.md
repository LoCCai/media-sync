**English** | [中文](README.zh.md)

# media-sync

`media-sync` is a local-first author subscription and media archiving service. It combines the platform coverage of [MediaCrawler](https://github.com/NanmiCoder/MediaCrawler) (as a license-gated external crawling runtime) with the media-library workflow of [bili-sync-up](https://github.com/NeeYoonc/bili-sync-up): authenticated creator subscriptions, incremental collection, resumable verified downloads, a SHA-256 archive and a deterministic Emby/Jellyfin library — behind one Python modular monolith with SQLite.

## Current status

The single source of truth is [`docs/status.md`](docs/status.md). Summary at the current execution 0055 Phase-A implementation checkpoint:

| Dimension | State |
| --- | --- |
| Offline implementation | The execution 0054 feature boundary remains intact. Execution 0055 now adds the backend single-operator credential/session/CSRF boundary and optional separate Bearer automation; playback evidence and the Web authentication integration are not implemented yet |
| Offline verification | The current execution 0055 backend slice passes **2811 tests with 14 skips and 1 existing warning**; 3 skips are Windows/POSIX differences and 11 are real-PostgreSQL races because this workstation has no test URL. The 190-test auth/API focus, 69 Web tests, format/check/build, full static gates, docs/upstreams and distribution build also pass. The overall 0055 exit gate remains open for Web auth and playback evidence |
| REST API + web console | Every non-public backend route is now fail-closed behind exact Host plus browser session or optional Bearer authentication. The SvelteKit and `/legacy` clients do not yet provide the login shell, in-memory CSRF propagation, or unified expiry handling, so the Web console is not currently an operable administration surface |
| Docker packaging | The example Compose deployment mounts a host-provided operator credential as a Docker secret and explicitly permits only the host-loopback browser origin while binding `0.0.0.0` inside the container. The 0047 Linux restart/restore/process evidence remains `NOT_RUN` |
| Live qualification | **Every implemented live platform/CDN/media-server row remains `NOT_RUN`**; provider task completion, playback evidence and automatic post-export scan are `NOT_IMPLEMENTED`, not unexecuted live rows |
| Release blockers | Web authentication integration, the remaining 0055 playback-evidence slice, the Linux operator baseline, and zero live rows; see [`docs/status.md`](docs/status.md) |

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

Docker deployment and the seven-platform qualification procedure are documented in [`docs/deployment.md`](docs/deployment.md) (build/run), [`docs/operations.md`](docs/operations.md) (backup/restore/upgrade) and [`docs/executions/0047-seven-platform-live-qualification/`](docs/executions/0047-seven-platform-live-qualification/) (the acceptance plan with support tiers). `media-sync serve` now requires an externally resolved operator credential before it binds. Keep the example port on host loopback; non-loopback browser origins require HTTPS. The current Web bundle has not yet integrated that backend session/CSRF contract, so use the CLI or resident supervisor and do not claim Web QR/login workflows until the remaining 0055 frontend work lands.

## Scope

- Platforms: Xiaohongshu, Douyin, Kuaishou, Bilibili, Weibo, Tieba, Zhihu (adapter framework; per-platform live status is tracked in the qualification matrix, not implied).
- Authentication: platform accounts retain explicit double-gated QR login, opaque Cookie references and background-only saved sessions. The administration backend additionally has one process-local operator session plus optional distinct Bearer automation; its Web login client is still pending. Phone login is unsupported.
- Non-goals: comments/keyword crawling, bangumi/live media, multi-user/public-network deployment.

## License boundary

MediaCrawler uses a custom non-commercial learning license. Its checkout is an optional external runtime and is never vendored here. Docker images embedding it are for personal local use only — do not publish or redistribute them. See [`docs/decisions/0001-upstream-boundary.md`](docs/decisions/0001-upstream-boundary.md).
