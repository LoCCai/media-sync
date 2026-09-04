**English** | [中文](goal.zh.md)

# Execution 0054 Phase B goal

- Status: Planning baseline frozen; implementation not started
- Date: 2026-09-05
- Baseline: `4945df1` (Execution 0054-A closeout)
- Database revision: none planned
- Scope: bounded provider/path lookup and honest post-refresh managed-item observation

## Outcome

Complete the smallest safe follow-up to 0054-A without claiming a capability that Emby and Jellyfin do not expose. The existing empty-object `{}` targeted-refresh request remains available and proves acceptance only. An operator may additionally select one locally authorized published author, inspect whether the exact managed provider/path item is present, request one refresh with postcondition observation, and follow durable verification activity. The product reports refresh acceptance, managed-item observation, and playback as separate facts.

## Truth boundary

The supported Emby and Jellyfin HTTP APIs return no durable task identity from `POST /Items/{id}/Refresh`. Global Scheduled Task state cannot be correlated to that POST, and Jellyfin WebSocket refresh progress is neither a durable nor uniquely correlated task contract. Therefore Phase B does not implement or claim provider task completion.

The implemented capability is named `post_refresh_item_observation`. Its strict success evidence is:

1. Before dispatch, a complete bounded lookup observes no exact item.
2. The one refresh POST returns a trusted 2xx response.
3. A later complete lookup observes exactly one item whose provider key/value and server path both match the server-derived selector.
4. A second observation after a positive interval finds the same unique item.

This proves an absent-to-unique-match postcondition after accepted refresh. It does not prove that every provider queue has drained, metadata is final, media is playable, or the refresh caused every remote change.

An item that already exists at baseline is ineligible for strict success. The author observation mode terminates before POST with `media_server_scan_observation_precondition_failed`; an operator who wants an acceptance-only manual refresh may use the preserved `{}` request instead. Etag changes, Scheduled Task transitions, an idle server, `DateModified`, `DateLastRefreshed`, `DateLastSaved`, and `RefreshState` are not completion evidence.

## Acceptance

1. Preserve `POST /api/v1/media-server/scan` with `{}` as the 0054-A acceptance-only contract. The same route additionally accepts exactly `{"author_id":"<uuid>"}` for observation mode. Explicit null and unknown fields are invalid. Neither shape can provide an origin, URL, path, Library ID, provider selector, remote item ID, API key, network rule, timeout, page size, or polling policy.
2. The backend derives the selector from the current unique successful publication head and strict manifest: provider key `media-sync-{platform}-creator`, the author's stored remote ID, and the configured server Library path joined with the deterministic author directory. It revalidates the same publication immediately before dispatch.
3. Add bounded synchronous `GET /api/v1/media-server/items/by-author/{author_id}`. A complete zero-match traversal returns normal `not_found`; a complete unique dual match returns `matched`. It returns only safe digests, counts, completion scope, and timestamps.
4. Emby lookup uses its documented `GET /Items` Path and AnyProviderIdEquals filters plus ParentId, Recursive, fixed Fields, disabled images/user data, and `Limit=2`. Every returned row is still checked locally for an exact provider value and exact derived path.
5. Jellyfin lookup uses documented `GET /Items` pagination below the configured Library with ParentId, Recursive, fixed Fields, disabled images/user data, and total-count reporting. It does not send unsupported Path or AnyProviderIdEquals filters. SearchTerm is never absence authority.
6. A lookup cannot report `matched` until the traversal proves uniqueness. Multiple exact item identities produce `media_server_item_lookup_ambiguous`; any exhausted or inconsistent page/item/byte/JSON/deadline budget produces `media_server_item_lookup_incomplete`, never `not_found`.
7. Refresh routing is provider-specific. Emby may receive documented `Recursive=true`; Jellyfin must not receive that undocumented query parameter. There is no global refresh fallback, Scheduled Tasks inference, WebSocket completion inference, or POST retry.
8. Reuse the existing `media-server-scan` Operation kind and profile-exclusive domain. Legacy `{}` requests remain targetless. Observation Operations use `target_type=author` and `target_id=<author UUID>`; the existing target relation links the author, and the publication Job is attached atomically as a `related` subject before the worker starts. The mode, profile, author target, and publication identity form the new request fingerprint without changing the legacy fingerprint.
9. Durable phases are `preparing`, `baselining`, `dispatching`, `accepted`, `polling`, and `observed`. A new lease/revision-fenced running checkpoint writes `accepted` or `observed` evidence to the existing `result_summary` while reusing `operation_phase_changed`; it adds no Event kind or schema migration. Progress is a verification count with no total, never a remote scan percentage.
10. A matched author baseline or a cancel/failure known to precede transport dispatch sends no POST. A matched baseline ends `media_server_scan_observation_precondition_failed` and directs an acceptance-only operator to the legacy request. After transport entry but before a trusted 2xx, every ambiguity is terminal non-retryable `media_server_scan_acceptance_unknown`. After trusted 2xx, timeout, cancellation, restart, lookup failure, drift, or exhausted observation budget is terminal non-retryable `media_server_scan_completion_unknown` while preserving the accepted checkpoint. An observed checkpoint may commit only if cancellation has not already won its authoritative lock; once observed commits, a later cancel cannot overwrite it, and no coordinator fallback may replace accepted evidence with an empty summary.
11. API, SQLite, Events, SSE, Web, logs, and support bundles never expose raw server paths, provider values, remote item IDs, Etags, response bodies, remote error text, credentials, or complete secret references. Only domain-separated digests and fixed codes may cross the boundary.
12. Unit, integration, API, Web, security, migration-compatibility, SQLite race, and real PostgreSQL race tests cover the frozen contract. Mocked results establish implementation evidence only; real-server qualification remains `NOT_RUN`.

