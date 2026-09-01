# Execution 0025 plan / 执行 0025 计划

- Status / 状态：Frozen and ready to execute / 已冻结并可执行
- Plan date / 计划日期：2026-09-02
- Predecessor / 前置：`46905a50bbba19b7c4b74a0f7a274d5efdb013d6`
- Database migration / 数据库迁移：None planned / 计划无

## Baseline and audit / 基线与审计

Execution 0024 is clean and reconciled at `46905a5`. `ResolvedLocator` already validates one primary plus at most eight distinct backups, hides all URLs from repr and exposes the ordered runtime-only `.urls` tuple. Strict DASH detail/normalization carries those candidates in memory, but `_download_component` currently requests only `.url`; a `401`/`403`, transport failure or HTTP failure stops without trying a backup. Component sidecars are already URL-free and fenced by durable locator fingerprint, DASH selection and role. The pinned bili-sync-up `Stream::urls()` similarly yields primary plus backups and its downloader attempts candidates sequentially; its checkout remains read-only evidence, not copied implementation. / Execution 0024 在 `46905a5` 保持干净并已核对。`ResolvedLocator` 已校验一个主地址与最多八个互异备用地址，从 repr 隐藏全部 URL，并暴露有序、仅运行时的 `.urls` 元组。严格 DASH 详情/归一化已在内存中携带这些候选，但 `_download_component` 当前只请求 `.url`；遇到 `401`/`403`、传输或 HTTP 失败会直接停止，不会尝试备用地址。组件 sidecar 已不含 URL，并由持久 locator fingerprint、DASH selection 与 role 约束。锁定 bili-sync-up 的 `Stream::urls()` 同样产生“主地址 + 备用地址”，其下载器按顺序尝试候选；该 checkout 只作为只读证据，不复制实现。

Baseline gates remain `456 passed in 66.47s` focused, `1780 passed, 1 skipped in 333.43s` complete, and the documentation-closeout production ffmpeg/ffprobe composition rerun passes `1 passed in 1.83s`. Documentation, upstream, diff and repository audits pass with 112 Markdown files, two locked clean checkouts, 300 tracked files and zero untracked/runtime/upstream tracked files. / 基线门禁保持专项 `456 passed in 66.47s`、完整 `1780 passed, 1 skipped in 333.43s`；文档收尾时生产 ffmpeg/ffprobe 组合复验通过 `1 passed in 1.83s`。文档、上游、diff 与仓库审计通过：112 份 Markdown、两个锁定且干净的 checkout、300 个跟踪文件，以及零未跟踪/runtime/upstream 跟踪文件。

## Delivery sequence / 交付顺序

1. Add a closed internal candidate-pass helper for DASH components. Preserve primary-first ordering, one shared deadline and the existing component byte/restart limits without changing public locator or database schemas. / 为 DASH 组件增加封闭的内部候选轮次 helper；保持主地址优先、共享截止时间及既有组件字节/restart 上限，不改变公开 locator 或数据库 schema。
2. Classify only candidate-local DNS/transport/interruption/HTTP/Range failures as failover-eligible. Preserve immediate failure for network-policy, resource-limit, local capability, filesystem, probe and mux errors. / 只把候选局部 DNS/传输/中断/HTTP/Range 失败分类为可故障切换；网络策略、资源上限、本地能力、文件系统、探测及合并错误继续立即失败。
3. Reload partial state between candidates, require exact validator/length/offset continuity and defer destructive restart until all candidates reject the current partial. Preserve all-auth exhaustion as `locator_refresh_auth_expired`. / 候选之间重新加载 partial 状态，要求 validator/长度/offset 精确连续，并把破坏性 restart 延后到全部候选均拒绝当前 partial 后；全部候选鉴权失败时继续返回 `locator_refresh_auth_expired`。
4. Add unit coverage for primary short-circuit, video/audio backup success, mixed/all-auth exhaustion, forbidden-network fail-closed behavior, cross-candidate Range resume and whole-pass restart. Keep existing no-backup interruption, failed mux and recovery tests green. / 增加主地址成功短路、视频/音频备用成功、混合/全鉴权穷尽、禁用网络关闭失败、跨候选 Range 续传及整轮 restart 的单元覆盖；保持既有无备用中断、合并失败与恢复测试通过。
5. Extend the real local H.264+AAC integration composition so primary component endpoints fail and backup endpoints reach production ffprobe → ffmpeg → final ffprobe → SHA-256 archive → Emby, while whole-tree scans prove all signed candidates remain absent. / 扩展本地真实 H.264+AAC 集成组合：主组件端点失败，备用端点贯穿生产 ffprobe → ffmpeg → 最终 ffprobe → SHA-256 归档 → Emby，同时整树扫描证明全部签名候选均未保留。
6. Run focused and complete suites plus Ruff, format, strict mypy, compileall, build, docs, upstream, diff and retained-artifact audits; update root truth documents, create bilingual implementation/closeout commits, push and reconcile GitHub. / 运行专项与完整套件，以及 Ruff、格式、严格 mypy、compileall、构建、文档、上游、diff 与保留产物审计；更新根真值文档，创建双语实现/收尾提交，推送并核对 GitHub。

## Planned commit sequence / 计划提交序列

1. Documentation baseline / 文档基线 — `docs: 启动 Bilibili DASH CDN 故障切换 / start Bilibili DASH CDN failover`
2. Implementation / 实现 — `feat: 闭环 Bilibili DASH CDN 故障切换 / close Bilibili DASH CDN failover`
3. Documentation closeout / 文档收尾 — `docs: 收尾 Bilibili DASH CDN 故障切换 / close Bilibili DASH CDN failover`

`.upstream` remains excluded, unmodified and clean. / `.upstream` 继续排除在跟踪外、保持未修改且干净。
