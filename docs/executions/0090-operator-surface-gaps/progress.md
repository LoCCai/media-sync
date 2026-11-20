**English** | [中文](progress.zh.md)

# Progress: surface the operator-visible gaps 0088 left behind

Status: implemented and verified locally. Nothing deployed, no live account or
platform request used.

## Result

Three findings that 0088 recorded as NIT/RISK are closed. Each was about the
deployment being harder to operate than the code was to write.

## What was wrong

1. **Four platforms' continuation pacing was invisible.** `/api/v1/settings` and
   `doctor --deep` — the two surfaces an operator diffs against the supervisor's
   environment — listed only Bilibili, XHS, Douyin and Kuaishou. Weibo, Tieba and
   Zhihu were missing from both, so a mismatch in their pacing had no place to
   show up. That is precisely how 0088's "nine of nine construction sites omitted
   the policies" stayed unnoticed.
2. **The dashboard answered a different question than it appeared to.** The KPI
   cards derived "待处理任务" from `jobs?limit=12` and "已归档资产" from
   `assets?limit=200`. Both numbers were correct about the window and misleading
   about the queue and the library.
3. **Every non-scheduler operation row said "已有白名单摘要".** A verified download,
   a fresh export and a successful login all rendered the same phrase, because the
   cell printed one constant whenever a whitelisted projection existed.

## What changed

- All seven delays are now reported by both operator surfaces and declared in the
  console's `Settings` type; the API test enumerates them instead of sampling.
- The KPI labels name their window and mark the two genuinely complete arrays as
  全量, so "how many" is answerable for the two things that can answer it.
- `operationResultLabel` derives a closed, qualitative label from the existing
  whitelisted projection — asset-download verified/exported/empty, export
  re-export vs fresh, login auth status — without ever reading raw `result`.

## Verification

Web `849 passed` (846 before, +3 for the label cases); `svelte-check` 0/0;
Prettier clean; build succeeds. Python: Ruff and `ruff format --check` clean,
strict mypy over 182 files clean, `check_docs.py` links OK over 886 files.
Exact per-gate evidence is in [verification.md](verification.md).

## Deliberately not done

The dashboard still reads bounded arrays rather than server-side aggregates.
Adding aggregate endpoints is a new API surface with its own pagination and
redaction questions; the honest fix here was to stop presenting a window as a
total, not to build new counting endpoints in a documentation-adjacent execution.
