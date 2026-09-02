**English** | [中文](plan.zh.md)

# Execution 0020 plan

- Status: Completed for the frozen offline scope
- Plan date: 2026-09-02
- Predecessor: Execution 0019 closeout commit `431fd855dafce502e83f74a055a4b27ae5c6f40b`
- Plan commit: `df7a38a6f9beee35c6c19336260b512ebc87ce0d`
- Implementation commit: `8a0e935624e944809af1a56b0f02186686433d95`
- Database migration: None planned

## Baseline

The branch starts clean and reconciled at `431fd855dafce502e83f74a055a4b27ae5c6f40b`. The pre-edit focused ingestion/detail/database/download/runtime/refresh baseline passed `307 passed in 36.66s`. Both pinned upstream locks passed and both checkout worktrees were clean. A bounded unauthenticated public-API audit established the current type/key/host/query shape without retaining response bodies or query values.

## Delivery sequence

1. **Freeze source and response contracts**
   - Add a source-bound contract for MediaCrawler SHA `d6f7c5bb906b6dac40ddf343ef9e26438a3de092` that executes the real `extract_note_detail_from_api` → `TiebaNote` → `update_tieba_note` → JSONL loss boundary. Bind the test to `_get_pc_page_data`, `get_note_by_id`, creator `asyncio.gather`/parent storage and the JSONL export without modifying upstream.
   - Freeze the synthetic offline response from the observed current shape: ordinary type-0 text plus exactly one type-3 image and exact `origin_src` authority. Record that the live read-only audit is current structural evidence, not a retained fixture or authenticated qualification.

2. **Capture exact first-floor media and bound creators**
   - Add integration-owned `tieba_media.py` with strict positive thread IDs, canonical thread URLs, bounded first-floor item validation, exact type-3 key contract, strict signed/query-free image URL validators and source-hint derivation.
   - Patch only verified checkout objects: extractor → exact-object frozen capture → parent `update_tieba_note` ContextVar → matching JSONL row. Full repeat installation is idempotent; wrong origin, partial/collision state, uncarryable model, identity mismatch and cross-task leakage fail closed.
   - Wrap the pinned creator loop only for scheduled runs with the trusted Subscription cap. Validate page dictionaries, `thread_list`, positive unique IDs, `has_more`, exact returned note identity and callback batch bounds; truncate before detail, stop before post-cap sleep and reject repeated/no-progress/drift pages.
   - Install the capture in both scheduled creator and detail children after verified import and before upstream `main()`.

3. **Normalize and refresh one ARTICLE-owned IMAGE**
   - Extend Tieba normalization all-or-nothing: keep ARTICLE, emit one `<note_id>:image:0`, recursively strip the private field and persist only the canonical query-free hint. Preserve legacy zero-image ARTICLE rows.
   - Add Tieba to exact detail execution and refresh support. Derive note ID only from the persisted canonical URL, require one exact normalized content/Asset/hint match, validate the new signed URL again and return DEFAULT profile without account headers.

4. **Qualify bytes and compose Emby output**
   - Enable the existing bounded static-image structure gate for Tieba IMAGE and prove acceptance/rejection plus normal/recovery/takeover flag preservation.
   - Add an isolated SQLite → fake detail → mock public DNS/HTTP → production byte gate → immutable archive → Emby integration test with poster/backdrop/gallery/body/NFO/source outputs and query-only zero-work replay.
   - Audit retained database, WAL/SHM, runtime, archive and export trees for private fields and transient token/query fragments.

5. **Verify, review and publish**
   - Run the source contract, focused gate, complete suite, Ruff, format, strict mypy, compileall, upstream locks, build, docs, diff and retained-artifact audits. Record only executed commands, counts, durations and skips.
   - Update these four execution documents plus capability/roadmap/index truth. Keep authenticated Tieba login/creator/detail, future CDN behavior and real Emby/Jellyfin scan/display `NOT_RUN`; keep broader media shapes active.
   - Create and push separate bilingual plan, implementation and closeout commits, reconciling local, tracking and GitHub SHAs.

## Commit sequence

1. `df7a38a` — `docs: 启动贴吧首楼图片闭环 / start Tieba first-floor image pipeline`
2. `8a0e935` — `feat: 闭环贴吧首楼图片 / close Tieba first-floor image pipeline`
3. This documentation closeout commit — `docs: 收尾贴吧首楼图片闭环 / close Tieba first-floor image pipeline`; its self-referential SHA is intentionally left to Git history

`.upstream` must remain excluded, unmodified and clean throughout this execution.
