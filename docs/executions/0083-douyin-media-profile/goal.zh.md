[English](goal.md) | **中文**

# 目标：抖音媒体请求 profile 与有界选流

## 结果

让一次抖音创作者作品交付能够取用钉定上游详情响应里本来就携带的**最高可用**流，而不是上游 store 恰好留下的那条扁平 URL，并让这些媒体请求带上平台期望的浏览器形状请求头。

## 触发本执行的证据

- 钉定上游把详情响应压成四个标量（`.upstream/MediaCrawler/store/douyin/__init__.py:132-140`）：先 `play_addr_h264`，再 `play_addr_256`，再 `play_addr`，各取首个非空候选的 `url_list[-1]`。更丰富的 `video.bit_rate[]` 数组——每个画质一项，各自带 `play_addr.url_list` 与 `data_size`——在 media-sync 看到之前就被丢弃，因此"只交付 1080p"无法表达。
- media-sync 目前对包括抖音在内的所有非 B 站资产都用 `MediaRequestProfile.DEFAULT` 解析，该 profile 不发送任何 `User-Agent`、`Referer`、`Accept` 请求头（`src/media_sync/media/network.py:25-32`、`src/media_sync/integrations/mediacrawler/refresh.py:614-618`）。抖音 CDN 对这类请求常以 `403` 回应。
- 操作者报告了一个已跑通的参考实现（TikTokDownloader，GPLv3）。其行为事实可用；其源码、常量与结构不可用，也不得复制（见 `THIRD_PARTY_NOTICES.md`）。

## 必需行为

1. **封闭请求 profile。** 新增 `MediaRequestProfile.DY_MEDIA`，只含固定桌面 `User-Agent`、`Referer: https://www.douyin.com/`、`Accept: */*`，别的一律不带。没有 Cookie、没有 `Authorization`、没有调用方 header。该 profile 只由 `refresh.py` 按平台选择；B 站既有 profile 行为不受影响。
2. **有界选流。** 一个纯函数只依据有文档的响应字段，把一个钉定上游 `aweme_detail` 映射归约为 `(video_url | None, cover_url | None, source rank)` 决策。遇到漂移必须拒绝而不是猜测：缺失 `url_list`、非 HTTPS URL、超出可接受抖音媒体域的 host、重复或超界数组（`bit_rate` 最多 8 项），以及"期望视频但视频缺失"。
3. **不持久化签名材料。** 选流发生在子进程内；只有既有的无 query `source_hint` 进入 SQLite，私有选流字段由既有私有字段纪律在组装 envelope 前剥离。
4. **回退保住历史。** 当 `bit_rate[]` 缺失或不可用时，契约回退到上游扁平 `play_addr_h264` / `play_addr_256` / `play_addr` 顺序，使当前可交付的每条抖音作品继续以字节一致的既有形状交付。
5. **可解释的操作者界面。** 交付载荷可以报告**哪一档**胜出（不含 URL、不含 host、不含 query），使将来的金丝雀无需泄露签名定位器即可证明选流。

## 验收

- 单元测试固定排序规则（先最高分辨率，再最高码率，再最大 `data_size`，最后声明顺序）与每条拒绝分支。
- 契约测试证明子进程 shim 通过私有字段发出所选档位、该字段永不进入 envelope，且回退路径逐字节复现今天的既有 URL。
- 集成测试为一条 `bit_rate[]` 携带比 `play_addr_h264` 更好流的抖音作品驱动 SQLite → 刷新 → mock DNS/HTTP → 归档 → Emby，并证明零工作重放。
- `MediaRequestProfile.DY_MEDIA` 通过断言 mock 传输上的精确出站 header 集合、且不存在其他 header 来证明。
- 完整 Python/Web/静态/文档门通过；部署、真人登录与任何真实 CDN 字节获取仍为 `NOT_RUN`。

## 明确非目标

- 复刻 TikTokDownloader 的 `a_bogus`/`msToken` 签名、TLS 指纹或它的重试/分片策略。MediaCrawler 仍是唯一签名权威。
- 去水印声明。当选流能在响应里选到未加水印候选时允许优先，但没有真人金丝雀就不对真实字节作任何声明。
- 任何 Emby/Jellyfin 服务器控制，以及任何对 0074/0076/0080/0081 游标、覆盖、迁移或进度表语义的改动。
