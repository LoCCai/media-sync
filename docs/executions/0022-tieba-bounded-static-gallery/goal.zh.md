[English](goal.md) | **中文**

# 执行 0022 目标

- 状态：冻结离线范围已交付并验证；真人验收 `NOT_RUN`
- 日期：2026-09-02
- 前置：Execution 0021 closeout `817875bdd1902f54c72397fa7da46359fbe33207`
- 计划提交：`fbcb7cf5c642fc9da210faa5d92b6886b350a9b8`
- 实现提交：`b6d03aa1c6705e52c2e47c63086a5b7200c208e7`
- 范围：贴吧作者普通主题首楼中的 3 至 64 张有序静态图片

## 目标结果

在不改变已交付单图与双图贴吧 ARTICLE 版本身份的前提下扩展能力。包含 3–64 个当前 type-3 图片对象的合格普通首楼会成为一个 ARTICLE 与等量有序 IMAGE Asset。校验 shim 把完整签名 gallery 跨越锁定 gather-child → parent-store 丢失边界，持久状态只保留互异无 query 身份，精确 canonical 详情刷新重新取得完整当前 gallery，既有有界字节/归档/Emby 流水线按位置确定性处理每项图片。

## 冻结验收边界

1. v1 继续代表精确单图，v2 继续代表精确双图；独立 `__media_sync_tieba_first_floor_gallery_v3` 字段只代表 3–64 张图片，同一行只能声明一个版本字段。
2. gallery 上限为 64；结合既有 4,096 字符 locator 上限，v3 捕获 URL 列表在 JSON 转义前最多约 256 KiB，即 1 MiB child watchdog 行预算的四分之一；常规 JSONL/watchdog 限制继续作为整条记录的最终门禁。
3. 每张图片都满足既有精确十键/标量/host/path/query 合约；来源顺序即 Asset position，所有无 query 身份互异。65 张及以上、畸形项、重复项、其他内容类型与版本字段冲突均关闭失败。
4. 刷新绑定完整持久身份元组；任一请求 position 都要求当前 gallery 的数量、顺序与无 query 身份完整一致；缺图、增图、重排、替换或重复均关闭失败。
5. 离线组合至少证明三份不同静态图片字节/格式、精确下载、SHA-256 归档、poster/backdrop/N 项 gallery/body/NFO/source 输出及仅 query 变化的零工作重放。

## 明确排除

图片与视频/语音/表情/链接/富卡片混合首楼、回复/评论媒体、其他图片权限、64 张以上图片、替换语义及全部登录/现网平台/CDN/Emby/Jellyfin 行继续延期或保持 `NOT_RUN`；本执行不宣称完整贴吧媒体支持。
