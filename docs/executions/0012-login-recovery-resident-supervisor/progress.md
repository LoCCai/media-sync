**English** | [中文](progress.zh.md)

# Execution 0012 progress

- Status: Implementation and offline closeout complete
- Started: 2026-08-31 03:46 +08:00
- Completed: 2026-08-31 04:54 +08:00
- Plan commit: `4494226`
- Implementation commit: `28655f8`

## Completed

- Audited the login runner, LoginSession repository/application flow, generic MediaCrawler parent-control implementation, Windows Job behavior and current bounded scheduler/pipeline CLI surfaces. No source files were changed during the audit.
- Located the critical persisted-state gap: hard parent death can leave `waiting_user` plus `qr/authenticating`, while current active-session lookup ignores `expires_at`.
- Located the lock/finalization ordering constraint: the runner releases the account lock before the application writes the terminal database transition. Recovery is therefore frozen to `expires_at <= now`, not mere lock availability.
- Re-ran the predecessor process baseline: three generic hard-parent-death plus login timeout/cancellation cases pass.
- Replaced EOF-delimited login input with a 4-byte big-endian request length, bounded payload and independent START/CANCEL/EOF control. Parent containment attaches before START; child containment and control watching exist before upstream import.
- Added the corresponding bounded result length frame. The parent can receive the authoritative result while the child guardian remains alive, then close control, join the entire tree and reject any appended bytes. This avoids the Windows standard-pipe EOF dependency and removes exit-code authority from an authenticated result.
- Added child-owned Windows Job/POSIX process-group supervision plus a post-result guardian. A deterministic real child/grandchild contract hard-kills the parent after result receipt but before control close and proves the complete tree exits before the inherited account lock can be reacquired.
- Added exact expired-session candidate enumeration and atomic recovery. Repository CAS revalidates session identity/status/method/challenge/deadline, Account adapter/platform/login/auth/credential/profile state and active siblings, rolling back both rows on any drift.
- Added the public `MediaCrawlerAccountLock` boundary and application reconciler. Global sweeps use a serialized rotating `(expires_at, id)` cursor so busy/conflicted early candidates cannot starve later accounts; exact account reconciliation does not share that cursor. Login start, login status and the resident supervisor all reach the reconciler.
- Added `media-sync scheduler supervise` with bounded configuration and stable per-process worker identities. Each fair cycle runs stale-login sweep, scheduler tick, subscription sync and pipeline work. The Fake SQLite integration reaches succeeded sync and pipeline Jobs in one cycle without separate bounded worker commands.
- Implemented phase-correct shutdown. The first signal requests cooperative stop; a repeated signal force-exits with `128 + signal`. Subscription work is cancelled and joined; one already-active thread-backed pipeline attempt stays heartbeat-protected and drains exactly. Both joins tolerate repeated task cancellation and propagate the first caller cancellation only after the exact attempt is done.
- Completed the root integrated focused gate, full suite, Ruff, format, mypy, documentation/upstream checks, build, patch check and retained artifact/secret audits. Exact evidence is in `verification.md`.

## Deviations and decisions

- The resident loop includes pipeline work for a functional full chain, but shutdown will drain one already-active synchronous attempt under heartbeat instead of claiming that asyncio cancellation stopped its worker thread.
- No schema migration or PID ownership column is planned. Exact durable identities, deadline CAS and the existing per-account filesystem lock are sufficient for the frozen single-host boundary.
- Windows does not deliver EOF for its standard stdout pipe while the guardian process remains alive, even after CRT descriptor 1 closes. The result protocol therefore uses explicit bounded length framing; process exit and standard-pipe EOF are not result boundaries.
- Recovery authority remains strictly `expires_at <= now`. A missing runtime account directory is unavailable rather than auto-created, and lock availability by itself never proves abandonment.
- Real QR/account/platform/CDN/Emby behavior is not inferred from offline process tests. All live qualification remains `NOT_RUN`.

## Remaining outside execution 0012

- Real QR/account/creator/CDN and Emby/Jellyfin qualification for all seven platforms remains `NOT_RUN` and requires user-authorized accounts plus human interaction where applicable.
- Automatic restart, Windows Service/systemd integration, Docker, REST, distributed HA and forced termination of synchronous pipeline threads remain future product work.
- Additional playable media shapes—especially Bilibili video beyond the currently supported cover—remain later functional slices.
