**English** | [中文](plan.zh.md)

# Plan: independent six-discipline code review

Status: **executed.** Six read-only reviewers ran in parallel; every finding was
re-verified before any code changed.

## 1. Freeze a baseline

Confirm the tree is clean at `830b4d0` and the pre-existing gates pass, so a later
failure is attributable to a fix rather than to the starting state.

## 2. Fan out with disjoint scopes

Six reviewers, one scope each (see [goal.md](goal.md)), all instructed to prove
findings by reading production code and running targeted probes, and to report
"verified" separately from "could not confirm".

The critical instruction is the negative one: **do not trust the previous
closeouts.** 0085/0086's delivery tests drive the repositories directly, which is
precisely how a missing publisher or a dropped coverage field can survive a green
suite.

## 3. Re-verify every finding before changing code

For each claim: read the cited code, reproduce the failure with a probe or a
focused test, and only then decide. Two claims were rejected at this stage, so
the record stays honest about what was actually wrong.

## 4. Fix in dependency order

1. **State machines first** (Weibo stall accounting, Tieba page skip and empty
   page, Zhihu replay and shift semantics, Weibo `declared_total` bound), because
   the capture shims and the delivery transitions are written against them.
2. **Capture shims** (Zhihu loop shape, Tieba/Zhihu callback, empty-page
   classification), against the corrected unit semantics.
3. **Production wiring** (coverage passthrough, Zhihu publisher, `source_run_id`,
   continuation policies at every construction site, guard tuples).
4. **Ingestion boundary** (per-platform record cap).
5. **Security** (`secure_delete` WAL coverage, injected-connection pragmas, managed
   engine for `db status`, narrowed media child environment).
6. **Frontend** last, because three of its findings depend on payload fields the
   backend had to start sending correctly.

## 5. Pin each fix with a failing-first test

Every functional fix gets a regression test that fails on the pre-fix code. For
the wiring fixes (Zhihu publisher, revision allowlist) the pin is an
enumeration-style test: it walks the set of platforms or migrations and fails when
one member is omitted, so the next platform cannot repeat the omission silently.

## 6. Re-run the full gate set

Complete Python suite, Ruff lint and format, strict mypy, documentation links,
pinned upstreams, and all four Web scripts. Record the exact counts.

## 7. Record honestly

Write [verification.md](verification.md) with three separate sections: fixed,
rejected after verification, and reported-but-not-fixed. The third section is
mandatory — a review that quietly drops the findings it did not act on is worse
than no review.

## 8. Out of scope

- Behaviour changes to 0076/0081/0083, which need their own executions.
- Any deployment, login or platform request.
