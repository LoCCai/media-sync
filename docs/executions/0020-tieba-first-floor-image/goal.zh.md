[English](goal.md) | **中文**

# 执行 0020 目标

- 状态：冻结离线范围已交付并验证；登录/现网验收 `NOT_RUN`
- 日期：2026-09-02
- 前置：Execution 0019 closeout commit `431fd855dafce502e83f74a055a4b27ae5c6f40b`
- 计划提交：`df7a38a6f9beee35c6c19336260b512ebc87ce0d`
- 实现提交：`8a0e935624e944809af1a56b0f02186686433d95`
- 范围：贴吧作者普通主题首楼中的精确一张静态图片

## 目标结果

Execution 0020 已增加首个可下载的贴吧媒体切片，从而为第七个平台建立一条狭窄媒体路径。校验 checkout 的运行时 shim 会在锁定 MediaCrawler extractor 把结构化内容压成文本前，从当前 `page_pc` 响应中捕获首楼精确一个 `type=3` 图片。定时作者发现受 Subscription `max_items` 约束；归一化保留 ARTICLE 主题并增加一个 position 0 IMAGE；下载前通过精确 canonical 详情查找重新取得当前瞬态 `tbpicau` locator；既有有界静态图片门、SHA-256 归档及确定性 Emby/Jellyfin 布局完成离线闭环。

## 本切片证据

- 在锁定 MediaCrawler SHA `d6f7c5bb906b6dac40ddf343ef9e26438a3de092` 中，`BaiduTieBaClient.get_note_by_id` 先调用 `_get_pc_page_data`，再调用 `TieBaExtractor.extract_note_detail_from_api`。后者收到完整响应，但 `_extract_api_content_text` 只保留 `text`/`c`；因此 `TiebaNote`、`model_dump()` 与 JSONL 会丢失全部图片 locator。
- 2026-09-02 对当前公开 API 的有界、未登录、只读审计找到了真实成功首楼，其中精确包含一个整数 `type=3` 项。该项公开稳定键族 `origin_src`、`cdn_src`、`big_cdn_src`、`cdn_src_active`、`pic_id`、`bsize`、`origin_size`、`is_long_pic` 与 `show_original_btn`；观察到的图片 URL 均使用 HTTPS `tiebapic.baidu.com` 与唯一 `tbpicau` query 键。本仓库不保留任何 query 值或响应正文。
- 一次瞬态 DEFAULT-profile 检查中，刷新后的带签名 `origin_src` 返回 65,144 字节 JPEG；同一 origin/path 去掉 query 后返回另一份 4,262 字节 JPEG。这证明即使无 query 地址返回 HTTP 200，也不能把无 query 持久提示直接作为下载 locator；该检查不代表未来 CDN 行为已验收。

## 冻结验收边界

1. 合格 API 形状必须具有规范正整数主题 ID、精确 `https://tieba.baidu.com/p/<id>` 返回 URL、有界首楼 content 列表、精确一个整数 `type=3` 图片项，且其余兄弟项只能是普通整数 `type=0` 文本。零图片继续保持历史仅 ARTICLE 行为，但不属于本次媒体声明；多图片、其他内容类型、缺失/额外歧义媒体键、畸形 ID 或返回对象不匹配均不产生合格 Asset，并使刷新关闭失败。
2. 选择只使用 `origin_src`。它必须是有界 HTTPS、host 精确为 `tiebapic.baidu.com`、使用默认端口与规范 `/forum/pic/item/<40 位小写十六进制>.<jpg|jpeg|png|webp>` 路径，精确包含一个非空有界 `tbpicau` query 参数，且不含 userinfo、fragment、空白、控制字符或反斜杠。派生的持久 source hint 只保留规范 scheme/authority/path。
3. shim 只包装已校验的锁定对象，把一个冻结捕获绑定到精确返回的 `TiebaNote`，通过该对象跨越 `asyncio.gather` 子任务到父任务存储，并只在嵌套 `update_tieba_note` → JSONL store 调用中使用 `ContextVar`。错误来源、marker 冲突、部分安装、字段冲突、对象/行不匹配及并发泄漏均关闭失败；`.upstream` 保持未修改且不纳入跟踪。
4. 定时作者执行最多成功处理 Subscription `max_items`。校验 wrapper 保留锁定 creator endpoint 与 callback 合约，同时校验有界页面形状、正整数唯一主题 ID、精确详情结果身份、`has_more` 推进与节奏。它在详情请求前裁剪，达到上限后不再请求下一页或执行额外 sleep，并对重复、畸形页面或身份漂移关闭失败。
5. 归一化保持 `ContentKind.ARTICLE`，并增加精确一个 position 0、remote ID 为 `<note_id>:image:0` 的 `AssetKind.IMAGE`。私有捕获字段与全部瞬态 query 值递归地不进入归一化 raw、SQLite 或保留产物。
6. 刷新只从持久的精确 canonical 主题 URL 派生 detail 权限，执行一次有界详情运行，并要求唯一匹配 ARTICLE、唯一匹配 IMAGE 身份/position 及相同无 query source hint。它只以 `MediaRequestProfile.DEFAULT` 返回新校验的签名 URL；账户 Cookie、Authorization、Referer 与 Origin 不会转发给图片 host。
7. 贴吧 IMAGE 下载自动使用有界静态结构门。合格 JPEG、PNG 与 WebP 通过；GIF、APNG、animated WebP 与 AVIF 失败。该门是结构资格校验而非完整像素解码，且标志在 normal、recovery 与 takeover 准备链中保持。
8. 一个隔离组合贯穿精确 SQLite 来源、fake detail、mock 公网 DNS/HTTP、生产字节资格校验、SHA-256 归档及 Emby poster/backdrop/gallery/body/NFO/source 发布。仅 query 变化的重放新增工作为零，保留的 SQLite/runtime/archive/export/WAL/SHM 产物不含私有字段或瞬态 query 值。

## 明确排除

首楼多图片/gallery、视频/语音/表情/链接/富卡片类型、回复/评论媒体、其他贴吧图片 host/path、媒体替换语义、真实保留的脱敏 API 夹具及登录/现网验收继续延期或保持 `NOT_RUN`。本执行只是一个冻结的首楼静态图片切片，不代表贴吧媒体或七平台产品能力已全部完成。
