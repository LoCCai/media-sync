[English](goal.md) | **中文**

# 执行 0016 目标

- 状态：冻结离线范围已完成；全部真人验收行保持 `NOT_RUN`
- 开始时间：2026-08-31
- 前置：Execution 0015 closeout commit `b105d00`
- 计划提交：`b7bb818`
- 实现提交：`a77ca74`

## 已交付结果

执行 0016 已收口一条经过离线验收的普通原创微博图片帖路径：从作者发现、精确 detail 刷新、两项独立图片下载，到不可变 SHA-256 归档发布与 Emby/Jellyfin 文件系统布局输出。接受边界为规范正整数 creator/note identity，不含 `retweeted_status`，不含媒体 `page_info`，并具有扁平有序的 `mblog.pics` 列表。每张图片必须具有唯一合法 `pid`，来源仅限 `sinaimg.cn` 或其子域，且静态扩展名仅限 `jpg`、`jpeg`、`png`、`webp`。单图归一化为 `ContentKind.IMAGE`；多图归一化为 `ContentKind.GALLERY`；图片 Asset 保持 `0..N-1` position。

作者发现与 detail 刷新都会在导入已验证的锁定 checkout 后安装同一个 task-local 集成 shim。该 shim 在上游 store 边界捕获原始 `mblog.pics`，只增强瞬态 contents JSONL 记录，不修改 `.upstream`。creator 侧发现是创建初始 Asset 与精确 `AssetRefreshSource` 的必要条件；只支持 detail 仍无法让自动订阅流水线可达。

## 验收结果

1. **Creator 与 detail shim — PASS.** 隔离 creator child 证明并发 note 工作下的 task-local 捕获；隔离 detail child 证明 `platform=wb`、精确纯 numeric `WEIBO_SPECIFIED_ID_LIST`、JSONL/媒体关闭/并发控制、账户/profile 范围、有界 framing 及成功 attempt 清理。
2. **封闭形状与持久边界 — PASS.** 只有具有有序、唯一新浪静态图片项的普通原创 numeric 帖子会产生 Asset。字符串/嵌套/缺字段/重复/漂移项、外部源站、非静态扩展名、转发及 `page_info` 均关闭失败。集成私有字段、捕获 PID 值与嵌套签名 URL sentinel 会从 normalized raw、SQLite 及保留的 runtime/archive/export 落点中递归消失。
3. **精确身份与刷新 — PASS.** WB 只接受 image Asset。父请求构造、resolved detail reference 与 child frame 三层都要求完全相同的规范纯 numeric note ID；刷新还会精确匹配 Account、Subscription、content、remote ID、kind、position 与无 query source hint。图片重排或重复身份会关闭失败。
4. **双图组合 — PASS.** Gallery E2E 创建两个有序 IMAGE Asset 与精确 SQLite 来源，执行两次 detail 刷新、两次默认 profile HTTP/DNS 传输与两个独立 SHA-256 归档发布，然后输出首图 poster、次图 backdrop、两个有序 gallery 文件、NFO 与白名单 source 元数据。请求不含 Cookie、Authorization、Referer 或 Origin。
5. **重放与门禁 — PASS.** 已验证/已导出的 Asset 不会新增 detail、HTTP、DNS、probe、archive 或 export 工作。专项门禁通过 388 项；完整套件通过 1251 项，另有一项 Windows 不适用的 POSIX mode-bit 测试跳过。Ruff、格式、mypy、文档、上游锁定校验、构建、diff 及保留产物门禁均通过。

## 审查修复

- 把代理 URL 内嵌源站从任意 host 收紧为仅 `sinaimg.cn` 及其子域。
- 把冻结媒体扩展名收紧为 `jpg`、`jpeg`、`png` 与 `webp`；视频、GIF 动图及未知后缀不能产生 IMAGE Asset。
- 在 WB 请求构造、引用解析与 child-load 三层边界要求 `detail_reference` 与 `content_remote_id` 完全相等。
- 把组合测试从单图扩展为真正双图 Gallery，分别证明刷新、传输与归档。

## 明确排除与总目标待办

- 微博视频、动图语义、长图特殊处理、媒体 `page_info`、转发、直播/付费/受限媒体、评论及作者头像媒体仍未实现或未验收。
- 有界 creator 分页仍不可用；锁定微博 creator 路径会遍历完整历史，因此显式 `allow_full_history` 与外层 watchdog 仍为强制要求。
- 新浪直连请求 profile、第三方代理可用性、同 ID 媒体替换检测及注入清理失败 quarantine 继续延期。
- 全部真人登录、creator 扫描、detail/代理/CDN 传输、真实平台字节探测及 Emby/Jellyfin 服务器扫描/查看行均保持 `NOT_RUN`；完整项目目标要求的其他平台工作继续进行。
