**English** | [中文](progress.zh.md)

# Pasted Cookie login progress

- Date: 2026-09-05
- Status: Requirement accepted; read-only audit documented; implementation not started

## Completed in this increment

- Captured the user's added requirement to paste a captured Cookie, validate it and save authenticated only when valid, without changing the full seven-platform/subscription/archive/Emby-Jellyfin goal.
- Inspected the existing account/ref model, read-only secret providers, Cookie collection/download consumers, login child guards and pinned upstream login checks. Recorded evidence and limitations in [verification](verification.md).
- Prepared bilingual goal, draft plan, progress and verification documents. The plan is deliberately not frozen: private-storage, account-lifecycle and identity-binding choices still need review before implementation.

## Existing capability, not new delivery

The project can already configure Cookie accounts through opaque `credential_ref` values and resolve them for collection/download. That is not a console paste/validate/save flow. There is no raw-Cookie ingestion endpoint or managed write workflow in the audited path; creating such an account does not itself authenticate the Cookie.

The current QR/saved-session login result cannot be repurposed as reliable pasted-Cookie validation: its post-login update hook reports authentication without a fresh remote check, and some platform `pong` implementations check only local Cookie markers. The separate Node.js/QR-relay and login-diagnostic repairs do not implement Cookie login.

## Pending next increment

Resolve new-account versus existing replacement behavior, remote identity binding, managed private vault integration and Linux/Windows protection. Freeze the exact reviewed contract and verification plan before coding. Implement an explicitly supported Bilibili end-to-end slice first; establish authoritative remote self-authentication contracts before enabling each remaining platform. Keep unsupported UI states truthful and preserve old valid credentials on candidate failure.

Functional validation, secure persistence, UI integration, real Cookie login/reuse and downstream capture/playback are all `NOT_RUN` for this added flow. No real Cookie was requested, read, stored or submitted during the audit. No Cookie implementation or qualification-complete claim is made.
