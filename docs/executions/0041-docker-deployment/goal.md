**English** | [中文](goal.zh.md)

# Execution 0041 goal

- Status: Packaging delivered; build and live qualification execute on the operator's Linux host
- Date: 2026-09-03
- Predecessor: Execution 0040 implementation (same working session)
- Scope: A single Docker image plus compose layout that runs media-sync, its web console and the pinned MediaCrawler runtime, enabling operator-driven QR login and subscription download verification

## Outcome

1. `Dockerfile` builds two layers: the app venv (`/app/.venv`) and the pinned MediaCrawler checkout (`/opt/mediacrawler` + own venv + Playwright Chromium at `/opt/mediacrawler-venv`) at the SHA recorded in `upstreams.lock.json`, with `ffmpeg`, `Xvfb`, CJK fonts and a curl healthcheck.
2. `docker/entrypoint.sh` starts Xvfb on `:99` (the child env allowlist already carries `DISPLAY`/`XAUTHORITY`), runs the idempotent `db init`, then execs the command.
3. `docker-compose.example.yml` ships as a template: the operator copies it to a git-ignored `docker-compose.yml` and edits freely, so upstream updates never conflict with local deployment configuration. It publishes `127.0.0.1:8632:8632` only, keeps all state under the `media-sync-data` volume (`/data`), and offers an optional `supervisor` profile running `scheduler supervise` with both MediaCrawler gates.
4. Bilingual deployment documentation (`docs/deployment.md` / `.zh.md`) walks build → console QR login → subscribe → sync/pipeline → Emby library with an honest verification checklist.

## Acceptance boundaries

- No image publication or redistribution: the upstream's non-commercial license forbids it; the image is built locally by the operator.
- The console/API stays unauthenticated; the compose default never exposes it beyond the host loopback.
- Every live row (QR login, crawl, download, media server) is executed and recorded by the operator on Linux; this repository records only the packaging and instructions.

## Explicitly deferred

CI pipelines, multi-arch builds, HTTPS/reverse-proxy guidance and any form of remote authentication remain future work.
