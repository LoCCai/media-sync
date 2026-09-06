**English** | [中文](goal.zh.md)

# Goal: safe process-output diagnostics

Extend the existing log center so a future failed QR-login or creator crawl leaves enough retained evidence to distinguish browser, network, platform, protocol and runtime failures. Capture the safely usable diagnostic output produced inside the MediaCrawler login and crawl child processes, correlate it to the exact durable work, and keep it in the existing managed JSONL segments with their rotation, capacity and retention controls.

“All logs” means all diagnostic output that the service can safely retain, not a raw transcript. Cookie values, authorization material, QR payloads or images, signed URLs, account profiles, private paths, creator content and arbitrary upstream stdout/stderr must never be persisted merely to improve diagnosis. Protocol streams must remain valid and authentication success must still come only from the existing durable account state.

This execution starts from repository baseline `4620291`. It does not deploy the edited tree, retry a real login, resume the supervisor, read production credentials or claim that an already-failed scan has become recoverable. Failures from an older deployment that discarded process output cannot be reconstructed; the new evidence applies only after this version is deployed and a controlled attempt is made.

## Acceptance criteria

1. Reuse `state_dir/logs` and the existing process-owned JSONL store; do not create a second unbounded raw-log archive. Existing size/date rotation, retention, capacity, managed-file and symlink protections remain authoritative.
2. Capture MediaCrawler upstream file-descriptor output inside the child-process boundary without mixing it into the generic crawler result protocol, QR-login result frames or QR-login event frames.
3. Apply a bounded diagnostic policy before persistence: at most 4 MiB, 4096 lines and 64 KiB per line for one capture; normalize invalid text; preserve only explicit log/exception shapes; redact known and generic secret forms. A keyword such as `error` or `login` alone is insufficient: JSON/JSONL, HTML/DOM and likely work/body objects are always policy-filtered. Flood, oversize, invalid encoding, policy filtering and log-sink rejection are visible as fixed counters/reasons.
4. Persist closed `process_output`, `process_output_summary` and `process_output_dropped` events. Free `message` text is accepted only for the process-output event and is rejected if it still resembles a Cookie/token, `Set-Cookie`, Authorization, storage-state, QR/base64 payload, signed URL or private Windows/POSIX absolute path. If reliable partial redaction is uncertain, retain only fixed `[REDACTED]` evidence or a drop count.
5. Bind each event only to trusted canonical identities. Creator crawl output includes the exact manifest account, subscription, Job, Run, platform and attempt. QR-login output includes account/platform plus the parent Operation/correlation identity when present. Missing or malicious propagated context is ignored rather than invented or partially accepted.
6. Direct/untrusted runner invocation remains quiet unless an authorized parent explicitly enables capture. Absolute account/profile/job/output paths are treated as secrets and cannot appear in retained events.
7. Authenticated log APIs and the Chinese log-center UI preserve and display the safe output message, stream, summaries and dropped reasons without weakening closed filters, pagination or output encoding.
8. Deterministic tests prove protocol isolation, exact correlation, hostile environment rejection, redaction, bounds, flooding and UI/API parsing. Focused Python/Web gates, formatting, type checks and repository hygiene are recorded exactly; Linux image and live platform qualification remain `NOT_RUN` unless actually executed.

## Deferred but unchanged

- Wire the same capture policy into any independent Cookie-validation, creator-profile, content-detail or download runner that does not pass through the two covered MediaCrawler entry points.
- Deploy this version and perform one user-authorized failed-platform retry before diagnosing the real QR cause. New logging improves evidence; it is not itself a platform-login fix.
- Continue the original seven-platform subscription, historical backfill, risk-controlled download, incremental synchronization and Emby-compatible directory objective. This observability execution must not replace or narrow that product work.
