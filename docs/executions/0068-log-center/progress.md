**English** | [中文](progress.zh.md)

# Progress

Verified baseline and0067 next-version requirements. Current loss points: discarded login stderr/upstream fd1/2, status-only frame, opaque crawler.start and coarse authenticating phase; existing support bundle is aggregate only. Freeze a separate event channel/managed segment design while preserving strict results and authentication authority.

## Implemented

- Private JSONL segments under state_dir/logs. Defaults: 16 MiB or UTC date rotation, 7 days, 1 GiB aggregate capacity, queue 1024. Process-owned writers coordinate capacity/cleanup; closed schema, directory/leaf identity guards and authenticated managed-segment markers protect file operations. Queries report corruption, unavailable segments and omitted tails. Status distinguishes acceptance, persistence, dropping and incomplete shutdown.
- Separate bounded, real-time login diagnostic channel; strict result v1 remains unchanged. Observable browser launch/navigation/click/QR acquisition/relay/confirmation and cleanup preserve safe stage, action, error class, source category and duration. A caught sub-step failure followed by fallback is not terminal failure. Parent binds the exact committed account/session and API operation/correlation. Channel truncation is explicit; raw upstream output stays muted.
- Operation, scheduler worker, pipeline worker and supervisor lifecycle integration. API request status/duration, safe standard-logging category/level events, CLI login/worker/supervisor and manual download/output commands use the private store. Manual commands use correlation IDs without inventing database Operations. This is structured component coverage, not a capture of every shell, dependency or third-party message.
- Four authenticated log routes, closed filters and bounded cursors, operation/control-event trace and explicit diagnostic JSON download. Free database error/message/context values are not exported. SupportBundle v1 is unchanged. Chinese log page, task deep links and settings entry expose retention and evidence limits. No media-server connection needed.

## Review corrections

Frontend review found unset select values, mutable in-flight filters, disposed requests, mixed-filter pagination and unvalidated download data. Storage review reproduced an idle/close race leaving graceful shutdown unsealed, synchronous idle sealing bypassing the close timeout, and failed seal rename poisoning later writes. These were corrected with deterministic regression tests, including transient writer-thread start failure recovery. Final API-to-frontend review also found the missing /logs login-return allowlist; both server/client lists and exact-route tests were corrected. Failed initial root fixtures used nonexistent Operation state failed; corrected to failed_retryable. Old CLI fake constructors/assertions now require the newly wired callable event sink. Exact results are recorded in verification.

## Remaining and scope

Current Linux image, actual platform QR retry, PostgreSQL races and live history/download/playback are NOT_RUN. New evidence does not itself fix four failed QR platforms or authenticate an account. Old stage details cannot be reconstructed. Crash-orphan open segments are preserved, not automatically reclaimed; counters do not survive process restart. Retention cleanup happens on writing. The overall seven-platform goal remains active.

Independent review also reproduced an older Windows exporter pin weakness: exporter.py _open_windows_directory_handle requests zero access, permitting a held ancestor directory to be renamed. The new log store uses directory-list access and its real Windows rename rejection test passes. Existing exporter logic was not silently expanded into this change; a bounded security follow-up is required before relying on that Windows rename guarantee. This observation is not a demonstrated Linux deployment failure.
