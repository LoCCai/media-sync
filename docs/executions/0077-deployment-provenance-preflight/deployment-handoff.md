**English** | [中文](deployment-handoff.zh.md)

# Deployment handoff: identify first, then run one XHS canary

## Status

**PLANNED OPERATOR WORK ONLY.** This handoff does not authorize this local closeout to change the server, start the supervisor, log in, crawl or download. Execute it later on the Linux host after the GitHub push is visible. Keep every unrelated Subscription paused.

## Preconditions

- Preserve an application-consistent backup of the SQLite database, managed credentials and all persistent `/data`; preserve the private Compose file and external operator secret separately. Follow the repository [operations guide](../../operations.md).
- Confirm the exact MediaCrawler non-commercial learning license before setting either API or supervisor acknowledgement.
- Keep the reverse proxy and exact HTTPS origin already used by the deployment. Do not replace the private Compose file wholesale; merge new tracked fields deliberately.
- Stop the supervisor before rebuilding or inspecting the first canary:

```bash
docker compose --profile supervisor stop supervisor
```

## Pull and bind the exact source

```bash
git fetch origin
git checkout main
git pull --ff-only origin main
test -z "$(git status --porcelain)"
export MEDIA_SYNC_SOURCE_REVISION="$(git rev-parse HEAD)"
printf 'media-sync source: %s\n' "$MEDIA_SYNC_SOURCE_REVISION"
sh scripts/fetch_mediacrawler.sh
python3 scripts/check_upstreams.py
```

The private Compose build must include this field under `services.media-sync.build.args`:

```yaml
MEDIA_SYNC_SOURCE_REVISION: ${MEDIA_SYNC_SOURCE_REVISION:-unavailable}
```

Keep `MEDIA_SYNC_XHS_SCAN_CONTINUATION_DELAY_SECONDS` identical in `media-sync` and `supervisor`; do the same for the Bilibili continuation delay. Keep `/data/state`, `/data/archive`, `/data/library`, `/data/jobs` and `/data/mediacrawler` on the same persistent mount in both services.

## Build and prove image identity

```bash
docker compose config >/dev/null
docker compose build --no-cache media-sync
test "$(docker image inspect media-sync:local --format '{{ index .Config.Labels "org.opencontainers.image.revision" }}')" = "$MEDIA_SYNC_SOURCE_REVISION"
docker compose run --rm --no-deps --entrypoint /app/.venv/bin/media-sync media-sync serve --check-config
docker compose up -d --no-deps --force-recreate media-sync
docker compose ps media-sync
docker compose logs --tail=100 media-sync
```

Normal startup may apply migration `0015_xhs_creator_notes`; that is why backup precedes the rebuild. A successful healthcheck or `serve --check-config` does not prove application identity, database currency, crawler checkout or live login.

## Compare API and supervisor preflight

Sign in to the main console, open Diagnostics, force a refresh and record only the safe fields: full media-sync SHA, current/expected migration, Bilibili/XHS continuation delays, pinned upstream SHA and fixed check states. Then run the same report under both service definitions without starting either resident process:

```bash
docker compose run --rm --no-deps --entrypoint /app/.venv/bin/media-sync media-sync \
  doctor --deep --accept-mediacrawler-license --json
docker compose --profile supervisor run --rm --no-deps --entrypoint /app/.venv/bin/media-sync supervisor \
  doctor --deep --accept-mediacrawler-license --json
```

Proceed only when both reports identify `$MEDIA_SYNC_SOURCE_REVISION`, show current/expected `0015_xhs_creator_notes`, report the intended equal continuation values and qualify the pinned checkout/runtime/browser. `live_qualification: NOT_RUN` is expected. A nonzero CLI exit is a stop condition, not permission to bypass a check.

## One bounded XHS canary

1. With supervisor still stopped, use authenticated `/crawler/` for one authorized XHS native login and wait until its process is idle.
2. Explicitly adopt that saved profile into one matching XHS Account. Never paste a Cookie, token, profile path or opaque cursor into the evidence document.
3. Create one paused low-volume creator Subscription with the exact protected creator URL. Resume only that Subscription and invoke one exact manual delivery.
4. Confirm one source page unit, retained page-tail state, exact Job/Run/pipeline ownership, fixed partial/blocked codes and no secret values in API or rolling logs.
5. Inspect real downloaded bytes, SHA-256 archive and configured XHS directory/NFO/sidecars through the host mount. No Emby/Jellyfin API connection is required.
6. Run a bounded continuation, verify no duplicate publication, restart the API once and prove the same durable state resumes.
7. Only after those checks pass, start the supervisor and observe one scheduled continuation. Stop it again on any ambiguity.

## Stop and record

Stop on a source/migration/config mismatch, checkout failure, authentication ambiguity, creator mismatch, unexpected scan scope, token/cursor disclosure, access restriction, directory permission error or unexplained Job/Run divergence. Do not automatically retry a restricted account and do not resume unrelated subscriptions.

Create a new bilingual qualification record containing the deployed full SHA, timestamps, redacted identities, safe CLI/UI evidence, bounded directory-tree facts and explicit `PASS`/`FAIL`/`NOT_RUN` rows. Do not modify checked-in live matrices from expectation alone.

## Following work

After the XHS canary passes or has a documented blocking cause, trace the pinned Douyin creator-work source and freeze a separate delivery contract for its pagination, `has_more`/cursor, aweme identity, detail/media authority, page-tail retention and risk-control behavior. Do not copy Bilibili page numbers or XHS token semantics. No Douyin implementation is authorized by this handoff.
