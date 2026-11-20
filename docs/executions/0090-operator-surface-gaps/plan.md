**English** | [中文](plan.zh.md)

# Plan: surface the operator-visible gaps 0088 left behind

Status: **executed.**

## 1. Continuation delays: make the comparison complete

`/api/v1/settings` and `doctor --deep` are the two surfaces an operator diffs
against the supervisor environment. Both now report all seven delay fields, and
the Web `Settings` type declares them so the console cannot silently drop one.

The test that pins this is an enumeration, not a sample: it asserts every
platform's delay rather than the two that happened to exist when the assertion was
written.

## 2. Dashboard: keep the number, fix the claim

The KPI cards keep reading the same bounded arrays — adding server-side aggregate
endpoints would be a new API surface and is out of scope — but the labels now say
which window each number comes from (`最近 12 条任务中的…`, `最近 200 个资产中的…`).
For accounts and subscriptions the arrays *are* complete, so those two say 全量.
That difference is the whole point: an operator must be able to tell which of the
four numbers answers "how many".

## 3. Jobs table: name the outcome

A single `operationResultLabel(operation)` helper derives a short, closed label
from the already-whitelisted `safeOperationResult` projection. It never reads raw
`operation.result`, so the Jobs page keeps its existing guarantee that unknown
remote fields are discarded.

## 4. Pin each change with a test

- The API assertion enumerates all seven delays.
- Three new front-end cases cover the label helper: asset-download
  verified/exported/empty, export re-export vs fresh, and the login auth status.
- The Web test count must go up by exactly those cases; a change that adds no
  assertion is an unverified change.

## 5. Verify and record

Full Web gate set plus Ruff, `ruff format --check`, strict mypy and
`check_docs.py`. Exact counts go in [verification.md](verification.md).
