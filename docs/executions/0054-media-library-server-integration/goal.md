**English** | [中文](goal.zh.md)

# Execution 0054 goal

- Status: Phase A delivered and frozen-verified; Execution 0054 remains open for a separately frozen Phase B
- Started: 2026-09-05 02:45 +08:00
- Predecessor: `22b5864` (Execution 0053 closeout)
- Scope: Phase A of 0054 — safe published-library inspection, one environment-owned Emby/Jellyfin profile, durable connection/targeted-refresh operations, and an evidence-led qualification view
- Planned database revision: `0007_media_server_operations`

## Outcome

Turn the existing deterministic Emby/Jellyfin-compatible export into an operator-verifiable media product. An operator can inspect the current managed author tree and drift without learning host paths, configure exactly one media server outside the browser, test that configured server, trigger a bounded library refresh, and see what durable evidence exists without mistaking local or mocked checks for live qualification.

## Acceptance

1. Preserve the existing `GET /api/v1/library` array response and filters. Add an author-UUID detail endpoint whose authority is the database publication chain plus the strict managed manifest, never a caller-supplied path.
2. Return only bounded logical relative nodes and allowlisted publication facts: layout/source/tree/manifest identities, publication Job identity, managed counts, independent freshness and integrity states, protected-user-change state, cursor facts, and fixed allowed actions. `blocked` is a normal freshness state when the current source snapshot is not exportable; it is not mislabeled as publication corruption. Do not return export roots, host paths, raw Job payloads, exception text, locators, source URLs, or file bytes.
3. Inspect manifests and managed files under an existing-only per-author lock and fail closed on malformed manifests, links, path escapes, case collisions, missing files, size/hash drift, replacement races, or inconsistent publication chains. Each request verifies at most 128 files, the operator-configured byte budget (default 1 GiB), and the operator-configured deadline (default 10 seconds), under a process-wide single-flight gate. A manifest-bound cursor prevents pages from mixing different publications. The response reports exact `page`, `complete`, or `budget_exhausted` scope and never upgrades partial work to whole-tree health. Inspection is read-only and performs no repair, deletion, lock creation, or directory creation.
4. Add one immutable environment-owned media-server profile for `emby` or `jellyfin`. The API exposes a hand-built safe summary only; API-key values and complete secret references never cross into API responses, logs, operation payloads, or SQLite.
5. Media-server requests may reach only the configured canonical origin and operator allowlisted IP/CIDR ranges. Requests cannot supply URL, host, key, path, library, or network-policy overrides. Every DNS answer must be allowed, resolution and connection are pinned, redirects are rejected, time/header/body/item limits are enforced, and private/loopback targets require explicit deployment configuration.
6. Persist connection probes and manual targeted-refresh triggers as closed `media-server-probe` and `media-server-scan` Operations. Both endpoints are disabled by default and share one profile-exclusive key; UI action flags never replace server-side enforcement. The only mutating protocol is fixed `POST /Items/{configured-library-id}/Refresh` after exact virtual-folder matching. `404`, `405`, or `501` becomes `media_server_targeted_scan_unsupported`; there is no fallback to global `/Library/Refresh`. Cancellation is honored only before dispatch. The POST has no transport retry: timeout, disconnect, cancellation, or crash after dispatch becomes non-retryable `media_server_scan_acceptance_unknown`/`interrupted`, never false success, safe failure, or cancellation. Only allowlisted evidence is durable.
7. Upgrade Library, Settings, and Jobs views to show the real managed tree, safe connection posture, durable probe/scan activity, and qualification evidence. Local export success, request acceptance, and mocked tests must not imply a live scan or playable sample.
8. Add migration, unit, integration, API, Web, security, and packaging coverage. Existing Emby export, content/asset explorer, operation/event, migration, and Web contracts remain compatible.

## Qualification boundary

This execution may prove local manifest/tree behavior and fake or mocked Emby/Jellyfin protocol behavior. No server URL, API key, or library ID is currently configured in this workspace. The implemented connection probe, version/library discovery, and targeted-refresh acceptance remain live `NOT_RUN` until an operator performs them on an authorized deployment. Scan-completion polling, provider/path item lookup, playback-evidence recording, and automatic export-to-scan chaining are `NOT_IMPLEMENTED` in phase A, not `NOT_RUN`. Linux deployment evidence and every seven-platform live-account/CDN row remain `NOT_RUN`.

## Deferred

0054 remains open after phase A: a separately frozen 0054-B must address mockable scan-completion progress and provider/path item lookup before the roadmap may call media-server linkage complete. Playback-evidence mutation waits for operator authentication and remains 0055 work. Browser-writable settings, multiple profiles, destructive cleanup, retention, orphan repair, forced overwrite, and access control also remain 0055 work; final legacy-console removal remains 0056 work. Automatic post-export scanning is future scope whose execution assignment has not been frozen.
