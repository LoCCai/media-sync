**English** | [中文](goal.zh.md)

# Pasted Cookie login goal

- Date: 2026-09-05
- Status: User goal accepted; design draft, not frozen or implemented
- Audit context: login diagnostics and urgent Node.js/QR-relay repairs are separate increments; HEAD was `7268352` when this draft was recorded.

## Accepted objective

Let the operator paste a captured platform Cookie into the authenticated local console, validate it against the platform, and save it as authenticated only after trustworthy remote proof. Do not ask the operator to paste credentials into chat or GitHub. This addition preserves the original seven-platform login, author subscription, text/image/video capture, and Emby/Jellyfin-compatible archive objective; it does not replace QR login or reduce eventual platform coverage.

The first implementation slice should provide one complete, explicitly supported Bilibili flow using the authenticated self-session response from `/x/web-interface/nav`. Other platforms follow only after their authoritative remote authentication contracts are established. Until implemented and validated, the UI must state that their pasted-Cookie flow is unavailable; no generic seven-platform support claim is justified by this audit.

## Acceptance direction

1. A fresh candidate is validated without reusing an old authenticated profile or falling back to QR. Cookie presence, browser import, public content access, and `update_cookies` completion are not authentication proof.
2. Only a successful, bounded, platform-specific remote self-authentication result may authorize persistence. Invalid credentials, network failure, anti-bot challenges, ambiguous responses, or unsupported validation never produce authenticated success.
3. Preserve existing valid credentials and profiles when a replacement candidate fails or is uncertain. Use the same account exclusion boundary and a stale-result compare-and-swap fence before publishing any accepted replacement.
4. Keep raw Cookies out of database rows, Operations, logs, diagnostics, command arguments, URLs, console local/session storage, documentation, and Git. Persist only through an explicitly designed private credential store, exposing opaque references to existing consumers.
5. Record implementation tests separately from operator-assisted real login, reuse, capture, and playback evidence. Until those tests occur, functional qualification remains `NOT_RUN`.

## Decisions still required

The next increment must settle new-account creation versus existing-account replacement, first and subsequent remote-user identity binding, the managed private vault, Linux ownership/permissions, Windows ACL or DPAPI support, rollback/crash handling, and the exact API/protocol/result contract. No endpoint, secret-reference scheme, database migration, or storage layout is frozen by this document. See the [draft plan](plan.md), [progress](progress.md), and [verification](verification.md).
