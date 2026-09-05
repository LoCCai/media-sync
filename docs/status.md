**English** | [中文](status.zh.md)

# Unified project status (single source of truth)

The pushed execution 0055 backend-authentication implementation is commit `f19bfaa` (the frozen planning baseline is `4564b2a`). It resolves a required typed operator credential before bind, supports an optional distinct Bearer credential, enforces exact Host/Origin policy, rotates a process-local HttpOnly `SameSite=Strict` session cookie, requires CSRF on unsafe cookie-authenticated methods, applies deny-by-default ASGI protection with an exact anonymous allowlist, accepts only strict bounded login JSON, and wires the credential/origin contract into Docker Compose. Its 190-test auth/API focus and complete offline regression (`2811 passed, 14 skipped, 1 warning in 561.43s`) pass, as do 69 Web tests and all locally available static/build/docs/package gates. Three skips are Windows/POSIX differences; 11 real-PostgreSQL races and Docker validation were unavailable on this workstation and are not claimed.

Confirmation is published as `13de3b7`. The current [projection checkpoint](executions/0055-operator-auth-playback-evidence/evidence-projection/progress.md) adds bounded author evidence reads and qualification schema v3. A complete fresh lookup with stable publication/profile authority precedes a short read transaction; current evidence is queried independently, history defaults to 20 rows with a maximum of 50, and at most `limit + 2` ledger rows are materialized. History-page truncation does not invalidate the independent current row; remote lookup truncation prevents PASS. Remote uncertainty makes history unknown; complete absence makes it stale. Only exact durable attestation can yield author-scoped PASS. With no author, scope is `not_requested` and no evidence or remote query runs. Web login/session/CSRF and confirmation UI remain pending. Checked-in live qualification stays `NOT_RUN`; provider completion and automatic scanning stay `NOT_IMPLEMENTED`. See [current verification](executions/0055-operator-auth-playback-evidence/evidence-projection/verification.md). Execution 0047 remains the operator gate.

Follow the [delivery priority addendum](executions/0055-operator-auth-playback-evidence/delivery-priorities.md): secure Web login/session/CSRF and credential/pre-migration validation, then the current Linux image and authorized Bilibili/XHS canaries. Minimal evidence UI does not block an existing-CLI live flow.

## Milestone status

| Milestone | Status |
| --- | --- |
| Offline feature work | Platform shapes frozen at the 0039 boundary plus 0040/0044 operations and the 0050 Console v2 control-plane foundation; 0043 (danmaku/subtitles) remains deferred |
| REST API + web console | Authenticated author evidence reads and qualification v3 join the existing library, observation and task workflows. Console v2 and `/legacy` still need login/session/CSRF and confirmation UI before they are usable administration clients |
| Operator authentication + playback evidence | Backend authentication, immutable identity/ledger, browser-only confirmation, bounded current/stale/unknown projection and qualification v3 are implemented. Without exact current evidence playback is IMPLEMENTED/NOT_RUN; PASS applies only to the selected author. Web integration is pending; live playback is NOT_RUN |
| Docker packaging | Historical candidate images and Console v2 multi-stage builds were delivered in 0041/0048–0050; that repaired image passed doctor, deep readiness and Chromium launch. The current 0055 auth-aware image remains unexecuted; historical PASS cannot be reused |
| Operations docs / security review / release checklist | Delivered (0045, 0046) |
| Live qualification (final gate) | Open — execution 0047, operator-assisted on Linux |

## Verification matrix

