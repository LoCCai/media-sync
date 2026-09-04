**English** | [中文](verification.zh.md)

# Execution 0054 Phase B verification

- Status: Planning baseline only; implementation verification not run
- Date: 2026-09-05
- Baseline: `4945df1`
- Planned database revision: none; Alembic remains at `0007`

## Verification policy

This file separates planning evidence, future automated implementation evidence, and future human qualification. A documentation check proves only that this startup package is structurally valid. It does not prove lookup, polling, real-server compatibility, remote completion, or playback.

No official API response may be interpreted more strongly than its contract. A refresh 200/204 proves acceptance only. A complete exact item lookup proves an observation only. Mocked provider tests prove implementation behavior only. Only an authorized real-server run may change a human status from `NOT_RUN`.

## Baseline evidence

| Check | Command or source | Status |
| --- | --- | --- |
| Git baseline | `git rev-parse HEAD` | `PASS` — `4945df1969d4f4b8f2dd8c8da972b6183798f671` before planning edits |
| Initial tracked worktree | `git status --short` | `PASS` — no tracked changes; only pre-existing untracked `.mimosa/` |
| Pre-change focused tests | `uv run --frozen pytest -q -p no:cacheprovider tests/unit/test_media_server_connector.py tests/unit/test_media_server_application.py tests/unit/test_api_media_server.py tests/unit/test_operation_payloads.py tests/integration/test_operation_repository.py tests/integration/test_operation_coordinator.py` | `PASS` — 218 passed, 1 warning in 10.06s; the warning is the existing Starlette/httpx deprecation |
| Official route review | Four versioned OpenAPI documents and Jellyfin 10.10.7 controller linked from the goal | `PASS` — no targeted-refresh task ID; provider route differences recorded |
| Documentation structure | `uv run --frozen python scripts/check_docs.py` | `PASS` — documentation links OK for 490 Markdown files |
| Document set | Exact filename/count audit of `phase-b/` | `PASS` — exactly the eight expected Markdown files |
| Patch whitespace | Direct trailing-whitespace/final-newline audit of all eight untracked files, plus `git diff --check -- docs/executions/0054-media-library-server-integration/phase-b` | `PASS` — no trailing whitespace, every file ends with a newline, and the tracked diff check is clean |
| Scope audit | `git status --short --untracked-files=all -- docs/executions/0054-media-library-server-integration/phase-b` and full status excluding `.mimosa/` | `PASS` — only the eight intended Phase-B files appear; parent 0054 documents and the execution index are unchanged |

The pre-existing `.mimosa/` directory is excluded from every command that selects deliverable files and from any future commit.

## Contract evidence map

| Frozen requirement | Planned evidence |
| --- | --- |
| Honest capability name | Qualification and UI assert `post_refresh_item_observation`; `provider_task_completion` stays unsupported |
| Backward-compatible scan | Exact tests keep the legacy empty-object `{}` Operation targetless and preserve its accepted-only result plus golden `{profile_fingerprint}` request fingerprint |
| Observation identity | Author mode uses `target_type=author`, `target_id=<author UUID>`, the existing author target relation, and an atomic pre-worker publication Job `related` subject |
| Local authority | Current complete publication head/manifest tests; no caller remote selector; pre-POST revalidation |
| Exact lookup | Full provider/path dual-match truth table and complete uniqueness requirement |
| Emby/Jellyfin differences | Four-version request snapshots and forbidden-parameter/fallback assertions |
| Bounded work | Per-response, pass, Operation, page, item, byte, JSON, poll, and deadline exhaustion tests |
| Mutation truth | Matched baseline sends no POST; otherwise at most one POST, acceptance unknown versus completion unknown, and accepted/observed checkpoints use existing `result_summary` plus reused `operation_phase_changed` without a new Event kind |
| Cancellation and restart | Explicit accepted/cancel, observed/cancel/final, coordinator-fallback, transport-entry, phase-based reconcile, and lease/final/checkpoint CAS races |
| Concurrency boundary | Database profile exclusivity covers durable probe and scan Operations only; direct GET is an independent bounded snapshot with only process-local connector gating and no correlated-evidence claim |
| Migration and rollback | Alembic stays at `0007` with no new database vocabulary; an old binary cannot take over an active author observation |
| Confidentiality | Raw and encoded selector sentinels absent from logs, DB, Events, SSE, API, support bundle, and Web |
| Qualification truth | Automated, implementation, and human states remain independent |

## Planned automated matrix

