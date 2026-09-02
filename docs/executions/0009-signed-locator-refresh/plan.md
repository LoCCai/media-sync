**English** | [中文](plan.zh.md)

# Execution 0009 plan

- Status: Function-first MVP implemented; remaining hardening retained as follow-up
- Plan date: 2026-08-30
- Predecessor: Execution 0008 implementation commit `3889539`
- Network policy: offline fake pinned-upstream modules, local helpers and mock HTTP only
- Delivery priority: first make local refresh/download and the end-to-end workflow usable; record exhaustive hardening and authorized live qualification as explicit follow-up work

## Frozen design

The sections below preserve the original full-hardening design. The implemented MVP deliberately chose a smaller usable path: a lazy exact-current-source selector, a bounded stdout-framed detail helper, explicit XHS note-detail secret input, and existing `asset_download` Job semantics. Immutable Job-bound refresh-source payloads, automatic XHS creator-feed lookup, shared-lock coverage through CDN finalization and exhaustive retained evidence are deferred rather than claimed complete.

### Delivery slice

- Execution 0009 implements only explicit manual refresh/download for existing MediaCrawler `adapter_refresh` Assets and successful/recovery attempt terminal cleanup. It does not add automatic downstream Jobs.
- The runtime surface remains default-off and requires both MediaCrawler enablement and license acknowledgement on each CLI invocation. No source, secret or process work occurs before those checks.
- Cookie and saved-session refresh are the only non-interactive login paths. QR returns a fixed user-interaction-required result without mutation; phone remains unsupported.

### Relational provenance and migration

Add Alembic revision `0005_asset_refresh_sources` and ORM model `AssetRefreshSource`. Do not add a single source column to Asset because the same author/asset may be observed by multiple account subscriptions.

| Column or rule | Frozen contract |
| --- | --- |
| Primary identity | Composite primary key `(asset_id, subscription_id)` |
| `asset_id` | FK to `assets.id`, `ON DELETE CASCADE` |
| `subscription_id` | FK to `subscriptions.id`, `ON DELETE CASCADE` |
| `last_run_id` | Nullable FK to `sync_runs.id`, `ON DELETE SET NULL`; audit only |
| `observation_kind` | Closed values `ingested` and `legacy_unique_inferred` |
| `observed_generation` | Positive audit value; never the eligibility key |
| `observed_semantic_fingerprint` | Exact lower-case SHA-256 copied from current Asset |
| `observed_locator_fingerprint` | Exact lower-case SHA-256 copied from current Asset |
| Timestamps/run | `first_seen_at` is immutable; `last_seen_at` never decreases; `last_run_id` advances only by total `(SyncRun.created_at, SyncRun.id)` order, so an older replay cannot regress audit state |
| Indexes | `subscription_id`; `(asset_id, observed_semantic_fingerprint, observed_locator_fingerprint)` |

Eligibility requires both observation fingerprints to equal the current Asset and also checks the current stable locator, Content author, Subscription author, Account platform and `adapter='mediacrawler'`. `observed_generation` is diagnostic only. A verified archive reset may increment generation without changing semantic/locator fingerprints and must retain eligibility. Any persisted semantic- or locator-fingerprint replacement must increment generation and reset downloader state before a new immutable Job source can bind; query-only signed-URL rotation is not a persisted replacement. Other observations remain as ineligible audit rows.

Migration backfill parses only valid `adapter_refresh` locators with adapter `mediacrawler`, recomputes `stable_asset_key()` and requires exact equality across `Asset.platform == Content.platform == Author.platform == Account.platform`, `Subscription.author_id == Content.author_id`, and `Account.adapter == 'mediacrawler'`. It inserts `legacy_unique_inferred` only when exactly one Subscription satisfies the entire chain. It never chooses the first of multiple accounts, reads raw data to recover secrets, resolves a secret reference or reconstructs a signed URL. Zero/ambiguous/malformed/corrupt cases remain unbound. Downgrade drops only this table and its indexes/constraints.

### Ingestion observation

