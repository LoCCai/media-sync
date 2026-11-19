**English** | [中文](progress.zh.md)

# Progress: independent six-discipline code review

Status: implemented and verified locally. Nothing deployed, no live account or
platform request used.

## Result

The review found that 0085 and 0086 were **not** deliverable as shipped. Both had
green local suites, and both would have failed on the first real run:

- Tieba and Zhihu never completed a single bounded unit — the capture shims
  aborted before sealing their coverage witness (a positional replay loop and an
  upstream store callback), and `NormalizedMediaCrawlerOutput` silently dropped
  the two coverage payloads, so the handler rejected every run as
  `output_security_failed`.
- Even past that, no progress row could advance: the pipeline worker never
  published Zhihu progress, and no Weibo/Tieba/Zhihu receipt carried a
  `source_run_id`, so every publisher returned `None` on a schema-1 receipt.
- The WebUI could never reach the durable chain at all: nine of nine service
  construction sites omitted the new continuation policies, so the policies
  defaulted and no progress row was ever materialized.

This is exactly the class of defect a self-authored test suite cannot catch, which
is why the review was commissioned.

## Fixed

26 defects across six areas, each re-verified before the change and pinned by a
regression test:

- **Functional, blocking (4):** Zhihu positional replay; Tieba/Zhihu upstream
  callback double-store; dropped coverage passthrough; missing Zhihu publisher.
- **Functional, durable chain (6):** missing `source_run_id`; Weibo stall counted
  as a consumed page; Tieba advancing past a stall; Tieba empty-page-as-source-end;
  Zhihu partial-overlap blocking; Zhihu empty-body hard fault.
- **Ingestion boundary (2):** Bili's 30-record cap applied to every platform;
  Weibo `declared_total` outside the column bound.
- **Security (4):** `secure_delete` not covering the WAL sidecar; injected Alembic
  connections migrating without pragmas; `db status` on an unmanaged engine;
  ffprobe/ffmpeg inheriting the whole environment.
- **Frontend (6):** unreachable QR relay; Kuaishou stop-reason mismatch; missing
  Weibo/Tieba/Zhihu panels; stale revision allowlist; dashboard one-failure-kills-
  all; missing error copy and silent clipboard failure.
- **Operator contract (4):** continuation policies at every site; two revision ids
  that were file names; two guard tuples covering only four platforms; `models.__all__`.

## Rejected

Two reviewer claims did not survive re-verification and are recorded as such, so
the report does not overstate the findings.

## Reported but deliberately not fixed

Four findings are real but belong to frozen earlier executions (0076/0081/0083):
Douyin's 8-entry `bit_rate` cap silently disabling 0083's ranking, Kuaishou's
missing CDN allowlist, XHS accepting plaintext `http`, and animated images passing
as static on five platforms. Each needs its own execution that re-derives the
pinned upstream facts; changing them here would silently alter delivered
behaviour.

## Verification

`7331 passed, 62 skipped`; Web `846 passed` (three new platform cases);
Ruff, strict mypy over 182 files, documentation and upstream gates green;
`svelte-check` 0/0 and the Web build succeeds. Exact per-gate results are in
[verification.md](verification.md).
