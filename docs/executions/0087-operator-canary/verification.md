**English** | [中文](verification.zh.md)

# Verification: the operator-run bounded canary per platform

## Final result

This execution produces documentation and a qualification record only. The
verification below therefore separates what *can* be proven locally from what
cannot.

| Gate | Result | Evidence and boundary |
| --- | --- | --- |
| Documentation structure | `PASS` | `scripts/check_docs.py` reports links OK and the bilingual heading structure matches for `goal`, `plan`, `progress` and `qualification`. |
| Claimed stop reasons match the code | `PASS` | Every stop reason named in the seven-platform table exists in the corresponding module: `source_end`/`head_boundary`/`item_limit`/`list_limit`/`restarted` (`bilibili_scan.py:20`), `has_more_false`/`empty_page_stalled` (XHS, Douyin), `no_more_echoed`/`empty_page_end` (Kuaishou), `total_inferred_end`/`empty_page_end` (Weibo), `has_more_false`/`empty_page_end` (Tieba), `is_end`/`empty_page_end` (Zhihu). |
| Claimed migrations match the tree | `PASS` | `0014`–`0020` exist under `src/media_sync/infrastructure/db/migrations/versions/` and the metadata head is `0020_zhihu_creator_answers`, as `tests/integration/test_packaged_migrations.py` and `tests/unit/test_deployment_provenance.py` assert. |
| Claimed continuation settings exist | `PASS` | `MEDIA_SYNC_*_SCAN_CONTINUATION_DELAY_SECONDS` fields exist in `src/media_sync/config.py` for all seven platforms and are consumed by both the scheduler service and the pipeline worker. |
| Product behaviour unchanged | `PASS` | The complete Python suite remains `7307 passed, 63 skipped`; Web remains `30 files / 843 tests`; Ruff, strict mypy and the upstream check stay green with no product file touched by this execution. |
| Live bounded canary (7 platforms) | `NOT_RUN` | Requires a Linux host, a real native login, a platform request and CDN bytes. |
| Real media bytes (7 platforms) | `NOT_RUN` | Same boundary. |
| Zero-work replay (7 platforms) | `NOT_RUN` | Same boundary. |
| Restart resume (7 platforms) | `NOT_RUN` | Same boundary. |

## What this record deliberately does not claim

- It does not claim any platform is supported. `qualification.md` keeps every live
  row `NOT_RUN`.
- It does not claim an inferred end proves a complete history; each platform's own
  record already states that an inferred end only opens reconciliation.
- It does not claim the procedure has been executed even once.

## Commands run

```text
python scripts/check_docs.py
python -m pytest -q
python -m ruff check src tests
python -m ruff format --check src tests
python -m mypy --strict src
python scripts/check_upstreams.py
npm --prefix web run check | test | format:check
git diff --check
```
