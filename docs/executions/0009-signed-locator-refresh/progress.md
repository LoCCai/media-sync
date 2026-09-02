**English** | [中文](progress.zh.md)

# Execution 0009 progress

- Status: Function-first MVP implemented locally
- Started: 2026-08-30 20:38 +08:00
- Paused: 2026-08-31 00:06 +08:00
- Resumed: 2026-08-31 00:39 +08:00
- Implementation: `MVP COMPLETE; HARDENING DEFERRED`
- Verification: `PASSING OFFLINE FOCUSED GATES`
- Predecessor: Execution 0008 implementation commit `3889539`

## Planning baseline

- Execution 0008 closed only the offline cancellation/security evidence. Signed-locator refresh, successful/recovery terminal cleanup and real CDN traffic were still outside its implementation.
- Read-only data-flow review proved that the stable `adapter_refresh.asset_key` is one-way and Asset/Content has no Subscription/Account provenance. An author may have multiple account subscriptions, so choosing the first account would be unsafe.
- The frozen design adds many-to-many `asset_refresh_sources`. Eligibility uses semantic/locator fingerprints; generation stays a download fence only, so local archive reset does not destroy a valid source.
- Design audit found that locator-only replacement previously stayed in the same generation and conflicted with immutable Job source binding. The frozen repair advances generation for either persisted semantic or locator replacement, while a generation-only archive reset keeps matching provenance eligible.
- XHS refresh authority must come from the exact Subscription's creator secret, with strict author/token/source validation and a 4 x 30/120-second bound. The private result channel is a dedicated OS pipe/handle distinct from stdout/stderr, which are redirected before upstream import.
- Read-only handler review found four post-success gaps: fresh success keeps its root, recovered success loses the source path, already-succeeded restart returns before cleanup, and malformed result/readback errors after a real commit can still mark the succeeded Run failed. Recovered metadata and concurrent cleanup also require stronger identity/race checks.
- Pinned-upstream review found in-memory detail entry points before store/JSONL for all platforms. The current normalized Asset surface is only XHS image/video, Douyin image/video/audio/cover, Kuaishou video/cover and Bilibili cover; Weibo/Tieba/Zhihu have no Asset.
- At the planning baseline no implementation had run. A later local worktree checkpoint landed two partial slices only; no helper process, browser, platform account, CDN request, media-server operation or execution 0010 work has run.

## Pause checkpoint

The user requested a pause before execution 0009 acceptance. The following code is preserved in one local WIP commit as incomplete work, not as delivered capability. The manual signed-locator path is still unavailable and the CLI still returns `locator_refresh_unsupported`.

### Partial code landed

- Added `AssetRefreshSource` ORM relationships, composite identity, constraints and indexes, plus migration `0005_asset_refresh_sources` with conservative unique legacy-source backfill and downgrade.
- Added repository APIs for observation upsert, monotonic `(created_at, id)` run audit ordering and eligible-source lookup. Semantic or persisted-locator replacement advances generation and resets download state; generation-only archive reset does not rewrite provenance.
- Added exact recovered `source_paths`; fresh, recovered and already-succeeded paths now attempt terminal cleanup. Closed metadata checks bind attempt/execution/run identity with deterministic `uuid5`, and post-commit database truth is protected from contradictory failure mutation. `UNRESOLVED` remains a hard fence.

### Still to implement

- Exact 0/1/N and existing-Job-bound source selection; immutable Job source with `run_id = NULL`.
- Shared account lock, filesystem-block second check and TOCTOU barrier before secret resolution/claim/spawn.
- Private refresh protocol, dedicated pipe/handle, detail child and runner; XHS/Douyin/Kuaishou/Bilibili selectors; fixed no-spawn Weibo/Tieba/Zhihu paths.
- Context-aware refresh and exact one 401/403 re-resolution; CLI `--enable-mediacrawler`, license and `--subscription-id` wiring.
- Functional refresh/download CLI, platform detail selection and automatic workflow integration.
- Full hardening matrix, authorized live rows and retained sentinel are explicitly deferred until the functional path is complete. Execution 0010 automatic DAG remains not started.

## Resumed implementation tranche

- Promoted `0005_asset_refresh_sources` to the CLI/package head and added `0004 → 0005 → 0004 → 0005` coverage for schema constraints, foreign keys, indexes and conservative 0/1/N legacy backfill.
- Wired exact Asset/Subscription observation into the same ingestion transaction before checkpoint publication. Wrong run/relation rolls back the entire batch; replay ordering, multi-account replacement and archive-reset eligibility are covered.
- Closed fresh, recovered and already-succeeded cleanup behavior, preserved committed success truth and made concurrent disappearance of the exact root converge safely.
- Merged verification: Ruff PASS, strict mypy PASS for 65 source files, and `87 passed, 1 skipped` across migration/ingestion/handler/supervision focused gates.
- Added one automatic re-resolution after an adapter-refresh HTTP 401/403. A second auth failure returns fixed retryable `locator_refresh_auth_expired`; direct locators never invoke refresh.

