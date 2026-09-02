[English](plan.md) | **中文**

# 执行 0026 计划

- 状态：冻结离线范围已执行完成
- 计划日期：2026-09-02
- 前置：`7cb84fc6c93b832492b95513d9cb6a9708ee6cc9`
- 计划提交：`0694934bc9230151a85c040a061d6e704dffc4fc`
- 实现提交：`190488f77d1704492cc148b890d6f9ae16d84f84`
- 数据库迁移：无需且未增加

## 基线与审计

Execution 0025 在 `7cb84fc` 保持干净并已核对。`ResolvedLocator` 已校验、限制、去重并隐藏一个主地址与最多八个备用 URL。DASH 已按顺序使用这些候选并执行严格 partial 连续性，但 `_bili_playback_result` 会丢弃 progressive `durl[0].backup_url`，私有 progressive 桥接只携带主地址，`_download_locked` 也只请求 `locator.url`。稳定 fingerprint 与 partial sidecar 已不含 URL，因此无需 schema 或 migration。

锁定 MediaCrawler checkout 仍只选择 progressive 主 URL。锁定 bili-sync-up analyzer 为 DASH 建模主/备用地址，其 stream cache 暴露通用 `backup_urls`，但 mixed `durl` 当前也仅保留主地址；两者只作为只读设计证据，不复制也不修改。基线门禁为 Execution 0025 专项 `466 passed in 66.96s`、完整 `1790 passed, 1 skipped in 331.33s`、生产备用路径组合 `1 passed in 1.74s`、116 份 Markdown、两个锁定且干净的 checkout、304 个跟踪文件，以及零未跟踪/runtime/upstream 跟踪文件。

## 交付顺序

1. 增加一个私有单 P progressive 备用字段，并以 `backup_urls` 扩展多分 P 私有 payload；把新字段纳入碰撞检测与递归移除，同时保持历史仅主地址 payload 兼容。
2. 通过封闭 helper 解析 `durl[0]` 主地址与备用别名，强制既有“最多八个/互异/URL”约束，并返回 repr-safe 运行时 `ResolvedLocator`。
3. 从已验证 DASH 路径提取共享有序候选轮次 helper，并用于普通 resolved locator；保持主地址优先、单一截止时间、精确 partial 约束、整轮 restart 与关闭失败错误分类。
4. 只有一轮全部为 `401`/`403` 后才执行一次 adapter 重解析，以保持鉴权刷新语义；progressive 路径拒绝刷新为 DASH/schema 漂移，并保持 direct locator 行为。
5. 增加解析器/归一化/单元覆盖：别名与非法形状、主地址短路、有序备用成功、DNS/HTTP 穷尽、网络策略/上限关闭失败、严格跨候选续传、整轮 restart 及新详情鉴权轮换。
6. 扩展 Bilibili progressive 的 SQLite → 精确 CID 详情 → 主地址失败 → 备用 HTTP → 探测 → SHA-256 归档 → Emby 组合及保留树扫描，并按需覆盖单 P 兼容与多分 P part 发布。
7. 运行专项与完整套件，以及 Ruff、格式、严格 mypy、compileall、构建、文档、上游、diff 与仓库审计；更新执行四件套与根真值，再创建双语实现/收尾提交，推送并核对 GitHub。

## 计划提交序列

1. 文档基线 — `docs: 启动 Bilibili progressive CDN 故障切换 / start Bilibili progressive CDN failover`
2. 实现 — `feat: 闭环 Bilibili progressive CDN 故障切换 / close Bilibili progressive CDN failover`
3. 文档收尾 — `docs: 收尾 Bilibili progressive CDN 故障切换 / close Bilibili progressive CDN failover`

`.upstream` 继续排除在跟踪外、保持未修改且干净。
