# Execution 0015 plan / 执行 0015 计划

- Status / 状态：Frozen before implementation / 实现前已冻结
- Plan date / 计划日期：2026-08-31
- Predecessor / 前置：Execution 0014 closeout commit `6098923`

## Delivery sequence / 交付顺序

1. **Freeze scope and baseline / 冻结范围与基线**
   - Create four bilingual execution records plus journal/roadmap entries before source edits. Preserve both pinned upstream commits and the external-runtime/license boundary. / 在源码编辑前创建四份双语执行记录及日志/路线图条目；保持两个锁定上游提交与外部 runtime/许可证边界。
   - Record the 269-test predecessor baseline covering ingestion, detail, refresh/runtime, downloader/network, Emby application/layout and both existing playable-platform compositions. / 记录覆盖导入、detail、refresh/runtime、下载器/网络、Emby application/layout 及两个既有可播放平台组合的 269 项前置基线。

2. **Close Douyin durable media raw / 封闭抖音持久媒体 raw**
   - Add a real normalize→SQLite red test using dynamic known/unknown query, fragment, userinfo and nested-shape sentinels across all four Douyin media fields. / 增加真实 normalize→SQLite 红测，以动态已知/未知 query、fragment、userinfo 与嵌套形状哨兵覆盖全部四个抖音媒体字段。
   - Generalize the existing platform media-field sanitizer without changing AssetSnapshot URLs. Mirror `_url_list` comma splitting for string `note_download_url`; sanitize each item independently and fail closed for opaque shapes. / 泛化既有平台媒体字段 sanitizer，但不改变 AssetSnapshot URL。对字符串 `note_download_url` 镜像 `_url_list` 的逗号拆分，逐项独立净化，并对不透明形状关闭失败。
   - Preserve Kuaishou behavior and rerun its raw/pipeline regressions. / 保持快手行为并重跑其 raw/pipeline 回归。

3. **Compose the Douyin platform pipeline / 组合抖音平台流水线**
   - Strengthen the existing real fake-checkout contract only where needed for the frozen pure-ID/config/cleanup claims. / 只按冻结的纯 ID/配置/清理声明强化既有真实 fake-checkout 契约。
   - Add a new SQLite-bound E2E with one numeric aweme video plus optional cover, exact AssetRefreshSource provenance, lazy runtime construction, deterministic signed detail output, public-DNS mock HTTP, controlled MP4 probe, archive and Emby publication. / 新增 SQLite 绑定 E2E：一个 numeric aweme 视频与可选封面、精确 AssetRefreshSource 来源、惰性 runtime 构造、确定性签名 detail 输出、公网 DNS mock HTTP、受控 MP4 probe、归档及 Emby 发布。
   - Assert `DEFAULT` profile and no Cookie/Auth/Referer/Origin; keep music empty and do not claim external-track semantics. / 断言 `DEFAULT` profile 及无 Cookie/Auth/Referer/Origin；音乐字段保持为空，不宣称外挂音轨语义。

4. **Prove replay, failures and sinks / 证明重放、失败与落点**
   - Prove exact missing/drift/duplicate/wrong-source failures through existing and new focused cases. / 通过既有与新增专项 case 证明精确缺失/漂移/重复/错误来源失败。
   - Rotate forward query values and re-read live runner/network/probe counters after replay; scan ORM, SQLite/sidecars, runtime/work/archive/library, repr and Git-visible/build files for constructed markers. / 轮换 forward query 值，重放后重新读取实时 runner/network/probe 计数；扫描 ORM、SQLite/sidecar、runtime/work/archive/library、repr 及 Git 可见/build 文件中的构造 marker。
   - Obtain independent read-only review and close every actionable finding before final gates. / 获取独立只读审查，并在最终门禁前关闭全部可执行问题。

5. **Verify, document and commit / 验证、记录并提交**
   - Run the focused execution gate, full pytest, Ruff lint/format, mypy, docs/upstream checks, build, patch and retained-marker audits. / 运行执行专项、完整 pytest、Ruff lint/格式、mypy、文档/上游检查、构建、补丁及保留 marker 审计。
   - Update implemented/remaining truth in the four records, README, roadmap, capability matrix and architecture. Keep every live row `NOT_RUN`. / 在四份记录、README、路线图、能力矩阵与架构中更新已实现/待实现真值；全部真人行保持 `NOT_RUN`。
   - Create separate bilingual implementation and closeout commits, push `main`, and verify local/tracking/GitHub SHA equality. / 分别创建双语实现与收尾提交，推送 `main`，并验证本地/tracking/GitHub SHA 一致。

## Risks and rollback points / 风险与回退点

- `note_download_url` is a comma-joined upstream field. Sanitizing it as one URL could retain later-item queries in a path; implementation must mirror discovery splitting and test multiple items. / `note_download_url` 是上游逗号拼接字段；把它当作单个 URL 净化可能把后续项 query 留在 path 中，必须镜像 discovery 拆分并测试多项。
- Associated `music_download_url` is background music, not a proven external video track. It remains outside this slice even though the domain can store an audio Asset. / 关联 `music_download_url` 是背景音乐，不是已经证明的视频外挂音轨；即使领域可保存 audio Asset，它仍不属于本切片。
- Douyin remains on `MediaRequestProfile.DEFAULT`. No special header may be introduced without pinned source or live evidence. / 抖音继续使用 `MediaRequestProfile.DEFAULT`；没有锁定源码或真人证据时不得增加专用 header。
- If composition exposes a product defect, repair the smallest shared contract and rerun Bilibili/Kuaishou regressions; do not expand into galleries or live qualification. / 若组合暴露产品缺陷，只修复最小共享契约并重跑 Bilibili/快手回归；不得扩张到图集或真人验收。
