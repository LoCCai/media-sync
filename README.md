**English** | [中文](README.zh.md)

# media-sync

`media-sync` is a local-first author subscription and media archiving service. It combines the platform coverage of [MediaCrawler](https://github.com/NanmiCoder/MediaCrawler) (as a license-gated external crawling runtime) with the media-library workflow of [bili-sync-up](https://github.com/NeeYoonc/bili-sync-up): authenticated creator subscriptions, incremental collection, resumable verified downloads, a SHA-256 archive and a deterministic Emby/Jellyfin library — behind one Python modular monolith with SQLite.

## Current status

Current implementation and verification are tracked in [`docs/status.md`](docs/status.md); the latest increment is [0065 Cookie self checks and optional avatar](docs/executions/0065-cookie-auth-and-avatar/progress.md). Source support is not live platform qualification.

| Area | Current scope |
| --- | --- |
| Local media library | Archive and Emby/Jellyfin-compatible directories work independently of optional server connections; text/gallery sidecars are not a claim of native video playback |
| Accounts and creators | Seven pasted-Cookie self validators (KS requires the cp.api_ph subset); six exact nickname platforms. Bili/WB/Tieba plus limited Zhihu optional avatars. QR and Cookie flows still need live qualification |
| Subscriptions and operations | Reversible subscription removal preserves media/history; platform profiles, local aliases, safe Job reports and user-oriented status/next actions are implemented |
| Verification | Exact current tests/build/packages, failures and unrun environments are in [0065 verification](docs/executions/0065-cookie-auth-and-avatar/verification.md), not inherited historical counts |
| Remaining implementation/qualification | XHS exact profiles, DY/KS avatars and broader Zhihu avatar forms, remaining media and current Linux/platform/archive/playback; historical failed Bili canary remains unresolved |

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
