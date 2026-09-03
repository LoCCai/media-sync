**English** | [中文](plan.zh.md)

# Execution 0041 plan

- Status: Delivered; live checklist executes on Linux
- Date: 2026-09-03

## Delivery sequence

1. Multi-layer Dockerfile (app venv + pinned checkout + Playwright/Chromium + ffmpeg/Xvfb/fonts) with a build arg for the upstream commit matching `upstreams.lock.json`.
2. Entrypoint with Xvfb, idempotent schema init and exec; compose with loopback-only publishing, a data volume, healthcheck and an optional supervisor profile.
3. Bilingual deployment documentation with an honest operator checklist (QR login, subscribe, sync, pipeline, Emby) that records only what actually runs.
4. Verification on this workstation is limited to composing the files and the repo's static gates; the image itself builds on the operator's Linux host.

## Risks and rollback

- Deleting `Dockerfile`, `docker/`, `docker-compose.yml`, `.dockerignore` and the deployment docs fully reverts this execution; no runtime code depends on them.
