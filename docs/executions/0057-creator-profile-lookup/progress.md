**English** | [中文](progress.zh.md)

# Progress

The previous goal turn completed 0056 publication and remote-consistency evidence and is classified as progress. Continue automatic profiles from the current clean `87ef7fd` baseline. Reviewed the upstream single-profile endpoint, shared-Author overwrite risk and existing Operation boundary, then froze this plan.

Committed plan `36e004d` before parallel implementation. The Bili saved-session source/UI slice and local verification are complete and published as `141f7c4`. A fresh fetch verified HEAD and origin/main both at `141f7c424226a1b7f8cdc97b24e3b43d61ae6f40`, divergence `0 0`, with a clean worktree before this publication-record update. Offline tests do not qualify a live platform.

## Implemented

- A standalone guardian supervises source verification, Chromium and one profile call. Authentication/WBI is bounded; content/dynamics/comments/QR fallback are forbidden. The shared account lock covers the entire child tree; uncertain cleanup retains the lock and a fixed incident.
- 0010 adds account-scoped profile/lookup tables, monotonic authentication revision and subscription notes, retaining existing Author names/URLs, archive paths, checkpoints and history. Concurrent insert-if-missing prevents a later account from overwriting an existing author.
- Double lease/cancel fences guard short transactions; profile publication and Operation success commit atomically. The second fence defines success time, with ORM revision refreshed before terminal CAS. Receipts bind exact operation/account/creator/revision/expiry; read-side errors use a fixed allowlist.
- One isolated ten-second process performs restricted public retrieval/decoding, without redirects/environment proxies, bounded to twoMiB/eight-million pixels/one frame, then stores metadata-free PNG in the database. Added locked Pillow dependency; CSP unchanged; failed avatars retain the older revision.
- Completed input queries once per identity generation without overwriting local notes. A valid success receipt permits creation without a note. List/detail views show both names, avatar and observation times. Browser review found ambiguous unacknowledged-license messaging; fixed to explicitly say no lookup started, without consuming the automatic opportunity or accepting the license.

## Remaining

The full offline checkpoint completed with 3972 passed, 22 skipped and 1 warning in 852.47s; after final hardening, the frozen-source union passed 575 tests in 109.47s. These are separate, overlapping runs, not a second complete final-source run. Final Web verification passed 492 tests in 19 files with check/format/build passing. See [verification](verification.md) for static/package checks and publication status.

Browser checks cover normal test login, browse-only and preloaded synthetic profiles, without accepting a license or submitting lookup/creation through UI. Independent API tests cover the write loop; controller tests cover the gate-message fix, whose browser recheck is incomplete. The dedicated tab and verified temporary server are closed.

Six other platforms/Cookie profiles, pasted-Cookie validation/private storage/reuse, correct bounded Bili coverage, live capture/archive/media-server qualification remain open. No production deployment or supervisor restart; the historical zero-content Bili failure is not requalified.
