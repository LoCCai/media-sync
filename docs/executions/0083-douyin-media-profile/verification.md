**English** | [中文](verification.zh.md)

# Verification: Douyin media request profile and bounded stream selection

Plan baseline: the frozen plan in this directory. Implementation is a single
commit on top of the 0082 hardening.

## Final result

| Gate | Result | Evidence and boundary |
| --- | --- | --- |
| Selection ranking | `PASS` | `tests/unit/test_douyin_media.py`: highest `max(width, height)` wins; ties fall through to `bit_rate`, then `data_size`, then declaration order; `bit_rate` is bounded at 8 entries. |
| Fail-closed drift | `PASS` | Same file: non-mapping `bit_rate`, an empty array, an over-limit array, a missing `url_list`, duplicate URLs, `http`, userinfo, non-default port, root path, fragment and a host outside the Douyin media suffix list each raise `DouyinMediaSelectionError` with a fixed code. |
| Fallback parity | `PASS` | Same file: with no `bit_rate`, the selected URL is exactly `play_addr_h264` → `play_addr_256` → `play_addr`, last `url_list` entry, i.e. the pinned flattening rule. |
| Private field discipline | `PASS` | `test_private_rank_field_never_reaches_the_persisted_envelope`: the normalizer strips `__media_sync_dy_media_rank_v1`; neither the field name nor a sentinel from the signed URL appears in the persisted envelope. |
| Store shim | `PASS` | `tests/contract/test_douyin_media_capture.py`: the installed shim prefers a declared higher stream, leaves the pinned record byte-identical when no ranking exists, ignores a drifted declaration without inventing a rank, and is idempotent on reinstall. |
| Media profile headers | `PASS` | `tests/unit/test_media_network.py`: `DOUYIN_MEDIA` sends exactly `User-Agent`, `Referer: https://www.douyin.com/` and `Accept: */*` plus the transport's `Accept-Encoding`; no Cookie, `Authorization`, `Origin` or caller header. Caller headers are still rejected with `download_range_invalid`. |
| Refresh profile wiring | `PASS` | `tests/unit/test_mediacrawler_refresh.py` and `tests/contract/test_mediacrawler_detail_refresh.py`: Douyin assets resolve with `DOUYIN_MEDIA`; Kuaishou, Weibo, Tieba, Zhihu and XHS keep `DEFAULT`; Bilibili keeps its own profile. |
| End-to-end delivery | `PASS` | `tests/integration/test_douyin_playable_pipeline.py`: SQLite → refresh → mock DNS/HTTP → archive → Emby passes with the DY profile asserted on the wire, plus the gallery slice and zero-work replay. |
| Full Python suite | `PASS` | `7228 passed, 63 skipped, 108 warnings in 1624.06s`. Skips are the documented Windows/POSIX symlink, POSIX-directory and PostgreSQL-URL branches. |
| Ruff lint / format | `PASS` | `ruff check src tests` → `All checks passed!`; `ruff format --check src tests` → `441 files already formatted`. |
| Strict mypy | `PASS` | `mypy --strict src` → `Success: no issues found in 170 source files`. |
| Docs | `PASS` | `scripts/check_docs.py` → `Documentation links OK (828 Markdown files checked)`. |
| Web gates | `PASS` | `svelte-check` → `0 errors and 0 warnings`; `vitest` → `30 files / 843 tests`. The Web app is untouched by this execution. |
| Docker / Linux host / live login / CDN bytes | `NOT_RUN` | No deployment, account, platform request or real media fetch. |

## Fixes made while running the gates

- Four existing refresh tests and one process-runner test asserted the headerless
  `DEFAULT` profile for Douyin. They now assert `DOUYIN_MEDIA`, which is the
  behaviour this execution deliberately changed.
- `tests/contract/test_browser_policy_wiring.py` disables capture hooks by name;
  the new Douyin store shim had to be added to that list, otherwise the real
  creator/detail entries failed with exit code 30 while trying to import the fake
  checkout's absent `store.douyin`.
- `tests/contract/test_mediacrawler_detail_refresh.py` builds a fake checkout with
  only the config and main modules. Since the Douyin shim is installed for every
  Douyin child, the fixture now also writes the `store.douyin` modules the shim
  imports; the fixture's own JSONL path is unchanged.
- The integration pipeline handlers previously asserted that no `User-Agent`
  beginning with `Mozilla/5.0` and no `Referer` reached the wire for Douyin. That
  is exactly what this execution changes, so those assertions were replaced with
  the closed DY header set.

## Commands run

```text
python -m pytest -q
python -m pytest tests/unit/test_douyin_media.py tests/contract/test_douyin_media_capture.py -q
python -m pytest tests/integration/test_douyin_playable_pipeline.py -q
python -m pytest tests/contract/test_browser_policy_wiring.py -q
python -m pytest tests/contract/test_mediacrawler_detail_refresh.py -q
python -m ruff check src tests
python -m ruff format --check src tests
python -m mypy --strict src
python scripts/check_docs.py
npm --prefix web run check | test
```

## Boundary notes

- Selection is proven against response shapes taken from the pinned upstream
  source and from the documented `bit_rate[]` contract. No live response was
  captured, so a shape the platform no longer emits would surface as a fixed
  `douyin_media_field_invalid` rejection rather than a wrong download.
- The profile is a closed header set, not a TLS impersonation. Whether the CDN
  accepts it can only be proven by one operator-run canary.
