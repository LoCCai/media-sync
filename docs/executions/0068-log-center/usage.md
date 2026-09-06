**English** | [中文](usage.zh.md)

# Log center usage and deployment

## Deploy deliberately

The authoring machine cannot run Docker; these are operator instructions, not executed production steps. Preserve current credentials, origins, mounts and authenticated profiles. Keep the previously stopped supervisor stopped during login diagnosis. Do not use a bulk login/retry action.

```sh
git pull --ff-only
docker-compose build media-sync
docker-compose run --rm --no-deps --entrypoint /app/.venv/bin/media-sync media-sync serve --check-config
docker-compose up -d --no-deps --force-recreate media-sync
```

Run the last command only after configuration validation succeeds. The existing /data mount retains logs at /data/state/logs; no public static mount or media-server connection is needed. Both API and supervisor must retain the same state mount. Do not publish this directory via the reverse proxy.

Optional environment settings (same values for API and supervisor): MEDIA_SYNC_LOG_SEGMENT_MAX_BYTES=16777216, MEDIA_SYNC_LOG_TOTAL_MAX_BYTES=1073741824, MEDIA_SYNC_LOG_RETENTION_DAYS=7. Total capacity must hold at least two segments. Limits are deployment configuration, not editable in the browser.

## Diagnose one attempt

1. Open the authenticated console's log center; check storage health and dropped/invalid/queued counts first.
2. After deployment, manually retry only one previously failed platform when ready. Do not retry authenticated accounts merely to produce logs.
3. Open that exact task, follow its log-center link and inspect stage/action/outcome. A failed selector or probe can be followed by a successful fallback. Only durable account state establishes authenticated success.
4. Select the operation and explicitly download its diagnostic JSON. It contains a bounded retained log page, durable control events/subjects, version information and coverage limitations. No automatic upload occurs.
5. If a page reports scan limits, omitted tails, corruption or more pages, it is incomplete. Continue pagination or narrow the time/platform/identity filters. A diagnostic file is not an unlimited archive; retain its coverage flags when sharing.

Read routes: /api/v1/logs/status, /api/v1/logs, /api/v1/logs/operations/{operation_id}, /api/v1/logs/operations/{operation_id}/diagnostic. All require existing operator authentication. Query supports operation/account/login_session/job/run/subscription UUIDs, platform/module/level/event_code and since/until. API timestamps use exact UTC microseconds (2026-09-06T12:00:00.000000Z); the page converts local input. Limit is 1–200. Unknown/duplicate parameters and arbitrary file paths are rejected. Cursors are bound to the same filters and store instance; refresh after restart or retention expiry.

## What is and is not retained

Segments rotate by size or next write on a new UTC day. Retention/capacity pruning runs on writes, only on authenticated managed sealed ordinary files; active files and unrelated paths are preserved. Queue/flush/close and reads are bounded. Enqueue is not durability, fsync failure may drop an event, and the page exposes degradation. Read ordering is segment ascending, not global time order. At most 4096 inventory entries and 4 MiB/2 seconds of event scanning per page; storage reads may initialize its private marker.

Counters are process-local and reset after restart. Abnormal-exit .open files are readable but not automatically reclaimed; they count toward capacity and can eventually stop new writes. No automatic deletion command is provided: inspect and back up the exact log directory before any manual maintenance. Do not delete another live process's active segment. Permission/disk problems must be corrected by the operator.

Pagination is not a consistent snapshot: an older active segment can receive new events after the cursor has moved past it. Those events may be omitted from subsequent pages; start a fresh query after the task finishes. Repair storage failures before restarting a degraded writer. A bounded diagnostic page may not contain the selected operation's full retained history.

Only safe structured categories and explicit lifecycle events are stored. Cookie values, headers, URLs, QR content, remote HTML, selector text, raw exception strings, traceback locals and arbitrary log messages are excluded. Standard Python logs preserve category/level/count, not their message text. Early boot/configuration failures, Docker/Xvfb output and uninstrumented third-party internals are not automatically archived here; their existing console evidence remains necessary. Old missing QR details cannot be recovered. This version has no live platform qualification.
