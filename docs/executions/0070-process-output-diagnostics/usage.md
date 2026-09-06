[**English**](usage.md) | [中文](usage.zh.md)

# Safe process-log usage

The new records use the existing authenticated **Log center** at `/logs`; there is no raw-output browser or unmanaged log directory.

1. Deploy the same image for the API and supervisor and keep their existing shared `/data` volume.
2. Keep the three log budgets identical in both services: `MEDIA_SYNC_LOG_SEGMENT_MAX_BYTES`, `MEDIA_SYNC_LOG_TOTAL_MAX_BYTES`, and `MEDIA_SYNC_LOG_RETENTION_DAYS`.
3. Reproduce only one failed platform login. Do not run parallel QR attempts for the same account.
4. On the account result card, select **View this run's logs**. The link filters by the exact Operation. Use the Job/diagnostic links for adjacent lifecycle evidence.
5. Record the Operation ID and the displayed event codes, phases, streams, safe messages, summaries, and drop counters. Do not copy Cookie values, QR images, browser profiles, or raw third-party pages into an issue.

`[REDACTED]` and `policy_filtered` are expected safety outcomes, not logger failures. `log_sink_rejected` means some otherwise eligible evidence was not accepted and should be correlated with writer-health events. A summary counts all lines read from that stream; it does not mean every line was persisted.

The managed logs remain private operational data. Back up or remove them only with the same state-volume procedures documented for the existing log center. Never publish a whole segment to GitHub.
