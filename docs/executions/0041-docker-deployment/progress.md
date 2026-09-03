**English** | [中文](progress.zh.md)

# Execution 0041 progress

- Status: Packaging delivered; operator executes build and live checklist on Linux
- Date: 2026-09-03

## Completed

- `Dockerfile` (python:3.12-slim-bookworm base; app venv via `uv sync --locked --no-dev`; MediaCrawler cloned at the locked commit `d6f7c5b…` with its own venv, requirements and `playwright install --with-deps chromium`; ffmpeg/Xvfb/xauth/CJK fonts; non-root `mediasync` user; curl healthcheck; `MEDIACRAWLER_COMMIT` build arg).
- `docker/entrypoint.sh` (Xvfb `:99`, `media-sync db init`, exec CMD) and `.dockerignore`.
- `docker-compose.example.yml` template (renamed from a tracked live file after review so operator copies never conflict with `git pull`): loopback-only port publishing, `media-sync-data` volume, 1 GB `/dev/shm` for Chromium, healthcheck, optional `supervisor` profile running `scheduler supervise --enable-mediacrawler --accept-mediacrawler-license --idle-interval-seconds 30`.
- Bilingual `docs/deployment.md` / `docs/deployment.zh.md` with the operator verification checklist.

## Deviations and decisions

- No image build was attempted on the Windows workstation per operator direction; Docker build and every live row execute on the Linux host and will be recorded there (this record intentionally leaves those rows `NOT_RUN`).
- `DISPLAY=:99` is set image-wide; the login child's env allowlist already carried it, so no bridge code changed for display handling.

## Remaining

- Operator: `cp docker-compose.example.yml docker-compose.yml`, edit freely, then `docker compose build` / `up -d`, run the complete test suite inside or beside the container, perform console QR login + subscribe + sync + pipeline + Emby checks, and record honest outcomes.
