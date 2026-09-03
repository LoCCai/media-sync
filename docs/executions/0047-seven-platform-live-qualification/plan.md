**English** | [中文](plan.zh.md)

# Execution 0047 plan

- Status: Awaiting operator execution (master phase; restructured by 0048)
- Date: 2026-09-03

## Operator procedure

**Phase B — Linux baseline (before any live account)**

1. `git pull && uv sync --all-groups --locked && uv run pytest -q` — record exact numbers; compare against the execution 0049 baseline of `2066 passed, 1 skipped` (execution 0048's 33/35 flaky runs are only a historical anomaly set) and investigate any platform-specific divergence.
2. `cp docker-compose.example.yml docker-compose.yml && docker compose build && docker compose up -d`; verify `/api/v1/health` + `/api/v1/ready`, console reachable, `db init` idempotent on restart.
3. Restart persistence: `docker compose restart`, confirm accounts/subscriptions/jobs survive; run one backup → restore-into-fresh-volume drill per [`operations.md`](../../operations.md).
4. Process expectations: exactly one managed Xvfb per running container that needs a display (two containers under the supervisor profile is normal); zero Chromium and zero ffmpeg/ffprobe while idle; no orphaned processes after tasks; all of them gone once the container stops.

**Phase C — canary (Bilibili, then XHS)**

For each canary: login (QR preferred) → subscribe to the sample matrix creators → run-now → scheduler run (both gates) → pipeline run → record per-shape outcomes, archived bytes, Emby tree. Then the two incrementality rows (no-change rerun; true increment via the controlled test account). Then the recovery rows: kill a download worker mid-flight and confirm convergence; restart the container mid-crawl; expire a session and re-authenticate; force one CDN primary failure and observe backup selection. Mount `/data/library` read-only into the real Emby/Jellyfin, rescan, verify metadata/posters and sample playback.

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
