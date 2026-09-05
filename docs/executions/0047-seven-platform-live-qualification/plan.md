**English** | [中文](plan.zh.md)

# Execution 0047 plan

- Status: Awaiting prerequisites and operator execution (master phase; restructured by 0048)
- Date: 2026-09-03

## Operator procedure

**Phase B — Linux baseline (before any live account)**

1. `git pull && uv sync --all-groups --locked && uv run pytest -q` — record exact numbers and investigate platform-specific divergences. See the latest [0055 projection verification](../0055-operator-auth-playback-evidence/evidence-projection/verification.md). Windows skips and unconfigured real-PostgreSQL cases do not replace the complete Linux host gate with PostgreSQL enabled.
2. Before any Compose startup, create a dedicated UTF-8 operator-credential file outside the repository, restrict it to mode `0600`, and set `export MEDIA_SYNC_OPERATOR_CREDENTIAL_FILE=/absolute/private/path/operator-credential.txt`. The credential must be 16–1024 UTF-8 bytes, contain no control characters, and must not reuse a platform cookie or media-server key. Keep this absolute path available across restarts; the example Compose file mounts it as `/run/secrets/operator_credential` and passes only `file:operator_credential` to the application.
3. `cp docker-compose.example.yml docker-compose.yml && docker compose build && docker compose up -d`; confirm the required typed credential resolves before bind and the configured browser origin exactly matches `http://127.0.0.1:8632`. With a reviewed HTTP client that does not expose the credential in logs or shell history, prove anonymous access is limited to `GET`/`HEAD /api/v1/health`, `GET`/`HEAD /api/v1/ready`, `POST /api/v1/operator-auth/login`, `GET /api/v1/operator-auth/session` and the public root assets; prove an anonymous business route and `/api/docs` are rejected; then prove login → cookie session → CSRF-protected unsafe request → logout. If optional Bearer automation is tested, configure a separately resolved credential that differs from the browser credential. Record exact status codes without recording credentials, cookies or CSRF values.
4. Restart persistence: `docker compose restart`, confirm accounts/subscriptions/jobs survive and the process-local operator session is invalidated; run one backup → restore-into-fresh-volume drill per [`operations.md`](../../operations.md).
5. Process expectations: exactly one managed Xvfb per running container that needs a display (two containers under the supervisor profile is normal); zero Chromium and zero ffmpeg/ffprobe while idle; no orphaned processes after tasks; all of them gone once the container stops.

**Qualification hold point:** backend authentication, revision `0008`, confirmation, bounded author evidence reads and qualification v3 are implemented. Console v2 and `/legacy` still lack login/session/CSRF and confirmation UI. Keep all live rows NOT_RUN until the Web checkpoint is verified and an authorized operator runs the live steps. A schema-v3 author-scoped PASS requires exact current durable attestation; implementation or local/mock tests never produce checked-in live PASS.

**Phase C — canary (Bilibili, then XHS)**

After the hold point is cleared, for each canary: authenticate through the completed Web login shell, login to the platform (QR preferred) → subscribe to the sample matrix creators → run-now → scheduler run (both gates) → pipeline run → record per-shape outcomes, archived bytes and the Emby tree. Then run the two incrementality rows (no-change rerun; true increment via the controlled test account). Then run the recovery rows: kill a download worker mid-flight and confirm convergence; restart the container mid-crawl; expire a session and re-authenticate; force one CDN primary failure and observe backup selection. Mount `/data/library` read-only into the real Emby/Jellyfin, rescan, verify metadata/posters, record sample playback through the implemented authenticated evidence path, and only then change the corresponding live rows from `NOT_RUN`.

**Phase D — remaining platforms in media-class batches**

Douyin/Kuaishou/Weibo (video/gallery/cover/signed CDN), then Tieba/Zhihu (articles/body/galleries/pagination), each against its sample matrix.

**Phase E — stability**

Supervisor across several scheduling cycles; no growing Chrome/Xvfb processes; no permanently claimed/running Jobs; SQLite + archive backup restore; Emby rescan + sampled playback.

**Phase F — closeout**

Update the platform capability matrix and [`docs/status.md`](../../status.md) with per-platform tiers; flip the completion-archive live rows; if the two canaries are Supported and every platform is classified, tag `v0.1.0-rc1`.

## Defect loop

Any live failure → numbered fix sub-execution (`0047-dN`) → code change → automated regression (full suite on the host) → rerun the affected platform → rerun affected same-class platforms → only then update this record.

## Rollback

This execution changes no product code by itself; fix sub-executions carry their own rollback records.