- Change Asset upsert plumbing to return the authoritative Asset row. Within every exact ownership-guarded batch, prove the SyncRun belongs to the same Subscription and the full author/platform/account relation, then upsert one observation using that `subscription_id`, `run_id`, Asset generation and fingerprints before commit/checkpoint advancement. Any mismatch rolls back observation, Asset and checkpoint changes together.
- Replaying the same subscription/run is idempotent. Another subscription can add a second observation. A semantic- or locator-fingerprint replacement increments Asset generation, resets downloader state and updates the observing subscription's row; other rows remain audit evidence but no longer qualify.
- Empty or filtered batches create no observation. A failed or fenced ingestion transaction creates neither Asset change nor provenance.

### Read-only selection and Job binding

Introduce a closed source-selection result that contains no ORM object or secret. It freezes Asset ID/generation/platform/content remote type and ID/kind/position/synthetic remote ID, semantic/locator fingerprints, query-free source hint, Author platform/remote ID, Account ID/platform/adapter/login method/credential-reference identity/profile identity/auth status, and Subscription ID/account/author/enabled/canonical closed MediaCrawler policy identity. The policy identity covers the creator-secret reference without exposing it.

Selection has two exact modes:

1. **No same-generation Job:** an explicit subscription must be an eligible observation; otherwise return `locator_refresh_source_mismatch`. Without one, zero eligible rows return `locator_refresh_source_unavailable`, exactly one is selected and more than one returns `locator_refresh_source_ambiguous`.
2. **Existing same-generation Job:** its closed immutable source binding is authoritative and must still identify one eligible current observation. Optional `--subscription-id` must equal the bound subscription. Missing/open/corrupt/stale binding returns `locator_refresh_source_mismatch`; unrelated newly eligible observations are ignored for ambiguity and never trigger rebind. Retry/running/prepared recovery always follows this mode.
3. Before Job creation/claim, recompute `stable_asset_key()` from authoritative Content/Asset fields and compare it with the parsed locator. Under the shared account security lock, recheck the filesystem cleanup block outside SQLite; then recheck generation, both fingerprints and every frozen database Author/Account/Subscription/configuration identity in the claim transaction.

Keep the existing Job natural key `asset_id:generation`. For MediaCrawler refresh, fill the existing `subscription_id`, `account_id` and `platform` columns and keep `run_id = NULL`. Add a closed immutable `refresh_source` payload containing only schema version, asset/subscription/account IDs, platform and semantic/locator fingerprints; reject unknown fields and never store observation kind, credential refs, policies containing creator references, resolved URLs, source URLs, filesystem roots or profile paths. Observation kind may upgrade from `legacy_unique_inferred` to `ingested` without changing Job source equality. `AssetRefreshSource.last_run_id` is audit only: execution 0009 creates no Job dependency, predecessor, ingestion fan-out or SyncRun ancestry inference.

### Preflight and recovery ordering

- Hard order: enable/license -> read-only unresolved-account block fence -> read-only classify already-verified, exact prepared recovery or network-bearing work. Blocked paths call SecretResolver, run attach, bridge/refresh preparation, child spawn and HTTP exactly zero times.
- Read-only inspection itself is zero-mutation. A valid already-verified archive returns without Job/Asset mutation. Exact prepared recovery may perform only CAS/lease takeover and success finalization of the already-bound Job/Asset generation; it creates no Job, rebinds no source, consumes no new attempt, resolves no credential, spawns no child and issues no HTTP.
- For network-bearing work, continue with source/runtime/profile/reference validation -> acquire the shared account/profile security lock -> recheck the filesystem cleanup block outside SQLite -> resolve Cookie/creator secret outside SQLite -> short transaction rechecking only database source/Asset/Author/Account/Subscription/configuration identities and claiming the Job -> supervised refresh -> safe download/finalization -> cleanup -> release lock. Every cleanup path that can create an account block uses this same lock (or an equivalent atomic fence), so no writer can insert a block between the second check and release.
- If any frozen login method, credential-reference identity, profile identity, auth status, enabled flag, account/author relation or canonical closed-policy identity changes between selection/secret resolution and `_begin`, fail closed. A barrier test creates a block after the first read: lock acquisition plus the second check must stop before SecretResolver, claim and spawn. A secret object may remain in trusted-parent memory during `_begin`, but secret resolution, filesystem checks and external I/O never occur inside a database transaction; closed credential/config identities never enter Job payload or logs.
- Existing prepared/retry/running recovery keeps its originally bound source and never consumes a new account implicitly.

