**English** | [中文](progress.zh.md)

# Progress: the operator-run bounded canary per platform

Status: **procedure and qualification record frozen. No live step executed.**

## Result

0087 does not add product behaviour. It fixes the procedure an operator must
follow and records the honest state of every live row, so the project's remaining
work is visible as *operator work* rather than as unfinished code.

## What was produced

1. **[`goal.md`](goal.md)** — the seven-platform durable-chain table (0074 through
   0086) and the statement that what remains needs a Linux host, a real login, a
   platform request and CDN bytes.
2. **[`plan.md`](plan.md)** — the seven-step procedure: prove image and migration
   identity, claim one native session, pause everything else, run one bounded
   single-author canary, download and publish real bytes, replay for zero work,
   restart once, then record. It also fixes per-platform "must observe / must
   never observe" pairs taken from each execution's own stop reasons.
3. **[`qualification.md`](qualification.md)** — the single table that records
   `NOT_RUN` for all seven platforms across live canary, real bytes, zero-work
   replay and restart resume, plus exactly what evidence would change a row.

## What did not change

- No product code, migration or test was modified by this execution.
- The durable chains, stop reasons and delivery rules of 0074–0086 stand as their
  own verification records state.
- Every live row stays `NOT_RUN`. This record cannot move one.

## Why this is the correct closeout

The remaining items are not defects and not missing logic: each needs a real
platform. Recording them as `NOT_RUN` with a reproducible procedure is the honest
endpoint, and it keeps a future operator from mistaking a passing local suite for
a live qualification.