| Dimension | State | Evidence / blocker |
| --- | --- | --- |
| Implementation (offline shapes) | 15+ frozen shapes across seven platforms | Executions 0013–0039 records |
| Offline complete suite | Current projection: 2999 passed, 22 skipped, one warning in 613.66s; focused union: 220 passed, one warning in 51.09s. Exact results are in [verification](executions/0055-operator-auth-playback-evidence/evidence-projection/verification.md); skipped PostgreSQL cases are not execution evidence | Execution 0055 projection record |
| API/console tests | Current projection/confirmation/API/auth/qualification/SQLite union passes 220 tests, including safe bounded author reads and the 59-route inventory. Web passes 69 tests plus format/check/build, without claiming the missing login/CSRF, confirmation UI or real frontend/backend browser smoke | Execution 0055 projection verification |
| Static and distribution gates | Current Ruff/format, mypy, compileall, Web, docs/upstream and wheel/sdist results and counts are in the [verification](executions/0055-operator-auth-playback-evidence/evidence-projection/verification.md) | Execution 0055 projection record |
| Docker image build | The 0050/0047 image preflight remains historical PASS. Current 0055 auth-aware Compose wiring is code-reviewed but `NOT_RUN` because Docker CLI is unavailable on this workstation | Executions 0050/0047 and 0055-A verification |
| Container readiness / restart persistence / backup-restore drill | Old-image deep readiness is historical `PASS`; current-image readiness, restart persistence and backup/restore are `NOT_RUN` | Execution 0047; docs/operations.md procedures ready |
| Live login (any platform) | `NOT_RUN` — operator (Phase C canary: Bilibili + XHS) | Execution 0047 |
| Live crawl / download / incrementality | `NOT_RUN` — operator (Phases C–E) | Execution 0047 |
| Real Emby/Jellyfin connection, Library discovery and targeted-refresh acceptance | `NOT_RUN` — implemented in 0054-A but no authorized server was used | Executions 0054 and 0047 |
| Provider/path item lookup and post-refresh item observation | `IMPLEMENTED / NOT_RUN` — local/mock gates pass, but no authorized real Emby/Jellyfin server was used | Execution 0054-B verification |
| Provider task completion | `NOT_IMPLEMENTED` — the common Emby/Jellyfin refresh APIs provide no durable task identity; phase B does not claim it | Execution 0054-B truth boundary |
| Operator access control | `IMPLEMENTED / offline verification PASS` — the backend fails before bind without its required typed credential, enforces exact Host/Origin plus deny-by-default route protection, and supports a rotating HttpOnly session with CSRF plus an optional distinct Bearer credential. The 190-test focus and complete locally available suite pass. Web login/session/CSRF integration remains pending, so no operable authenticated console or live qualification is claimed | Execution 0055-A [goal](executions/0055-operator-auth-playback-evidence/goal.md) and [verification](executions/0055-operator-auth-playback-evidence/verification.md); implementation commit `f19bfaa` |
| Playback identity / persistence / confirmation backend | IMPLEMENTED and offline verified in `13de3b7`; the read/qualification checkpoint now consumes the ledger. Real PostgreSQL races remain NOT_RUN on this workstation | Execution 0055 |
| Evidence projection and qualification / automatic scan | Author evidence and schema v3 are IMPLEMENTED. No selected author or no exact current evidence is NOT_RUN; incomplete/uncertain remote authority cannot grant PASS. Automatic post-export scan stays NOT_IMPLEMENTED | [Projection plan](executions/0055-operator-auth-playback-evidence/evidence-projection/plan.md) |
| External security audit | `NOT_RUN` — optional | docs/security-review.md residual risks |

## Release blockers (v0.1.0-rc1)

1. P0: secure Web login/session/CSRF and credential/pre-migration validation remain incomplete. Minimal evidence/confirmation UI remains promised follow-up work but does not block existing-CLI live canaries; follow [delivery priorities](executions/0055-operator-auth-playback-evidence/delivery-priorities.md).
2. P0: the exact current commit/image Linux baseline is incomplete (runtime-user secret reads, migration boundary, complete suite, host ports, startup/restart persistence, backup restore and process baseline) — Phase B; old-image passes cannot substitute.
3. Zero live rows recorded — Phase C canary (Bilibili + XHS) then remaining platforms.

Minimum 0.1 release condition: at least the two canary platforms reach **Supported** (login, sync, download, true incrementality, Emby rescan + sample playback), every other platform honestly classified (Experimental / Metadata-only / Blocked External / Unsupported), and the project describes itself as "seven-platform adapter framework; see the status matrix" rather than "supports seven platforms".