## Function-first delivery completed

### Implemented

- Added `MediaCrawlerDetailProcessRunner`: it validates the pinned checkout and explicit Python runtime, reuses the exact account profile, runs bounded detail mode, returns content JSONL in memory and removes only the UUID-scoped attempt root.
- Added `MediaCrawlerRefreshContext` and `MediaCrawlerLocatorRefresher`: they recompute the stable Asset identity, reuse the normal ingestion normalizer and select exactly one URL by content/type/id, kind, position and query-free source hint.
- Added `LazyMediaCrawlerLocatorRefresher`: it selects the exact current `AssetRefreshSource`, Subscription and Account only if the downloader actually needs a locator; Cookie secrets remain transient.
- Wired `asset download --enable-mediacrawler --accept-mediacrawler-license [--subscription-id]`. XHS also accepts `--xhs-detail-reference-ref`; missing runtime/license/XHS detail authority is blocked before download orchestration.
- Added fixed source errors for unavailable, ambiguous and mismatched observations plus unavailable credentials. Operator-correctable source errors remain retryable.
- Offline fake-child, normalizer selection, cleanup and downloader renewal regressions pass; no real platform, CDN, credential or media-server traffic ran.

### Pending

- Execution 0010 automatic `sync → download → Emby` coordinator and worker.
- Automatic XHS creator-feed lookup for a fresh note-specific `xsec` detail URL; the MVP uses an ephemeral operator-supplied secret reference.
- Live Cookie/saved-session/QR qualification, real CDN download and real Emby/Jellyfin scan.
- Exhaustive hardening/retained-sentinel/full-suite/build/wheel/public deployment matrices.

## Entry gaps to close

| Gap | Planned closure | Status |
| --- | --- | --- |
| No exact refresh source | `0005_asset_refresh_sources`, conservative backfill and same-transaction observations | `PASS (focused)` — schema, backfill, repository and ingestion wired |
| Context-free refresh port | Frozen Asset/Content/Subscription/Account context plus stable-key and fingerprint rechecks | `PASS (offline focused)` |
| No private detail protocol | Supervised detail-only child and one bounded non-relayed frame | `PASS (offline fake child)` |
| Short-lived auth URL | Exact one adapter-only 401/403 re-resolution; persistent locator-only partial identity | `PASS (offline focused)` — resolver and CLI wired |
| Post-success truth and roots | Exact fresh/recovered/restart cleanup; preserve committed truth across result/readback/cleanup/cancel errors; race-safe four states | `PASS (focused)` — handler and concurrent cleanup regressions pass |
| Signed data sink risk | Injection/transport proof and fail-closed filesystem/SQLite/operator/JUnit scans | `NOT_RUN` |
| Configuration/block TOCTOU | Shared account lock; filesystem block recheck outside SQLite before secrets/claim/spawn; transactional DB identity recheck; all block writers share fence | `NOT_RUN` |

## Planned implementation sequence

1. Terminal cleanup red tests and minimal race/identity repair.
2. Migration, ORM/repository provenance and conservative backfill.
3. Same-transaction ingestion observations and exact selector/Job binding.
4. Context-aware refresh port, supervised private child and fixed errors.
5. Four supported fake platform shapes, three fixed no-spawn paths and downloader re-resolution.
6. CLI wiring, adversarial security gates, full suite, build/package and one-shot retained evidence.

## Current qualification

| Scope | Status | Truth |
| --- | --- | --- |
| Refresh provenance/migration | `PASS (focused)` | Migration/repository/ingestion focused gates pass |
| Private refresh child | `PASS (offline fake child)` | Detail-mode helper ran against a fake pinned checkout and cleaned its exact attempt root |
| Manual signed-locator download | `PASS (offline wiring)` | Explicit CLI flags construct the lazy exact-source refresher; real traffic remains unqualified |
| Successful/recovery terminal cleanup | `PASS (focused)` | Handler `53 passed`; supervision `14 passed, 1 skipped` |
| Automatic `sync → download → Emby` DAG | Unimplemented | Execution 0010 |
| Live login, creator traffic, refresh, CDN and Emby/Jellyfin | `NOT_RUN` | No authorized environment supplied |

## Deferred truthfully

- QR challenge presentation and phone login are not implemented by this plan.
- Bilibili playable video/DASH/multi-part/subtitle/danmaku and Weibo/Tieba/Zhihu Asset discovery remain unavailable.
- Credential-bearing CDN headers and child-side downloads are deliberately excluded; real URLs requiring them remain unqualified.
- Unresolved account cleanup blocks have no automatic clear/bypass path.
- REST, resident supervision, Docker, public deployment and HA/PostgreSQL remain later work.
