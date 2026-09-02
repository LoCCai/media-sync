**English** | [中文](goal.zh.md)

# Execution 0004 goal

Deliver a credential-safe, license-gated MediaCrawler process bridge for all seven pinned platform identifiers, plus fixture-proven normalization and restart-safe forward/backfill checkpoints. The default test suite remains network-free and never launches a browser or uses a real account.

## Acceptance

- A bridge doctor verifies the configured external checkout, exact locked SHA, Python entry point and license acknowledgement without modifying upstream files.
- QR, Cookie and saved-session capabilities are exposed only where the pinned source supports them; phone login remains unavailable.
- Raw credentials never enter command arguments, SQLite, manifests, events, logs, exception text or Git. A child receives a secret through one private environment variable and removes it before upstream execution.
- Every run uses a path-confined, unique job/profile/output directory, conservative item/time limits and an explicit full-history acknowledgement for upstream paths known to ignore the item cap.
- Safe dry-run command contracts cover `xhs`, `dy`, `ks`, `bili`, `wb`, `tieba` and `zhihu`, including the Zhihu creator-input compatibility shim.
- Versioned fixture JSONL for all seven platforms normalizes authors, text/image/gallery/video/audio/dynamic content and ordered assets without copying upstream source.
- Incremental ingestion tolerates a truncated final line, quarantines malformed/unknown records, enforces output limits and is idempotent under replay.
- Forward scans consume publish watermark plus same-timestamp known IDs; historical continuation uses a separate backfill cursor. Checkpoint publication uses optimistic fencing and cannot erase `next_run_at` or overwrite a newer run.
- Browser/network waits occur outside SQLite write transactions; each accepted batch plus its checkpoint commits atomically.
- Ruff, format, strict mypy, offline unit/contract/integration tests, package build, documentation and secret-sentinel scans pass with exact evidence recorded here.

## Truth boundary

Dry-run commands and fixtures prove our bridge contract only. Until a user supplies authorized credentials and completes interactive checks, all seven live login, creator scan and media outcomes remain `NOT_RUN`; no automated result may promote them to `PASS`.
