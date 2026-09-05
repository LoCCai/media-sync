**English** | [中文](operations.zh.md)

# Operations: backup, restore and upgrade

Applies to the Docker compose deployment from [`deployment.md`](deployment.md). All application-managed persistent state lives in the `media-sync-data` volume mounted at `/data`:

| Path | Contents | Backup value |
| --- | --- | --- |
| `/data/state/media-sync.sqlite3` | The database: accounts, subscriptions, contents, assets, jobs, export records, durable Operations/Events and the revision-`0008` playback-evidence ledger | Critical (contains platform-account credential *references* and any explicitly confirmed playback associations represented by UUIDs/digests/timestamps; never raw secrets, remote item IDs, operator credentials/sessions or media-server keys/references) |
| `/data/archive/` | Immutable SHA-256 media blobs | Critical (re-derivable only by re-downloading everything) |
| `/data/library/` | The Emby/Jellyfin tree (NFO, posters, episodes) | Re-derivable from database + archive via re-export |
| `/data/jobs/`, `/data/mediacrawler/` | Work roots, manifests, browser profiles | Disposable; browser profiles lost means re-login |

The operator-auth configuration and execution 0054-A media-server profile are deployment configuration, not application data in this volume. Preserve the absolute host path named by `MEDIA_SYNC_OPERATOR_CREDENTIAL_FILE`, the credential file itself, non-secret environment selectors, and any external `env:` / `file:` / `keyring:` material through the operator's configuration and secret-management process. Never add a raw operator credential, Bearer token, media-server API key, or complete private secret reference to a database/archive backup, support bundle, shell transcript, or Git. Browser sessions and CSRF values are process-local memory and are deliberately neither backed up nor restored.

## Backup

Offline (service stopped, simplest and always consistent):

> The composed volume name is `<project>_media-sync-data`; confirm yours with `docker volume ls | grep media-sync` if your clone directory differs.

```bash
docker compose stop
docker run --rm -v media-sync_media-sync-data:/data -v "$PWD/backup:/backup" alpine \
  tar czf /backup/media-sync-data-$(date +%F).tgz -C /data .
docker compose start
```

Starting the API creates a new process with no browser session. Any previously issued operator cookie is invalid and the operator must authenticate again after the Web login client is delivered.

