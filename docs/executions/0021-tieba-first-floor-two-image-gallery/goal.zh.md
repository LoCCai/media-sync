[English](goal.md) | **中文**

# 执行 0021 目标

- 状态：冻结离线范围已交付并验证；真人验收 `NOT_RUN`
- 日期：2026-09-02
- 前置：Execution 0020 closeout `e5d871050cdf25da1a51e2f057ba317dea2cffb1`
- 计划提交：`5095ed6e803a8a2f0a3134e756dd3e101fef10bd`
- 实现提交：`e0fb8d572c8f5535a5495c2dfbf5b9cdf78461e7`
- 范围：贴吧作者普通主题首楼中的精确两张有序静态图片

## 目标结果

在不改变已交付单图贴吧 ARTICLE 身份或兼容性的前提下扩展能力。普通文本加精确两个当前 type-3 图片对象的合格首楼，会成为一个 ARTICLE 与 position 0、1 的两项有序 IMAGE Asset。校验 shim 把两个签名 locator 跨越锁定 gather-child → parent-store 丢失边界，持久状态只保留互异的无 query 身份，精确 canonical 详情刷新在既有静态字节/归档/Emby 流水线前重新取得两个当前签名 locator。

## 冻结验收边界

1. Execution 0020 单图私有字段、归一化身份、刷新与导出保持兼容；新 gallery 字段独立版本化，同一行不得同时声明两个字段。
2. 媒体形状包含有界首楼列表、至少一个普通 type-0 文本项及精确两个满足既有十键/标量/host/path/query 合约的 type-3 项；顺序即来源顺序。零图、单图、三张及以上、其他内容类型、重复持久身份或畸形项不通过本 gallery 声明。
3. 归一化保留 ARTICLE，并精确输出 `<note_id>:image:0` 与 `<note_id>:image:1`；私有字段与签名 query 递归地不进入 raw、SQLite 与保留产物。
4. 刷新只接受精确双图 ARTICLE 的 position 0 或 1，复核 canonical 父/child 权限，要求完整有序 gallery 与匹配无 query hint，再以无凭据 DEFAULT profile 返回当前签名 URL；重排或替换关闭失败。
5. 两张图片都自动使用有界静态结构门与确定性 Emby gallery 布局；双图组合必须证明精确下载、SHA-256 归档、poster/backdrop/两项 gallery/body/NFO/source 输出及仅 query 变化的零工作重放。

## 明确排除

三张及以上图片、媒体替换语义、图片与视频/语音/表情/链接/富卡片混合内容、回复/评论媒体、其他图片权限、保留的真实响应夹具及全部登录/现网平台/CDN/Emby/Jellyfin 行继续延期或保持 `NOT_RUN`；本切片不代表贴吧 gallery 或媒体能力已完整支持。
