**English** | [中文](progress.zh.md)

# Progress

Implemented and locally verified from frozen plan 9ec7d8d and refinement 79c2168: root Python unions pass 368 and 269 tests (one Windows skip); Web passes 343 tests and static build gates. See [verification](verification.md) for exact commands, intermediate corrections and publication status.

## Implemented

1. Three closed diagnostics distinguish ordinary heartbeat failure, typed native SQLite BUSY/LOCKED and the first result-finalization exception boundary. All retain terminal/circuit-affecting semantics; no retry, lease, timeout, transaction, migration or historical-data policy changes.
2. Lease/cleanup fences propagate before diagnostic finalization. Cancellation joins the handler and in-flight heartbeat, including simultaneous completion and a cleanup fence raised during external cancellation. Already committed succeeded Runs remain authoritative.
3. Shared API/CLI Job projection exposes nullable last_error_code; CLI worker JSON exposes nullable error_code. Only exact recognized vocabulary in six failure/wait/retry/fenced states can be shown. Unknown, malformed and stale-success values become null. No additional queries, raw exception text, private payloads or batch Operation schema changes.
4. Jobs list/detail display fixed Chinese stage/next-step explanations, with schema_invalid explicitly ambiguous. Detail renders only existing allowlisted fields and sanitized error; exact identity, abort and request-generation checks prevent late or wrong-Job replies from replacing the selected detail. New Web accepts old APIs without a diagnostic field.
5. Real file-backed SQLite contention and injected failures are separately tested. The second writer genuinely exhausts a test-only timeout; handler cancellation releases its lock before finalization. The test reproduces a failed Job, running/no-error Run, zero content and unchanged authenticated account without exposing database text or paths. It is not production attribution.

## Still pending

- First production capture remains FAILED; its historical schema_invalid is unchanged. New diagnostics are NOT_RUN on the deployed image. No production login, sync retry, download, export, deployment or supervisor restart occurred in this increment; the test subscription remains paused.
- Bili creator collection still needs a genuinely enforced scan/item boundary; the existing creator path does not honor max_items=1. Pasted-Cookie remote validation/private persistence/reuse remains accepted but NOT_IMPLEMENTED.
- Fresh saved-session reuse, the other platforms, real archive/download/incrementality and Emby/Jellyfin playback qualification remain open. The full seven-platform goal is unchanged, and this diagnostic slice does not complete it.
