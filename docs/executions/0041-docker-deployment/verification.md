**English** | [中文](verification.zh.md)

# Execution 0041 verification

- Status: Packaging composed and statically validated; Docker build and live rows execute on the operator's Linux host
- Date: 2026-09-03

## Implemented evidence

| Check | Command | Exit | Result |
| --- | --- | ---: | --- |
| Packaging files present and consistent | `Dockerfile`, `docker/entrypoint.sh`, `docker-compose.example.yml`, `.dockerignore`, `docs/deployment.md`, `docs/deployment.zh.md` | 0 | Entrypoint executable bit committed; compose references only existing commands (`serve`, `scheduler supervise --idle-interval-seconds`) |
| Upstream commit pin matches the lock | `grep MEDIACRAWLER_COMMIT Dockerfile` vs `upstreams.lock.json` | 0 | Both `d6f7c5bb906b6dac40ddf343ef9e26438a3de092` |
| Documentation links | `uv run python scripts/check_docs.py` | 0 | `342 Markdown files checked` (includes both deployment docs) |
| Static gates (shared with 0039/0040) | mypy strict, ruff check/format, compileall | 0 | All green on this workstation |

## Operator checklist on Linux (recorded here once executed)

| Row | Command | Result |
| --- | --- | --- |
| Image build | `cp docker-compose.example.yml docker-compose.yml && docker compose build` | `NOT_RUN` on this workstation |
| Service up + health | `docker compose up -d` → `curl http://127.0.0.1:8632/api/v1/health` | `NOT_RUN` on this workstation |
| Complete suite (pre-deploy) | `uv sync --all-groups --locked && uv run pytest -q` | `NOT_RUN` on this workstation |
| Real QR login via console | console dialog + `login-status` | `NOT_RUN` until executed |
| Real creator crawl | scheduler run with both gates | `NOT_RUN` until executed |
| Real media download + Emby tree | pipeline run + `/data/library` listing | `NOT_RUN` until executed |

This execution claims only packaging and documentation; every live row stays `NOT_RUN` until the operator records actual evidence.