### Refresh port and private child protocol

Replace the context-free `resolve(AdapterRefreshLocator)` call with a frozen `RefreshRequest`/`RefreshContext`. Subscription UUIDs remain outside the globally persisted locator. The resolver returns `ResolvedLocator` with URL hidden from `repr`; execution 0009 deliberately keeps the CDN contract URL-only and does not add credential-bearing request headers.

Implement a dedicated detail-only child and parent runner, reusing or extracting the existing account/profile lock, checkout/runtime/license verification, start handshake, parent-death supervision, cancellation, descendant join and bounded timeout. The trusted parent never imports MediaCrawler.

- Private inputs use the existing early-pop secret envelope and never appear in argv, manifest or operator output.
- Create a dedicated inherited OS result pipe/handle that is distinct from fd 1/2; before importing any upstream module, redirect ordinary stdout/stderr to null at OS level. The parent concurrently drains at most 16 KiB plus the overflow probe to EOF, never relays bytes, and closes every local/inherited handle on success, failure, timeout and cancellation.
- One frame, maximum 16 KiB, canonical UTF-8 JSON plus newline. Success uses a closed schema with version, fixed status, exact request-identity fingerprint and URL; failure contains only version, fixed status and allowlisted code. Exit status, one frame, EOF and handle closure must agree. Watchdog timeout maps to retryable `locator_refresh_temporary`; nonzero exit, no frame, exit/frame disagreement and every invalid-frame shape map to terminal `locator_refresh_result_invalid`; cancellation preserves the existing cancellation result.
- Reject duplicate/unknown keys, invalid UTF-8, multiple/trailing frames, overflow, truncation, identity mismatch and non-`ResolvedLocator` URL syntax without echoing bytes.
- Child extracts detail dictionaries in memory before upstream store/JSONL. It never invokes store or writes an attempt/output file. Child code owns semantic candidate validation; the parent validates the fingerprint covering the full frozen request, closed hint contract and URL syntax, not a candidate echo that the frame cannot independently prove.

### Offline platform selector matrix

| Platform | Supported current Asset | Frozen selector | Explicit boundary |
| --- | --- | --- | --- |
| `xhs` | image, video with exact stored query-free hint | Strictly parse exact Subscription creator URL; require HTTPS XHS host, matching author ID and non-empty token/source; scan at most 4 x 30 feed items in a 120-second child watchdog, then detail and exact hint selection | Invalid/mismatched authority=`configuration_invalid`; expired=`auth_expired`; absent after 120=`asset_not_found`; malformed/repeating pagination=`schema_changed`; watchdog=`temporary`; never reconstruct/persist xsec |
| `dy` | image, video, audio, cover | `get_video_by_id`; reproduce current image-first/video-suppression semantics and exact candidate matching | Browser state may generate API signing material only inside child |
| `ks` | video, cover | GraphQL `visionVideoDetail(photoId)`; exact one video/cover candidate | No live CDN claim |
| `bili` | cover only | `/x/web-interface/view/detail` and exact cover match | Never call playurl; no playable video/DASH/multi-part claim |
| `wb`, `tieba`, `zhihu` | none | Fixed `locator_refresh_platform_unsupported`; no child spawn | Asset discovery remains unimplemented |

Every supported Asset must have an exact stored query-free hint. The synthetic `Asset.remote_id` and numeric position are not durable platform variant IDs. Inside the trusted child, position may only participate after current normalization semantics and the hint have produced a unique candidate set; it cannot break same-kind ambiguity by itself. The child emits only the full-request fingerprint after that check. A missing hint or a hint that no longer chooses exactly one candidate returns `locator_refresh_asset_mismatch`.

### Fixed error taxonomy

| Phase | Fixed codes | Disposition |
| --- | --- | --- |
| Zero-mutation preflight | `locator_refresh_disabled`, `license_acknowledgement_required`, `locator_refresh_source_unavailable`, `locator_refresh_source_ambiguous`, `locator_refresh_source_mismatch`, `locator_refresh_platform_unsupported`, `locator_refresh_kind_unsupported`, `locator_refresh_qr_required`, `locator_refresh_credentials_unavailable`, `locator_refresh_configuration_invalid` | No Job/Asset mutation |
| Retryable attempt | `locator_refresh_account_busy`, `locator_refresh_auth_expired`, `locator_refresh_rate_limited`, `locator_refresh_temporary` | Fixed redacted retryable failure under existing attempt limits |
| Terminal/security | `locator_refresh_asset_not_found`, `locator_refresh_schema_changed`, `locator_refresh_asset_mismatch`, `locator_refresh_result_invalid` | Fixed terminal failure; no raw child bytes |

