**English** | [中文](progress.zh.md)

# Progress

Status: implemented, offline verified, and published to `origin/main` in implementation commit `b22e938`; this closeout record follows in the documentation commit.

- Added `POST /api/v1/subscriptions/{id}/execute`. It creates or replays one durable `subscription-delivery` Operation, materializes and claims only the requested subscription, drives its exact scheduler and pipeline Jobs, and returns a closed local-directory delivery result. An Emby/Jellyfin server connection remains optional.
- Added a closed pipeline receipt v2. The receipt and successful pipeline state commit in one transaction; readers remain compatible with historical v1 rows. A lost API response, supervisor ownership, worker retry, expired Operation or process restart reconstructs from the exact durable Job/Run/receipt chain instead of creating a second chain.
- Closed the publication and recovery races found during independent review. Due scheduling skips subscriptions with an active exact-delivery Operation; exact materialization and pipeline enqueue share writer/row-lock ordering and reject active predecessor/successor work; `retry_wait` remains attached to the same exact Job until terminal state. While observing supervisor-owned `claimed` or `running` work, the API now retries the same exact claim: an unexpired lease remains untouched and an expired lease is reclaimed without creating a second chain. The Operation exclusive key is not released while its sync or pipeline Job is active.
- MediaCrawler enablement and licence acknowledgement are checked before creating work. The delivery Operation does not advertise unsupported cancellation and returns the fixed `subscription_delivery_cancel_unsupported` conflict instead of a false cancellation promise.
- Added durable Bilibili uploads/dynamics scan observations. Per-feed source-end evidence is retained, but neither it nor an item limit is promoted to permanent history completeness; the other six platform histories remain explicitly unproven.
- Fixed the Windows exporter directory pin by requesting `FILE_LIST_DIRECTORY`, so an ancestor cannot be renamed while the export target is validated and written.
- Added migration `0013_exact_subscription_delivery`. SQLite downgrade requires one explicit exclusive-maintenance connection and refuses retained delivery/scan history; PostgreSQL locks both history tables before auditing. Unsupported dialects fail closed. The bilingual downgrade runbook requires both API and supervisor to be stopped.
- No deployment, production subscription execution, supervisor restart, live platform request, download or media-server action was performed.
