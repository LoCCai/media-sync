[English](plan.md) | **中文**

# 执行 0016 计划

- 状态：冻结离线交付序列已完成
- 计划日期：2026-08-31
- 前置：Execution 0015 closeout commit `b105d00`
- 计划提交：`b7bb818`
- 实现提交：`a77ca74`

## 已执行交付顺序

1. **冻结范围与基线 — COMPLETE**
   - 已审计锁定的微博、贴吧与知乎路径；选择微博是因为原始 `mblog.pics` 已进入 creator/detail 工作流，只是在锁定 JSONL store 被丢弃。贴吧需要新增 HTML 提取，知乎没有等价的稳定媒体契约。
   - 在源码编辑前创建四份双语执行记录，并记录前置门禁：`272 passed in 46.92s`。

2. **安装共享微博媒体 shim — COMPLETE**
   - 新增一个由集成拥有的 task-local shim，并在 creator 与 detail child 导入已验证 checkout 后安装。它只增强瞬态 contents JSONL 边界，保持 `.upstream` 不变。
   - 把接受的原始形状冻结为规范正整数原创帖子、无 `retweeted_status`、无媒体 `page_info`、唯一有序 `pid` 项、源站仅 `sinaimg.cn` 或其子域，以及静态 `jpg/jpeg/png/webp` 文件；其他形状全部关闭失败。

3. **归一化并刷新精确图片 Asset — COMPLETE**
   - 只解析私有 v1 图片字段，把单图映射为 `IMAGE`、多图映射为 `GALLERY`，并生成按 position 排序的 IMAGE Asset；构建持久 raw 前递归移除全部 media-sync 私有字段。
   - 增加 WB 仅 image 的 detail/refresh 支持；请求构造、引用解析与 child 加载都要求同一个规范纯 numeric ID，同时刷新保留精确 Account、Subscription、content、Asset identity、顺序及无 query source-hint 匹配。

4. **离线组合生产路径 — COMPLETE**
   - 扩展隔离 fake checkout 契约，覆盖 creator/detail 安装、并发隔离、配置、framing 与正常成功清理；归一化加 SQLite 证明有序 Asset 与精确 `AssetRefreshSource` 来源。
   - 把平台组合 E2E 扩展为双图；每个 Asset 分别执行精确 detail 刷新、默认 profile 公网 DNS/HTTP 传输与 SHA-256 归档发布；Emby 布局接收首图 poster、次图 backdrop、两个有序 gallery 文件、NFO 与白名单 source 元数据；重放不产生额外工作。

5. **审查与修复 — COMPLETE**
   - 独立审查发现并关闭三项边界缺陷：任意代理内嵌源站、非静态/未知扩展名，以及不同但合法的 WB numeric detail reference。
   - 同一审查发现单图组合证据不足以支持 Gallery 声明；E2E 现已证明两个不同 Asset、下载、归档与 gallery 输出。

6. **验证实现 — COMPLETE**
   - 合并 15 文件专项门禁：`388 passed in 125.73s`。
   - 完整套件：`1251 passed, 1 skipped in 359.38s`；跳过项是 Windows 不适用的 POSIX mode-bit 用例。
   - Ruff 静态检查通过；228 个文件格式正确；严格 mypy 通过 78 个源码文件；两个锁定上游条目校验通过；`uv build` 产生 wheel 与源码分发包；diff 检查通过。

7. **完成交付收尾 — COMPLETE**
   - 已定稿双语真值文档，重跑文档/构建/diff 检查，审计保留产物，并准备独立双语收尾提交。推送该提交并核对本地、`origin/main` 与 GitHub SHA 属于提交后的交付动作，由任务交接结果报告。

## 延期范围与风险

- 微博视频、GIF/动图语义、长图处理、媒体 `page_info`、转发及受限/直播媒体仍不属于本切片。
- creator 模式仍遍历完整历史；由于尚未实现有界 creator 分页，显式 `allow_full_history` 与外层 watchdog 仍为强制要求。
- 离线验收证明确定性代理 URL 构造与封闭请求 profile，不证明第三方代理可用性、限流、服务条款或新浪直连 profile。
- 同 ID 媒体替换检测、注入清理失败 quarantine 及全部真人平台/CDN/媒体服务器验收继续延期或保持 `NOT_RUN`。
