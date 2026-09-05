**English** | [中文](progress.zh.md)

# Progress

Implemented the first four-platform Cookie workflow: bounded request parsing, explicit remote self-account validation, account-scoped supervised processes, immutable managed credentials, migration 0011, atomic Account/Operation publication and the Accounts dialog. Rejected, cancelled, late, invalid or failed-save candidates preserve the existing credential. Publication rechecks Operation target, authentication identity/revision, lease and cancellation. Interrupted candidates cannot be automatically replayed after restart.

Private storage is separate from read-only Docker secrets. POSIX access is directory-handle-relative; Windows uses protected DACLs and pinned directory handles. Immutable old/unreferenced versions are retained to avoid deleting a committed credential after an ambiguous acknowledgement. Explicit runtime resolvers cover scheduler, capture, detail download and Bili creator profiles.

Cookie capture/detail uses fresh nonpersistent browser contexts with complete injection, preserving equals signs and lawful outer quotes. Bili single-creator profiles now accept validated Cookie accounts through private frames; saved-session behavior remains separate. Zhihu signing explicitly uses Node pipes, not Windows JScript temporary files. Bounded JSON transport rejects compressed or wrong-type responses before reading the body.

Web clears input on close/submission/logout/account switch, requires explicit replacement of authenticated accounts, binds responses to account/platform/session/generation/Operation/revision and distinguishes rejection from an unknown outcome. QR stays separate; DY/KS/Tieba paste validators are explicitly unavailable. Synthetic browser inspection confirmed entry points, license gate, replacement warning, clean close/reopen and readable narrow-panel layout. No license was accepted and no remote validation was submitted through the browser.

The initial full-suite checkpoint exposed 53 failures, including old browser fixtures, migration expectations and a production support-bundle sensitive-word conflict. Corrections and their exact verification are recorded in [verification](verification.md); no failed checkpoint is presented as a pass.

Still required: reliable DY/KS/Tieba identity validators, creator profiles for the other six platforms, correct bounded creator-history coverage and authorized live login/reuse/capture/archive/Emby/Jellyfin qualification. The historical Bili zero-content/schema_invalid canary is not reclassified as fixed. No production deployment, subscription mutation, capture/download/export or supervisor restart occurred. This is progress, not completion of 0058 or the seven-platform goal.

Implementation `3dc8905` is published to origin/main with fresh-fetch equality and a clean implementation worktree. Complete offline directories passed4256 tests/23 skips and Web553; detailed timing, the final guard check and exclusions remain in verification. Next planned work is bounded Bili creator capture/root-cause qualification, followed by the remaining identity/profile and archive/playback gaps; no automatic live retry is implied.
