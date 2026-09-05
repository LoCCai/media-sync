**English** | [中文](progress.zh.md)

# Execution 0054 Phase B progress

- Status: Delivered and locally verified; live qualification remains `NOT_RUN`
- Date: 2026-09-05
- Baseline: `4945df1`
- Planning commit: `d7e14c9`
- Implementation/verification commits: `b4af46d`, `ff5da07`, `88f5ed0`, `22bd9ef`, `48ecbe9`, `d8bbdf7`
- Database revision: unchanged at `0007_media_server_operations`

## Baseline

Phase B starts from the published Execution 0054-A closeout at `4945df1`. Before this planning package, the worktree had no tracked changes and contained only the pre-existing untracked `.mimosa/` directory. That directory is outside project scope and remains excluded.

The baseline already implements the managed-tree inspector, immutable server profile, hardened connector, accepted-only targeted refresh, two media-server Operation kinds, qualification schema v1, and Library/Settings/Jobs integration. At this historical boundary, provider/path item lookup and post-refresh item observation remain explicitly `NOT_IMPLEMENTED`; Phase B now implements both capabilities and upgrades qualification to schema v2.

## Frozen design

The Phase-B review checked the official Emby 4.8.10/4.9.5 and Jellyfin 10.10.7/10.11.11 API descriptions plus Jellyfin's queued item-refresh controller. No common durable task identity is returned by targeted refresh. Scheduled Tasks, WebSocket messages, server idle state, timestamps, and Etag changes cannot correlate a provider task to the request.

The frozen implementable claim is therefore `post_refresh_item_observation`: a complete absent baseline, one accepted refresh, and two consecutive observations of the same unique provider/path item. `provider_task_completion` stays unimplemented with an explicit provider-API limitation.

The design also freezes:

- provider-specific lookup and refresh query templates;
- full local provider/path equality and uniqueness;
- incomplete-versus-not-found truth;
- per-response, per-pass, and per-Operation budgets;
- all-answer DNS policy, pinning, Host/SNI, no proxy/redirect/next-link, and header-only credential flow;
- query-log constantization and raw-selector non-persistence;
- distinct acceptance-unknown and completion-unknown states;
- pre-dispatch failure for an already-matched author baseline, with legacy `{}` retained for acceptance-only refresh;
- targetless legacy `{}` Operations versus `target_type=author` observation Operations, with the publication Job atomically attached as a `related` subject before worker start;
- phase-aware cancellation, final CAS, and conservative restart handling, with accepted and observed running checkpoints stored in the existing `result_summary` and projected through the reused `operation_phase_changed` Event;
- database exclusivity only for durable probe and scan Operations; synchronous direct lookup is an independent snapshot bounded only by the connector's process-local gate;
- no new Operation kind, Event kind, or database migration because revision `0007` already provides the required target, subject, result, and Event vocabulary.

## Compatibility decision

The existing `POST /api/v1/media-server/scan` request `{}` remains acceptance-only and targetless and keeps the exact 0054-A safe result and `{profile_fingerprint}` request-fingerprint parameters. The same route gains a strict author object for observation mode. A matched baseline ends that mode before POST; acceptance-only refresh remains an explicit legacy request. This avoids silently changing old clients, idempotency replays, existing Operation rows, or the top-level manual refresh action.

The author mode uses the same `media-server-scan` kind with `target_type=author` and `target_id=<author UUID>`. The existing target relation links that author, and the publication Job is attached as a `related` subject before worker start. The target plus `{profile_fingerprint, mode=post_refresh_item_observation, publication_fingerprint}` form its request fingerprint without redefining historical targetless rows. The synchronous author lookup creates no Operation, has no database-exclusive key or cross-process correlation, and cannot itself serve as correlated scan evidence.

No migration is needed: the current `0007` schema already permits the author target, author/Job subjects and target/related roles, the `result_summary` checkpoint field, and the `operation_phase_changed` Event code. Phase B adds no database kind, state, Event kind, subject type, role, table, column, or constraint value.

## Work status

Delivered after the planning baseline:

