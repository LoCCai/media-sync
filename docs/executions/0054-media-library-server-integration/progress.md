**English** | [中文](progress.zh.md)

# Execution 0054 progress

- Status: Phase A and Phase B delivered and locally verified; live qualification remains `NOT_RUN`
- Closeout date: 2026-09-05
- Baseline: `22b5864`
- Plan and hardening commits: `793d33b`, `d913537`
- Phase-A implementation commits: `554277c`, `efdb27c`, `2ad051c`, `1b34632`
- Phase-B planning and implementation/verification commits: `d7e14c9`; `b4af46d`, `ff5da07`, `88f5ed0`, `22bd9ef`, `48ecbe9`, `d8bbdf7`
- Database revision: `0007_media_server_operations`

## Delivered

Phase A:

1. Fetched `origin/main` before resuming. Local and remote `main` both resolved to `d913537`, so there was no incoming change to merge and the preserved implementation worktree was not overwritten.
2. Added author-UUID managed-tree inspection authorized by the successful database publication chain plus the strict manifest. It uses existing-only locks, process single-flight, manifest-bound HMAC cursors, 128-file pages, byte/deadline budgets and independent freshness/integrity states without exposing host paths or unmanaged names.
3. Hardened filesystem identity across platforms: POSIX uses stable directory descriptors and `O_NOFOLLOW`; Windows holds handles without delete sharing. Manifest and managed files require descriptor/name identity plus a single-link invariant, and a non-zero final page no longer upgrades partial work to whole-tree `complete`.
4. Added one all-or-none environment-owned Emby/Jellyfin profile with a safe summary and default-off operation gate. Validation canonicalizes the origin/network policy and hides rejected configuration input.
5. Added a provider-neutral connector with all-answer DNS/CIDR enforcement, pinned connection IP, preserved Host/TLS SNI, disabled proxies and redirects, fixed probe/targeted-refresh routes, absolute deadline and connector single-flight. The API key is resolved only at the request boundary; dynamic `httpx`/`httpcore.*` logs are request-scoped redacted and the prior LogRecord factory is restored.
6. Added durable `media-server-probe` and `media-server-scan` Operations plus revision `0007`. Probe and scan share one profile-exclusive domain. Scan never falls back to `/Library/Refresh`; cancellation can win only before dispatch, while post-dispatch timeout, cancellation, disconnect, cleanup or response ambiguity becomes terminal non-retryable `media_server_scan_acceptance_unknown`.
7. Linearized final scan persistence with cancellation. The authoritative final read reserves the SQLite writer and compiles to PostgreSQL `SELECT ... FOR UPDATE`: cancel-first becomes acceptance-unknown, while final-lock-first preserves success and a later cancel cannot rewrite it. Restart reconciliation remains conservative `interrupted`, and scan interruption is not retryable.
8. Added `GET /api/v1/library/{author_id}`, `GET /api/v1/media-server`, `POST /api/v1/media-server/probe`, `POST /api/v1/media-server/scan` and `GET /api/v1/qualifications`. Status and evidence are scoped to the current profile and use closed, allowlisted payloads.
9. Upgraded Library, Settings and Jobs for paged media-tree inspection, redacted configuration, qualification evidence and durable probe/scan activity. Request generations prevent late responses from overwriting current state; Settings has independent failure domains; Jobs skips a poll while its previous request is still active.
10. Updated deployment, architecture, operations, security and capability documentation. The Phase-A browser smoke covered Library, Settings and Jobs with the server unconfigured, disabled probe/scan controls, accurate `NOT_RUN`/`NOT_IMPLEMENTED` labels and 422 rejection of request-body target overrides.

Phase B:

