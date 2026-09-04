**English** | [中文](plan.zh.md)

# Execution 0054 plan

- Status: Frozen for implementation
- Plan date: 2026-09-05
- Baseline: `22b5864`
- Planned database revision: `0007_media_server_operations`

## Baseline and decisions

`git pull --ff-only origin main` reports that `main` is current at `22b58646e79b17b2d49ff803df34e976466999c3`; only the pre-existing untracked `.mimosa/` directory remains. Execution 0053 already delivered safe content/asset catalogues and archive preview. Its `/api/v1/library` endpoint is only a database aggregate, while the Web page explicitly defers physical tree and media-server behavior.

The exporter already owns strict layout planning, a canonical `.media-sync-managed-v1.json`, per-author locking, complete hash validation, compare-and-swap publication, crash recovery, and protection of modified managed or unmanaged files. Whole-author publication identity lives in the successful `export.emby` Job predecessor chain; per-content `ExportRecord` rows alone are not authoritative for a tree. There is no media-server HTTP client or server configuration today. Operations and the database CHECK constraint have a closed five-kind vocabulary, so scan support requires one coherent migration and payload/coordinator update rather than an endpoint-only shortcut.

The frozen minimum is one environment-owned server profile. Browser-writable configuration is unsafe before operator authentication and is therefore deferred. Connection tests and scans accept no remote target in their request bodies. A scan success means only that the configured server accepted the targeted refresh request; live completion and playback remain separate `NOT_RUN` qualification rows unless real operator evidence is later recorded.

## Delivery sequence

1. Commit this bilingual goal, plan, in-progress journal, and pre-change verification baseline before implementation.
2. Add public immutable exporter inspection models and a read-only inspection method. Reuse canonical manifest parsing, path checks, same-descriptor hashing/identity checks, and fixed drift classifications without exposing private filesystem objects. Add a separate existing-only author-lock primitive: unlike publication locking it must never call `mkdir`, `O_CREAT`, recovery, or cleanup.
3. Add an application read service that resolves an author UUID, current exportable source fingerprint, publication-scope identity, and the unique successful publication-chain head. It returns `not_published`, `current`, `outdated`, `drifted`, or `inconsistent` with bounded stable file pages and fixed allowed actions.
4. Keep `GET /api/v1/library` byte-compatible and add `GET /api/v1/library/{author_id}` with bounded offset/limit. The response is explicitly projected and contains logical author-relative paths only. Each file page is hash-verified; the response distinguishes `page` from `complete` integrity so pagination or an inspection byte/file budget can never imply unchecked files are healthy.
5. Extend immutable Settings with an all-or-none media-server profile: provider, canonical base URL, library ID, API-key secret reference, server-side library path mapping, explicit allowed IP/CIDR ranges, TLS verification, bounded timeout, and a default-off scan gate. Add a safe configuration summary that omits the secret reference, network ranges, and local host paths.
6. Add a provider-neutral, mockable media-server connector. Resolve the configured secret only at the request boundary; pin DNS to connection; preserve Host/SNI; disable environment proxies and redirects; enforce exact origin, HTTP method/path allowlists, bounded response sizes, fixed JSON schemas, and safe error codes. Support server information, virtual-folder discovery, and one configured-library refresh for both Emby and Jellyfin-compatible APIs.
7. Add `media-server-probe` and `media-server-scan` to the closed operation contracts, ORM constraint, request/result allowlists, recovery policy, API labels, and migration `0007_media_server_operations`. Both are targetless, profile-fingerprinted operations; the scanner uses one profile exclusive key and checks cancellation before every network phase. Restart reconciliation is conservatively `interrupted` because there is no durable remote task identity.
8. Add `GET /api/v1/media-server`, `POST /api/v1/media-server/probe`, and `POST /api/v1/media-server/scan`. The first is network-free; the POST routes submit durable work and never accept URL/key/path/library overrides. Include only latest allowlisted Operation evidence in the status projection.
9. Add a qualification projection. Seven-platform live rows remain explicit `NOT_RUN`; local content/archive/export counts are shown as automated evidence only. Media-server probe and scan-trigger evidence links to exact Operations, while scan completion and sample playback remain `NOT_RUN` absent operator evidence.
10. Upgrade Library to inspect the actual managed tree and request export/probe/scan only when server-provided allowed actions permit it. Upgrade Settings with a redacted read-only profile summary and Jobs labels for the two new kinds. Put state/query derivation in tested pure TypeScript helpers.
11. Run focused security, exporter, application, API, migration, operation, and Web tests, then whole-repository Ruff/format, strict mypy, complete Python suite, Web format/test/check/build, compile/build, docs/upstream, tracked-output, host-path, whitespace, and push reconciliation gates.

