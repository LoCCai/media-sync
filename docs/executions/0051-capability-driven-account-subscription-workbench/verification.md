**English** | [中文](verification.zh.md)

# Execution 0051 verification

- Status: Offline implementation gates pass; live qualification remains `NOT_RUN`
- Date: 2026-09-04
- Baseline: `38e0ebe`
- Database migration: None

## Automated gates

| Check | Command | Result |
| --- | --- | --- |
| Complete Python suite | `uv run pytest -q` | `PASS` — 2135 passed, 3 skipped |
| Frontend formatting | `pnpm format:check` | `PASS` |
| Svelte/TypeScript | `pnpm check` | `PASS` — 0 errors, 0 warnings |
| Frontend units | `pnpm test` | `PASS` — 7 tests |
| Static production bundle | `pnpm build` | `PASS` — adapter-static build completed |
| Ruff | `uv run ruff check . --no-cache` | `PASS` |
| Ruff format | `uv run ruff format --check .` | `PASS` |
| strict mypy | `uv run mypy --strict --no-incremental src` | `PASS` — 90 source files |
| Bytecode compilation | `uv run python -m compileall -q src` | `PASS` |
| Distribution build | `uv build` | `PASS` — sdist and wheel |
| Documentation | `uv run python scripts/check_docs.py` | `PASS` — 458 Markdown files |
| Locked upstreams | `uv run python scripts/check_upstreams.py` | `PASS` — 2 SHA/remote checks and 2 clean checkouts |

The locked checkouts remain MediaCrawler `d6f7c5bb906b6dac40ddf343ef9e26438a3de092` and bili-sync-up `dcb5bb73b56ac45b2525da14b389e185b0ea6dbd`. Neither checkout was modified during implementation or closeout.

## Requirement evidence

| Requirement | Verified evidence |
| --- | --- |
| Stable seven-platform capability contract | Endpoint/serialization contracts assert the v1 shape and exact order `xhs`, `dy`, `ks`, `bili`, `wb`, `tieba`, `zhihu` |
| Conservative creator authority | Focused application and API tests enforce `[A-Za-z0-9._-]{1,255}`, XHS-only secret references and rejection before mutation |
| Explicit full-history acknowledgement | Equivalent CLI/API drafts for Bilibili, Douyin, Kuaishou and Weibo reject without `allow_full_history=true`; no Author or Subscription row is written |
| Shared CLI/REST workbench | Contract tests exercise equivalent preview/create rules and retain the CLI's legacy JSON projection |
| Concurrent idempotent creation | SQLite same-draft races converge to one Account or Subscription under the workbench-scoped immediate writer reservation |
| Login-only preflight | Mandatory database/account/licence/checkout/runtime/browser/profile/lock failures allocate no new process-local Operation or LoginSession; ffmpeg/ffprobe do not participate |
| Exact-session QR authority | Tests cover active ownership, non-QR rejection, abandoned-session reconciliation, stale cleanup, 2 MiB regular-file bounds, inode/size validation, post-read durable revalidation and terminal non-disclosure |
| Capability-driven Web workbench | Svelte state/unit coverage verifies composite account state, preflight/session QR polling and the three-stage subscription preview/confirmation flow |
| Safe response projection | Secret, credential, signed-URL, path and cursor sentinels stay absent from preview/result/detail responses; 422 validation does not echo hostile input |

## Residual risk

A successful preflight is a point-in-time snapshot. The handoff from that result to a process-local Operation and then the background application service is not one atomic transaction across API processes. Two API processes can therefore both pass preflight before the durable login boundary selects a winner. Durable `LoginSession` compare-and-set and the account OS lock remain authoritative, and the loser fails closed.

This is a non-blocking coordination/UX residual assigned to Execution 0052's durable Operations and cross-process idempotency work. It is not the QR file read/post-read revalidation interval and does not grant credential or QR authority.

## Evidence policy

No real browser login, creator endpoint, platform API/CDN, downloaded creator media or Emby/Jellyfin server was used. Local fixtures, mocked runtimes and browser/unit tests are offline evidence only. No live-account, crawl, download, rescan or playback row was changed from `NOT_RUN`; those claims remain gated by Execution 0047 operator evidence.
