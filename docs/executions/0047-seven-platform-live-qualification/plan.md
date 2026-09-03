**English** | [中文](plan.zh.md)

# Execution 0047 plan

- Status: Awaiting operator execution
- Date: 2026-09-03

## Operator procedure (per platform, on the deployment host)

1. Precondition gate: `uv sync --all-groups --locked && uv run pytest -q` green; `docker compose up -d` healthy; console reachable.
2. Login: console 扫码登录 (or Cookie for accounts that prefer it); record method, challenge types and duration.
3. Subscribe: one known-good creator per platform with a small `max_items`; 立即运行.
4. Sync: 运行同步 worker; record job outcome, items discovered.
5. Download/export: 运行下载/导出 pipeline; record asset counts, archived bytes, Emby tree listing.
6. Re-run the sync once; record incrementality (second run discovers only new items, zero re-download).
7. Record one row per platform in this directory (bilingual), update the capabilities matrix and the completion archive, then closeout with the offline suite numbers.

Any blocked platform gets `BLOCKED_EXTERNAL` with the reason (no account, unsupported region, changed upstream behavior) — the record is the deliverable, not a pass.

## Rollback

No code is changed by this execution; platform records are append-only documentation.
