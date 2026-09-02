[English](goal.md) | **中文**

# 执行 0019 目标

- 状态：冻结离线切片已交付；真人验收 `NOT_RUN`；七平台总目标继续推进
- 日期：2026-09-02
- 前置：`4fb639a`
- 计划提交：`dc1714c`
- 实现提交：`2edb9d763b4948c56cc182bcc5012914bcb644d1`

## 目标

在不修改锁定 MediaCrawler checkout 的前提下增加首个知乎可下载媒体切片：以 Subscription `max_items` 成功约束作者订阅，从普通回答捕获精确一个静态图片候选，把它归一化为 ARTICLE 所属 IMAGE，以持久且不含密钥的权限刷新，经生产安全边界下载，并发布确定性的 Emby/Jellyfin 兼容输出。

## 冻结验收边界

1. 锁定上游回答请求包含原始 `content` HTML，但 extractor/update/JSONL 路径会丢弃可下载属性。源码绑定合约在 MediaCrawler SHA `d6f7c5bb906b6dac40ddf343ef9e26438a3de092` 上执行该真实丢失边界；`.upstream` 保持未修改且不纳入跟踪。
2. 只声明作者普通回答中的精确一张受管图片。属性优先级为 `data-original` → `data-actualsrc` → `src`；重复或竞争性 lazy/`srcset` 候选、多图、player/video/容器漂移、畸形 ID 与不支持 URL 均关闭失败。canonical 回答 URL 拒绝 query/fragment 分隔符；图片 URL 要求有界 HTTPS `zhimg.com` 权限、静态扩展名，且不得含空 query 或 fragment 分隔符。
3. 校验 checkout shim 把捕获绑定到精确返回的 Pydantic 对象，只在嵌套存储阶段使用 `ContextVar`，因此 `asyncio.gather` 子任务中的提取可由父任务存储且不会泄漏到并发任务。定时作者执行把 `max_items=23` 约束为页面大小 `20 + 3` 的两次 API 请求与两次 callback 调用，callback 精确处理 23 行，页间执行一次节奏 sleep；达到上限后没有第三次请求或额外 sleep。短非终止页与重复页关闭失败。因此知乎已从 `FULL_HISTORY_PLATFORMS` 移除。
4. 归一化保持 `ContentKind.ARTICLE`，并创建精确一个 position 0、remote ID 为 `<content_id>:image:0` 的 IMAGE。私有捕获字段与瞬态 query 权限不会进入归一化 raw、SQLite 或保留产物。
5. 惰性刷新只从持久 canonical 回答 URL 派生允许的 detail 权限，在 refresh/父/child 边界独立复核，要求唯一精确的 ARTICLE/IMAGE/source-hint 匹配，并返回不携带账户 Cookie、Authorization、Referer 或 Origin 的 `MediaRequestProfile.DEFAULT`。
6. 知乎 IMAGE 下载自动要求有界静态结构资格校验。结构合格的 JPEG、PNG、WebP 夹具通过；GIF、APNG、animated WebP 与 AVIF 夹具失败。该门是有界容器/结构检查，不是完整像素解码器；normal、recovery 与 takeover 准备链都会保留此要求。
7. 隔离组合贯穿精确 SQLite 来源、fake detail、mock 公网 DNS/HTTP、生产字节资格校验、SHA-256 归档及 Emby poster/backdrop/gallery/body/NFO/source 发布。仅 query 变化的重放新增工作为零，保留的 SQLite/runtime/archive/export/WAL/SHM 产物不含私有捕获数据或瞬态 query 值。
8. 扩大专项门、完整套件、Ruff、格式、严格 mypy、compileall、上游锁、构建、文档、保留产物审计及独立审查必须在收尾前通过。真人知乎登录/作者/detail/CDN 与真实 Emby/Jellyfin 验收明确保持 `NOT_RUN`。

## 延期范围

知乎回答多图/gallery、文章、zvideo 播放/封面、真实脱敏夹具及真人验收继续延期或保持 `NOT_RUN`。贴吧仍没有已验收的可下载媒体切片，因此七平台总目标继续推进。
