**English** | [中文](plan.zh.md)

# Execution 0054 Phase B plan

- Status: Planning baseline frozen; implementation not started
- Plan date: 2026-09-05
- Baseline: `4945df1`
- Predecessor: Execution 0054-A
- Planned database revision: none

## Baseline and frozen decisions

Execution 0054-A already provides one immutable environment-owned server profile, exact Library discovery, an SSRF-resistant connector, durable targetless `media-server-probe` and `media-server-scan` Operations, an accepted-only targeted refresh, SSE progress projection, and redacted Library/Settings/Jobs surfaces. Its empty-object `{}` scan request and result `scan_state=accepted` are public compatibility contracts and remain valid.

Phase B preserves `POST /api/v1/media-server/scan` with `{}` as the existing acceptance-only request. That legacy mode remains targetless. The same route additionally accepts exactly `{"author_id":"<uuid>"}` for the new observation mode, whose Operation targets that author. Explicit null, unknown fields, and every remote selector remain invalid. The two shapes share the existing Operation kind and profile-exclusive domain but have distinct request fingerprints and result contracts.

Official Emby/Jellyfin APIs expose no durable task ID for targeted item refresh. Phase B therefore freezes `provider_task_completion` as unsupported and implements only an absent-to-unique-match `post_refresh_item_observation`. No Scheduled Task, idle-state, WebSocket, timestamp, or Etag heuristic may be promoted to completion.

## Delivery sequence

1. Commit the bilingual Phase-B planning baseline separately from implementation, with pre-existing untracked `.mimosa/` excluded.
2. Add an internal publication-target resolver. Given only an author UUID, it resolves the unique current successful publication head, validates its complete strict manifest, derives the deterministic server path and provider key/value, and returns only in-memory selectors plus safe fingerprints.
3. Extend the provider-neutral port with a bounded read-only item lookup result: complete `not_found`, complete unique `matched`, ambiguous, or incomplete. Keep raw selectors and response objects inside the connector.
4. Split request templates by provider. Implement filtered Emby lookup and exhaustive bounded Jellyfin lookup, including response-shape, pagination-consistency, uniqueness, cumulative-budget, and exact local matching checks.
5. Close the query-log boundary before enabling lookup. Dependency wire records for selector-bearing requests become fixed messages; raw and encoded query values are never retained.
6. Add the author-scoped lookup GET and its safe response. It remains synchronous and bounded and does not create a new Operation kind.
7. Extend the existing scan request parser with the two exact body shapes. Keep `{}` acceptance-only behavior; orchestrate author mode as baseline lookup, one refresh dispatch, durable accepted checkpoint, and bounded observation polling.
8. Extend `OperationRepository` and `OperationCoordinator` with a lease/revision-fenced running-result checkpoint; this is not a current capability. Add phase-aware cancellation, final CAS, and restart reconciliation. The transition writes durable accepted or observed evidence to the existing `result_summary` JSON and reuses `operation_phase_changed`; it adds no Event kind, table, or migration.
9. Update Library and Jobs: retain the top-level accepted-only refresh, add author-row “refresh and verify” only for a current complete publication, and label acceptance, observation, unknown completion, and playback separately.
10. Update qualification schema and bilingual architecture/deployment/security material only after focused and complete implementation gates pass. Mocked evidence does not change live status.

## Lookup contract

The resolver authority is the tuple of author UUID, publication-scope identity, deterministic output identity, unique successful predecessor-chain head, source/tree/manifest fingerprints, and a complete strict manifest. Neither an `ExportRecord`, a caller path, nor a filesystem discovery is sufficient alone. Resolution is repeated immediately before remote mutation; changed authority aborts before POST.

The server selector is:

- provider key: `media-sync-{platform}-creator`;
- provider value: the stored author remote ID;
- path: the exact configured server Library root plus the deterministic single-segment author directory;
- parent: the configured Library item ID.

Joining uses the configured server path syntax rather than the host operating system. An ambiguous or unrepresentable path style fails before network activity. Provider values that cannot be represented losslessly in Emby's AnyProviderIdEquals token may omit that server-side optimization, but Path filtering and a complete locally verified dual match remain mandatory.

Emby sends one `GET /Items` with `Path`, `AnyProviderIdEquals` when lossless, `ParentId`, `Recursive=true`, fixed `Fields=Path,ProviderIds`, `EnableImages=false`, `EnableUserData=false`, `StartIndex=0`, and `Limit=2`. A reported total beyond the returned bounded set, malformed count, or filter-outside response that prevents complete uniqueness is incomplete.