1. `d7e14c9` records the bilingual frozen Phase-B plan separately, preserves the legacy `{}` acceptance-only contract, and rules out every inference from provider-global state to task completion.
2. `b4af46d` delivers the publication-target resolver, strict-manifest authority, Emby filtered lookup, Jellyfin bounded complete pagination, and the synchronous author item-lookup API. Only a complete zero-match pass returns `not_found`; only one exact provider/path match returns `matched`.
3. `ff5da07` adds lease/revision-fenced accepted and observed running checkpoints in existing `result_summary`, then closes cancellation/final CAS and phase-aware restart reconciliation without adding a table, column, Event kind, or Alembic revision.
4. `88f5ed0` delivers author post-refresh observation and its API: a complete absent baseline, at most one POST, a durable accepted checkpoint after trusted 2xx, and an observed checkpoint only after two separated observations of the same unique item. A matched baseline fails before dispatch; inability to prove observation after acceptance preserves accepted evidence and finishes completion-unknown.
5. `22bd9ef` upgrades qualification to schema version 2 and establishes server-side Library authorization for `refresh_and_verify`. `item_lookup` and `post_refresh_item_observation` become `IMPLEMENTED` but receive no live PASS.
6. `48ecbe9` completes the Library and Jobs Web surfaces: strict `{}` is separate from strict `{"author_id":"<uuid>"}`, accepted/observed/acceptance-unknown/completion-unknown remain distinct, and author observation shows verification counts without inventing a provider percentage, playback, or remote task completion.
7. `d8bbdf7` adds an opt-in real-PostgreSQL two-connection race suite and hardens ordinary cancellation plus coordinator shutdown with authoritative locked reads before cancellation writes. Accepted/observed checkpoints, both cancel/final orderings, shutdown, coordinator fallback, lease loss, and duplicate finalization now have 11 non-skipped PostgreSQL cases that prove actual lock contention through `pg_stat_activity.wait_event_type='Lock'`.
8. API, SQLite, Events, SSE, Web, logs, and support bundles continue to expose only fixed states and allowlisted summaries; raw server paths, provider values, item IDs, Etags, response bodies, and remote error text have no retained or returned representation.

The frozen local gate, with real PostgreSQL enabled, passes 2,763 Python tests with 3 Windows-inapplicable skips and one existing Starlette/httpx deprecation warning in 544.08 seconds. Ruff, Python format across 219 files, strict mypy across 103 source files, compileall, package build, lock consistency, and locked-upstream checks pass. From `web/`, the final Web gate ran `pnpm test`, `pnpm format:check`, `pnpm check`, and `pnpm build` in that order: 69 tests passed, formatting passed, Svelte check reported 0 errors and 0 warnings, and the production build passed. An earlier production build alone failed because it ran concurrently with other Web commands that contended for shared `.svelte-kit` intermediate artifacts; after concurrent execution stopped, every gate passed in the clean serial rerun. The diagnostic build failure is retained in the verification record rather than hidden. No separate Phase-B browser smoke was run, so this closeout does not claim browser-interaction evidence.

The first PostgreSQL development diagnostic had 10 cases: 7 passed and 3 failed. The failures showed that ordinary cancellation and `shutdown()` read a stale revision before waiting on the competing row lock. Re-reading the authoritative row with `require_for_update()` before each cancellation write closed both windows; the expanded final matrix passed 11/11. The fixture creates only the four production Operation/Event/Subject/StreamState metadata tables in an isolated PostgreSQL schema. It does not claim complete application-schema compatibility or production PostgreSQL deployment support; SQLite remains the supported default.

## Qualification state

Qualification schema version 2 now reports:

- `connection_probe`, `library_discovery`, `targeted_scan_acceptance`, `item_lookup`, and `post_refresh_item_observation`: implementation `IMPLEMENTED`, human `NOT_RUN`.
- `provider_task_completion`: `NOT_IMPLEMENTED`, reason `provider_api_unsupported`, human status null.
- `playback_evidence` and `automatic_post_export_scan`: `NOT_IMPLEMENTED`, human status null.

No authorized real Emby or Jellyfin server was used. Local and mocked implementation evidence therefore does not create a human PASS.

## Workspace discipline

All Phase-B commits exclude the pre-existing `.mimosa/` directory. Runtime data, secrets, databases, archives, export/job trees, build output, caches, and reports remain excluded. The closeout repository gate passed for 490 Markdown files, both locked upstreams, 787 tracked files with no forbidden generated/runtime output, no workstation-path/private-key/assigned-secret match in the intended diff, and clean whitespace; the frozen Phase-B goal and plan remain byte-for-byte unchanged. All seven Phase-B commits—one planning commit plus six implementation/verification commits through `d8bbdf7`—are published on `origin/main`; this closeout record intentionally does not embed the SHA of its own containing commit.

After implementation, rollback to an old binary must not occur while an author-observation Operation is active. Operators must wait until every such row is terminal or deploy a binary with compatible reconciliation; audit rows and accepted/observed evidence must never be deleted to make rollback appear compatible.

## Next checkpoint

Phase B has no remaining implementation item. An authorized real-server run may later qualify lookup and observation under execution 0047, but is not required to prove the local implementation. Provider task completion, playback evidence, and automatic post-export scanning remain future capabilities and are not silently inferred from accepted or observed state.
