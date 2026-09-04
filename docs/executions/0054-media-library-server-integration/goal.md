**English** | [中文](goal.zh.md)

# Execution 0054 goal

- Status: In progress
- Started: 2026-09-05 02:45 +08:00
- Predecessor: `22b5864` (Execution 0053 closeout)
- Scope: Safe published-library inspection, one environment-owned Emby/Jellyfin profile, durable connection/scan operations, and an evidence-led qualification view
- Planned database revision: `0007_media_server_operations`

## Outcome

Turn the existing deterministic Emby/Jellyfin-compatible export into an operator-verifiable media product. An operator can inspect the current managed author tree and drift without learning host paths, configure exactly one media server outside the browser, test that configured server, trigger a bounded library refresh, and see what durable evidence exists without mistaking local or mocked checks for live qualification.

## Acceptance

1. Preserve the existing `GET /api/v1/library` array response and filters. Add an author-UUID detail endpoint whose authority is the database publication chain plus the strict managed manifest, never a caller-supplied path.
2. Return only bounded logical relative nodes and allowlisted publication facts: layout/source/tree/manifest identities, publication Job identity, managed counts, freshness, drift state, protected-user-change state, pagination facts, and fixed allowed actions. Do not return export roots, host paths, raw Job payloads, exception text, locators, source URLs, or file bytes.
3. Inspect manifests and managed files under an existing-only per-author lock and fail closed on malformed manifests, links, path escapes, case collisions, missing files, size/hash drift, replacement races, or inconsistent publication chains. A page reports its exact verification scope and never upgrades partial work to whole-tree health. Inspection is read-only and performs no repair, deletion, lock creation, or directory creation.
4. Add one immutable environment-owned media-server profile for `emby` or `jellyfin`. The API exposes a hand-built safe summary only; API-key values and complete secret references never cross into API responses, logs, operation payloads, or SQLite.
5. Media-server requests may reach only the configured canonical origin and operator allowlisted IP/CIDR ranges. Requests cannot supply URL, host, key, path, library, or network-policy overrides. Every DNS answer must be allowed, resolution and connection are pinned, redirects are rejected, time/header/body/item limits are enforced, and private/loopback targets require explicit deployment configuration.
6. Persist connection probes and manual scan triggers as closed `media-server-probe` and `media-server-scan` Operations with idempotency and a per-profile exclusive key. Scan is disabled by default, targets only the configured library, observes cancellation at safe boundaries, and records only allowlisted evidence. A crash without durable remote completion evidence becomes `interrupted`, never a false success.
7. Upgrade Library, Settings, and Jobs views to show the real managed tree, safe connection posture, durable probe/scan activity, and qualification evidence. Local export success, request acceptance, and mocked tests must not imply a live scan or playable sample.
8. Add migration, unit, integration, API, Web, security, and packaging coverage. Existing Emby export, content/asset explorer, operation/event, migration, and Web contracts remain compatible.

## Qualification boundary

This execution may prove local manifest/tree behavior and fake or mocked Emby/Jellyfin protocol behavior. No server URL, API key, or library ID is currently configured in this workspace. Real server connection, version/library discovery, scan completion, item lookup, playback, automatic scan, Linux deployment evidence, and every seven-platform live-account/CDN row remain `NOT_RUN` until an operator performs them on an authorized deployment.

## Deferred

Operator authentication, browser-writable settings, multiple media-server profiles, destructive cleanup, retention, orphan repair, forced overwrite of changed files, automatic export-to-scan chaining, and final legacy-console removal remain outside Execution 0054. They stay with Execution 0055/0056 or a separately planned follow-up.