Jellyfin sends locally indexed `GET /Items` pages with `parentId`, `recursive=true`, `fields=Path,ProviderIds,Etag`, `enableImages=false`, `enableUserData=false`, `enableTotalRecordCount=true`, `startIndex`, and `limit=128`. It sends neither Path nor AnyProviderIdEquals. Total count and start index must be present, nonnegative, and stable; item IDs must be unique across pages; a complete pass must account for the advertised total. One bounded restart may handle a changing enumeration; otherwise it is incomplete.

Every candidate requires exactly equal derived path, exactly one canonical provider-key entry, exactly equal provider value, and a bounded nonempty item ID. Zero exact matches after a complete pass is `not_found`; one is `matched`; two different item IDs are `media_server_item_lookup_ambiguous`. Duplicate pages, duplicate IDs, unstable counts, missing required fields, or exhausted limits are `media_server_item_lookup_incomplete`.

## Scan and Operation contract

Both request modes reuse `media-server-scan`, the existing profile-exclusive key, idempotency handling, lease fencing, Event stream, and result-size boundary.

For `{}`:

- keep `target_type` and `target_id` null, preserve the exact 0054-A request fingerprint parameters `{profile_fingerprint}`, and preserve the accepted-only result shape for old clients and idempotency replay;
- discover the configured Library, dispatch exactly one provider-specific refresh, persist `accepted`, and finish succeeded;
- do not perform item lookup or imply observation.

For `{"author_id":"<uuid>"}`:

- create the Operation with `target_type=author` and `target_id=<author UUID>`; use request parameters `{profile_fingerprint, mode=post_refresh_item_observation, publication_fingerprint}` so the target and parameters together bind the request identity without changing the legacy fingerprint;
- use the existing target relation for the author and atomically attach the publication Job as a `related` subject before worker start;
- require a complete baseline; ambiguous/incomplete baseline sends no POST;
- an absent baseline is eligible for observation success;
- an already-matched baseline terminates before POST as `media_server_scan_observation_precondition_failed`; response guidance points an operator who wants only a manual refresh to the preserved legacy `{}` request.

Phases are `preparing → baselining → dispatching → accepted → polling → observed` for observation mode. Acceptance-only mode may omit baselining/polling/observed. `dispatching` is persisted before transport entry. After validated 2xx, `accepted` and its safe checkpoint are persisted to the existing `result_summary`; after the second confirming lookup, `observed` and its safe checkpoint use the same field. Both checkpoint transitions reuse `operation_phase_changed`. Progress increments verification `steps` with `total=null`; it does not estimate remote work.

Terminal rules are:

| Last authoritative fact | Terminal result |
| --- | --- |
| cancellation or failure before transport entry | `cancelled` or classified pre-dispatch failure; POST count zero |
| author baseline already matched | `failed_terminal / media_server_scan_observation_precondition_failed`; POST count zero |
| transport entered, trusted 2xx not established | `failed_terminal / media_server_scan_acceptance_unknown` |
| trusted 2xx and acceptance-only mode | `succeeded`, existing accepted result |
| trusted 2xx, absent baseline, same unique item observed twice | `succeeded`, accepted plus `absent_to_unique_match` observation |
| trusted 2xx, but observation cannot be proved | `failed_terminal / media_server_scan_completion_unknown`, accepted checkpoint retained |

The POST is never retried by transport, connector, coordinator, idempotency replay, restart reconciliation, or UI. Read-only lookup attempts may retry only inside the frozen aggregate budget.

Restart reconciliation uses the author target, publication Job subject, and durable phase/checkpoint:

- `preparing` or `baselining`: pre-dispatch interrupted; a new manual request is safe.
- `dispatching`: terminal acceptance unknown, non-retryable.
- `accepted` or `polling`: terminal completion unknown with the accepted checkpoint retained, non-retryable.
- `observed` before final CAS: succeed only when the stored observed checkpoint is valid; otherwise terminate completion unknown while retaining any accepted evidence.
- legacy targetless `{}` scans keep the 0054-A conservative reconciliation behavior unchanged.

Every phase/checkpoint/final transition uses revision, lease owner, lease token, and an authoritative locked read. Cancel-before-entry prevents POST; after entry it cannot rewrite the result to cancelled. Once a trusted 2xx is known, the accepted checkpoint may persist despite a concurrent cancel because acceptance is authoritative. A cancel that wins the locked race before the observed checkpoint blocks that checkpoint and yields completion unknown; an observed checkpoint that wins first survives any later cancel or finalization race. Coordinator exception and generic finalization paths must retain an accepted summary, must never replace it with `{}`, and must never make post-dispatch work retryable.

## API and Web contract

`POST /api/v1/media-server/scan` is a strict union of the legacy empty object and the author observation object. Responses continue to be 202 Operation submissions. An idempotency key replay returns the same Operation; the same key with a different mode, author, profile, or publication conflicts.

