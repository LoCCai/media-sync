# Execution 0017 progress / 执行 0017 推进记录

- Status / 状态：Offline implementation and documentation closeout complete / 离线实现与文档收尾已完成
- Last updated / 最近更新：2026-09-01
- Plan commit / 计划提交：`9d19e7e`
- Implementation commit / 实现提交：`2f8dbaa` (pushed to `origin/main` / 已推送至 `origin/main`)

## Implemented / 已实现

- [x] Exact XHS note/creator validators, XOR request boundaries and child schema v3, including decoded xsec value validation. / 精确小红书 note/creator 校验器、互斥 request 边界与 child schema v3，包括解码后 xsec 值校验。
- [x] Exact Subscription creator-secret fallback and `max_items` projection; explicit detail override wins with zero creator-secret resolution. / 精确 Subscription creator-secret fallback 与 `max_items` 投影；显式 detail 覆盖优先且作者 secret 解析为零。
- [x] Bounded isolated creator child with one configured XHS path, cleared lists, concurrency one and disabled comments/media. / 有界隔离 creator child，只配置一条小红书路径、清空列表、单并发并关闭评论/媒体。
- [x] Unique ordinary raw `type="normal"` IMAGE/GALLERY/all-IMAGE target gate and duplicate-target rejection. / 唯一普通 raw `type="normal"` IMAGE/GALLERY/全 IMAGE 目标门及重复目标拒绝。
- [x] Exact SQLite provenance, DEFAULT-profile mock HTTP, synthetic image validation, SHA-256 archive and idempotent Emby/Jellyfin output with zero-work replay. / 精确 SQLite 来源、DEFAULT-profile mock HTTP、合成图片校验、SHA-256 归档及带零工作重放的幂等 Emby/Jellyfin 输出。
- [x] Durable raw shape preservation with field-specific authority/query cleanup; fixed pipeline/scheduler error taxonomy. / 持久 raw 形状保持与按字段执行的权限/query 清理；固定 pipeline/scheduler 错误分类。
- [x] Exact authority preflight before archive repair or lifecycle writes; valid VERIFIED replay zero-secret; non-XHS CLI option rejection. / 归档修复或生命周期写入前执行精确权限 preflight；有效 VERIFIED 重放零 secret；非小红书 CLI 选项拒绝。

## Verification completed / 已完成验证

- Focused: `266 passed in 56.90s`; post-format related: `89 passed in 13.74s`. / 专项：`266 passed in 56.90s`；格式后相关：`89 passed in 13.74s`。
- Complete: `1298 passed, 1 skipped in 365.73s`; only skip is the Windows-inapplicable POSIX mode-bit test. / 完整：`1298 passed, 1 skipped in 365.73s`；唯一跳过项是 Windows 不适用的 POSIX mode-bit 测试。
- Final pipeline/worker regression: `52 passed in 4.57s`. / 最终 pipeline/worker 回归：`52 passed in 4.57s`。
- Ruff PASS; format 234 files; strict mypy 79 sources; compileall, two upstream locks, two build artifacts, diff and retained-artifact audits PASS. No coverage run is claimed. / Ruff 通过；格式检查 234 个文件；严格 mypy 79 个源码；compileall、两个上游锁、两个构建产物、diff 与保留产物审计均通过。不宣称 coverage。

## Remaining / 待实现或待验收

- [ ] Main thread: create/push the bilingual closeout commit and reconcile local/tracking/GitHub SHAs; the post-edit checker already passes for 84 Markdown files. / 主线程：创建/推送双语收尾提交并核对本地/tracking/GitHub SHA；编辑后检查已通过 84 个 Markdown 文件。
- [ ] Real XHS QR/Cookie, creator/feed/detail, CDN bytes and Emby/Jellyfin server rows remain `NOT_RUN`. / 真人小红书 QR/Cookie、creator/feed/detail、CDN 字节及 Emby/Jellyfin 服务器行保持 `NOT_RUN`。
- [ ] Automatic XHS video/live-photo/animation/mixed-media, authority-expiry recovery and remaining platform/media shapes remain future work. / 小红书自动视频/实况照片/动图/混合媒体、权限过期恢复及其余平台/媒体形状仍为后续工作。

Execution 0017 is complete at its offline boundary; the broader user goal remains active. / Execution 0017 已在离线边界完成；更大的用户目标继续推进。