Retain `locator_refresh_unsupported` as the generic media-layer code when no refresher is supplied; the MediaCrawler CLI preflight must normally prevent reaching it. All public messages remain fixed in the error registry.

### Downloader re-resolution

- Direct locator behavior is byte-for-byte unchanged. Adapter refresh resolves once immediately before HTTP.
- Only an HTTP 401/403 from an adapter-refresh request can consume one additional resolution. Reuse the exact frozen source/context. A second 401/403 raises `locator_refresh_auth_expired`; other statuses retain existing classification.
- `.part` metadata and recovery identity use only the canonical persistent locator fingerprint. A refreshed query, expiry, API header or Cookie never reaches metadata, archive names or result payloads.
- Range/If-Range remains safe. If a new signed URL answers a resumed request with `200`, the existing bounded restart logic discards/restarts rather than appending incompatible bytes.
- No Cookie, Origin or Referer is added to `SafeHttpClient` redirects. If a real CDN requires such credentials, that live row remains unsupported/`NOT_RUN`; execution 0009 does not bypass DNS pinning, redirect, Range, size or probe contracts by downloading inside the child.

### Successful/recovery terminal cleanup

Repair four existing gaps: fresh `_ingest()` success currently returns with its root; recovered success drops source paths; already-succeeded restart returns before cleanup; and malformed in-memory result or authoritative readback failure after a committed success can still reach `_set_run_failure()`.

1. Extend `_RecoveredOutput` with exact `source_paths`. Recovered ingestion cleans that source root, never the new successor path.
2. After authoritative DB success and before outward success, run terminal cleanup through the repeated-cancellation-safe join helper. Lease loss/cancellation does not let the caller unwind before cleanup reaches a secured/unresolved verdict.
3. For an already-succeeded restart, validate a closed run-metadata schema. Fresh cleanup uses top-level attempt/execution identity. Recovered cleanup uses `recovered_artifact` source attempt/execution/run identity and proves `execution_id == uuid5(job_id, "media-sync/mediacrawler/attempt/{source_attempt}")`. Never trust an open path or successor execution ID.
4. Make `cleanup_attempt_root()` concurrency-idempotent. After every no-follow/scope check and rename/remove transition, disappearance caused by a concurrent exact cleanup converges to safe `ABSENT`/`REMOVED`; it must not become false `UNRESOLVED`. Unsafe replacement, escape or unverifiable metadata still fails closed.
5. Introduce an explicit post-commit-success boundary. Once authoritative Run/checkpoint/content success exists, malformed result objects, readback mismatch/error, all four cleanup states, cancellation and lease loss may only produce fixed control outcomes while preserving database truth. They never call `_set_run_failure()`, re-ingest or roll back; repeated restart performs exact cleanup only.

Terminal state mapping is fixed:

| Cleanup | Database truth | Outward behavior |
| --- | --- | --- |
| `ABSENT`, `REMOVED` | Preserve succeeded Run/checkpoint/content | Success |
| `QUARANTINED` | Preserve success; isolated root remains an enumerated credential-bearing boundary | Success with only fixed internal disposition; no path |
| `UNRESOLVED` | Preserve success, attempt fixed marker persistence and hard-fence account | Raise fixed cleanup-blocked control result; never stale-fail/reingest |

The persistent unresolved account block has no automatic clear path in execution 0009. No restart, refresh or manual download silently bypasses it.

### Security and retained evidence

