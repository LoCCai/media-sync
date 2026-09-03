**English** | [中文](operations.zh.md)

# Operations: backup, restore and upgrade

Applies to the Docker compose deployment from [`deployment.md`](deployment.md). All persistent state lives in the `media-sync-data` volume mounted at `/data`:

| Path | Contents | Backup value |
| --- | --- | --- |
| `/data/state/media-sync.sqlite3` | The database: accounts, subscriptions, contents, assets, jobs, export records | Critical (contains credential *references*, never raw secrets) |
| `/data/archive/` | Immutable SHA-256 media blobs | Critical (re-derivable only by re-downloading everything) |
| `/data/library/` | The Emby/Jellyfin tree (NFO, posters, episodes) | Re-derivable from database + archive via re-export |
| `/data/jobs/`, `/data/mediacrawler/` | Work roots, manifests, browser profiles | Disposable; browser profiles lost means re-login |

## Backup

Offline (service stopped, simplest and always consistent):

> The composed volume name is `<project>_media-sync-data`; confirm yours with `docker volume ls | grep media-sync` if your clone directory differs.

```bash
docker compose stop
docker run --rm -v media-sync_media-sync-data:/data -v "$PWD/backup:/backup" alpine \
  tar czf /backup/media-sync-data-$(date +%F).tgz -C /data .
docker compose start
```

Online (database-consistent while running, using SQLite's stdlib backup API inside the container):

```bash
docker compose exec media-sync /app/.venv/bin/python -c \
  "import sqlite3; src=sqlite3.connect('/data/state/media-sync.sqlite3'); dst=sqlite3.connect('/data/state/backup.sqlite3'); src.backup(dst); dst.close()"
# then copy /data/state/backup.sqlite3 plus archive/ out of the volume as above
```

## Restore

1. Stop the stack: `docker compose stop`.
2. Restore the archive into a fresh volume (or overwrite the existing one):

```bash
docker volume create media-sync_media-sync-data
docker run --rm -v media-sync_media-sync-data:/data -v "$PWD/backup:/backup" alpine \
  sh -c "tar xzf /backup/media-sync-data-DATE.tgz -C /data"
```

3. Start again: `docker compose up -d`. The entrypoint runs `media-sync db init`, which applies any pending migrations idempotently; a restored database at an older revision is upgraded automatically.
4. Verify: `curl -fsS http://127.0.0.1:8632/api/v1/ready` and check the console shows accounts/subscriptions; spot-check one archived file's SHA-256 if you want deep assurance.

If only the database was lost (archive intact), restoring just `state/` is enough; assets re-verify against existing blobs without re-downloading. If the browser profiles under `mediacrawler/` were lost, accounts stay `saved_session` records but the upstream sessions must be re-established via one QR login per account.

## Upgrade

```bash
cd /www/wwwroot/docker/media-sync     # your clone
git pull
cp -f docker-compose.example.yml docker-compose.yml   # only when the template changed and you have no local edits
docker compose build
docker compose up -d
```

Schema migrations run at container start (`db init` is idempotent). `uv.lock` guarantees the same dependency set the release was tested with. The live `docker-compose.yml` is git-ignored, so upstream updates never conflict with your deployment configuration. Roll back a bad release with `git checkout <previous-tag-or-sha>` and rebuild — database down-migrations are not automatic; check the release notes before downgrading.
