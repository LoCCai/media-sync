**English** | [中文](plan.zh.md)

# Playback evidence projection plan

- Date: 2026-09-05
- Baseline: `13de3b7`
- Status: Frozen before implementation

1. Commit this bilingual goal/plan/progress/verification baseline before implementation.
2. Add read-only repository methods: exact observation lookup (at most one row) and author history ordered by confirmed time then ID descending (at most limit + 1 rows). Default history limit 20, maximum 50. Exclude an independently verified current row from history. Never COUNT the ledger; at most limit + 2 rows are materialized.
3. Add a query service with one absolute deadline of at most 120 seconds. Resolve A, read immutable profile A, perform one complete lookup, resolve B, read profile B, and require stable targets/profiles plus consistent recomputed observation identity. Finish all external work before opening the short read transaction. Unknown authority returns safe unknown historical states and cannot grant PASS.
4. Freeze truncation semantics: remote traversal truncation/incompleteness prevents current authority and PASS. History-page truncation is explicitly reported but does not invalidate an independently verified exact current row. This distinction refines the parent progress note: an old current row must not disappear or become a false negative merely because newer historical rows exceed the page limit.
5. Add `GET /api/v1/media-server/playback-evidence/by-author/{author_id}?limit=20`, protected by the existing Cookie/Bearer read boundary. Reject noncanonical UUIDs, unknown/repeated query parameters and noncanonical/out-of-range limits before service work. Return only a hand-built safe projection; storage failure has one fixed error, remote failure yields an unavailable current state and unknown history.
6. Upgrade `/api/v1/qualifications` to v3 with one optional canonical `author_id`. With no author, evidence scope is `not_requested` and no evidence/remote query runs. With an author, evaluate that one author, share the same query service, and label playback PASS as author-scoped. Playback becomes IMPLEMENTED/NOT_RUN without current evidence; provider completion and automatic scan stay unchanged. Preserve existing automated count/operation fields.
7. Update Web response types and current status/roadmap/architecture/API documentation. Add behavior tests for identity drift, failed/incomplete lookup, old current beyond history limit, storage failure, read bounds, absence of writes, auth-before-work, strict queries, safe responses and qualification scope. Run required focused/full Python, serial Web, quality, docs/upstream and package gates; record unavailable environment gates honestly.
8. Record results, stage explicit paths, inspect frozen-parent diffs and retained outputs, commit with a bilingual explanation and push/reconcile GitHub. Continue to Web login and confirmation in the next checkpoint.
