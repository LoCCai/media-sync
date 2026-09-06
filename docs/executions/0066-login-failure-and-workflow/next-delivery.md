**English** | [中文](next-delivery.zh.md)

# Next delivery: subscription to files

This is the accepted next sequence, not completed implementation. Avatar expansion is lower priority than a usable collection/download loop.

1. **Output settings:** editable common media root, default platform subdirectory and optional platform roots. Persist a database policy/revision shared by API and supervisor; resolve and freeze it at a fenced job boundary. Preview effective container paths and document identical mounts. Reject private-root overlap and symlink escapes. Preserve legacy output roots/records; Save must not implicitly move, delete or bulk republish. Existing media need immutable location bindings or a blocked activation until an explicit migration is completed.
2. **One subscription, one complete run:** an explicit action targets the exact selected subscription and chains discovery, downloads, validation and compatible directory writes. It must not drain other subscriptions. Show discovery/download/written/failed counts, not a successful Worker as successful media collection.
3. **History then incremental:** persist per-feed backfill completion, pagination continuation and newer-item watermark. Bili currently has bounded alternating head/history/feed scans but no permanent history-completed marker. Other platforms need individual coverage audits. Preserve interruption and deduplication; one completed batch is not completed history.
4. **Partial progress:** the current author pipeline waits for every eligible asset to verify before publication. Design safe per-content publication so an unavailable old asset does not indefinitely hide unrelated verified new posts, while preserving multipart/gallery integrity.
5. **Risk handling:** preserve request caps and pacing. Connect positively identified auth/challenge/rate-limit responses to pause/backoff and actionable diagnostics. Existing scheduler status names do not prove that each real platform emits them. No automated challenge bypass or credential/proxy rotation.
6. **Real acceptance:** use an already authorized account and one confirmed creator in a bounded canary, coordinating supervisor and download scope with the operator. Verify actual content, media bytes, final directory and duplicate-free rerun before testing history continuation and periodic updates. Retain the historical Bili failure until new evidence proves replacement success.

Required acceptance: settings survive restart/concurrent edits; running jobs retain their output revision; no credentials in responses; failing items do not corrupt verified output; exact subscription scope; no server API required; zero-work replay; explicit NOT_RUN for untested live steps.