Online (database-consistent while running, using SQLite's stdlib backup API inside the container):

```bash
docker compose exec media-sync /app/.venv/bin/python -c \
  "import sqlite3; src=sqlite3.connect('/data/state/media-sync.sqlite3'); dst=sqlite3.connect('/data/state/backup.sqlite3'); src.backup(dst); dst.close()"
# then copy /data/state/backup.sqlite3 plus archive/ out of the volume as above
```

The SQLite backup includes durable `media-server-probe` / `media-server-scan` audit rows and their allowlisted evidence, including phase-B author targets, related publication Jobs, and accepted/observed checkpoints. At revision `0008` it also includes append-only playback-evidence rows created or replayed by the browser-only confirmation backend. Those rows contain canonical author/publication-Job identities, context-bound digests and server timestamps, not a raw server item ID or path. The API response omits the observation fingerprint and all internal context digests. A backed-up row records an explicit operator attestation; it does not prove remote telemetry. After restore, schema v3 re-resolves current authority for one explicitly selected author before that attestation can grant scoped PASS; uncertain remote authority returns unknown history. It never infers a global or checked-in live PASS from restored rows. The backup does not include the environment-owned media-server profile, operator credential, optional Bearer token, session cookie, or CSRF value. Back up only the required deployment inputs through the separate secret-management process described above.

## Restore

1. Stop the stack: `docker compose stop`.
2. Restore the archive into a fresh volume (or overwrite the existing one):

```bash
docker volume create media-sync_media-sync-data
docker run --rm -v media-sync_media-sync-data:/data -v "$PWD/backup:/backup" alpine \
  sh -c "tar xzf /backup/media-sync-data-DATE.tgz -C /data"
```

3. Restore or recreate the Git-ignored deployment configuration and external secret-provider material. Before Compose starts, export `MEDIA_SYNC_OPERATOR_CREDENTIAL_FILE` as the absolute path to the mode-`0600` credential file required by the example secret mount. Keep `MEDIA_SYNC_MEDIA_SERVER_OPERATIONS_ENABLED=false` until the restored safe summary, origin, TLS posture, network-rule count and Library digest have been checked.
4. Start again: `docker compose up -d`. The entrypoint runs `media-sync db init`, which applies any pending migrations idempotently; a restored database at an older revision is upgraded automatically.
5. Verify the intentionally public probe with `curl -fsS http://127.0.0.1:8632/api/v1/ready`; verify that an anonymous business request receives the fixed authentication rejection; spot-check one archived file's SHA-256 if deeper assurance is required. The current Web bundle has no login/CSRF client, so do not use console rendering as a restore criterion and do not enable media-server Operations through the Web UI yet.

If only the database was lost (archive intact), restoring just `state/` is enough; assets re-verify against existing blobs without re-downloading. If the browser profiles under `mediacrawler/` were lost, accounts stay `saved_session` records but the upstream sessions must be re-established via one QR login per account.

## Upgrade

```bash
cd /www/wwwroot/docker/media-sync     # your clone
git pull
cp -f docker-compose.example.yml docker-compose.yml   # only when the template changed and you have no local edits
export MEDIA_SYNC_OPERATOR_CREDENTIAL_FILE=/absolute/private/path/operator-credential.txt
docker compose build
docker compose up -d
```

Schema migrations run at container start (`db init` is idempotent), before `serve` validates operator authentication. An authentication startup failure therefore does not guarantee an unchanged database. Back up before upgrade and use the [entrypoint-bypassing runtime-user credential preflight](deployment.md) before starting; full pre-migration configuration validation remains pending. Keep the credential restricted and readable by the effective container user, not simply root-owned `0600`. `uv.lock` guarantees the same dependency set the release was tested with. The live `docker-compose.yml` is git-ignored, so upstream updates never conflict with your deployment configuration. The backend authentication boundary from commit `f19bfaa` is active, but Web login/session bootstrap and CSRF propagation remain pending; use CLI/supervisor workflows until that frontend checkpoint closes.

Revision `0007_media_server_operations` is forward-only once the database contains any `media-server-probe` or `media-server-scan` row. Its downgrade deliberately fails closed instead of deleting durable audit evidence, and an older application must not be run against that database. A database with no new-kind rows may use the tested downgrade path, but down-migrations are never automatic. Before checking out an older tag/SHA, inspect the release notes and database state; if new-kind rows exist, restore a compatible pre-upgrade backup or continue with an application version that understands revision `0007`.

Execution 0054-B historically added no migration and ended at `0007`. Execution 0055 advances Alembic to `0008_playback_evidence`; its browser-only confirmation service can now populate that ledger through the application-owned transaction. The table is empty on upgrade and has `RESTRICT` links to the author and publication Job; the application repository exposes create-or-exact-replay rather than update/delete. An online downgrade to `0007` succeeds only while the table is empty. If any evidence row exists, downgrade fails closed with `playback_evidence_rows_prevent_downgrade`; offline SQL downgrade is rejected because it cannot audit table contents. Never delete evidence rows merely to force a rollback. Restore a compatible pre-`0008` backup or continue with a binary that understands `0008`.

SQLite remains the supported production store. The `0008` migration emits portable SQLite/PostgreSQL DDL, and the repository has PostgreSQL-specific unique-conflict/savepoint semantics plus an optional isolated three-table race suite. That real-PostgreSQL suite has not run on this workstation, and its Author/Job/PlaybackEvidence fixture does not demonstrate a complete application schema, container deployment or production PostgreSQL support.

Before rolling an application binary back across the historical `0007` boundary, wait until every author-observation scan is terminal or deploy a reconciliation-compatible binary. Never delete Operation rows or accepted/observed checkpoints to force compatibility.

Authentication is also an application rollback boundary even though it adds no database revision. Do not run an older anonymous `serve` binary to regain console access. Keep traffic stopped and deploy an authentication-compatible build; an external proxy is not implicitly trusted by this application and needs its own review.
