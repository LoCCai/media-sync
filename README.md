**English** | [中文](README.zh.md)

# media-sync

`media-sync` is a local-first author subscription and media archiving service. It combines the platform coverage of [MediaCrawler](https://github.com/NanmiCoder/MediaCrawler) (as a license-gated external crawling runtime) with the media-library workflow of [bili-sync-up](https://github.com/NeeYoonc/bili-sync-up): authenticated creator subscriptions, incremental collection, resumable verified downloads, a SHA-256 archive and a deterministic Emby/Jellyfin library — behind one Python modular monolith with SQLite.

## Current status

Current implementation and verification are tracked in [`docs/status.md`](docs/status.md); the latest increment is [0077 deployment provenance and XHS canary preflight](docs/executions/0077-deployment-provenance-preflight/progress.md), implemented in `d6db86a` on top of [0076 durable XHS creator-note delivery](docs/executions/0076-xhs-creator-notes-delivery/progress.md). Source support and image identity are not live platform qualification.

| Area | Current scope |
| --- | --- |
| Local media library | Archive and Emby/Jellyfin-compatible directories work independently of optional server connections; text/gallery sidecars are not a claim of native video playback |
| Accounts and creators | Native MediaCrawler QR/Cookie login can be explicitly adopted into an Account as a verified, isolated saved-session profile; creator identity enrichment and all live platform results still require qualification |
| Subscriptions and operations | Bilibili and XHS now have source-specific durable bounded backfill/reconciliation/incremental delivery paths. All MediaCrawler platforms share a revision-fenced paused-state editor; Bilibili alone has capture scope. Editing never starts or resumes work |
| Verification | Exact current tests/build/packages, corrected findings and unrun environments are in [0077 verification](docs/executions/0077-deployment-provenance-preflight/verification.md), not inherited historical counts |
| Remaining implementation/qualification | Pull the published SHA, build with that exact source identity, compare API/supervisor deep readiness, then qualify one authorized XHS creator with real CDN, host directory/NFO and restart/supervisor evidence. Only then derive the next durable platform contract from pinned Douyin source; the historical failed Bili canary remains unresolved |

Per-execution detail, evidence and exact commands live in [`docs/executions/`](docs/README.md) — this README intentionally does not stack execution narratives.

## Crawler console

The Docker build compiles the pinned MediaCrawler WebUI directly. After reviewing its pinned non-commercial learning license, set `MEDIA_SYNC_MEDIACRAWLER_LICENSE_ACKNOWLEDGED=true` in the **API service environment**; the supervisor's separate `--accept-mediacrawler-license` flag does not enable `/crawler/`. Then sign in to media-sync and choose **Crawler console** in the sidebar or open `/crawler/` to use the upstream platform selector, QR/Cookie login, creator/detail/search modes, start/stop controls, live logs and data browser. media-sync adds only the same-origin auth/CSRF boundary, authenticated WebSockets, browser QR relay, fixed upstream Python, persistent profiles and a fixed output root; it does not reimplement the platform crawlers.

Use the native console to log in, wait until its process is idle, then return to **Accounts** and explicitly adopt that platform's saved session into the matching Account. The scheduler uses the verified Account-specific snapshot for Subscription history and later incremental runs. Shared artifacts in `/data/mediacrawler/webui-output` remain an interactive-console area and are intentionally not imported into unrelated Jobs. A deployment may bind-mount all of `/data`; an Emby/Jellyfin connection is not required to generate compatible directories and NFO files. Real seven-platform login/capture/download results still require deployment qualification.

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

Docker deployment and the seven-platform qualification procedure are documented in [`docs/deployment.md`](docs/deployment.md) (build/run), [`docs/operations.md`](docs/operations.md) (backup/restore/upgrade) and [`docs/executions/0047-seven-platform-live-qualification/`](docs/executions/0047-seven-platform-live-qualification/) (the acceptance plan with support tiers). [0077's handoff](docs/executions/0077-deployment-provenance-preflight/deployment-handoff.md) adds exact image identity and API/supervisor comparison before the XHS canary. `media-sync serve` requires an externally resolved operator credential before it binds. Keep the example port on host loopback; non-loopback browser origins require HTTPS. Configuration or provenance preflight does not substitute for current Linux-image, platform-account or media-server live qualification.

## Scope

- Platforms: Xiaohongshu, Douyin, Kuaishou, Bilibili, Weibo, Tieba, Zhihu (adapter framework; per-platform live status is tracked in the qualification matrix, not implied).
- Authentication: platform accounts retain explicit double-gated QR login, opaque Cookie references and background-only saved sessions. The administration backend additionally has one process-local operator session plus optional distinct Bearer automation; its Web login client is implemented and verified with local synthetic-browser fixtures. Phone login is unsupported.
- Non-goals: making the upstream comment/keyword tools part of the subscription archive pipeline, bangumi/live media, multi-user or unprotected public-network deployment.

## License boundary

MediaCrawler uses a custom non-commercial learning license. Its checkout is an optional external runtime and is never vendored here. Docker images embedding it are for personal local use only — do not publish or redistribute them. See [`docs/decisions/0001-upstream-boundary.md`](docs/decisions/0001-upstream-boundary.md).
