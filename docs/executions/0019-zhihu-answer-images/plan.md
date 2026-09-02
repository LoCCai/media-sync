**English** | [中文](plan.zh.md)

# Execution 0019 plan

- Status: Implementation delivered and pushed; this change is the documentation closeout
- Date: 2026-09-02
- Predecessor: `4fb639a`
- Plan commit: `dc1714c`
- Implementation commit: `2edb9d763b4948c56cc182bcc5012914bcb644d1`

## Delivery sequence

1. **Audit and freeze the upstream boundary**
   - Lock the real answer `content` include, extractor → update → JSONL locator-loss boundary, default answers-only creator dispatch and absence of a native creator cap. Execute the real pinned extractor/store objects and preserve a clean `.upstream`.
2. **Implement bounded capture and creator execution**
   - Add the strict one-image HTML/URL parser, exact-object capture binding, nested-store task isolation and install/collision/origin guards. Replace only the verified Zhihu answer loop with a successful Subscription-`max_items` bound; validate short, repeated and malformed pages.
3. **Normalize and refresh durable media**
   - Materialize ARTICLE plus one `<content_id>:image:0` IMAGE, strip private/transient authority recursively, derive exact detail authority from the persisted answer URL, and require an exact credential-free DEFAULT-profile refresh match.
4. **Qualify bytes and compose Emby output**
   - Automatically enable bounded static structural qualification for Zhihu IMAGE downloads. Accept qualified JPEG/PNG/WebP, reject GIF/APNG/animated WebP/AVIF, and preserve the flag through normal/recovery/takeover paths. Compose SQLite → detail → mock HTTP → archive → Emby output and audit WAL/SHM plus retained trees. This gate is intentionally not described as complete image decoding.
5. **Verify, review and publish**
   - The final expanded gate passes 505 tests, the complete suite passes 1543 with one Windows-inapplicable skip, all static/type/build/docs/audit gates pass, and a fresh independent review finds no P0/P1/P2. The bilingual implementation commit is pushed and reconciled. This change is the bilingual documentation closeout; its self-referential SHA is intentionally kept in Git history, and post-push reconciliation is reported in the task handoff.

## Commit sequence

1. `dc1714c` — `docs: 启动知乎回答图片闭环 / start Zhihu answer-image pipeline`
2. `2edb9d763b4948c56cc182bcc5012914bcb644d1` — `feat: 闭环知乎回答图片 / close Zhihu answer-image pipeline`
3. `SELF` — `docs: 收尾知乎回答图片闭环 / close Zhihu answer-image pipeline` (the commit containing this record; SHA intentionally not embedded

The implementation commit is reconciled across local `main`, `origin/main` and GitHub. `.upstream` remains excluded and clean. Live qualification and the larger seven-platform product goal remain outside this offline closeout.
