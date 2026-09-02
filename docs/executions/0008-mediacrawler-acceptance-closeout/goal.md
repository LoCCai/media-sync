**English** | [中文](goal.zh.md)

# Execution 0008 goal

- Status: Complete for the offline acceptance scope
- Started: 2026-08-30 15:48 +08:00
- Completed: 2026-08-30
- Predecessor: Execution 0007 implementation commit `d071618`
- Network boundary: offline fixtures and repository-owned local helper processes only

## Outcome

Close execution 0007 acceptance criteria 6 and 13 without expanding the product surface. Execution 0008 must prove the two remaining cancellation windows deterministically and complete a closed failure-type × retained-filesystem/SQLite/operator-sink secret matrix. It may repair races exposed by those tests, but it does not implement signed-locator refresh, real media retrieval or an automatic downstream DAG.

## Acceptance criteria

1. All implementation and verification stay offline. Tests may start only repository-owned helper processes that perform no browser or network work. No real secret reference, platform/CDN endpoint, Emby/Jellyfin server or Git remote is used.
2. A deterministic child-exit/pre-seal barrier cancels after a real helper child has returned `0` and the complete process tree has joined, but before `write_completion_receipt()` begins. No receipt is published, normalization/ingestion never starts, the runner reaches a definite cancelled verdict before unwind, the ordinary attempt root is secured, and the account/profile lock is reacquirable.
3. A deterministic post-seal/pre-ingest barrier cancels after a valid receipt exists but before ingestion starts. The handler joins any active normalization/security task before propagating cancellation; no Content/Asset is created, the checkpoint does not advance, the SyncRun does not become succeeded, and the ordinary attempt root is secured. Repeated cancellation must not make the outer task unwind early.
4. The closed failure set is exactly `known_secret_echo`, `nonzero_exit`, `timeout`, `output_bytes`, `output_items`, `output_files`, `output_line_bytes`, `output_tree`, `receipt_rejected`, `cancellation` and `lease_loss`. Every case injects a unique generated sentinel into attempt-private output before its failure is observed.
5. Every failure case verifies all three sink classes in the same case: retained filesystem, SQLite, and operator output. Ordinary active attempt roots end `ABSENT` or `REMOVED` and the retained safe tree has no sentinel; every SQLite text/JSON value and retained database file has no sentinel or scheduler authority inconsistent with the documented terminal/fenced state; serialized results, CLI/captured output, and exception/result `str`/`repr` have no sentinel, lease token, local root or raw cleanup error.
6. A matrix-completeness test proves set equality for `required_failure_cases × {filesystem, sqlite, operator}`. Adding or removing a failure type without updating all three sink assertions must fail collection or the focused gate.
7. `QUARANTINED`, `UNRESOLVED` and the persistent browser profile remain explicit credential-bearing negative boundaries, not false whole-tree zero-match evidence. Quarantine may retain a sentinel only below the ignored restricted quarantine root. Unresolved cleanup must attempt to persist fixed redacted markers and must hard-fence later secret resolution, run attachment, bridge preparation and spawn whether marker persistence succeeds or fails; a successful marker write remains durable. Paths and raw cleanup errors never enter operator output.
8. Fixed failure semantics remain unchanged: nonzero exit maps to `temporary_upstream`; timeout to `upstream_timeout`; output, receipt and secret rejection to `output_security_failed`; cancellation and lease loss propagate fencing and the stale handler never finalizes.
9. Execution 0007's four records remain historical `PARTIAL` evidence. Execution 0008 alone records the successor closeout. Manifest v2/receipt v1 compatibility stays byte-exact, read-only and manual-ingest/shared-normalization-only; scheduled recovery still trusts v3 only.
10. Ruff, format, strict mypy, the full branch-aware suite, the focused cancellation/matrix gate, build, packaged migrations/resources, documentation, upstream pins, patch checks, ignored/untracked-runtime checks and a fresh retained-artifact sentinel all pass with exact recorded results.

## Truth boundary and non-goals

- Execution 0008 closes only offline acceptance evidence. It does not promote any live login, creator traffic, scheduled platform run, CDN retrieval or Emby/Jellyfin row.
- Signed-locator refresh remains execution 0009 scope. Current successful sealed attempt JSONL may contain an unknown expiring signed query that the parent could not pre-register as a known secret; that crash-recovery artifact is an explicit credential-bearing temporary boundary until execution 0009 implements terminal cleanup/isolation as part of refresh.
- Automatic `sync → download → Emby` planning remains execution 0010 scope. The current `adapter_refresh.key` is one-way and the download entry point lacks the required subscription/account/license context, so execution 0008 does not create blocked downstream Jobs.
- `wb`, `tieba` and `zhihu` currently normalize no downloadable assets; this is unavailable/deferred functionality, not a successful or merely untested media-download claim.
- Phone login remains unsupported. Per-request HTTP spacing, bounded live pagination, QR/challenge presentation UX, REST, resident supervision, Docker, public deployment and HA/PostgreSQL remain unimplemented or deferred.
