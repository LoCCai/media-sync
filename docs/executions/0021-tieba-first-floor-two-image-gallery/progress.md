# Execution 0021 progress / 执行 0021 推进记录

- Status / 状态：Frozen offline scope and documentation closeout complete / 冻结离线范围与文档收尾完成
- Last updated / 最近更新：2026-09-02
- Predecessor / 前置：`e5d871050cdf25da1a51e2f057ba317dea2cffb1`
- Plan commit / 计划提交：`5095ed6e803a8a2f0a3134e756dd3e101fef10bd`
- Implementation commit / 实现提交：`e0fb8d572c8f5535a5495c2dfbf5b9cdf78461e7`

## Completed / 已完成

- [x] Closed and reconciled Execution 0020 with a clean worktree. / 已以干净工作树收尾并核对 Execution 0020。
- [x] Reused the prior bounded read-only evidence that current public responses contain real two-image first floors; no body, personal data or signed query value is retained. / 复用此前有界只读证据：当前公开响应包含真实双图首楼；未保留正文、个人数据或签名 query 值。
- [x] Frozen this execution to exactly two ordered static images while preserving the single-image slice. / 已把本执行冻结为精确两张有序静态图片，并保持单图切片兼容。
- [x] Added the mutually exclusive `__media_sync_tieba_first_floor_images_v2` capture while retaining the v1 single-image field and install markers. Exact source order, distinct durable identities, three-image rejection, exact-object carry and concurrent isolation pass. / 已增加与 v1 单图字段互斥的 `__media_sync_tieba_first_floor_images_v2` 捕获，同时保留安装 marker；精确来源顺序、互异持久身份、三图拒绝、精确对象携带及并发隔离通过。
- [x] Normalized one ARTICLE plus positions 0/1 IMAGE Assets, recursively removed both private fields, and persisted only query-free hints. / 已归一化一个 ARTICLE 与 position 0/1 两项 IMAGE Asset，递归移除两个私有字段，并只持久化无 query hint。
- [x] Bound lazy refresh to the complete persisted ordered gallery. Both positions refresh under canonical thread authority and DEFAULT profile; missing, reordered, replaced, duplicated or dual-claimed galleries fail closed. / 已把惰性刷新绑定到完整持久有序 gallery；两个 position 均在 canonical 主题权限与 DEFAULT profile 下刷新，缺图、重排、替换、重复或双重声明 gallery 均关闭失败。
- [x] Proved two downloads, JPEG/PNG static gates, two SHA-256 archives, Emby poster/backdrop/two gallery files/body/NFO/source output, retained-marker absence and query-only zero-work replay. / 已证明两次下载、JPEG/PNG 静态门、两个 SHA-256 归档、Emby poster/backdrop/两项 gallery/body/NFO/source 输出、保留 marker 不存在及 query 零工作重放。
- [x] Pushed implementation `e0fb8d5`; local, tracking and GitHub `main` reconciled. / 已推送实现 `e0fb8d5`，本地、tracking 与 GitHub `main` 已核对一致。

## Verification complete / 验证完成

- [x] Focused regression: `413 passed in 44.50s`. / 专项回归：`413 passed in 44.50s`。
- [x] Complete suite: `1668 passed, 1 skipped in 314.72s`; the skip is the Windows-inapplicable POSIX mode-bit boundary. / 完整套件：`1668 passed, 1 skipped in 314.72s`；跳过项为 Windows 不适用的 POSIX mode-bit 边界。
- [x] Ruff, format, strict mypy, compileall, wheel/sdist build, docs, both upstream locks/worktrees and Git/diff audits pass. / Ruff、格式、严格 mypy、compileall、wheel/sdist 构建、文档、两个上游锁/工作树及 Git/diff 审计通过。

## Remaining / 待实现

Three-or-more images, mixed/rich first-floor media, replies/comments media, replacement semantics and all authenticated/live platform/CDN/Emby/Jellyfin rows remain deferred or `NOT_RUN`. The broader goal remains active. / 三张及以上图片、首楼混合/富媒体、回复/评论媒体、替换语义及全部登录/现网平台/CDN/Emby/Jellyfin 行继续延期或保持 `NOT_RUN`；更大的目标仍在推进。
