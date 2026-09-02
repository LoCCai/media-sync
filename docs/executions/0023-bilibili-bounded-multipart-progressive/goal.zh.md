[English](goal.md) | **中文**

# 执行 0023 目标

- 状态：冻结离线范围已交付并验证；真人验收 `NOT_RUN`
- 日期：2026-09-02
- 前置：Execution 0022 closeout `27e45c89f20e8eb6bc871ab1505fe25167b70ae3`
- 计划提交：`bd45478b28cc61a7f35b6211faf3a0fc1eb94138`
- 实现提交：`24fd41c600eb30fb2df22079e3cf52778589959e`
- 范围：普通 numeric-aid Bilibili 投稿中的 2 至 64 个有序分 P，每个分 P 一个 progressive 流

## 目标结果

在不削弱既有逻辑首 P Bilibili 视频精确单页兼容边界的前提下扩展能力。合格的 2–64 分 P 普通投稿会成为一个 VIDEO 内容行与等量有序、仅 locator 的 VIDEO Asset。校验 shim 把稳定 `page`/`cid` 身份跨越锁定 MediaCrawler 的 store 丢失边界，精确详情刷新只解析请求的 CID，同时绑定完整当前分 P 元组，既有有界下载/归档/Emby 流水线确定性发布每个已验证分 P。

## 冻结验收边界

1. 既有精确单页身份 `<aid>:video:0` 保持兼容；有效 2–64 分 P 捕获使用有序、互异的正 CID，并在 `0..N-1` 位置使用稳定 `<aid>:video:cid:<cid>` 身份。
2. forward child 只在锁定 Bilibili store 丢弃数据前捕获非秘密的 `page` 与 `cid`；私有捕获字段和签名播放 URL 在持久化前递归移除。
3. 刷新加载完整持久 VIDEO 兄弟元组，通过严格 child 协议传递目标 CID，要求当前详情元组在数量、顺序与身份上完全一致，并只接受该 CID 的精确一个 progressive `durl`；缺失、新增、重排、替换、重复或畸形分 P 均关闭失败。
4. 离线组合至少证明三个分 P 的不同字节、定向详情调用、Bilibili 请求 profile、SHA-256 归档、确定性 Emby 主/part 媒体与 NFO/source 文件，以及 query-only 重放零新增 detail/DNS/HTTP/archive/export 工作。
5. 两个锁定上游 checkout 保持只读且干净；集成只在 `media-sync` 内实现。

## 明确排除

DASH 音视频选择与合并、多 `durl` 分段、字幕、弹幕、备用 URL 故障切换、FLV 转封装、64 个以上分 P、番剧/付费/直播媒体、真实账户/CDN 行为及真实 Emby/Jellyfin 扫描继续延期或保持 `NOT_RUN`；本执行不宣称完整 Bilibili 媒体支持。
