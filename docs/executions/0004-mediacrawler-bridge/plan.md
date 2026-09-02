**English** | [中文](plan.zh.md)

# Execution 0004 plan

1. Freeze the license acknowledgement, checkout discovery, run-directory and secret-channel contracts.
2. Add typed secret references/providers and recursive sink redaction/rejection with sentinel tests.
3. Implement checkout validation and a redaction-safe seven-platform bridge command builder.
4. Implement the isolated child runner, account-level browser profile, timeout/output watchdog and Zhihu creator shim without editing upstream.
5. Define a versioned raw envelope and JSONL reader with truncated-tail tolerance and quarantine.
6. Build and fixture-test normalizers for all seven platform schemas and ordered asset discovery.
7. Separate forward watermark/known-ID state from backfill continuation; add optimistic checkpoint fencing.
8. Refactor live ingestion into short batch transactions with no browser/network await under the SQLite writer lock.
9. Add CLI doctor/dry-run/account adapter/sync-ingest commands with fixed, secret-free output.
10. Run all offline gates, record exact results and create bilingual local commits.

## Rollback and safety

Automated tests use only temporary directories, fixture JSONL and a fake child process. They do not invoke the upstream crawler, start Playwright, contact platform endpoints, or resolve a real secret. Live execution requires an explicit license acknowledgement plus a separately authorized account workflow.
