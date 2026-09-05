**English** | [中文](verification.zh.md)

# Execution 0055 Phase A verification

- Status: Planning evidence only; implementation verification not run
- Date: 2026-09-05
- Baseline: `d0a8cc2`
- Planned revision: `0008_playback_evidence`

## Evidence policy

Planning checks establish only that the next slice is scoped, reviewable, and based on current code. They do not prove authentication, authorization, playback, real-server compatibility, or migration behavior. Implementation evidence and authorized human qualification will remain separate.

## Planning baseline evidence

| Check | Command or source | Status |
| --- | --- | --- |
| Git synchronization | `git fetch --prune origin`; compare `HEAD...origin/main` | `PASS` — both at `d0a8cc2`, divergence `0 0` before planning edits |
| Initial worktree | `git status --short` | `PASS` — only pre-existing untracked `.mimosa/` after the 0054-B closeout |
| Prior frozen gate | Execution 0054-B verification | `PASS` — 2763 Python tests passed with 3 skips and 1 existing warning, including 11 real-PostgreSQL Operation races; 69 Web tests and all recorded quality gates passed |
| Route inventory | Inspect `create_api_app` and `app.routes` | `PASS` — 51 baseline routes; no auth dependency or middleware; sensitive route classes recorded in the goal/plan |
| Secret/redaction reuse | `config.py`, `security/secrets.py`, `security/redaction.py` | `PASS` — typed env/file/keyring references and value-safe wrappers exist; no operator auth setting exists |
| Publication/evidence reuse | Publication resolver, observation service, qualification schema v2, DB models/migrations | `PASS` — complete publication authority and safe item fingerprints exist; there is no authenticated playback ledger |
| Scope review | 0053/0054 remaining-work records and security review | `PASS` — operator authentication and playback evidence belong to 0055; destructive/writable administration remains separately unfrozen |
| Bilingual planning set | Review the four English/Chinese goal, plan, progress, and verification pairs | `PASS` — eight files preserve the same frozen scope and explicitly state that implementation has not started |
| Documentation and upstreams | `uv run --frozen python scripts/check_docs.py`; `uv run --frozen python scripts/check_upstreams.py` | `PASS` — 498 Markdown files have valid links and both locked upstream checkouts match their pins |
| Intended tracked set | Root generated/runtime denylist over the current 787 tracked files plus the eight new execution files | `PASS` — intended post-commit count is 795; no forbidden output is selected and pre-existing `.mimosa/` remains untracked |
| Confidentiality and workspace paths | Scan the 14 intended changed/new files for workstation paths, private-key/token forms, and assigned secret values | `PASS` — zero matches |
| Whitespace | `git diff --check` | `PASS` |

## Required implementation evidence

The exit gate requires exact passing evidence for:

1. Fail-before-bind credential resolution and non-loopback origin posture.
2. Full route-enumeration denial with only the frozen anonymous allowlist.
3. Browser session rotation/expiry/logout, cookie flags, CSRF, Host/Origin, Bearer, rate limiting, fixed errors, and secret non-retention.
4. QR, archive GET/HEAD/Range, EventSource, docs, legacy, and SPA behavior through authenticated cookies without URL tokens.
5. Observation-fingerprint stability/domain separation and every authority-context drift.
6. Resolve → unique lookup → resolve TOCTOU closure and zero-write failure paths.
7. Append-only revision 0008 constraints, natural replay, SQLite/PostgreSQL concurrency, RESTRICT parents, and guarded downgrade.
8. Qualification schema v3 truth: no evidence is `IMPLEMENTED/NOT_RUN`, exact current evidence may be PASS, stale evidence never is, provider completion and automatic scan stay unimplemented.
9. Web login/expiry/logout and explicit matched-only playback-attestation interaction, including accessibility and truthful wording.
10. Complete Python and serial Web suites plus all quality, package, documentation, upstream, generated-output, host-path, secret, whitespace, and Git publication gates.

## Live qualification

No 0055-A live authentication or real Emby/Jellyfin playback has run. Planning, mocks, generated media, database rows created by tests, and item observation cannot produce a checked-in human PASS. Live playback remains `NOT_RUN` until an authorized operator actually plays and explicitly confirms an exact current item.

## Exit gate

Phase A may close only after all frozen local requirements have exact evidence, no P0/P1/P2 review finding remains, migration/rollback is safe, every non-public route is denied by default, and retained outputs contain no credential/session/CSRF/raw selector. Closeout must still state the unexecuted 0047 live rows and every excluded 0055 administration feature.