## Frozen contracts

- Publication authority is `(author UUID, publication scope digest, output identity, unique successful Job chain head, manifest identity)`. Neither `ExportRecord.output_path` nor a filesystem scan alone can authorize a tree.
- The browser may address an author UUID and bounded page values only. It cannot submit a path, filename, URL, server host, library ID, remote path, key, or secret reference.
- Tree output lists only manifest-managed entries. Unmanaged entries are never made browseable. Drift classification may state that unmanaged or modified content blocks safe publication without exposing its name or bytes.
- A changed managed file is protected, not silently repaired. Destructive recovery remains unavailable in this execution.
- The media-server origin and allowed IP/CIDR ranges are canonicalized at startup and are the sole network authority. Every DNS answer must be inside the configured policy; cross-origin or any redirect is rejected before credentials can be forwarded.
- Secret material exists only in a `SecretValue` at the connector boundary. Exception messages, response samples, server bodies, and headers do not enter durable state.
- Probe/scan Operation summaries use fixed provider/state values, a conservative version string, a digest of the configured library identity, and counts/timestamps only. Server URL, library name/path, key/ref, request headers, response body, and remote error text are absent.
- `media-server-scan` means targeted refresh accepted, not completed or playable. The qualification view uses different labels for automated evidence and live qualification.

## Verification plan

- Exporter/application: golden tree, deterministic pagination and exact page/complete scope, current/outdated/not-published states, malformed manifest, wrong identity, missing/modified/replaced/link/case-collision paths, existing-only lock behavior, inspection budgets, no repair, no lock/directory creation, and non-disclosure sentinels.
- Configuration/connector: all-or-none validation, URL/CIDR canonicalization, exact origin and route methods, explicitly allowed private targets, all-answer network policy, DNS pinning, TLS modes, no proxy/redirect, auth header sink, timeout/header/body/item limits, malformed JSON, provider variants, missing/duplicate library, and secret/error redaction.
- Operations/migration/API: new kind constraints through fresh and upgraded SQLite plus PostgreSQL SQL generation where covered; request fingerprints, result summaries, idempotent replay, exclusive scan, cancel boundaries, conservative restart reconciliation, safe status projection, legacy library response compatibility, and no reads that mutate durable state.
- Web: tree grouping/paging, state/action derivation, qualification labels, no path/ref rendering, request races, operation links, format, Vitest, Svelte check, production build, and a local browser smoke against a fake API or bounded local test server.
- External: real Emby/Jellyfin, real playback, automatic scan, Linux host drills, accounts, platform APIs, and CDNs stay `NOT_RUN` in this workspace.

## Commit and rollback strategy

Use reviewable bilingual commits in this order: plan/baseline; library inspector; media-server connector; operation/API/migration; Web console; closeout evidence. Push each passing boundary to `origin/main`. The migration only widens an operation-kind CHECK and has an empty-database downgrade path; no destructive data migration is planned. `.mimosa/`, `.upstream/`, databases, secrets, archive/export/job runtime data, `node_modules`, Web build output, `.svelte-kit`, `dist`, caches, and XML reports remain excluded.
