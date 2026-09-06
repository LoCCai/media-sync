**English** | [中文](verification.zh.md)

# Verification

Status: offline release gates passed on the frozen source; live/Linux/PostgreSQL qualification remains explicit below.

## Final evidence

- Final complete Python coverage was executed in three isolated groups and totals `6924 passed, 40 skipped` after removing one intentional eight-test helper overlap: unit `4604 passed, 3 skipped`, contract `1085 passed, 2 skipped`, integration `1235 passed, 35 skipped`. The raw unit command reported `4612 passed, 3 skipped in 511.42s` because it also collected the eight-test media-server helper; contract completed in 489.20s and integration in 422.79s. The only warning class was the existing Starlette/httpx deprecation. Skips are Windows/POSIX or unavailable real-PostgreSQL conditions.
- The earlier exact-delivery race/recovery review suite passed `255` tests. After final review found the stale supervisor-lease gap, the corrected source additionally passed all 17 subscription-delivery API tests and a 14-test lease-focused selection. These overlapping selections cover both scheduler/pipeline enqueue orderings, supervisor ownership, `claimed`/`running` expiry reclaim, same-ID `retry_wait`, expired-Operation deferral, durable receipt recovery and no-second-chain assertions.
- Migration/database/package-resource selection: `52 passed`. SQLite authorized/refused downgrade cases and PostgreSQL statement ordering are covered; no real PostgreSQL URL was configured.
- The final stale-inventory correction selection passed `112` tests after updating SystemExit semantics, seven Cookie-capable platforms and the authenticated route inventory to 75.
- Web final gate passed 25 files / 781 tests; Prettier passed, Svelte reported 0 errors and 0 warnings, and the production build passed.
- Ruff lint passed; the final whole-repository Ruff format check reported 1101 files already formatted; strict mypy passed 149 source files; compileall passed; `uv lock --check` resolved 62 packages; both locked upstream checkouts passed; `git diff --check` passed.
- The post-fix wheel and sdist contain all 165 application Python files byte-identical to the workspace. Wheel: 172 members, SHA-256 `eaba763d84ce337027cd04cd6f0a6c7fcfad015b240e139a4c61f8e783e3a4cd`. Sdist: 1222 members, SHA-256 `bc073ab59a56f26ec114cbcedacb041b91f06144119a6e97a9827629d1cc1def`. Required migration/Mako resources are present; the precise member audit found no actual `.env`, database, private key, credential, runtime log/profile/output, build-cache, temporary, VCS/tool-state or link member. `.env.example` and eight versioned JSONL crawler fixtures are templates/test data, not runtime state.

## Failures retained, not relabelled

- Independent review found four recovery/duplicate-chain risks: an active pipeline owned by supervisor, the reciprocal pipeline-enqueue/materialize ordering, a direct `retry_wait` that prematurely terminalized the Operation, and an observer that only polled a crashed supervisor's stale `claimed`/`running` lease. Each was reproduced, fixed and covered; the last regression only succeeds when the same exact Job is retried and reclaimed after expiry.
- Full runs started while review edits were still landing were deliberately interrupted and are not release evidence. A later `-x` run found one stale browser-diagnostic assertion after 3219 passes; the next complete run found stale Cookie-capability and 74-route inventories after 6918 passes. After the final lease fix, a monolithic run was stopped at 3% solely to reduce wall time. The first isolated unit command then exposed two collection errors because cross-directory helper imports were omitted from that command; explicitly collecting the eight-test helper fixed the command. The three successful final groups above cover the full 6964-item collection with that overlap accounted for.
- The first package denylist pass reported the legitimate `web/src/routes/logs/+page.svelte` as suspicious because the rule matched any `logs` path. The rule was narrowed to package-root runtime directories and the complete audit then passed; no member was removed or ignored manually.

## Not run

- Current Linux/Docker image and real PostgreSQL transactions.
- Live QR login, creator crawl, CDN retrieval, production download/directory playback, Emby/Jellyfin refresh or supervisor recovery.
- No production state, credentials, subscriptions or media files were changed.
