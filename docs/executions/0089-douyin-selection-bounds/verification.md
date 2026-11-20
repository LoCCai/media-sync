**English** | [中文](verification.zh.md)

# Verification: close the two Douyin selection gaps deferred by 0088

## Final result

| Gate | Result | Evidence and boundary |
| --- | --- | --- |
| Ranking reachability | `PASS` | `tests/unit/test_douyin_media.py::test_a_realistic_multi_codec_bit_rate_array_still_ranks` builds a 12-entry (4 qualities x 3 codecs) payload and asserts it ranks to the 2160x3840 entry. Before this change the same payload raised `douyin_media_field_invalid`, the shim swallowed it (`douyin_media.py:322-325`), and 0083's ranking never engaged. |
| Bound still enforced | `PASS` | The existing over-limit case now uses the new constant: a 33-entry array still raises `douyin_media_field_invalid`, so an unbounded server array is refused. |
| Shim/reader agreement | `PASS` | `test_a_comma_bearing_signed_url_is_refused_rather_than_silently_dowgraded`: a comma URL is refused by `validate_douyin_media_url` and by `select_douyin_media`. Direct probe before the change: the same URL normalized to `kind=text` with zero assets, i.e. a VIDEO work silently downgraded to TEXT. |
| Fallback parity preserved | `PASS` | The pre-existing fallback tests still pass: with no `bit_rate`, the selected URL is exactly `play_addr_h264` -> `play_addr_256` -> `play_addr`, last `url_list` entry. |
| Douyin and refresh slices | `PASS` | `tests/contract/test_douyin_media_capture.py`, `tests/integration/test_douyin_playable_pipeline.py`, `tests/unit/test_mediacrawler_refresh.py`, `tests/integration/test_douyin_creator_work_ingestion.py` -> `212 passed in 5.06s`. |
| Douyin unit file | `PASS` | `tests/unit/test_douyin_media.py` -> `26 passed in 0.90s` (24 pre-existing + 2 new). |
| Static gates | `PASS` | `ruff check src tests` -> `All checks passed!`; `ruff format --check` -> `466 files already formatted`; `mypy --strict src` -> `Success: no issues found in 182 source files`. |
| Live canary | `NOT_RUN` | No deployment, login, platform request or CDN byte fetch. |

## What changed

1. `DOUYIN_MAX_BIT_RATE_ENTRIES` 8 -> 32, with the reasoning written inline so a
   later reader does not shrink it back to an unreachable value.
2. `validate_douyin_media_url` now refuses `,`. The comma stays meaningful for
   `_dy_url_list`, which is shared by the note-gallery and other media fields
   where a comma really is a list separator; widening that function would accept
   a smuggled second URL, so the refusal belongs on the selection side.

Both changes are inside 0083's own scope (Douyin stream selection). No other
platform's behaviour, and no pinned upstream file, was touched.

## Deliberately still open

| Finding | Why it is not fixed here |
| --- | --- |
| Kuaishou image-CDN allowlist | No real Kuaishou CDN hostname exists anywhere in this repository, the pinned upstream checkout, or any fixture. A tree-wide search for `yximgs`, `kwimgs`, `kwaicdn`, `kscdn` and `kuaishoucdn` returned zero hits, and every test fixture uses `img.example.test`. An allowlist cannot be derived from committed evidence; guessing one would fail closed against every real atlas. It needs one operator-captured real URL. |
| XHS plaintext `http` | 0018's own verification qualifies "ordinary bounded HTTP/HTTPS" and its test suite asserts `http://xhscdn.com:80/...` is accepted, so the code matches its recorded contract. The reviewer's claim that the docs promise HTTPS-only was inaccurate. Tightening it changes a qualified capability and needs an operator decision. |
| Animated images published as stills | Only Kuaishou, Weibo and Zhihu gate image extensions (`.jpeg/.jpg/.png/.webp`); XHS, Tieba and Douyin do not, and the sniffed static-image gate (`src/media_sync/application/downloads.py:44-45`) applies only to Tieba/Zhihu. Verified: GIF bytes still pass the Douyin/Kuaishou gate. Making it universal would change 0076/0081 media semantics, so it needs its own execution. |

## Commands run

```text
python -m pytest tests/unit/test_douyin_media.py -q
python -m pytest tests/contract/test_douyin_media_capture.py tests/integration/test_douyin_playable_pipeline.py tests/unit/test_mediacrawler_refresh.py tests/integration/test_douyin_creator_work_ingestion.py -q
python -m ruff check src tests
python -m ruff format --check src tests
python -m mypy --strict src
python scripts/check_docs.py
git diff --check
```
