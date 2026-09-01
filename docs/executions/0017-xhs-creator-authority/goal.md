# Execution 0017 goal / 执行 0017 目标

- Status / 状态：Offline execution complete; live qualification remains `NOT_RUN` / 离线执行已完成；真人验收保持 `NOT_RUN`
- Date / 日期：2026-09-01
- Predecessor / 前置：Execution 0016 closeout commit `4774c34`
- Plan commit / 计划提交：`9d19e7e`
- Implementation commit / 实现提交：`2f8dbaa`
- Scope / 范围：XHS creator-authority lookup for ordinary static IMAGE/GALLERY / 小红书普通静态 IMAGE/GALLERY 的作者权限自动查找

## Outcome / 目标结果

Execution 0017 closes the missing automatic refresh path for an exact XHS author Subscription. Without an explicit note override, the runtime resolves only that Subscription's opaque `creator_input.secret_ref`, privately validates the signed creator URL and performs a bounded creator lookup. An operator-supplied `xhs_detail_reference_ref` remains the higher-priority compatibility override and prevents creator-secret resolution. / 执行 0017 已补齐精确小红书作者 Subscription 的自动刷新路径。未提供显式 note 覆盖项时，运行时只解析该 Subscription 的不透明 `creator_input.secret_ref`，私下校验带签名作者 URL 并运行有界 creator 查找。操作员提供的 `xhs_detail_reference_ref` 继续作为更高优先级的兼容覆盖项，并阻止解析 creator secret。

The frozen offline-qualified shape is one unique ordinary `type="normal"` XHS record with one or more ordered static images. It produces IMAGE/GALLERY content and ordered IMAGE Assets, then traverses exact provenance, `MediaRequestProfile.DEFAULT`, controlled image validation, immutable SHA-256 archive publication and idempotent Emby/Jellyfin poster/backdrop/gallery/NFO/source output. / 冻结的离线验收形状是一条唯一的普通 `type="normal"` 小红书记录，包含一张或多张有序静态图片；它产生 IMAGE/GALLERY 内容及有序 IMAGE Asset，并贯穿精确来源、`MediaRequestProfile.DEFAULT`、受控图片校验、不可变 SHA-256 归档发布及幂等 Emby/Jellyfin poster/backdrop/gallery/NFO/source 输出。

## Delivered acceptance boundary / 已交付验收边界

1. Parent context, request and child schema v3 accept exactly one XHS authority path: an exact note-detail URL or exact creator URL, never both. Host/path/identity and decoded, unique, bounded `xsec_token`/`xsec_source` values are revalidated at every boundary. / 父 context、request 与 child schema v3 精确接受一条小红书权限路径：精确 note 详情 URL 或精确作者 URL，二者不可同时存在；host/path/身份及解码后唯一、有界的 `xsec_token`/`xsec_source` 值会在每层重复校验。
2. Creator fallback comes only from the exact Asset observation's Account/Subscription provenance. `subscription.max_items` must fit watchdog `max_output_items`; the child clears every creator/detail list, configures one XHS path, uses concurrency one and disables comment/media side effects. / Creator fallback 只来自精确 Asset observation 的 Account/Subscription 来源；`subscription.max_items` 必须受 watchdog `max_output_items` 限制；child 清空全部 creator/detail 列表，只配置一条小红书路径，使用单并发并关闭评论/媒体副作用。
3. Creator results require exactly one matching raw `type="normal"` IMAGE/GALLERY target with only IMAGE Assets. Duplicate targets, video/mixed/nonordinary records and identity/source-hint drift fail closed. Explicit detail mode retains historical compatibility without broadening this claim. / Creator 结果要求精确一条匹配的 raw `type="normal"` IMAGE/GALLERY 目标及纯 IMAGE Asset；重复目标、视频/混合/非普通记录及身份/source-hint 漂移均关闭失败。显式 detail 模式保留历史兼容，但不扩大本声明。
4. Pipeline/CLI preflight runs before child Job or Asset mutation. Valid VERIFIED replay resolves no secret; missing/damaged VERIFIED archive repair preflights before quarantine/reset. Only the dedicated authority-required error maps to the XHS prompt; other fixed causes/retryability remain distinct, and non-XHS CLI option use is rejected. / Pipeline/CLI preflight 在 child Job 或 Asset 变更前运行。有效 VERIFIED 重放不解析 secret；VERIFIED 归档缺失/损坏时在 quarantine/reset 前执行 preflight。只有专用权限错误映射为小红书提示；其他固定 cause/retryability 保持区分，非小红书 CLI 选项使用会被拒绝。
5. Durable XHS raw removes the known top-level authority fields and query-strips the pinned `note_url`/`image_list`/`video_url` fields while preserving accepted scalar/empty/container shapes. No database migration was added and neither pinned `.upstream` checkout was modified. / 持久小红书 raw 会移除已知顶层权限字段，并清除锁定 `note_url`/`image_list`/`video_url` 字段的 query，同时保留已接受的标量、空值与容器形状。未新增数据库 migration，两个锁定 `.upstream` checkout 均未修改。

## Explicit exclusions / 明确排除

- Real QR/Cookie login, creator/feed/detail traffic, real XHS CDN bytes and real Emby/Jellyfin server scans/playback remain `NOT_RUN`; offline mocks do not imply them. / 真人 QR/Cookie 登录、creator/feed/detail 流量、真实小红书 CDN 字节及真实 Emby/Jellyfin 服务器扫描/播放保持 `NOT_RUN`；离线 mock 不代表这些项目通过。
- Automatic XHS video, live photo, animation, mixed media, authority-expiry recovery, pagination hardening and cross-Asset refresh caching remain deferred. / 小红书自动视频、实况照片、动图、混合媒体、权限过期恢复、分页加固及跨 Asset 刷新缓存继续延期。
- Remaining platform/media shapes stay outside this execution. Execution 0017 is complete, while the broader user goal remains active. / 其余平台/媒体形状不属于本执行。Execution 0017 已完成，但更大的用户目标继续推进。
