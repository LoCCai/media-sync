# Execution 0022 progress / 执行 0022 推进记录

- Status / 状态：Frozen offline scope and documentation closeout complete / 冻结离线范围与文档收尾完成
- Last updated / 最近更新：2026-09-02
- Predecessor / 前置：`817875bdd1902f54c72397fa7da46359fbe33207`
- Plan commit / 计划提交：`fbcb7cf5c642fc9da210faa5d92b6886b350a9b8`
- Implementation commit / 实现提交：`b6d03aa1c6705e52c2e47c63086a5b7200c208e7`

## Completed / 已完成

- [x] Reconciled Execution 0021 with a clean local/tracking/GitHub `main`. / 已以干净的本地/tracking/GitHub `main` 核对 Execution 0021。
- [x] Audited the 512 first-floor item cap, 4,096-character URL cap, 4 MiB normal JSONL limit and 1 MiB child watchdog line limit. / 已审计 512 项首楼上限、4,096 字符 URL 上限、4 MiB 常规 JSONL 限制与 1 MiB child watchdog 行限制。
- [x] Frozen v3 to 3–64 ordered distinct static images while preserving exact v1/v2 meanings. / 已把 v3 冻结为 3–64 张有序互异静态图片，并保留 v1/v2 精确语义。
- [x] Added the mutually exclusive v3 field and shared 64-image maximum while preserving exact v1/v2 capture, object binding, install markers and concurrent isolation. / 已增加互斥 v3 字段与共享 64 图上限，同时保留精确 v1/v2 捕获、对象绑定、安装 marker 与并发隔离。
- [x] Normalized 3–64 ordered IMAGE Assets, recursively stripped all three private fields and persisted only distinct query-free hints. / 已归一化 3–64 项有序 IMAGE Asset，递归移除三个私有字段，并只持久化互异无 query hint。
- [x] Bound every lazy refresh position to the complete 1–64 sibling identity tuple; missing, added, reordered, replaced, duplicated and multi-version details fail closed. / 已把每个惰性刷新 position 绑定到完整 1–64 项兄弟身份元组；缺失、新增、重排、替换、重复与多版本详情均关闭失败。
- [x] Proved 3 and 64 images, rejected 65, and retained v1/v2 compatibility through source/unit/process/ingestion/refresh contracts. / 已通过源码/单元/进程/入库/刷新合约证明 3 与 64 图、拒绝 65 图并保留 v1/v2 兼容。
- [x] Proved three DEFAULT-profile JPEG/PNG/WebP downloads, three SHA-256 archives, Emby poster/backdrop/three gallery files/body/NFO/source and query-only zero-work replay. / 已证明三次 DEFAULT-profile JPEG/PNG/WebP 下载、三个 SHA-256 归档、Emby poster/backdrop/三项 gallery/body/NFO/source 及 query-only 零工作重放。
- [x] Focused regression passed `433 passed in 48.91s`; complete suite passed `1688 passed, 1 skipped in 321.22s`; all quality/build/docs/upstream/audit gates passed. / 专项回归通过 `433 passed in 48.91s`；完整套件通过 `1688 passed, 1 skipped in 321.22s`；全部质量/构建/文档/上游/审计门通过。
- [x] Pushed implementation `b6d03aa`; local, tracking and GitHub `main` reconciled. / 已推送实现 `b6d03aa`；本地、tracking 与 GitHub `main` 已核对一致。

## Remaining outside this execution / 本执行外待实现

Mixed/rich first-floor media, replies/comments media, more than 64 images, replacement semantics and all authenticated/live platform/CDN/Emby/Jellyfin rows remain deferred or `NOT_RUN`; the broader goal stays active. / 首楼混合/富媒体、回复/评论媒体、64 张以上图片、替换语义及全部登录/现网平台/CDN/Emby/Jellyfin 行继续延期或保持 `NOT_RUN`；更大的目标保持进行中。