1. Emby 4.8.10 and 4.9.5 use filtered `GET /Items`, locally validate every candidate, send documented recursive refresh, and accept documented 200.
2. Jellyfin 10.10.7 and 10.11.11 use bounded Library pagination without Path/AnyProviderIdEquals, send no refresh Recursive parameter, and accept documented 204.
3. No code calls a direct Emby item GET, `/ScheduledTasks`, WebSocket completion, global `/Library/Refresh`, a server-provided next link, or a second mutation attempt.
4. Complete zero match is `not_found`; complete one exact identity is `matched`; multiple identities are ambiguous; partial, drifting, duplicate, malformed, or exhausted traversal is incomplete.
5. Only absent baseline plus accepted POST plus the same unique item in two separated observations succeeds. Existing baseline ends pre-dispatch with `media_server_scan_observation_precondition_failed`; every Etag transition fails to prove completion.
6. The legacy empty-object `{}` scan remains targetless and succeeded/accepted and preserves both its exact result and golden `{profile_fingerprint}` request fingerprint. Author mode uses `target_type=author` and the author UUID, the existing target relation, and an atomically attached publication Job `related` subject before the worker starts.
7. Accepted and observed running checkpoints write the existing `result_summary` and emit only the existing `operation_phase_changed`; no new Event kind is introduced. Every later completion-unknown or coordinator fallback retains accepted evidence and never replaces its summary with `{}`.
8. The authoritative-lock race matrix proves that, after trusted 2xx is known, cancel-first versus accepted-checkpoint and accepted-first versus cancel both preserve acceptance; cancel-first versus observed-checkpoint blocks observed and ends completion unknown; observed-first versus cancel or finalization preserves observed success; and coordinator exception/finalization keeps accepted evidence non-retryable. Pre-entry cancellation sends zero POST, while entry-first timeout/reset/5xx/redirect/cleanup ambiguity sends at most one POST and ends acceptance unknown.
9. Same idempotency key and same identity replay one Operation; mode/author/profile/publication changes conflict. Profile exclusivity serializes durable probe, legacy scan, and author-observation scan Operations only. Direct GET remains bounded and independent, uses only the connector's process-local gate, has no database exclusivity, and is not scan-correlated evidence.
10. Every page repeats all-answer DNS/CIDR validation and pinning. Mixed answers, rebinding, Host/SNI drift, proxies, redirects, next links, non-header credentials, and route/query override attempts fail closed.
11. Raw path/provider/item/Etag/token and percent-encoded variants are absent from every retained or returned sink even when remote responses and exceptions contain them.
12. SQLite and a real PostgreSQL service verify phase-aware restart: `preparing`/`baselining` is pre-dispatch interrupted, `dispatching` is terminal acceptance unknown, `accepted`/`polling` is terminal completion unknown with its checkpoint, `observed` succeeds only with a valid observed checkpoint, and legacy targetless `{}` behavior is unchanged. Lost-lease and duplicate-final races still yield one terminal Event.
13. Migration-compatibility tests keep Alembic at `0007` and prove that Phase B adds no database kind, state, Event kind, subject type, role, table, column, or constraint value while using the already-valid author target, author/Job subjects, `result_summary`, and `operation_phase_changed`.
14. Web unit and browser tests cover both actions, author gating, SSE reconnect, request generations, truthful labels, no fake percentage, no raw selector, and unknown-state recovery guidance.
15. Deployment rollback checks and documentation prohibit an older binary from taking over an active author-observation Operation; rollback waits for those rows to become terminal or deploys a reconciliation-compatible binary, without deleting audit evidence.

Focused selections must be recorded without summing overlapping tests. Final verification also includes complete Python/Web suites, lint, format, strict typing, build/distribution, documentation, upstream, generated-output, host-path, secret-pattern, and whitespace gates.

## Live qualification

There is no real Emby/Jellyfin origin, Library, or credential in this workspace. At startup:

- current implemented connection, discovery, and targeted-acceptance capabilities remain human `NOT_RUN`;
- Phase-B lookup and observation remain implementation `NOT_IMPLEMENTED` until code lands;
- after code lands, they become implementation `IMPLEMENTED` but remain human `NOT_RUN` until an authorized operator run;
- provider task completion remains `NOT_IMPLEMENTED`, not `NOT_RUN`;
- playback evidence and automatic post-export scan remain outside this phase.

## Exit gate

Phase B may close only when every frozen local/mocked requirement has exact passing evidence, no P0/P1/P2 review issue remains, the compatibility tests retain legacy `{}` scan behavior and old rows, and all tracked output is intentional. The closeout must continue to state that provider task completion and playback are unproven. A real-server run is optional external qualification and cannot be fabricated from mocks.
