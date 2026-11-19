**English** | [中文](goal.zh.md)

# Goal: the operator-run bounded canary per platform

Executions 0084, 0085 and 0086 closed the last three creator-work deliveries, so
all seven creator platforms now share one durable chain:

| Platform | Execution | Migration | Cursor / page signal | Fixed stop reasons |
| --- | --- | --- | --- | --- |
| Bilibili | 0074 | `0014` | page number, 30 per page | `source_end`, `head_boundary`, `item_limit`, `list_limit`, `restarted` |
| XHS | 0076 | `0015` | opaque `cursor` + `has_more` | `has_more_false`, `empty_page_stalled`, `access_restricted`, `unit_cap_reached` |
| Douyin | 0080 | `0016` | opaque `max_cursor` + integer `has_more` | `has_more_false`, `empty_page_stalled`, `access_restricted`, `unit_cap_reached` |
| Kuaishou | 0081 | `0017` | echoed `pcursor` + `no_more` | `no_more_echoed`, `empty_page_end`, `access_restricted`, `unit_cap_reached` |
| Weibo | 0084 | `0018` | `since_id` + arithmetic `total` inference | `total_inferred_end`, `empty_page_end`, `access_restricted`, `unit_cap_reached` |
| Tieba | 0085 | `0019` | 1-based `pn` + `rn=20` `has_more` | `has_more_false`, `empty_page_end`, `access_restricted`, `unit_cap_reached` |
| Zhihu | 0086 | `0020` | integer `offset` + `paging.is_end` | `is_end`, `empty_page_end`, `access_restricted`, `unit_cap_reached` |

What remains is **not code**. Every remaining item needs a Linux host, a real
native login, a real platform request and real CDN bytes, which this workstation
cannot supply. The honest state of those items is `NOT_RUN`, and no code change
can turn them into `PASS`.

## Deliverable

One operator procedure that, for a single platform at a time:

1. proves the running image is the exact pushed source revision;
2. proves the database migrated to `0020_zhihu_creator_answers` on PostgreSQL or
   SQLite as deployed;
3. claims one real native session into one Account and pauses every unrelated
   Subscription;
4. runs one bounded, single-author canary and records the durable phase
   transitions (`backfill` → `reconciling` → `incremental`) it observes;
5. downloads real media bytes, produces the deterministic NFO, and lands the
   result in the library;
6. replays the same canary a second time and proves **zero** new work;
7. records one explicit `PASS` / `FAIL` / `NOT_RUN` row per platform with the
   exact revision, migration head and observed run ids.

## Explicitly out of scope

- Declaring any platform "supported" before its own row is `PASS`.
- Treating an inferred end (Weibo `total`, or a Zhihu `is_end` observed after a
  shift) as proof of a complete history.
- Any deployment, restart, login or platform call from this documentation
  execution. This record only fixes the procedure and the current `NOT_RUN`
  truth.
