**English** | [中文](progress.zh.md)

# Progress: close the two Douyin selection gaps deferred by 0088

Status: implemented and verified locally. Nothing deployed, no live account or
platform request used.

## Result

0083's Douyin stream ranking now actually runs on a real payload, and the shim can
no longer write a URL its own reader discards.

## What was wrong

1. **The 8-entry bound made the feature unreachable.** Upstream declares one
   `bit_rate[]` entry per (quality × codec), so a realistic payload carries
   10–16. Every such payload raised `douyin_media_field_invalid`; the shim
   swallowed the error (`douyin_media.py:322-325`) and fell back to the pinned
   flattening. The feature was implemented, tested with 2–3 entry fixtures, and
   never engaged in practice.
2. **The shim and its reader disagreed about commas.** `validate_douyin_media_url`
   accepted `,`; `apply_douyin_media_selection` wrote such a URL into
   `video_download_url`; `_dy_url_list(..., allow_scalar_commas=False)` then
   returned `()` for it. Direct probe: the record normalized to `kind=text` with
   zero assets — a video work silently became a text row.

## What changed

- `DOUYIN_MAX_BIT_RATE_ENTRIES`: 8 → 32, with the "quality × codec" reasoning
  inline. Anything above 32 still raises, so an unbounded server array stays
  refused.
- `validate_douyin_media_url` refuses `,`. The relaxation was deliberately **not**
  applied to `_dy_url_list`, which the note gallery and other media fields share
  and where a comma genuinely separates list members.

Both are inside 0083's own scope. The pinned upstream file was read for facts
(`store/douyin/__init__.py:122-139`) and not modified.

## Verification

`26 passed` for the Douyin unit file (24 existing + 2 new) and `212 passed` for
the Douyin/refresh/ingestion slices; Ruff, `ruff format --check` and strict mypy
over 182 files green. Exact per-gate evidence is in [verification.md](verification.md).

## Still open (recorded, not guessed)

- **Kuaishou image-CDN allowlist** — no real hostname exists anywhere in the
  tree, so an allowlist cannot be derived; it needs one operator-captured URL.
- **XHS plaintext `http`** — 0018 documented and tested HTTP/HTTPS, so tightening
  it changes a qualified capability and needs an operator decision.
- **Animated images as stills** — only Kuaishou/Weibo/Zhihu gate extensions; making
  it universal changes 0076/0081 semantics and needs its own execution.

These stay `NOT_RUN`/`OPEN` rather than being silently closed with a guess.
