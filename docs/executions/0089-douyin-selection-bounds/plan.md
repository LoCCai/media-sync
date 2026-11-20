**English** | [中文](plan.zh.md)

# Plan: close the two Douyin selection gaps deferred by 0088

Status: **executed.**

## 1. Re-derive the pinned facts before changing the bound

Read `.upstream/MediaCrawler/store/douyin/__init__.py:122-139` again: the pinned
store flattens `play_addr_h264` to `play_addr_256` to `play_addr`, takes
`url_list[-1]`, and requires `len(url_list) >= 2`. It never reads `bit_rate[]`,
which is why 0083's own ranking is the only path that can express a better
stream.

## 2. Change only what the evidence supports

- **Entry bound.** Replace the made-up 8 with 32 (a realistic ceiling for
  quality times codec declarations) and keep raising on anything above it, so an
  unbounded server array is still refused. Document the reasoning inline so the
  next reader does not "simplify" it back.
- **Comma refusal.** Add `,` to the rejected characters in
  `validate_douyin_media_url`, because the shim writes into comma-delimited
  fields its own reader splits on. Do **not** relax `_dy_url_list`: that function
  is shared by the note-gallery and OTHER media fields, where a comma genuinely
  is a list separator, and widening it would accept a smuggled second URL.

## 3. Pin both with failing-first tests

- A 12-entry (4 by 3) payload must rank to the largest stream; before the change
  it raised `douyin_media_field_invalid`.
- A 33-entry payload must still raise.
- A comma-bearing URL must be refused at selection time; before the change it
  normalized to `kind=text` with zero assets.

## 4. Do not touch the three findings that need an operator

Kuaishou's CDN allowlist, XHS plaintext `http`, and animated images each either
has no committed evidence to derive from (Kuaishou: zero real hostnames anywhere
in the tree) or changes a previously qualified capability (XHS is documented and
tested as HTTP/HTTPS). Recording them here is the correct closeout; inventing a
value would be a guess.

## 5. Verify and record

Run the Douyin and refresh slices, then the static gates. Record exact counts in
[verification.md](verification.md) and keep the deferred items in their own
section.