1. Added a publication-target resolver that authorizes only the current unique successful publication head and complete strict manifest, then derives the exact server provider/path selector without exposing it.
2. Added bounded exact item lookup: Emby uses its documented filters and Jellyfin uses complete bounded pagination; both apply local provider/path equality and uniqueness checks. Incomplete work never becomes `not_found`.
3. Added accepted/observed running checkpoints under lease/revision fencing, closed cancel/final races, and conservative phase-aware restart reconciliation without changing Alembic revision `0007` or adding an Event kind.
4. Preserved legacy `POST /api/v1/media-server/scan {}` as targetless and acceptance-only. Author mode accepts only `{"author_id":"<uuid>"}`, requires an absent baseline, sends at most one provider-specific refresh, preserves accepted evidence, and succeeds only after the same unique item is observed twice with a positive interval.
5. Added the safe author item-lookup API and qualification schema version 2. `item_lookup` and `post_refresh_item_observation` are implementation `IMPLEMENTED` with human `NOT_RUN`; `provider_task_completion` stays `NOT_IMPLEMENTED` with reason `provider_api_unsupported`.
6. Updated Library and Jobs in `48ecbe9`: the header action still sends strict `{}`, author refresh-and-verify sends only the author UUID, lookup returns only allowlisted facts, observation progress has no percentage, and fixed messages keep acceptance, observation, provider completion, and playback separate.
7. Added the real-PostgreSQL Operation race gate in `d8bbdf7` and fixed ordinary cancellation plus shutdown to acquire an authoritative row lock before writing cancellation. Eleven non-skipped two-connection cases cover accepted/observed checkpoints, cancel/final ordering, shutdown, coordinator fallback, lease loss, and duplicate finalization with observed database lock waits.

## Phase A review hardening

Independent reviews found and closed pagination scope inflation, ancestor/manifest replacement races, configuration-error disclosure, reflected server fields, non-absolute timeouts, POST cancellation/cleanup ambiguity, stale-profile evidence, retryable restart scans, dynamically created logger leakage, abandoned worker growth, late Web response overwrite, coupled Settings failures and self-starving Jobs polling. A final cross-database review then found the cancellation/final-success window closed by the locked authoritative read above. Connector and CAS rechecks found no remaining P0/P1/P2 in the delivered phase-A scope.

The first complete-suite run exposed one order-dependent test-harness failure in dependency logger capture: `1 failed, 2617 passed, 3 skipped, 1 warning in 505.38s`. The sensitive values were still redacted. The test now saves, explicitly controls and exactly restores logger and global logging state; its focused rerun passed. After the final CAS hardening, the frozen complete suite passes `2620 passed, 3 skipped, 1 warning in 505.44s`.

## Verification

- Python: the historical Phase-A complete suite passed 2620 tests. With the isolated real PostgreSQL service enabled, the Phase-B frozen suite now passes `2763 passed, 3 skipped, 1 warning in 544.08s`, including all 11 PostgreSQL race cases; Ruff, format across 219 files, strict mypy across 103 source files, compileall, lock consistency, wheel and sdist build all pass. An initial 10-case PostgreSQL diagnostic had 7 PASS/3 FAIL because ordinary cancel and shutdown read a stale revision before lock waiting; authoritative `require_for_update()` reads closed both windows before the final 11/11 run.
- Web: the historical Phase-A gate passed 58 tests. From `web/`, Phase B passes `pnpm test` (69 tests), `pnpm format:check`, `pnpm check` (0 errors and 0 warnings), and `pnpm build`. In the first concurrent attempt, only the production build failed because it competed with other Web commands for `.svelte-kit` intermediates; all four commands then passed serially. No separate Phase-B browser smoke was run.
- Repositories: 490 Markdown files and both locked upstream checkouts pass; 787 tracked files contain no forbidden generated/runtime output. The intended diff has no workstation-path, private-key or assigned-secret match and passes `git diff --check`. The frozen Phase-B goal/plan remain unchanged, and `.mimosa/` remains untracked and excluded. The PostgreSQL fixture creates only the four production Operation/Event/Subject/StreamState metadata tables in an isolated schema; SQLite remains the supported default and full-schema PostgreSQL deployment is not claimed.
- Git: Phase-B commits through `d8bbdf7` are pushed to `origin/main`; the closeout documentation commit is the commit containing this record and intentionally does not embed its own SHA.

## Remaining and external gates

Execution 0054 has no remaining local implementation work. Live use of the implemented connection probe, Library discovery, targeted-refresh acceptance, item lookup, and post-refresh item observation remains `NOT_RUN` under execution 0047. Provider task completion is `NOT_IMPLEMENTED` because the common APIs return no durable correlated task identity. Playback-evidence mutation, browser-writable settings, multiple profiles, authentication, and destructive/retention administration remain 0055. Automatic post-export scanning is `NOT_IMPLEMENTED` and has no frozen follow-up assignment. Every seven-platform live-account, creator, incremental, CDN, and Linux persistence/recovery row also remains `NOT_RUN`.