- A signed-URL sentinel is generated after collection and inserted into the private child frame. A private-pipe observer proves injection before parent consumption; mock HTTP proves the exact URL reached only the request boundary. Separate dynamic sentinels are injected after collection into fresh- and recovered-success JSONL roots, proved non-empty before cleanup, then the exact source roots are proved removed/secured; already-succeeded restart proves the same source identity.
- Scan every logical SQLite text/JSON value and all database/WAL/SHM bytes; Job/Asset locators, raw/source fields, payloads and results must be query-free and secret-free.
- Scan safe attempt/download/archive/sidecar/operator/JUnit trees, hidden and ignored files and path names fail-closed. No scan exclusion inside a declared safe root.
- Persistent profile, deliberate quarantine and unresolved cleanup evidence are a separately named negative set. Never delete or rewrite them to satisfy a scan; never expose their paths.
- Use a fresh ignored `.media-sync/verification/0009-refresh-sentinel-root` exactly once. It must not exist before the authoritative run and must never be deleted/recreated afterward. The 0007 and 0008 retained roots are read-only and untouched.

## Implementation sequence

1. Add red tests for fresh/recovered/already-succeeded terminal cleanup and concurrent exact-root cleanup; implement the minimal cleanup/state repair first.
2. Add `0005_asset_refresh_sources`, ORM/repository APIs, conservative backfill and packaged migration round-trip tests.
3. Integrate exact observation upsert into fenced MediaCrawler ingestion and prove replay/replacement/generation-reset semantics.
4. Add read-only source selection, immutable Job source payload/columns and zero-mutation CLI preflight.
5. Define the context-aware refresh port, fixed error taxonomy and strict private child frame.
6. Implement supervised fake-detail shapes for XHS/Douyin/Kuaishou/Bilibili and fixed no-spawn unsupported paths for the remaining platforms.
7. Integrate one-time 401/403 re-resolution into the existing secure downloader and wire the explicit CLI.
8. Run focused platform/supervision/migration/cleanup/security gates, the full suite, build/package checks and the one-shot retained sentinel; update capability truth without promoting live rows.

## Verification plan

| Gate | Required coverage |
| --- | --- |
| Migration | New DB head; constraints/FKs/indexes; exact relation/stable-key legacy backfill; ambiguous/corrupt unbound; upgrade/downgrade/re-upgrade; packaged inventory |
| Provenance | Same-transaction observation; wrong-run/cross-relation rollback; older-run replay cannot regress `(created_at,id)` audit order; multi-account; semantic- and locator-only replacement advance generation; archive reset alone retains eligibility |
| Selection/Job | No-Job 0/1/N; existing-Job authority; explicit source; audit upgrade; shared-lock second block check catches a barrier writer before SecretResolver/claim/spawn; no filesystem I/O in transaction; config race; `run_id = NULL` |
| Recovery ordering | Verified succeeds with no source/profile/credential/mutation; exact prepared recovery permits only bound CAS/finalization; both make zero SecretResolver/child/HTTP calls |
| Child/platform | Dedicated fd/handle; pre-import null redirection; bounded drain/EOF/closure; strict frame/error matrix; shared account lock held through child tree, download finalization and cleanup; every block writer uses same fence; parent death/cancel; selectors |
| Downloader | Signed URL reaches mock HTTP; exact one 401/403 re-resolve; direct unchanged; partial resume; no URL/query in metadata; redirect headers unchanged |
| Cleanup | Non-empty fresh/recovered sentinels; exact restart identity; after real success commit inject malformed result, readback failure/mismatch, four states, repeated cancel/lease loss and restart; assert no failure mutation/reingest; marker failure and concurrent disappearance |
| Secret sinks | Private-pipe and mock-transport proof plus exact post-cleanup filesystem/SQLite/operator/JUnit zero-match; named negative exclusions |
| Root quality | Locked sync; Ruff/format/mypy; full branch-aware pytest; build and wheel smoke; packaged migrations; docs/upstreams/diff/Git checks; fresh retained root |

## Explicit non-goals

- No durable automatic `sync → download → Emby` DAG, dependency table, fan-out/fan-in or shared-child cancellation semantics; execution 0010 owns them.
- No real platform/CDN/Emby traffic or capability promotion.
- No Bilibili playable video/DASH/multi-part/subtitle/danmaku, no Weibo/Tieba/Zhihu Asset discovery and no XHS variant identity redesign beyond fail-closed current-hint matching.
- No credential-bearing CDN headers, child-side media download, QR presentation UX, phone login, REST, resident supervisor, Docker or HA/PostgreSQL.
- No automatic clearing of unresolved cleanup blocks and no silent source rebind.
