**English** | [中文](plan.zh.md)

# Pasted Cookie login draft plan

- Date: 2026-09-05
- Status: DRAFT — security and lifecycle decisions pending; not an implementation contract
- Prerequisite: retain the urgent login runtime/diagnostic release as a separate increment.

## Ordered delivery

1. Review the read-only findings and resolve the decisions below. Freeze and commit a precise bilingual goal/plan before Cookie implementation. Preserve the seven-platform objective and all existing credential/lifecycle safeguards.
2. Establish an independent application-managed private vault. The deployment's `/run/secrets` input is an operator-owned, potentially read-only source, not an upload destination. Existing `SecretResolver` providers are read-only; their existence does not establish a safe write workflow. Decide the reference integration, permission checks, atomic publication, rollback and recovery before coding.
3. Implement the first complete flow for Bilibili only: authenticated console input, bounded private candidate handling, fresh remote self-session validation, accepted-result persistence, truthful status, and reuse through the existing Cookie consumers. Require a strict positive `/x/web-interface/nav` login result with a validated current-user identity; the exact response contract and binding policy must be frozen first.
4. Run security, lifecycle, integration and UI tests, then request an operator-assisted real Bilibili validation/save/reuse test. A mocked response or another account's existing valid profile is not live evidence. Invalid-candidate and uncertain-network outcomes must demonstrably preserve a previously valid credential.
5. Define and implement the remaining platform contracts individually. XHS and Zhihu have self-info endpoints worth investigating; Weibo has a remote login flag but needs an identity contract. Kuaishou's list success is not yet proven authoritative. Douyin and Tieba require new remote authentication proof beyond their existing local-marker checks. The UI must keep every unimplemented validator explicitly unavailable.
6. Update bilingual progress, verification and implemented/pending status after each actual increment. Use explanatory bilingual local commits and publish only after the appropriate review and verification. No step in this draft implies that Cookie support, seven-platform qualification, or playback is already complete.

## Required safety boundaries

- Accept sensitive input only through the existing operator-authenticated control plane with its exact Host/Origin and browser CSRF checks; retain HTTPS for non-loopback access. No anonymous import route or console local/session-storage persistence. The exact API and bearer policy remain design decisions.
- Bound request and private child-input bytes. Validate Cookie syntax and control characters deterministically, including an explicit duplicate-name policy. Never accept a user-chosen validation URL or arbitrary Cookie domain; derive allowlisted destinations from the selected platform. Freeze redirect/proxy behavior and time limits.
- Use a disposable clean candidate environment. Do not inherit a valid account profile, infer success from public endpoints, use upstream `update_cookies` as proof, or allow interactive QR fallback. Preserve existing bounded subprocess and full process-tree cleanup guarantees.
- Keep raw Cookie material out of SQLite/PostgreSQL, Operation summaries, structured diagnostics, logs, argv, URLs, support bundles, evidence and Git. Do not expose full upstream self-info responses; they may contain email or other personal fields. Audit HTTP validation/error paths as well as success paths.
- Share the existing per-account lock with login/collection consumers; bind the accepted result to the exact account and observed credential/configuration state. Fence stale successes and failures with compare-and-swap. An in-flight candidate must never become scheduler or download authority before successful verification.
- Preserve old valid material until a verified candidate is safely committed. Failure, cancellation, network uncertainty and crash recovery must not silently replace, expire or authenticate it. No unbounded retry or automatic login is authorized by this draft.

## Decisions to freeze next

1. **Account lifecycle:** whether v1 supports creating new accounts, replacing existing Cookie accounts, converting QR/saved-session accounts, or an explicitly bounded subset; how pending candidates and exact operations are represented without corrupting the existing auth transition rules.
2. **Identity binding:** canonical remote-user identity for Bilibili, first binding, subsequent different-user replacement, and the minimum persisted/public identity fields. A local display name is not remote identity proof; existing Account rows have no such binding.
3. **Private storage:** managed vault ownership/location and provider integration, atomic write/commit ordering, orphan recovery, backup/restore and credential replacement. No final secret scheme is selected here. Linux owner-only behavior is required; Windows ACL versus DPAPI and unsupported-platform behavior remain unresolved. POSIX-style `chmod` alone is not a Windows security decision.
4. **Contract and outcomes:** exact request/protocol shape, size limits, authenticated/invalid/uncertain/unsupported distinctions, sensitive-body error redaction, cancellation and timeout semantics, and backward compatibility. No invented endpoint or DB migration is authorized by this draft.
5. **Release evidence:** deterministic offline tests, supported OS gates, real Bilibili response qualification and operator handoff; authoritative proof and separate enablement criteria for each later platform.

## Planned verification

Cover positive self-authentication, expired/forged Cookies, fake local login markers, public-data-only success, malformed/oversized/control-bearing input, duplicate names, redirect/target confinement, response ambiguity and upstream failure. Cover no old-profile contamination, no QR fallback, account/credential drift, duplicate submission, cancellation, process-tree cleanup, vault/DB commit failure and restart recovery. Check secret sentinels across errors, logs, database, Operations, exports and support bundles. Verify UI availability and that invalid or unimplemented cases cannot display saved/authenticated success. All functional checks remain `NOT_RUN` at this draft stage.
