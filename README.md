**English** | [中文](README.zh.md)

# media-sync

`media-sync` is a local-first author subscription and media archiving service. It combines the platform coverage of [MediaCrawler](https://github.com/NanmiCoder/MediaCrawler) (as a license-gated external crawling runtime) with the media-library workflow of [bili-sync-up](https://github.com/NeeYoonc/bili-sync-up): authenticated creator subscriptions, incremental collection, resumable verified downloads, a SHA-256 archive and a deterministic Emby/Jellyfin library — behind one Python modular monolith with SQLite.

## Current status

The single source of truth is [`docs/status.md`](docs/status.md). Summary at the current execution 0055 incremental implementation checkpoint:

| Dimension | State |
| --- | --- |
| Offline implementation | Authentication (`f19bfaa`), revision `0008` and the ledger (`1d5b448`), browser-only confirmation (`13de3b7`), and the current bounded author evidence query plus qualification schema v3 are implemented. Web login/session/CSRF and confirmation interaction remain pending |
| Offline verification | Current full Python: 2999 passed, 22 skipped, one warning in 613.66s; Web: 69 tests plus format/check/build passed. Exact commands and other gates are in [projection verification](docs/executions/0055-operator-auth-playback-evidence/evidence-projection/verification.md). Docker and real PostgreSQL remain unavailable on this workstation |
| REST API + web console | Every non-public backend route is now fail-closed behind exact Host plus browser session or optional Bearer authentication. The SvelteKit and `/legacy` clients do not yet provide the login shell, in-memory CSRF propagation, or unified expiry handling, so the Web console is not currently an operable administration surface |
| Docker packaging | The example Compose deployment mounts a host-provided operator credential as a Docker secret and explicitly permits only the host-loopback browser origin while binding `0.0.0.0` inside the container. The 0047 Linux restart/restore/process evidence remains `NOT_RUN` |
| Live qualification | **Every implemented live platform/CDN/media-server row remains `NOT_RUN`**. Schema v3 marks playback evidence IMPLEMENTED and evaluates one explicitly requested author. Only revalidated durable attestation yields scoped PASS; provider completion and automatic scan remain NOT_IMPLEMENTED |
| Release blockers | Prioritize secure Web login/CSRF and credential/pre-migration validation, the current Linux image and authorized Bilibili/XHS canaries; minimal evidence UI does not block CLI live workflows. See [delivery priorities](docs/executions/0055-operator-auth-playback-evidence/delivery-priorities.md) and [status](docs/status.md) |

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
