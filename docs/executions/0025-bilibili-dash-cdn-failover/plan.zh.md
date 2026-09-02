[English](plan.md) | **中文**

# 执行 0025 计划

- 状态：冻结离线范围已执行完成
- 计划日期：2026-09-02
- 前置：`46905a50bbba19b7c4b74a0f7a274d5efdb013d6`
- 计划提交：`8e9467d2ecbedfd8f87e8d1d2ffb5a66d6d15591`
- 实现提交：`fe45abcb7262c3d70437aff82a05609e43902af4`
- 数据库迁移：无需且未增加

## 基线与审计

Execution 0024 在 `46905a5` 保持干净并已核对。`ResolvedLocator` 已校验一个主地址与最多八个互异备用地址，从 repr 隐藏全部 URL，并暴露有序、仅运行时的 `.urls` 元组。严格 DASH 详情/归一化已在内存中携带这些候选，但 `_download_component` 当前只请求 `.url`；遇到 `401`/`403`、传输或 HTTP 失败会直接停止，不会尝试备用地址。组件 sidecar 已不含 URL，并由持久 locator fingerprint、DASH selection 与 role 约束。锁定 bili-sync-up 的 `Stream::urls()` 同样产生“主地址 + 备用地址”，其下载器按顺序尝试候选；该 checkout 只作为只读证据，不复制实现。

基线门禁保持专项 `456 passed in 66.47s`、完整 `1780 passed, 1 skipped in 333.43s`；文档收尾时生产 ffmpeg/ffprobe 组合复验通过 `1 passed in 1.83s`。文档、上游、diff 与仓库审计通过：112 份 Markdown、两个锁定且干净的 checkout、300 个跟踪文件，以及零未跟踪/runtime/upstream 跟踪文件。

## 交付顺序

1. 为 DASH 组件增加封闭的内部候选轮次 helper；保持主地址优先、共享截止时间及既有组件字节/restart 上限，不改变公开 locator 或数据库 schema。
2. 只把候选局部 DNS/传输/中断/HTTP/Range 失败分类为可故障切换；网络策略、资源上限、本地能力、文件系统、探测及合并错误继续立即失败。
3. 候选之间重新加载 partial 状态，要求 validator/长度/offset 精确连续，并把破坏性 restart 延后到全部候选均拒绝当前 partial 后；全部候选鉴权失败时继续返回 `locator_refresh_auth_expired`。
4. 增加主地址成功短路、视频/音频备用成功、混合/全鉴权穷尽、禁用网络关闭失败、跨候选 Range 续传及整轮 restart 的单元覆盖；保持既有无备用中断、合并失败与恢复测试通过。
5. 扩展本地真实 H.264+AAC 集成组合：主组件端点失败，备用端点贯穿生产 ffprobe → ffmpeg → 最终 ffprobe → SHA-256 归档 → Emby，同时整树扫描证明全部签名候选均未保留。
6. 运行专项与完整套件，以及 Ruff、格式、严格 mypy、compileall、构建、文档、上游、diff 与保留产物审计；更新根真值文档，创建双语实现/收尾提交，推送并核对 GitHub。

## 计划提交序列

1. 文档基线 — `docs: 启动 Bilibili DASH CDN 故障切换 / start Bilibili DASH CDN failover`
2. 实现 — `feat: 闭环 Bilibili DASH CDN 故障切换 / close Bilibili DASH CDN failover`
3. 文档收尾 — `docs: 收尾 Bilibili DASH CDN 故障切换 / close Bilibili DASH CDN failover`

`.upstream` 继续排除在跟踪外、保持未修改且干净。
