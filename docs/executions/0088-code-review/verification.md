**English** | [中文](verification.zh.md)

# Verification: independent six-discipline code review

## Method

Six read-only reviewers audited the tree at `830b4d0` in parallel, each with a
disjoint scope: the durable creator state machines (0084–0086), the migrations
and ingestion boundary, the media download/network layer, the API/CLI operator
contracts, the Svelte console, and secrets/privacy. Each reviewer was told to
verify by reading production code and running targeted probes, to report only
confirmed findings, and to separate "verified defect" from "could not confirm".

Every finding below was re-verified in this session before code was changed. Two
reviewer claims were rejected after verification and are listed as such.

## Final gates after the fixes

| Gate | Result |
| --- | --- |
| Complete Python suite | `7331 passed, 62 skipped, 108 warnings in 1817.38s` |
| Ruff lint / format | `All checks passed!`; `466 files already formatted` |
| Strict mypy | `Success: no issues found in 182 source files` |
| Documentation links | `Documentation links OK (866 Markdown files checked)` |
| Pinned upstreams | `Upstreams OK (2 locked checkouts verified)` |
| Web `svelte-check` | `0 errors and 0 warnings` |
| Web `vitest` | `846 passed (846)` — up from 843, three new platform cases |
| Web Prettier / build | clean; `✓ built in 11.73s` |
| `git diff --check` | exit 0 |

## Fixed defects

### Functional — 0085/0086 could not complete a single unit

1. **Zhihu page-tail replay aborted the whole unit.** The shim walked
   `for content in contents` positionally. After a unit stopped mid-page it keeps
   the identical offset, so replay re-offered already-delivered answers and the
   unit rejected them as contract drift — persisting rows but sealing no witness.
   Now driven by `unit.next_action()`. Regression test
   `test_partial_page_replays_only_the_missing_answer` fails without the fix.
2. **Tieba/Zhihu invoked the upstream store callback.** Upstream passes
   `batch_update_tieba_notes` / `batch_update_zhihu_contents`, whose entire body
   re-runs the guarded store; the second write ran with the identity ContextVar
   reset and raised. The shim already persists every item, so the callback stays
   deliberately uninvoked (documented inline). Two regression tests pin it.
3. **`NormalizedMediaCrawlerOutput` dropped `tieba_coverage` / `zhihu_coverage`.**
   They were parsed and validated, then discarded, so the handler's
   `(manifest_scan is None) != (output_coverage is None)` check always failed and
   every 0085/0086 run died as `output_security_failed`.
4. **Pipeline worker never published Zhihu progress.** `zhihu_delivery_policy` was
   constructed but `ZhihuDeliveryProgressRepository` was never called, so the row
   stayed `backfill` forever. Added both transitions plus
   `tests/unit/test_pipeline_worker_wiring.py`, which enumerates all seven
   platforms and fails if any publisher is missing.

### Functional — the durable chain could never advance

5. **`source_run_id` was passed for only Bili-uploads and XHS.** Without it the
   delivery receipt stays schema 1, and all seven `publish_success`
   implementations return `None` on a schema-1 receipt — so every
   Weibo/Tieba/Zhihu (and Douyin/Kuaishou) progress row was created and never
   advanced. Now derived for every bounded creator platform.
6. **Weibo counted a non-advancing page as consumed.** `pages_consumed` was
   incremented before the stall test, so the arithmetic `total` mirror could
   report a **false source end** built from a replayed page and move the row into
   `incremental` while most of the history was unfetched.
7. **Tieba advanced past a stalled page.** `page + 1` on a repeated page dropped
   that page's threads permanently, and the next good page reset the stall
   counter, hiding the loss. The page number now stays put and the bounded stall
   counter blocks instead.
8. **Tieba accepted an empty page with `has_more=1` as a source end.** That shape
   is what a rate-limited envelope parses to; it published an **empty head
   boundary**, which reconciles equal to anything and let the row enter
   incremental with the whole backlog unfetched. It is now a bounded stall, and an
   empty page no longer establishes a head boundary on any of the three platforms.
9. **Zhihu treated any partial window overlap as a stall.** Because `offset` is a
   page\*limit product, one new answer legitimately repeats the previous page's
   tail; treating that as a stall wedged the subscription permanently on the first
   new answer. Partial overlap is now normal drift that advances; only an
   identical page stalls.
10. **Zhihu raised on an empty-but-not-ended body.** A rate-limited `data: []`
    became a hard upstream fault with no witness; it is now a bounded stall.

### Correctness at the ingestion boundary

11. **`_record_run_contents` applied Bili's 30-record cap to every platform.** The
    three new bounded ingests declare 1000, so any Weibo page above 30 notes
    aborted ingestion and retried forever. The cap is now a required `limit`
    argument supplied per call site.
12. **Weibo's `declared_total` was looser than the durable column.** Values above
    2⁵³−1 passed the scan layer and then failed the CHECK inside the pipeline
    transaction, turning a completed unit into an endless retry. Both the witness
    and the summary now bound it, matching the column.

### Security

