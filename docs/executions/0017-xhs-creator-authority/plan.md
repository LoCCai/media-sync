**English** | [中文](plan.zh.md)

# Execution 0017 plan

- Status: Executed and closed offline
- Plan date: 2026-09-01
- Predecessor: Execution 0016 closeout commit `4774c34`
- Plan commit: `9d19e7e`
- Implementation commit: `2f8dbaa`
- Database migration: None

## Baseline

Before source edits, the six-file gate passed `136 passed in 13.50s`: ingestion, refresh, database ingestion, download runtime, pipeline runtime and packaged migrations. The branch was clean at `4774c34`, with local `main`, `origin/main` and GitHub reconciled.

## Executed delivery sequence

1. **Authority protocol** ：shared strict XHS note/creator validation, decoded value checks, XOR repr-safe inputs and child schema v3.
2. **Exact Subscription authority** ：explicit detail override first; otherwise resolve only exact provenance creator secret and project bounded `subscription.max_items`.
3. **Bounded creator lookup** ：clear all creator/detail lists, configure one XHS path, concurrency one, bounded notes and disabled comments/media.
4. **Contracts and composition** ：authority/frame/provenance/preflight tests plus ordinary static IMAGE/GALLERY archive/Emby composition and zero-work replay.
5. **Independent review repairs** ：unique ordinary-static result gate, duplicate-target rejection, VERIFIED archive repair preflight, pipeline error taxonomy, durable raw shape preservation and non-XHS CLI rejection.
6. **Verification and closeout** ：all implementation gates and the post-edit 84-file documentation check pass; only the closeout commit/push remains for the main thread.

## Commit sequence

1. `9d19e7e` — `docs: 启动小红书作者权限闭环 / start XHS creator authority pipeline` — pushed
2. `2f8dbaa` — `feat: 闭环小红书作者权限查找 / close XHS creator authority lookup` — pushed
3. `docs: 收尾小红书作者权限闭环 / close XHS creator authority pipeline` — ready to commit/push; its SHA cannot be self-referenced

`.upstream` remains excluded and both pinned checkouts remain clean.
