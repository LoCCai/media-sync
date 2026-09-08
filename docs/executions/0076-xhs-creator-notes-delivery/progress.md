**English** | [中文](progress.zh.md)

# Progress: durable XHS creator-note delivery

Status: the local implementation is complete in `47ca107`. Docker/Linux deployment, real PostgreSQL, live XHS traffic and resident-supervisor qualification remain pending.

## Outcome

One XHS creator-notes Subscription can now follow the same durable local delivery chain as Bilibili while retaining XHS-specific source semantics:

```text
adopted XHS Account + protected creator URL
  -> one source-backed page unit with an opaque cursor
  -> fresh per-note xsec token used only inside the child
  -> exact Run-content ingestion and pipeline receipt
  -> archive + configured platform directory + NFO
  -> source-end head reconciliation
  -> bounded incremental head checks
```

No Emby/Jellyfin connection is required. The configured shared or XHS-specific directory remains the product output; a media server may read that mounted directory independently.

## Implemented

1. **Source-backed page state.** A canonical `xhs-notes-v1` cursor binds Account, author, protected creator reference, pinned upstream and one `notes` feed. Each unit lists at most one nominal 30-note source page. A retained page witness plus completed-note identities preserves the unconsumed page tail when `max_items < 30`; opaque source cursors are replayed verbatim.
2. **Fresh token boundary.** The list-page `xsec_token` is held only in child memory, matched by SHA-256 to the exact note and removed from normalized/persisted/public output. Detail uses that page's token, tries the upstream API and then HTML fallback, and re-lists the same retained page on a later unit when a detail remains incomplete. Dependency logging is suppressed around token-bearing calls.
3. **Durable ownership and recovery.** Migration `0015_xhs_creator_notes` adds one constrained progress row per Subscription. State and receipts are fenced by Account/auth revision, author, creator-reference fingerprint, policy, upstream SHA, checkpoint, schedule revision, Job, Run and pipeline Job. A creator-reference change invalidates the old cursor before another child can consume it.
4. **Truthful phases.** Delivery-qualified progress moves through `backfill`, `reconciling`, `incremental` and `blocked`. Only a delivered `has_more=false` page becomes source-end evidence. `access_restricted`, `empty_page_stalled` and `unit_cap_reached` remain distinct; a source-end observation is not a permanent claim that all historical notes exist locally.
5. **Stable reconciliation and incrementality.** After source end, the head is re-listed with fresh tokens. Drift keeps delivered content and requires another stable reconciliation; only a stable delivered head publishes the incremental baseline. Later unchanged checks fetch no details and write no new content, while a new or changed note is selected once.
6. **Per-content delivery.** Exact `SyncRunContent` selection connects accepted normal/video note records to the existing verified download, SHA-256 archive and deterministic Emby-compatible directory/NFO pipeline. One unsupported or unavailable note is reported as partial without discarding unrelated valid notes; a real writer failure still terminates the batch.
7. **Operator surface.** REST and Web expose only allowlisted phase, counters, stop reason, evidence timestamps, next eligibility and fixed block/partial states. Exact execution reports `xhs_access_restricted`, `xhs_empty_page_stalled` or `xhs_note_detail_partial` as failure rather than success. Token values, opaque cursors, creator URLs, raw responses and host paths stay private.
8. **Shared pacing configuration.** `MEDIA_SYNC_XHS_SCAN_CONTINUATION_DELAY_SECONDS` defaults to `300`, accepts `0` or `60..604800`, and must match between API and supervisor. Zero disables only fast continuation; it retains upstream binding, durable progress and ordinary subscription scheduling.

## Review corrections

- Exact API execution no longer reports success for a delivered unit whose XHS progress is blocked or partial.
- Zero XHS fast delay no longer disables progress binding; it schedules the next unit at the ordinary Subscription interval.
- Child normalization rejects one unsupported note locally without hiding valid siblings, while post-write failures remain terminal.
- Legacy structural runner doubles may omit `xhs_scan` without crashing non-XHS paths.
- The pipeline worker now parses MediaCrawler policy only for MediaCrawler accounts, preserving other adapter contracts.
- Current Bilibili provenance tests now include the creator fingerprint that production Run manifests require.

## Remaining

- Pull and rebuild the published revision on the Linux host, back up state first, apply migration `0015`, and configure the same XHS continuation delay in both services.
- Run one authorized, low-volume XHS creator canary through native session adoption, history units, local download/archive/NFO output, restart and then supervisor scheduling.
- Run the optional real PostgreSQL schema/race qualification.
- Linux/Docker, real XHS login/API/CDN bytes, host directory permissions/content, process restart, resident supervisor and optional media-server reading are all `NOT_RUN` in this execution.
- Follow [next delivery](next-delivery.md) before selecting the next platform. Execution 0077 has not started.