13. **`secure_delete=ON` did not cover the WAL sidecar.** Verified: after an
    abrupt process exit the sentinel was readable in `crash.sqlite3-wal` while the
    main file was clean. `checkpoint_sqlite_wal()` now runs after
    `upgrade_database`, with a regression test that proves the sentinel disappears
    from the sidecar.
14. **A caller-injected Alembic connection migrated with no pragmas.** A raw
    `Connection` from a plain `create_engine()` ran 0003's rebuild with
    `secure_delete=OFF`. `env.py` now applies the pragmas through the raw DBAPI
    cursor (not `exec_driver_sql`, which would autobegin and break Alembic).
15. **`db status` used a plain `create_engine`.** It was the one engine without the
    managed pragmas; it now uses `create_database_engine`.
16. **ffprobe/ffmpeg children inherited the whole environment.** Since `Settings`
    resolves `env:` secret references from `os.environ`, every probe/mux child got
    the platform Cookie and the media-server API key. Both now run under
    `media_child_environment()`, an allowlist.

### Frontend

17. **The native QR panel could never display a QR.** `nativeQrRead` requests
    `/crawler/api/crawler/qrcode`, which `sessionRequest` rejected before `fetch`
    because it only allowed `/api/`. The panel then blamed the platform and told
    every user to paste cookies instead. The read-only relay prefix is now allowed
    and the in-flight poll is aborted on `dispose()`.
18. **Kuaishou's panel degraded to "证据不可用" exactly when it had evidence.**
    It reused Douyin's stop-reason set, which lacks `no_more_echoed`. Stop reasons
    are now per-platform, and an unknown label falls back to the raw code rather
    than blanking.
19. **Weibo/Tieba/Zhihu had no delivery-baseline panel** although the API already
    sent all three payloads. Types, card specs (including the platform-specific
    `declared_total` / `last_page_number` / `last_offset` field and stop reasons)
    and panel branches were added.
20. **Exported diagnostic reports claimed schema drift on a healthy install.** The
    frontend revision list stopped at `0011_cookie_login`, so both revisions were
    nulled and `revision_matches` forced false. It now matches the backend set
    through `0020_zhihu_creator_answers`, verified equal by a set comparison.
21. **Dashboard reported one failing endpoint as a service-connection failure.**
    All nine requests were in one `Promise.all` that also cleared `healthOk`; one
    503 discarded the other eight. They are now independent (`allSettled`) and
    `healthOk` derives only from `/health`. The 30-second refresh no longer blanks
    the counters.
22. **Missing error copy leaked snake_case.** Added the codes the API emits
    (`operation_state_conflict`, `database_not_ready`, `log_cursor_stale`,
    `login_qr_gone`, …) and a `try/catch` around the clipboard copy.

### Operator contract

23. **Continuation policies were missing at 9 of 9 construction sites.** The
    WebUI's Tieba/Zhihu flows never materialized a progress row at all, and the
    pipeline publishers computed their binding with `upstream_sha=None`. All seven
    policies are now threaded through `api.py` (5 sites) and `cli.py` (4 sites),
    with `WeiboScanContinuationPolicy` imported where it was missing.
24. **Two `_KNOWN_DATABASE_REVISIONS` entries were file names, not revision ids.**
    A database at `0001_core`/`0002_checkpoint` reported `revision: null`. Fixed,
    with a lockstep test that parses each migration's real `revision` string.
25. **The "exactly one bounded contract" guards covered only four platforms** (both
    the output-consistency tuple and the sealed-recovery policy↔manifest pairs).
    Extended to all seven.
26. **`models.__all__` omitted the three new progress classes** and their
    vocabularies.

## Rejected after verification

- *"Every exported diagnostic report is wrong"* was partly overstated: the
  revision list was genuinely stale (fixed), but the report parser itself was
  already correct.
- *"Zhihu's `stalled_units` is dead code"*: after the shift-semantics fix the
  counter is now the only blocking path for Zhihu, so the finding no longer
  applies as written.

## Reported, not changed

- **Douyin `bit_rate` is capped at 8 entries**, so a realistic 10–16 entry payload
  silently falls back to the pinned flattening instead of using 0083's ranking.
  Raising the cap changes 0083's frozen behaviour, so it needs its own execution.
- **`validate_ks_image_url` has no CDN host allowlist; `validate_xhs_video_url`
  accepts plaintext `http`.** Both are 0081/0076 behaviour, outside this review's
  change scope; each deserves a dedicated execution with its own upstream facts.
- **Animated GIF/WebP is accepted as a static IMAGE on five platforms** (only
  Tieba/Zhihu require static). Same reasoning.
- **`DEFAULT` request profile still sends httpx's `User-Agent`**, so the docs'
  "no User-Agent at all" wording is inaccurate. Documentation-only.

## Commands run

```text
python -m pytest -q
python -m ruff check src tests
python -m ruff format --check src tests
python -m mypy --strict src
python scripts/check_docs.py
python scripts/check_upstreams.py
npm --prefix web run check | test | format:check | build
git diff --check
```
