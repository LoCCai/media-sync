# Execution 0021 goal / 执行 0021 目标

- Status / 状态：Plan frozen; implementation pending / 计划已冻结；实现待执行
- Date / 日期：2026-09-02
- Predecessor / 前置：Execution 0020 closeout `e5d871050cdf25da1a51e2f057ba317dea2cffb1`
- Plan commit / 计划提交：`PENDING`
- Implementation commit / 实现提交：`PENDING`
- Scope / 范围：Exactly two ordered static images in one ordinary Tieba creator thread first floor / 贴吧作者普通主题首楼中的精确两张有序静态图片

## Outcome / 目标结果

Extend the delivered single-image Tieba ARTICLE without changing its identity or compatibility. A qualifying first floor with ordinary text and exactly two current type-3 image objects becomes one ARTICLE with two ordered IMAGE Assets at positions 0 and 1. The verified shim carries both signed locators across the pinned gather-child → parent-store loss boundary, durable state retains only distinct query-free identities, and exact canonical detail refresh reacquires both current signed locators before the existing static-byte/archive/Emby pipeline. / 在不改变已交付单图贴吧 ARTICLE 身份或兼容性的前提下扩展能力。普通文本加精确两个当前 type-3 图片对象的合格首楼，会成为一个 ARTICLE 与 position 0、1 的两项有序 IMAGE Asset。校验 shim 把两个签名 locator 跨越锁定 gather-child → parent-store 丢失边界，持久状态只保留互异的无 query 身份，精确 canonical 详情刷新在既有静态字节/归档/Emby 流水线前重新取得两个当前签名 locator。

## Frozen acceptance boundary / 冻结验收边界

1. Execution 0020 single-image private field, normalized identity, refresh and export remain compatible. The new gallery field is versioned separately; one row cannot claim both fields. / Execution 0020 单图私有字段、归一化身份、刷新与导出保持兼容；新 gallery 字段独立版本化，同一行不得同时声明两个字段。
2. The media shape contains a bounded first-floor list, at least one ordinary type-0 text item and exactly two type-3 items satisfying the already frozen ten-key/scalar/host/path/query contract. Their order is the source order. Zero, one, three-or-more, other content types, duplicate durable identities or malformed items do not qualify this gallery claim. / 媒体形状包含有界首楼列表、至少一个普通 type-0 文本项及精确两个满足既有十键/标量/host/path/query 合约的 type-3 项；顺序即来源顺序。零图、单图、三张及以上、其他内容类型、重复持久身份或畸形项不通过本 gallery 声明。
3. Normalization retains ARTICLE and emits exactly `<note_id>:image:0` and `<note_id>:image:1`. Private fields and signed queries are recursively absent from raw, SQLite and retained artifacts. / 归一化保留 ARTICLE，并精确输出 `<note_id>:image:0` 与 `<note_id>:image:1`；私有字段与签名 query 递归地不进入 raw、SQLite 与保留产物。
4. Refresh accepts only positions 0 or 1 for the exact two-image ARTICLE, revalidates canonical parent/child authority, requires the complete ordered gallery and matching query-free hint, then returns the current signed URL with credential-free DEFAULT profile. Reordering or replacement fails closed. / 刷新只接受精确双图 ARTICLE 的 position 0 或 1，复核 canonical 父/child 权限，要求完整有序 gallery 与匹配无 query hint，再以无凭据 DEFAULT profile 返回当前签名 URL；重排或替换关闭失败。
5. Both images automatically use the bounded static structural gate and deterministic Emby gallery layout. A two-image composition must prove exact downloads, SHA-256 archives, poster/backdrop/two gallery files/body/NFO/source output and zero-work query-only replay. / 两张图片都自动使用有界静态结构门与确定性 Emby gallery 布局；双图组合必须证明精确下载、SHA-256 归档、poster/backdrop/两项 gallery/body/NFO/source 输出及仅 query 变化的零工作重放。

## Explicit exclusions / 明确排除

Three-or-more images, media replacement semantics, mixed image/video/voice/emoji/link/rich-card content, replies/comments media, alternate image authorities, retained real response fixtures and every authenticated/live platform/CDN/Emby/Jellyfin row remain deferred or `NOT_RUN`. This slice does not mean complete Tieba gallery or media support. / 三张及以上图片、媒体替换语义、图片与视频/语音/表情/链接/富卡片混合内容、回复/评论媒体、其他图片权限、保留的真实响应夹具及全部登录/现网平台/CDN/Emby/Jellyfin 行继续延期或保持 `NOT_RUN`；本切片不代表贴吧 gallery 或媒体能力已完整支持。
