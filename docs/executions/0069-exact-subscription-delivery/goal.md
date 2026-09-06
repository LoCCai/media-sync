**English** | [中文](goal.zh.md)

# Goal: exact subscription delivery

Turn the operator action for one selected subscription into one durable and observable chain: discover that subscription, claim only its exact scheduler Job, continue through the exact Run-derived pipeline Job, verify every required archive result, and publish the compatible local library directory without requiring an Emby or Jellyfin server connection.

This execution also records truthful per-feed history-scan evidence and fixes the reproduced Windows directory-pin weakness. It does not relabel a successful batch as complete history, does not silently drain another subscription, and does not claim that the four failing live QR logins are repaired.

## Acceptance criteria

1. A new durable `subscription-delivery` Operation targets one subscription and is started by `POST /api/v1/subscriptions/{id}/execute`. Its request identity is closed and redaction-safe, and its subjects persist the exact scheduler Job, SyncRun and pipeline Job identities.
2. The scheduler can materialize and claim an exact subscription cycle while preserving enabled/deleted state, schedule revision, global capacity, account/platform lane throttles, leases, retries and existing ownership reconciliation. It never falls through to another queued subscription.
3. The pipeline can claim only the coordinator derived from that exact succeeded scheduler Job and Run. Existing global scheduler and pipeline commands remain backward compatible.
4. The Operation returns a bounded typed receipt whose counts state their exact semantics: discovery rows, asset identities, selected active-author snapshot assets, newly finalized or reused verified archives, publication disposition, managed-file count and verified local-directory outcome. Worker completion alone is not delivery success.
5. Concurrent duplicate requests are idempotent or conflict on a per-subscription exclusive key. A supervisor race cannot create a second chain or cause the request to process unrelated work. Cancellation is only claimed before a next phase or after the currently entered fenced work has actually settled.
6. The subscription UI distinguishes “schedule earlier” from “execute discovery → archive → directory”, tracks the returned exact Operation, shows its stages and links to its exact Jobs/logs. The confirmation states that the current pipeline covers the author's active asset snapshot and does not contact a media-server API.
7. Migration `0013` expands the Operation kind constraint and adds per-subscription, per-feed scan-progress facts. Existing rows start `unproven`; no `last_success_at`, empty cursor or historical Run is backfilled as completion.
8. Bilibili uploads and dynamics may persist `scanning` or `source_end_observed` only from validated coverage committed with the successful Run/checkpoint transaction. The latter means only “the visible sweep observed an end”, remains subject to drift rescans, and is never exposed as permanent `history_complete`. The other six platforms remain `unproven` until real continuation evidence exists.
9. The Windows exporter opens its protected directory chain with `FILE_LIST_DIRECTORY`, retaining the existing no-delete sharing policy. A real Windows regression proves ancestor rename is denied while the pin is held and allowed after release; Linux behavior is unchanged.
10. Focused repository, migration, operation, API, web and real filesystem tests pass. A deterministic offline end-to-end case proves exact subscription → discovery → archive verification → compatible files, including zero-work replay and no configured media server. Live platform/CDN/server rows remain explicitly `NOT_RUN` unless new authorized evidence is produced.

## Deferred but unchanged product requirements

- Per-content publication so an unrelated failed historical asset cannot block a complete new content unit.
- Trustworthy bounded pagination and interruption-safe historical backfill for XHS, Douyin, Kuaishou, Weibo, Tieba and Zhihu.
- A stronger Bilibili stable-coverage or drift-reconciliation protocol before any permanent history-complete state.
- Controlled post-deployment diagnosis of one failed QR platform using execution 0068 logs; the previously stopped supervisor is not automatically resumed.

