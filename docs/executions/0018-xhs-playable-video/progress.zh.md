[English](progress.md) | **中文**

# 执行 0018 推进记录

- 状态：离线实现与文档收尾已完成
- 最近更新：2026-09-01
- 计划提交：已推送至 `origin/main`)
- 实现提交：已推送至 `origin/main`)

## 已实现

- 源码绑定合约执行锁定的小红书 store 函数，证明 `origin_video_key`、`originVideoKey`、H.264 `master_url`、逗号标量 `video_url` 与标量封面输出。
- 已实现严格的小红书初始媒体 locator 校验：只接受 HTTP/HTTPS `xhscdn.com` 根域/子域、规范化大小写/IDNA/尾点、默认端口及非根路径；userinfo、空白/控制字节、fragment、畸形 label、外域及自定义端口均关闭失败。
- 自动 creator fallback 现接受一条普通 raw `type="video"` 行：精确一个标量 VIDEO 候选及零或一个标量 IMAGE 候选，并一一映射为 VIDEO 或窄 MIXED 内容。
- 多个、重复、空、带空白、畸形+有效及容器漂移候选会在归一化 Asset 选择前失败；历史显式精确 note 视频路径继续兼容，且不纳入本次自动能力声明。
- 真实隔离 fake checkout 证明有界 creator 配置、精确 URL 选择、`MediaRequestProfile.DEFAULT`、清理及 repr-safe 权限处理。
- 完整 SQLite 来源 → 作者查找 → mock DNS/HTTP → 归档 → Emby 组合会发布可播放 `.mp4`、可选海报、NFO 与 source；仅 query 变化的重放不会新增 detail、DNS、HTTP、probe、归档或导出工作。
- 内嵌真实 H.264 MP4 已通过生产 `FFprobeMediaProbe`；确定性组合保留记录型 probe，以精确断言调用次数。
- 持久小红书 raw 与 Asset hint 保持无 query/userinfo/fragment，已完成 attempt 根会删除，两个锁定 `.upstream` checkout 均未修改或跟踪。

## 已完成验证

- 编辑前基线：`167 passed in 46.50s`；九文件专项：`222 passed in 43.69s`。
- 锁定上游源码合约：`4 passed`；真实 H.264/上游/组合检查：`6 passed in 8.84s`。
- 完整套件：`1353 passed, 1 skipped in 338.48s`；唯一跳过项是 Windows 不适用的 POSIX mode-bit 测试。
- Ruff 检查与格式均通过（`241 files already formatted`）；严格 mypy 通过 `80 source files`；compileall、两个上游锁、wheel/sdist 构建、文档、diff 与保留产物审计均通过。
- 独立最终审查未发现 P0–P2 问题；不宣称运行过 coverage。

## 待实现或待验收

- 主线程：创建/推送双语收尾提交并核对本地/tracking/GitHub SHA；提交前会再次运行编辑后文档/diff 检查。
- 真人小红书 QR/Cookie 登录、creator/feed/detail 流量、真实 CDN 视频/封面字节及 Emby/Jellyfin 服务器扫描/播放保持 `NOT_RUN`。
- 多视频、多图片、更广混合媒体、实况照片、动图、权限过期恢复、贴吧/知乎媒体 shim 及七平台其余形状仍为后续工作。

Execution 0018 已在离线边界完成；更大的用户目标继续推进。
