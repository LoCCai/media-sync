**English** | [中文](deployment-2026-09-12.zh.md)

# Deployment record: exact-identity rebuild reaches deep readiness (2026-09-12)

## Status

**DEPLOYMENT IDENTITY COMPLETE; XHS CANARY REMAINS NOT_RUN.** The Linux server executed the [deployment handoff](deployment-handoff.md) with the supervisor never started. One API container was rebuilt and recreated on the exact published source. No platform login, crawl, download, Subscription change or supervisor start occurred.

## Performed actions

| Step | Result |
| --- | --- |
| Backup before rebuild | Application-consistent SQLite backup (638,976 bytes), full `/data` volume snapshot (114 MiB), private Compose file, `.env` and operator secret directory copied to `/root/media-sync-backups/2026-09-12-pre0077-rebuild` |
| Source binding | Fast-forward pull to `3c31dce81f7240ea0c63a6309c04970c1b0741b4`; `git status --porcelain` empty; SHA exported as `MEDIA_SYNC_SOURCE_REVISION` |
| Upstream verification | `scripts/fetch_mediacrawler.sh`: prefetched checkout already current at `d6f7c5bb906b6dac40ddf343ef9e26438a3de092`; `scripts/check_upstreams.py`: `Upstreams OK (2 locked checkouts verified)` |
| Private Compose merge | One deliberate field added under `services.media-sync.build.args`: `MEDIA_SYNC_SOURCE_REVISION: ${MEDIA_SYNC_SOURCE_REVISION:-unavailable}`; no other deployment field changed |
| Image build | `docker-compose build --no-cache media-sync`, exit `0` after ~23.5 minutes, image `sha256:993669809891…f27e05928` tagged `media-sync:local` |
| Identity proof | OCI label `org.opencontainers.image.revision` equals the exported SHA; `/opt/BUILD-MANIFEST.txt` records the same `source_revision` |
| Pre-flight config | `media-sync serve --check-config` via the API service definition: `{"service":"media-sync-api","configuration":"valid"}`, exit `0` |
| Container recreation | `docker-compose up -d --no-deps --force-recreate media-sync`; container started `2026-09-12T08:39:48Z`, Docker health `healthy`; loopback `GET /api/v1/health` with the public proxy Host returned `200 {"status":"ok"}` |
| Database migration | Startup applied the schema upgrade; deep report shows `revision = expected = 0015_xhs_creator_notes`, `revision_current: true`, 25/25 required tables |

## Deep-report comparison (both service definitions)

`media-sync doctor --deep --accept-mediacrawler-license --json` ran once under the `media-sync` API definition and once under the `supervisor` profile definition without starting either resident process. Both exited `0` with `ok: true, code: ready`; every compared field was identical:

| Field | API | Supervisor |
| --- | --- | --- |
| `build_manifest.source_revision` | `3c31dce81f7240ea0c63a6309c04970c1b0741b4` (`pass`) | same |
| Database revision / expected | `0015_xhs_creator_notes` / `0015_xhs_creator_notes` | same |
| `continuations.bili_delay_seconds` | `300` | `300` |
| `continuations.xhs_delay_seconds` | `300` | `300` |
| `mediacrawler.upstream_sha` | `d6f7c5bb906b6dac40ddf343ef9e26438a3de092` | same |
| MediaCrawler checks | all 10 `pass` (license, lock, path, repository root, required files, license digest, revision, tracked files, clean worktree, runtime) | same |
| Browser | Chromium `151.0.7922.34`, `pass` | same |
| Tools / paths | git, ffmpeg, ffprobe, Xvfb `pass`; state, archive, export, jobs, mediacrawler runtime `pass` | same |
| Security | `warn` `api_not_loopback` (`0.0.0.0:8632`, requires operator review) — pre-existing known state behind the HTTPS reverse proxy | same |
| `live_qualification` | `NOT_RUN` | `NOT_RUN` |

## Explicit result rows

| Check | Result |
| --- | --- |
| Pre-rebuild backup of database, `/data`, Compose and secrets | PASS |
| Clean tree at exact published SHA, revision exported | PASS |
| Pinned upstream checkout/runtime verification | PASS |
| No-cache rebuild with SHA build arg | PASS |
| OCI revision label and `/opt/BUILD-MANIFEST.txt` match | PASS |
| `serve --check-config` | PASS |
| Container health and loopback API probe | PASS |
| Database migration currency (`0015_xhs_creator_notes`) | PASS |
| Bilibili/XHS continuation equality across definitions | PASS |
| API-versus-supervisor deep-report comparison | PASS |
| Network boundary review (`api_not_loopback`) | WARN (known, unchanged; reverse-proxied deployment) |
| Bounded XHS canary (login, adoption, delivery, CDN, NFO, restart) | NOT_RUN — operator-gated |
| Resident supervisor cycle | NOT_RUN — intentionally not started |
| Browser Diagnostics re-inspection | NOT_RUN — the CLI deep report and the Diagnostics page share the same safe evidence set; no browser session was opened |

## Bounded host facts

`/data` top-level directories remain `archive`, `jobs`, `library`, `mediacrawler`, `state` on one persistent named volume; no path layout changed. The prior image `f4a1241c2f26…` (revision label `unavailable`) remains on the host as an untagged rollback image.

## Decision

Per the handoff, the deployment now proves its exact application identity, current migration, equal continuation values and healthy pinned checkout/runtime under both service definitions, which unlocks the bounded XHS canary. That canary remains operator work: one authorized native XHS login through `/crawler/`, explicit Account adoption, one paused low-volume creator Subscription, one exact manual delivery, then restart/supervisor observation. No Douyin delivery work has started.
