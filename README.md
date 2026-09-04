**English** | [中文](README.zh.md)

# media-sync

`media-sync` is a local-first author subscription and media archiving service. It combines the platform coverage of [MediaCrawler](https://github.com/NanmiCoder/MediaCrawler) (as a license-gated external crawling runtime) with the media-library workflow of [bili-sync-up](https://github.com/NeeYoonc/bili-sync-up): authenticated creator subscriptions, incremental collection, resumable verified downloads, a SHA-256 archive and a deterministic Emby/Jellyfin library — behind one Python modular monolith with SQLite.

## Current status

The single source of truth is [`docs/status.md`](docs/status.md). Summary at the execution 0054-A boundary:

| Dimension | State |
| --- | --- |
| Offline implementation | Frozen platform shapes through 0039 plus API/operations, Console v2, content/archive browsing and 0054-A safe managed-tree/media-server controls; danmaku/subtitles and 0054-B scan completion/item lookup remain open |
| Offline verification | Execution 0054-A frozen suite: **2620 passed, 3 skipped, 1 existing warning**; see [`docs/status.md`](docs/status.md) |
| REST API + web console | SvelteKit 5 SPA includes safe managed-tree paging, redacted media-server posture, durable probe/targeted-refresh actions and qualification evidence; `/legacy` remains available for rollback |
| Docker packaging | Multi-stage frontend/runtime packaging and repaired-image preflight pass; 0047 Linux restart/restore/process evidence remains `NOT_RUN` |
| Live qualification | **Every implemented live platform/CDN/media-server row remains `NOT_RUN`**; capabilities absent from 0054-A are `NOT_IMPLEMENTED`, not unexecuted live rows |
| Release blockers | Linux baseline (Phase B) + zero live rows; see [`docs/status.md`](docs/status.md) |

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

Docker deployment, web-console QR login and the seven-platform qualification procedure are documented in [`docs/deployment.md`](docs/deployment.md) (build/run), [`docs/operations.md`](docs/operations.md) (backup/restore/upgrade) and [`docs/executions/0047-seven-platform-live-qualification/`](docs/executions/0047-seven-platform-live-qualification/) (the acceptance plan with support tiers). Console v2 asks for the personal-use/license acknowledgement once per browser and remembers it locally; runtime checkout and license gates are still enforced by the backend. The API/console carries no authentication: keep it on loopback or a trusted network.

## Scope

- Platforms: Xiaohongshu, Douyin, Kuaishou, Bilibili, Weibo, Tieba, Zhihu (adapter framework; per-platform live status is tracked in the qualification matrix, not implied).
- Authentication: explicit double-gated QR login, opaque Cookie references, background-only saved sessions; phone login unsupported.
- Non-goals: comments/keyword crawling, bangumi/live media, multi-user/public-network deployment.

## License boundary

MediaCrawler uses a custom non-commercial learning license. Its checkout is an optional external runtime and is never vendored here. Docker images embedding it are for personal local use only — do not publish or redistribute them. See [`docs/decisions/0001-upstream-boundary.md`](docs/decisions/0001-upstream-boundary.md).
