[English](progress.md) | **中文**

# 执行 0016 推进结果

- 状态：冻结离线实现与收尾证据已完成；真人验收保持 `NOT_RUN`
- 开始时间：2026-08-31
- 计划提交：`b7bb818`
- 实现提交：`a77ca74`

## 已实现

- 已在不修改任何上游 checkout 的前提下审计锁定版 MediaCrawler 微博、贴吧与知乎路径。选择微博是因为 creator/detail 已收到原始 `mblog.pics`；锁定微博 JSONL store 才是丢弃它的边界。
- 在真实 creator 与 detail child 导入已验证 checkout 后增加同一个 task-local 微博媒体 shim。并发 note task 保持独立捕获状态，JSONL 增强为瞬态，且 `.upstream` 保持干净。
- 冻结狭窄普通原创边界：规范正整数 note ID、非转发、无媒体 `page_info`、有序唯一 `pid`、源站仅 `sinaimg.cn` 或其子域、扩展名仅 `jpg/jpeg/png/webp`。非法标量、嵌套、缺字段、重复、外部源站、非静态扩展名及重排刷新形状均关闭失败。
- 把单图归一化为 `ContentKind.IMAGE`，多图归一化为 `ContentKind.GALLERY`；生成有序 IMAGE Asset、稳定 adapter-refresh locator，以及绑定 Account 与 Subscription 的精确 SQLite `AssetRefreshSource` observation。
- 增加 WB 仅 image 的 detail/refresh 支持，并在父请求构造、resolved detail reference 与 child frame load 三层校验完全相同的纯 numeric ID；精确 content/remote ID/kind/position/source-hint 匹配防止跨项或重排选择。
- 在创建持久 raw 前递归移除集成私有字段、捕获 PID 值及嵌套签名 URL 漂移；SQLite、runtime/work 根目录、两个归档、export staging/library 与 sidecar 产物均不含这些私有值。
- 把组合测试扩展为真实双图 Gallery：两次精确刷新、两次公网 DNS/默认 profile HTTP 传输、两份不同合成 PNG 字节流、两个独立 SHA-256 归档、首图 poster、次图 backdrop、有序 gallery 001/002、NFO 引用及白名单 source 元数据。
- 证明零工作重放：已验证 Asset 与已完成 export 不会新增 detail runner、HTTP、DNS、probe、archive 或 export 工作，且归档与媒体库树逐字节不变。
- 独立审查直接促成四项修正：新浪 authority 限制、静态扩展名限制、WB detail ID 精确相等，以及以双图 Gallery E2E 替代单图组合。

## 已完成验证

- 前置基线：`272 passed in 46.92s`。
- 15 文件合并专项门禁：`388 passed in 125.73s`。
- 完整套件：`1251 passed, 1 skipped in 359.38s`；跳过项是 Windows 不适用的 POSIX mode-bit 测试。
- Ruff 静态检查通过；`ruff format --check` 报告 228 个文件格式正确；严格 mypy 成功检查 78 个源码文件。
- 两个锁定上游条目校验通过；`uv build` 创建两个分发产物；diff 检查通过。
- 最终文档链接检查通过 80 个 Markdown 文件。保留清单报告 246 个 tracked 文件、零个标准 untracked 或禁止路径、914 个 runtime/build 文件、保留 runtime 数据中执行 0016 marker 零命中，并保留冻结的 0007/0008 两个 sentinel 根。

## 待实现

- 微博视频、GIF/动图语义、长图特殊处理、媒体 `page_info`、转发、受限/直播媒体及有界 creator 分页仍未实现或未验收。
- 新浪直连请求 profile、第三方代理可用性验收、同 ID 媒体替换检测及注入清理失败 quarantine 仍为后续工作。
- 全部真人 QR/Cookie/saved-session 登录、真人 creator 扫描、真实 detail/代理/CDN 传输、真实平台字节探测及真实 Emby/Jellyfin 服务器扫描/查看行均保持 `NOT_RUN`。
- 更广的项目目标继续进行：本微博切片不代表其余媒体形状及 MediaCrawler 全平台真人验收已经完成。