`GET /api/v1/media-server/items/by-author/{author_id}` returns schema version, author UUID, provider, Library digest, publication/selector digest, `matched|not_found`, exact match count, optional domain-separated item digest, observed time, and `complete=true`. It returns no selector component or remote payload and carries `Cache-Control: no-store`.

The scan result keeps the legacy exact shape for acceptance-only rows. Observation rows use a separately validated safe shape containing `scan_state=accepted`, observation state/evidence, profile/Library/publication/selector digests, optional item digest, match count, and observation time. Existing stored rows remain readable; API and qualification schema versions increase when their public shapes change, without implying a database migration.

The Library header retains “targeted refresh — acceptance only.” An author row exposes “refresh and verify” only when server-provided allowed actions confirm a current complete publication and no profile-exclusive Operation is active. Jobs renders phase and “verification N” without a percent bar. Copy states explicitly: “accepted is not observed,” “observed is not provider task completion,” and “observed is not playable.”

## Security and limits

Every request resolves all current DNS answers, requires all of them inside the configured CIDR policy, pins the chosen address, preserves Host and TLS SNI, disables environment proxies and redirects, and never follows a server-provided URL. The API key is resolved at the final request boundary and appears only in `X-Emby-Token`.

Per response, retain the 0054-A caps of 64 headers, 8 KiB per header line, 64 KiB total headers, 256 KiB body, JSON depth 8, 2,048 JSON items, and 4,096 characters per string. Phase B adds 128 Jellyfin rows per page; 32 pages, 4,096 unique items, and 8 MiB per lookup pass; 128 pages, 16,384 inspected rows, and 32 MiB per observation Operation; a 120-second observation deadline; at least two seconds between polls. These are hard defaults owned by deployment code, may be lowered by bounded operator settings, and cannot be supplied by API requests.

No raw path, provider value, remote item ID, Etag, header, body, remote error, credential, or complete secret reference enters structured logs, Operation request/result/event JSON, SQLite, SSE, API responses, support bundles, or Web state. Digests are domain-separated and bound to high-entropy profile/publication context rather than exposing a standalone digest of a low-entropy remote ID.

The profile-exclusive database key serializes durable probe, legacy scan, and author-observation scan Operations only. The direct author lookup is an independent read-only snapshot protected only by the connector's process-local gate; it has no database exclusivity, cross-process correlation, or status relationship with a scan Operation.

## Verification plan

- Provider matrix: Emby 4.8.10/4.9.5 and Jellyfin 10.10.7/10.11.11 exact routes, parameters, casing, pagination, 200/204 acceptance, and forbidden fallback routes.
- Lookup truth table: path-only/provider-only/near matches, zero/one/multiple identities, duplicate pages, changing totals, filter violations, malformed DTOs, and complete-versus-incomplete outcomes.
- Observation: absent then same unique item twice; one match then disappearance; changing item ID; existing baseline with changed/unchanged Etag; exhausted observation; and no false success.
- Mutation boundary: cancellation/deadline before entry, entry-first races, every post-entry transport/status/cleanup ambiguity, durable accepted checkpoint, one POST maximum, and no retry.
- Security: mixed DNS answers, rebinding on every page, IP pinning, Host/SNI, proxy/redirect/next-link rejection, header-only credential, raw and percent-encoded selector sentinels, malicious remote bodies, and support-bundle scans.
- Persistence: idempotency across both request shapes, subject links, legacy-row reads, phase-aware reconciliation, SQLite and real PostgreSQL cancel/final/checkpoint races, lease loss, and one terminal Event.
- Web: both scan actions, author gating, SSE replay, no stale response overwrite, truthful labels, no fake percentage, and safe unknown-detail rendering.
- Regression: current connector, Operation, migration, API, qualification, Library, Jobs, full Python and Web quality gates, distribution, docs, upstream, tracked-output, host-path, secret-pattern, and whitespace checks.

## Database and rollback

No schema migration is planned. Alembic remains at revision `0007`: its existing vocabulary already permits an author Operation target, author and Job subjects with `target` and `related` roles, the existing `result_summary`, and the reused `operation_phase_changed` Event code. Phase B adds no database kind, state, Event kind, subject type, role, table, column, or constraint value. A new lookup Operation kind, a remote task/baseline table, or resumable polling that requires a richer durable checkpoint would require a separately reviewed migration.

Rollback before any Phase-B code commit is deletion of only this planning directory. After implementation, rollback must preserve all 0054-A accepted-only rows and Phase-B observation rows. An old binary must never take over an active author-observation Operation; wait until every such row is terminal or deploy a binary with compatible reconciliation before rolling back. Public-payload compatibility is handled in application decoders rather than by deleting audit evidence. The pre-existing untracked `.mimosa/` directory and all normal runtime/generated outputs remain excluded from every commit.
