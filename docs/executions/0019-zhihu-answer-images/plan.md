# Execution 0019 plan / 执行 0019 计划

- Status / 状态：Implementation delivered and pushed; this change is the documentation closeout / 实现已交付并推送；本次变更即文档收尾
- Date / 日期：2026-09-02
- Predecessor / 前置：`4fb639a`
- Plan commit / 计划提交：`dc1714c`
- Implementation commit / 实现提交：`2edb9d763b4948c56cc182bcc5012914bcb644d1`

## Delivery sequence / 交付顺序

1. **Audit and freeze the upstream boundary / 审计并冻结上游边界 — complete / 已完成**
   - Lock the real answer `content` include, extractor → update → JSONL locator-loss boundary, default answers-only creator dispatch and absence of a native creator cap. Execute the real pinned extractor/store objects and preserve a clean `.upstream`. / 锁定真实回答 `content` include、extractor → update → JSONL locator 丢失边界、默认仅回答的 creator dispatch 及缺少原生 creator 上限的事实；执行真实锁定 extractor/store 对象并保持 `.upstream` 干净。
2. **Implement bounded capture and creator execution / 实现有界捕获与作者执行 — complete / 已完成**
   - Add the strict one-image HTML/URL parser, exact-object capture binding, nested-store task isolation and install/collision/origin guards. Replace only the verified Zhihu answer loop with a successful Subscription-`max_items` bound; validate short, repeated and malformed pages. / 增加严格单图 HTML/URL 解析器、精确对象捕获绑定、嵌套 store 任务隔离及安装/冲突/来源 guard。只把校验后的知乎回答循环替换为成功受 Subscription `max_items` 约束的实现；校验短页、重复页与畸形页。
3. **Normalize and refresh durable media / 归一化并刷新持久媒体 — complete / 已完成**
   - Materialize ARTICLE plus one `<content_id>:image:0` IMAGE, strip private/transient authority recursively, derive exact detail authority from the persisted answer URL, and require an exact credential-free DEFAULT-profile refresh match. / 物化 ARTICLE 加唯一 `<content_id>:image:0` IMAGE，递归移除私有/瞬态权限，从持久回答 URL 派生精确 detail 权限，并要求无凭据 DEFAULT profile 的精确刷新匹配。
4. **Qualify bytes and compose Emby output / 校验字节并组合 Emby 输出 — complete / 已完成**
   - Automatically enable bounded static structural qualification for Zhihu IMAGE downloads. Accept qualified JPEG/PNG/WebP, reject GIF/APNG/animated WebP/AVIF, and preserve the flag through normal/recovery/takeover paths. Compose SQLite → detail → mock HTTP → archive → Emby output and audit WAL/SHM plus retained trees. This gate is intentionally not described as complete image decoding. / 为知乎 IMAGE 下载自动启用有界静态结构资格校验；接受合格 JPEG/PNG/WebP，拒绝 GIF/APNG/animated WebP/AVIF，并在 normal/recovery/takeover 路径保留该标志。组合 SQLite → detail → mock HTTP → archive → Emby 输出，并审计 WAL/SHM 与保留目录；该门不会被描述为完整图片解码。
5. **Verify, review and publish / 验证、审查与发布 — complete for the frozen offline slice / 冻结离线切片已完成**
   - The final expanded gate passes 505 tests, the complete suite passes 1543 with one Windows-inapplicable skip, all static/type/build/docs/audit gates pass, and a fresh independent review finds no P0/P1/P2. The bilingual implementation commit is pushed and reconciled. This change is the bilingual documentation closeout; its self-referential SHA is intentionally kept in Git history, and post-push reconciliation is reported in the task handoff. / 最终扩大门通过 505 项，完整套件通过 1543 项且仅跳过 1 项 Windows 不适用用例；全部静态/类型/构建/文档/审计门通过，独立复核未发现 P0/P1/P2。双语实现提交已推送并核对。本次变更即双语文档收尾；其自引用 SHA 有意只保留在 Git 历史中，推送后的核对结果在任务交接中报告。

## Commit sequence / 提交顺序

1. `dc1714c` — `docs: 启动知乎回答图片闭环 / start Zhihu answer-image pipeline`
2. `2edb9d763b4948c56cc182bcc5012914bcb644d1` — `feat: 闭环知乎回答图片 / close Zhihu answer-image pipeline`
3. `SELF` — `docs: 收尾知乎回答图片闭环 / close Zhihu answer-image pipeline` (the commit containing this record; SHA intentionally not embedded / 包含本记录的提交；有意不嵌入自身 SHA)

The implementation commit is reconciled across local `main`, `origin/main` and GitHub. `.upstream` remains excluded and clean. Live qualification and the larger seven-platform product goal remain outside this offline closeout. / 实现提交已在本地 `main`、`origin/main` 与 GitHub 间核对一致；`.upstream` 继续排除且干净。真人验收与更大的七平台产品目标不属于本次离线收尾范围。