## Provider contract

The compatibility floor is Emby 4.8.10 and 4.9.5 plus Jellyfin 10.10.7 and 10.11.11.

- Emby `GET /Items` documents Path and AnyProviderIdEquals. Its refresh endpoint documents recursive refresh and an empty 200 response. A user-scoped route is required for direct item GET, so Phase B uses the list route.
- Jellyfin `GET /Items` documents ParentId, Recursive, Fields, IDs, and pagination, but not Path or AnyProviderIdEquals. Its item refresh endpoint queues work and returns 204 without a task ID; `Recursive` is not part of that public route.
- The common DTO may use only `Id`, `Path`, `ProviderIds`, and optional `Etag`. Etag is diagnostic only and is neither necessary nor sufficient for success.

Normative references are the [Emby 4.8.10 OpenAPI](https://github.com/MediaBrowser/Emby.SDK/blob/4.8.10.0/Resources/OpenApi/openapi_v3.json), [Emby item query](https://dev.emby.media/reference/RestAPI/ItemsService/getItems.html), [Emby item refresh](https://dev.emby.media/reference/RestAPI/ItemRefreshService/postItemsByIdRefresh.html), [Jellyfin 10.10.7 OpenAPI](https://api.jellyfin.org/openapi/stable/jellyfin-openapi-10.10.7.json), [Jellyfin 10.11.11 OpenAPI](https://api.jellyfin.org/openapi/stable/jellyfin-openapi-10.11.11.json), and [Jellyfin 10.10.7 ItemRefreshController](https://github.com/jellyfin/jellyfin/blob/v10.10.7/Jellyfin.Api/Controllers/ItemRefreshController.cs).

## Security and budget boundary

Every lookup page and the POST independently repeats the 0054-A all-answer DNS allowlist check, pinned connection, original Host/TLS SNI, disabled environment proxy, redirect rejection, fixed-origin and route allowlist, final-boundary secret resolution, `X-Emby-Token` credential sink, header/body/JSON limits, and absolute deadline checks. Server-provided next links are ignored; pagination indices are computed locally.

Initial fixed limits are 128 Jellyfin rows per page, at most 32 pages/4,096 unique items/8 MiB per lookup pass, and at most 128 pages/16,384 inspected rows/32 MiB across one scan observation. The whole observation window is at most 120 seconds with at least two seconds between polls. Existing per-response limits remain 64 headers, 8 KiB per header line, 64 KiB total headers, 256 KiB body, JSON depth 8, 2,048 JSON items, and 4,096 characters per string. A server-owned deployment setting may lower these values but no API request may raise or replace them.

Query-bearing wire events must not retain complete URLs or query strings. Substring redaction is insufficient because paths and provider values may be percent-encoded. The connector replaces dependency wire messages with a fixed event while the request is active and emits only application-owned fixed codes and domain-separated digests.

The profile-exclusive database key serializes durable probe, legacy scan, and author-observation scan Operations only. The synchronous lookup endpoint is an independent read-only snapshot; the connector's process-local gate bounds same-process access, but no cross-process exclusivity or correlation with a scan Operation is claimed.

## Qualification boundary

Phase B changes the taxonomy to:

- `item_lookup`: `IMPLEMENTED` after the implementation gate passes.
- `post_refresh_item_observation`: `IMPLEMENTED` after the implementation gate passes.
- `provider_task_completion`: `NOT_IMPLEMENTED`, with reason `provider_api_unsupported`.
- `playback_evidence` and `automatic_post_export_scan`: `NOT_IMPLEMENTED`.

No real Emby or Jellyfin credential is available in this workspace. Human status for implemented lookup and observation remains `NOT_RUN`; an unimplemented capability has null human status. Mock servers never confer a live PASS.

## Out of scope

Playback, authenticated evidence mutation, automatic export-to-scan chaining, browser-writable media-server profiles, multiple profiles, access control, retention, destructive cleanup, orphan repair, forced overwrite, and provider-specific background task plugins remain outside Phase B. Exact cross-provider scan-task completion requires a future provider-specific correlated task contract and is not silently approximated here.
