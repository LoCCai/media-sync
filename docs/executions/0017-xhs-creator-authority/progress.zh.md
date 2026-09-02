[English](progress.md) | **中文**

# 执行 0017 推进记录

- 状态：离线实现与文档收尾已完成
- 最近更新：2026-09-01
- 计划提交：`9d19e7e`
- 实现提交：已推送至 `origin/main`)

## 已实现

- 精确小红书 note/creator 校验器、互斥 request 边界与 child schema v3，包括解码后 xsec 值校验。
- 精确 Subscription creator-secret fallback 与 `max_items` 投影；显式 detail 覆盖优先且作者 secret 解析为零。
- 有界隔离 creator child，只配置一条小红书路径、清空列表、单并发并关闭评论/媒体。
- 唯一普通 raw `type="normal"` IMAGE/GALLERY/全 IMAGE 目标门及重复目标拒绝。
- 精确 SQLite 来源、DEFAULT-profile mock HTTP、合成图片校验、SHA-256 归档及带零工作重放的幂等 Emby/Jellyfin 输出。
- 持久 raw 形状保持与按字段执行的权限/query 清理；固定 pipeline/scheduler 错误分类。
- 归档修复或生命周期写入前执行精确权限 preflight；有效 VERIFIED 重放零 secret；非小红书 CLI 选项拒绝。

## 已完成验证

- 专项：`266 passed in 56.90s`；格式后相关：`89 passed in 13.74s`。
- 完整：`1298 passed, 1 skipped in 365.73s`；唯一跳过项是 Windows 不适用的 POSIX mode-bit 测试。
- 最终 pipeline/worker 回归：`52 passed in 4.57s`。
- Ruff 通过；格式检查 234 个文件；严格 mypy 79 个源码；compileall、两个上游锁、两个构建产物、diff 与保留产物审计均通过。不宣称 coverage。

## 待实现或待验收

- 主线程：创建/推送双语收尾提交并核对本地/tracking/GitHub SHA；编辑后检查已通过 84 个 Markdown 文件。
- 真人小红书 QR/Cookie、creator/feed/detail、CDN 字节及 Emby/Jellyfin 服务器行保持 `NOT_RUN`。
- 小红书自动视频/实况照片/动图/混合媒体、权限过期恢复及其余平台/媒体形状仍为后续工作。

Execution 0017 已在离线边界完成；更大的用户目标继续推进。
