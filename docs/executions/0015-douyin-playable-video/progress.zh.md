[English](progress.md) | **中文**

# 执行 0015 推进结果

- 状态：离线实现与收尾门禁完成；真人验收仍为 `NOT_RUN`
- 开始时间：2026-08-31 07:24 +08:00
- 完成时间：2026-08-31
- 计划提交：`76b1973`
- 实现提交：`95d314d`

## 已实现

- 一条包含十进制 `aweme_id`、空 `note_download_url`、精确一个合法 `video_download_url`、空 `music_download_url` 与可选合法封面的普通抖音记录，现已形成冻结的离线组合。被接受的视频为 `<aweme_id>:video:0`，可选封面为 `<aweme_id>:cover:0`；测试精确绑定内容类型、remote ID、position、MIME hint、无 query source hint 与稳定 `mediacrawler` 刷新 locator。
- 持久 raw 净化现已覆盖 `video_download_url`、`cover_url`、`music_download_url` 与 `note_download_url`。它会移除 URL userinfo、已知/未知 query 值与 fragment，同时内存中被接受的 `AssetSnapshot.source_url` 仍保留完整 URL。逗号拼接的 note 标量会变成有序平面序列；混合平面序列会保留安全的规范 origin/path 项，并把逗号夹带或嵌套的不透明子项替换为 `null`。该边界回归中的 gallery/audio 形状只证明净化，不代表已验收图库下载或外挂音轨语义。
- 真实隔离 fake checkout 已经过 `MediaCrawlerDetailProcessRunner`，证明 `platform=dy`、十进制字符串 `DY_SPECIFIED_ID_LIST`、detail/JSONL/媒体关闭/评论关闭/并发开关、`CRAWLER_MAX_SLEEP_SEC=0.25`、保存 profile 派生、有界结果 framing、对象表示脱敏及正常成功 attempt 清理。这是使用确定性 JSONL 的 fake checkout，不是真人抖音 detail 流量或登录。
- 平台 E2E 在真实 SQLite 中写入精确 Account/Author/Subscription 与两条 `AssetRefreshSource`，再把视频与封面刷新惰性绑定到精确 Account、Subscription、内容及 Asset 身份。组合 E2E 有意替换为 fake detail runner，并为两项 Asset 各创建一次、共两次精确 detail 调用；上方独立进程契约负责提供实际 child runner 证据。既有专项 case 证明缺失、漂移、重复及错误 Subscription/source 会在媒体传输前关闭失败。
- 两项 Asset 均使用 `MediaRequestProfile.DEFAULT`。Mock 媒体 HTTP 只包含下载器固定默认 header，不含 Cookie、Authorization、Referer、Origin 或调用方自定义 header。确定性 MP4/PNG 字节通过 mock 公网 DNS 固定与有界传输；只有视频执行受控强制结构探测。两项 Asset 均以不可变 SHA-256 归档路径及持久 succeeded Asset/Job 状态收尾。
- 本地 Emby/Jellyfin layout 把已验证 `.mp4` 发布为 episode 主媒体、把封面发布为 poster，并生成 NFO、受管 manifest 与白名单 `source.json`。仅 query 变化的 forward URL 轮换会保留 Asset generation 与已验证字节；重放返回 `already_verified`/`already_exported`，归档/媒体库树保持逐字节一致，并重新读取实时计数以证明没有新增 fake detail runner、detail 调用、HTTP 请求、DNS 解析或 probe。
- 首轮完整套件暴露了账户 profile 锁契约中的 Windows 时序竞态：轮询 JSONL 文件并不能证明第一个 runner 已经持有账户锁。测试现改为在持锁的 `_run_locked` 路径内部触发 Event 后再同步；非 timeout watchdog case 的 Windows 冷启动与扫描墙钟预算由 4 秒调整为 10 秒，而专用 timeout 契约继续保持 0.8 秒。随后最终完整套件通过。
- 专项门禁通过 `231` 项，耗时 41.79 秒；最终完整套件通过 `1209` 项，另有一项在 Windows 不适用而跳过，耗时 438.39 秒。Ruff、格式、严格类型、文档、锁定上游、构建及补丁门禁均通过。最终清单包含 240 个 tracked 文件、零个标准 untracked 文件、零个禁止跟踪路径、914 个 runtime/build 文件、精确 marker 零命中，并保留两个冻结 sentinel 根。

## 已知限制

- 持久身份由 `<aweme_id>:<kind>:0` 与无 query source hint 组成。若抖音在同一 aweme ID 与 origin/path 下替换字节且只变化 query，已验证字节不会自动失效；反之，CDN host/path 迁移可能重置 generation 或导致精确刷新失败。
- Detail 输出继承受信 Subscription 的作者归属，不能独立证明该 aweme 仍属于该创作者。已证明 detail 正常成功清理；注入文件系统清理失败仍缺少 scheduled runner 的完整 quarantine、incident 与账户阻断协议。

## 执行 0015 之外待实现

- 真人抖音 QR/Cookie/saved-session 登录保持 `NOT_RUN`。
- 真人作者扫描与增量重跑保持 `NOT_RUN`。
- 真人 detail 与签名 CDN 传输保持 `NOT_RUN`。
- 真实平台字节经 FFmpeg/ffprobe 保持 `NOT_RUN`。
- 真人 Emby/Jellyfin 重扫与播放保持 `NOT_RUN`。
- 抖音图集/图片、关联音乐/音频语义、多视频或封面 URL、slideshow、字幕、评论、直播/付费/受限/已删除内容、可信作者 profile、有界作者分页及任何经过证明的平台专用 CDN header 仍属于不支持或延期范围，不能记作通过。
- 媒体版本感知替换、清理失败 quarantine/incident/账户阻断、小红书多 note authority、新增微博/贴吧/知乎 Asset 捕获、REST/API 运维、部署/服务集成及跨主机 HA 仍属于后续工作。
