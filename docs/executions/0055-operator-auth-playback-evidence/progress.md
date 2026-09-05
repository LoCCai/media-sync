**English** | [中文](progress.zh.md)

# Execution 0055 Phase A progress

- Status: Planning baseline prepared; implementation not started
- Date: 2026-09-05
- Baseline: `d0a8cc2`
- Planned revision: `0008_playback_evidence`

## Completed in the planning checkpoint

1. Fetched `origin/main`; local and remote `main` both resolved to `d0a8cc2`, with no incoming commit to merge.
2. Read the 0053/0054 handoff, roadmap, status, architecture, deployment, operations, security review, and qualification source. The original product goal remains unchanged: seven-platform login/subscription/capture with Emby/Jellyfin-compatible output.
3. Inventoried the current FastAPI surface: 51 routes are anonymous, including business reads/writes, QR and archive bytes, SSE, support/deep readiness, docs/OpenAPI, `/legacy`, and the SPA fallback.
4. Confirmed the browser compatibility constraint: EventSource and direct QR/archive/media/navigation requests cannot safely carry an Authorization header, and tokens must never enter URLs. The frozen browser design therefore uses an HttpOnly same-origin session plus CSRF, while optional automation uses a separate Bearer header.
5. Reused existing typed secret references/redaction, publication authority, selector/item fingerprints, SQLite writer reservation, and PostgreSQL unique-lock behavior instead of creating parallel authority.
6. Froze one append-only playback-evidence table and a server-side resolve → lookup → resolve confirmation flow. Accepted refresh, item observation, provider completion, and human playback remain four distinct facts.
7. Explicitly excluded writable settings, multiple profiles, retention/deletion/repair, automatic scan chaining, multi-user auth, and real qualification from this slice.

## Not yet implemented

- No auth setting, middleware, login/session/logout endpoint, cookie, CSRF, Bearer token, rate limiter, or Web login shell exists yet.
- Revision 0008, the evidence repository/service/API, observation fingerprint, qualification schema v3, and Web confirmation UI do not exist yet.
- No implementation test or live credential/server flow has run for 0055-A. Playback remains `NOT_IMPLEMENTED` at this planning baseline and live status remains `NOT_RUN`.

## Next checkpoint

Commit the bilingual planning baseline, then implement the authentication configuration/runtime and deny-by-default route boundary first. Evidence persistence begins only after the control plane is authenticated.

The pre-existing `.mimosa/` directory remains untracked and excluded.
