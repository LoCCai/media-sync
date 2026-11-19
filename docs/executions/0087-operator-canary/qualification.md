**English** | [中文](qualification.zh.md)

# Qualification record: per-platform bounded canary

## Current truth

Every row below is `NOT_RUN`. No deployment, native login, platform request or
CDN byte fetch happened on this workstation, so no platform may be called
supported.

| Platform | Durable chain | Local code gates | Live bounded canary | Real media bytes | Zero-work replay | Restart resume |
| --- | --- | --- | --- | --- | --- | --- |
| Bilibili | 0074, migration `0014` | `PASS` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |
| XHS | 0076, migration `0015` | `PASS` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |
| Douyin | 0080, migration `0016` | `PASS` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |
| Kuaishou | 0081, migration `0017` | `PASS` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |
| Weibo | 0084, migration `0018` | `PASS` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |
| Tieba | 0085, migration `0019` | `PASS` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |
| Zhihu | 0086, migration `0020` | `PASS` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |

`Local code gates` means the repository suite and static gates passed for that
execution. It says nothing about the live platform.

## What a `PASS` will require

For the row to change, an operator must supply, from one session on the real host:

1. the exact source revision, image label and `MEDIA_SYNC_SOURCE_REVISION`;
2. the observed database revision `0020_zhihu_creator_answers`;
3. the Account id, author id and `auth_revision` of one claimed native session;
4. the `run_id` sequence and, per run, `phase`, `stop_reason`, page witnesses,
   `batch_count`, `cursor_step_count`, delivered and verified asset counts;
5. the real CDN byte count and the resulting library path with its NFO;
6. the second, zero-work replay result;
7. one supervisor restart that resumed rather than restarted the cursor.

Until every item above exists, the row stays `NOT_RUN`, and this file is the
single place that records it.

## Why local tests cannot move a row

The repository suite proves deterministic behaviour against the pinned upstream
source: cursor round-trips, the fixed stop reasons, page-tail replay, window-shift
detection, restricted ≠ end, and delivery only from closed receipts. It cannot
prove that a platform accepts the request headers, that a real login produces a
usable session, or that a CDN serves the declared stream. Those are exactly the
facts a canary exists to establish.
