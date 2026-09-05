**English** | [中文](goal.zh.md)

# Playback evidence projection goal

- Date: 2026-09-05
- Baseline: `13de3b7`
- Status: Frozen before implementation

Complete items 11–12 of the parent [plan](../plan.md): authenticated, bounded author evidence reads and qualification schema v3. Preserve the original seven-platform login/subscription/capture and Emby/Jellyfin goal. The parent frozen goal and plan remain unchanged.

Acceptance: one canonical author per request; no external work during a database transaction; a fresh complete unique observation with unchanged publication/profile authority is required for current evidence; only the exact durable attestation can confer an author-scoped PASS. Complete absence makes history stale, while failed, ambiguous, incomplete or changed authority makes it unknown. Retain all ledger rows. No new migration or write endpoint is needed.

The response exposes local evidence/author IDs, timestamps, safe states and pagination bounds only. Digests, publication Jobs, raw selectors, provider values, paths and remote item IDs remain internal. Automated tests never alter checked-in live qualification. Web login/session/confirmation interaction remains the next parent-plan item.
