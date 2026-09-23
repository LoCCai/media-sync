**English** | [中文](handoff-checklist.zh.md)

# Operator quick checklist: rebuild, prove identity, run one XHS canary

A condensed, checkable working list distilled from the [deployment handoff](executions/0077-deployment-provenance-preflight/deployment-handoff.md). The handoff remains authoritative; when in doubt, follow it. Execute on the Linux host. Keep every unrelated subscription paused.

## 0) Prepare

- [ ] Application-consistent backup of the SQLite database, managed credentials and all of `/data` (see [operations](operations.md)); private Compose file and operator secret preserved separately.
- [ ] MediaCrawler non-commercial learning license reviewed.
- [ ] Reverse proxy and exact HTTPS origin unchanged.
- [ ] Supervisor stopped: `docker compose --profile supervisor stop supervisor`.

## 1) Pull and bind the exact source

```bash
git fetch origin && git checkout main && git pull --ff-only origin main
test -z "$(git status --porcelain)"
export MEDIA_SYNC_SOURCE_REVISION="$(git rev-parse HEAD)"
sh scripts/fetch_mediacrawler.sh
python3 scripts/check_upstreams.py
```

- [ ] Private `docker-compose.yml` carries `MEDIA_SYNC_SOURCE_REVISION: ${MEDIA_SYNC_SOURCE_REVISION:-unavailable}` under `services.media-sync.build.args`.
- [ ] `MEDIA_SYNC_XHS_SCAN_CONTINUATION_DELAY_SECONDS` (and the Bilibili delay) identical in `media-sync` and `supervisor`; same persistent mounts for state/archive/library/jobs/mediacrawler.

## 2) Build and prove image identity

```bash
docker compose config >/dev/null
docker compose build --no-cache media-sync
test "$(docker image inspect media-sync:local --format '{{ index .Config.Labels "org.opencontainers.image.revision" }}')" = "$MEDIA_SYNC_SOURCE_REVISION"
docker compose run --rm --no-deps --entrypoint /app/.venv/bin/media-sync media-sync serve --check-config
docker compose up -d --no-deps --force-recreate media-sync
docker compose ps media-sync && docker compose logs --tail=100 media-sync
```

- [ ] OCI revision label equals `$MEDIA_SYNC_SOURCE_REVISION` (the `test` above exits nonzero otherwise — a stop condition).
- [ ] Startup applied migration `0015_xhs_creator_notes` (backup preceded the rebuild for exactly this reason).
- [ ] License environment changes applied via `--force-recreate`; plain `restart` does not replace environment.

## 3) Compare API and supervisor preflight

- [ ] Console → Diagnostics → refresh: full media-sync SHA, current/expected migration, Bili/XHS continuation delays, pinned upstream SHA, fixed check states.
- [ ] Both service definitions identify the same SHA and `0015`:

```bash
docker compose run --rm --no-deps --entrypoint /app/.venv/bin/media-sync media-sync \
  doctor --deep --accept-mediacrawler-license --json
docker compose --profile supervisor run --rm --no-deps --entrypoint /app/.venv/bin/media-sync supervisor \
  doctor --deep --accept-mediacrawler-license --json
```

- [ ] `live_qualification: NOT_RUN` is expected; any nonzero CLI exit is a stop condition.

## 4) One bounded XHS canary

1. [ ] Supervisor still stopped; authenticated `/crawler/` → one authorized XHS native login; wait until the process is idle.
2. [ ] Accounts page → explicitly adopt the saved profile into one matching XHS Account.
3. [ ] Create one paused low-volume creator subscription with the exact protected creator URL; resume only it; invoke one exact manual delivery.
4. [ ] Confirm one source page unit, retained page-tail state, exact Job/Run/pipeline ownership, fixed partial/blocked codes, no secret values in logs.
5. [ ] Inspect real downloaded bytes, SHA-256 archive, XHS directory/NFO output through the host mount (no media-server API needed).
6. [ ] Run one bounded continuation → no duplicate publication; restart the API once → same durable state resumes.
7. [ ] Only then start the supervisor and observe one scheduled continuation; stop on any ambiguity.

## 5) Stop conditions

Source/migration/config mismatch, checkout failure, authentication ambiguity, creator mismatch, unexpected scan scope, token/cursor disclosure, access restriction, directory permission error, unexplained Job/Run divergence. Do not auto-retry a restricted account; do not resume unrelated subscriptions.

## 6) Record

Create a bilingual qualification record: deployed full SHA, timestamps, redacted identities, safe CLI/UI evidence, bounded directory-tree facts, explicit `PASS`/`FAIL`/`NOT_RUN` rows. Never modify checked-in live matrices from expectation alone.

## Quick troubleshooting (operator experience)

| Symptom | Likely cause | Action |
| --- | --- | --- |
| `/crawler/api/crawler/qrcode` 404 forever | Platform login dialog never popped / QR selector failed (Douyin is known-fragile; upstream itself recommends Cookie) | Watch the `/crawler/` page log panel for `login qrcode not found`; for Douyin use Cookie paste instead (Accounts page, 0065 flow) |
| QR shown then 404 | 180-second freshness expiry | Re-run the login and open the QR immediately; keep the page polling |
| "No logs" in `docker compose logs` | Crawler child output is captured into the `/crawler/` page's in-memory log panel, not Docker logs | Read the `/crawler/` log area during a run; media-sync's own subprocess diagnostics live in console → Logs |
| Where do downloads go | Three layers: `/data/mediacrawler/webui-output` (raw crawler dump), `/data/archive` (verified SHA-256 store), `/data/library` (Emby/Jellyfin tree) | `docker compose exec media-sync ls /data/archive /data/library` |

## Following work

After the XHS canary passes (or a blocking cause is recorded): trace the pinned Douyin creator-work source and freeze a separate delivery contract. No Douyin implementation is authorized before that.
