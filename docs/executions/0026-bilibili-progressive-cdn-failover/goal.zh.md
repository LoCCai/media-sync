[English](goal.md) | **中文**

# 执行 0026 目标

- 状态：冻结离线范围已交付；真人验收保持 `NOT_RUN`
- 日期：2026-09-02
- 前置：Execution 0025 closeout `7cb84fc6c93b832492b95513d9cb6a9708ee6cc9`
- 计划提交：`0694934bc9230151a85c040a061d6e704dffc4fc`
- 实现提交：`190488f77d1704492cc148b890d6f9ae16d84f84`
- 范围：为既有单段 Bilibili progressive `durl` 形状增加有序、有界的主 CDN → 备用 CDN 故障切换

## 目标结果

保持当前兼容单 P 与 2–64 分 P progressive 媒体形状不变，同时把每个精确目标 CID 的 `durl[0].url` 与零至八个已校验 `backup_url` 候选，经私有详情桥接与运行时 locator 传递。下载时先尝试主地址，再在同一锁、截止时间、字节上限、严格 Range 约束、探测、不可变归档及确定性 Emby 生命周期下尝试备用地址。候选值与胜出序号保持瞬态。

## 冻结验收边界

1. 严格 Bilibili 播放解析器继续只接受精确一个 `durl` 分段；要求一个合法主 `url`，接受缺失或内容等价的 `backup_url`/`backupUrl` 别名，并通过 `ResolvedLocator` 校验最多八个互异字符串备用地址；畸形、冲突、重复或与主地址相同的候选均关闭失败。
2. 单 P 与多分 P 私有 JSONL 桥接只在有界私有字段中携带备用地址；归一化同时接受历史“仅主地址”桥接与新的“主地址加备用地址”桥接，返回一个 repr-safe `ResolvedLocator`，并在持久 raw 元数据、SQLite 或 Job 创建前递归移除全部私有字段。
3. 通用 resolved-locator 下载按来源顺序使用 `ResolvedLocator.urls`；主地址成功时不产生备用 DNS 或 HTTP 工作；每轮继续受“一个主地址加最多八个备用地址”及既有共享 `DownloadLimits.total_timeout_seconds` 约束。
4. 候选局部 DNS、timeout、传输、中断、HTTP 状态及非空 partial 的 Range 不兼容可推进；禁用/混合网络地址、重定向/header/encoding、chunk/size、文件系统、探测、归档与发布失败仍立即关闭，且不得触碰后续候选。
5. 跨候选追加要求请求 offset、总长度及强 validator 类型/值完全一致；仍有后续候选时，不兼容候选不得丢弃合法 partial；只有完整轮次拒绝后，才可消耗既有有界 restart 次数并从零开始。
6. 对 adapter-refresh locator，一轮内全部候选均返回 `401`/`403` 时触发现有的一次新详情重解析，再尝试新的有界候选列表一次；第二轮仍全部鉴权失败则返回 `locator_refresh_auth_expired`；混合穷尽返回固定脱敏错误。Direct/无刷新行为保持不变。
7. 由备用地址交付的 progressive MP4 仍须通过精确 Bilibili request profile、媒体探测、SHA-256 归档、主媒体/part Emby 发布及零工作重放；保留 SQLite、Job、runtime、work、归档、导出、NFO/source 与运维错误均不得包含签名候选或胜出序号。
8. 既有无备用 progressive、DASH 故障切换/合并、静态媒体、中断恢复、鉴权刷新及已发布成品恢复行为保持兼容；两个锁定上游 checkout 保持未修改且干净。

## 明确排除

多个 `durl` 分段、FLV remux、可配置 CDN 排序/评分、并行竞速、跨运行坏 CDN 缓存、混合/非鉴权穷尽后的新详情重试、字幕/弹幕、超过 64 个分 P、更广 Bilibili 类型、真实 Bilibili 账户/API/CDN 字节及真实 Emby/Jellyfin 扫描/播放继续延期或保持 `NOT_RUN`。本执行是既有形状的可靠性工作，不是第十三个冻结媒体形状，也不代表完整 Bilibili 支持。
