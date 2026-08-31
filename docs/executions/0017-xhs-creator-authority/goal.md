# Execution 0017 goal / 执行 0017 目标

- Status / 状态：Planned / 已计划
- Date / 日期：2026-09-01
- Predecessor / 前置：Execution 0016 closeout commit `4774c34`
- Scope / 范围：XHS creator-authority lookup for ordinary static IMAGE/GALLERY / 小红书普通静态 IMAGE/GALLERY 的作者权限自动查找

## Outcome / 目标结果

Close the missing automatic path for an XHS author subscription: reuse the exact Subscription's existing opaque `creator_input.secret_ref`, resolve its signed creator URL only in the private runtime, run a bounded XHS creator lookup to reacquire the target note's current `xsec_token` and `xsec_source`, and feed the returned content JSONL through the existing exact Asset refresh, default-profile download, SHA-256 archive and Emby/Jellyfin layout. An operator-supplied single-note `xhs_detail_reference_ref` remains a compatibility override. / 补齐小红书作者订阅缺失的自动路径：复用精确 Subscription 已有的不透明 `creator_input.secret_ref`，只在私有运行时解析带签名的作者 URL，通过有界 XHS creator 查找重新取得目标 note 当前的 `xsec_token` 与 `xsec_source`，再把返回的 content JSONL 接入现有精确 Asset 刷新、默认 profile 下载、SHA-256 归档及 Emby/Jellyfin 布局。操作员提供的单 note `xhs_detail_reference_ref` 继续作为兼容覆盖项。

The frozen offline qualification shape is an ordinary `type="normal"` XHS note with one or more ordered static images, producing IMAGE or GALLERY content and ordered IMAGE Assets. The implementation may preserve earlier manually authorized XHS video behavior, but this execution does not claim automatic video, live-photo, animation or mixed-media qualification. / 本次冻结的离线验收形状是一条普通 `type="normal"` 小红书笔记，包含一张或多张有序静态图片，产生 IMAGE 或 GALLERY 内容及有序 IMAGE Asset。实现可以保留此前人工授权的小红书视频行为，但本执行不宣称已验收自动视频、实况照片、动图或混合媒体。

## Why this slice / 选择依据

- The locked upstream creator path already accepts a signed creator URL, bounds retrieval with `CRAWLER_MAX_NOTES_COUNT`, obtains per-note `note_id`/`xsec_token`/`xsec_source`, details the notes and writes content JSONL. / 锁定上游 creator 路径已能接受带签名作者 URL，以 `CRAWLER_MAX_NOTES_COUNT` 限制获取量，取得逐 note 的 `note_id`/`xsec_token`/`xsec_source`，拉取详情并写出 content JSONL。
- media-sync already normalizes XHS images, creates stable adapter-refresh Assets, selects exact Account/Subscription provenance, refreshes signed media URLs in memory, archives verified bytes and publishes Emby metadata. The missing link is automatic per-note detail authority. / media-sync 已能归一化小红书图片、创建稳定 adapter-refresh Asset、选择精确 Account/Subscription 来源、在内存中刷新签名媒体 URL、归档已验证字节并发布 Emby 元数据；缺失环节只是逐 note 详情权限的自动取得。
- The upstream JSONL `note_url` hard-codes `xsec_source=pc_search` and therefore is not treated as durable authority. Creator lookup reacquires current feed authority without a database migration and without persisting `xsec` in SQLite. / 上游 JSONL 的 `note_url` 会硬编码 `xsec_source=pc_search`，因此不能作为持久权限；作者查找可以重新取得当前 feed 权限，无需数据库迁移，也不把 `xsec` 持久化到 SQLite。
- Tieba static images need a real redacted `/c/f/pb/page_pc` image response to freeze field and anti-hotlink behavior; Zhihu loses media structure before JSONL. Neither has enough locked evidence for a truthful implementation in this slice. / 贴吧静态图片仍需真实脱敏的 `/c/f/pb/page_pc` 图片响应来冻结字段与防盗链行为；知乎则在 JSONL 前已丢失媒体结构。两者在本切片都缺乏足够锁定证据，不能据此诚实实现。

## Acceptance boundary / 验收边界

1. Exact parent, request and child boundaries accept either one XHS note detail URL or one XHS creator URL, never both; creator host, path, author ID and unique non-empty `xsec_token`/`xsec_source` must match the trusted subscription context. / 父级、请求与 child 三层精确边界只接受一个 XHS note 详情 URL或一个 XHS 作者 URL，不能同时存在；作者 host、path、作者 ID 以及唯一非空的 `xsec_token`/`xsec_source` 必须匹配可信订阅上下文。
2. Creator lookup uses only the exact Subscription policy reference, sets creator mode, clears all unrelated creator/detail lists, uses concurrency one, disables comments/media side effects and caps notes by the Subscription's `max_items` and watchdog limits. / 作者查找只使用精确 Subscription 的 policy 引用，设置 creator 模式，清空所有无关 creator/detail 列表，使用单并发，关闭评论/媒体副作用，并同时受 Subscription `max_items` 与 watchdog 限制。
3. Returned multiple records are normalized with the trusted author identity; the existing refresher must select exactly one matching content/Asset or fail closed. / 返回的多条记录使用可信作者身份归一化；现有 refresher 必须精确选中唯一匹配的 content/Asset，否则关闭失败。
4. Ordinary single- and multi-image composition reaches default-profile HTTP, image validation, immutable SHA-256 archive and idempotent Emby poster/backdrop/gallery/NFO/source output; replay adds no work. / 普通单图及多图组合需贯穿默认 profile HTTP、图片校验、不可变 SHA-256 归档，以及幂等 Emby poster/backdrop/gallery/NFO/source 输出；重放不新增工作。
5. No creator/note token, signed authority or signed media query is retained in SQLite, archive metadata, Emby output, operator errors or completed attempt roots. / 作者/note token、签名权限及签名媒体 query 均不得保留在 SQLite、归档元数据、Emby 输出、运维错误或已完成 attempt root 中。

## Explicit exclusions / 明确排除

- Real QR/Cookie login, creator/feed/detail requests, real XHS CDN bytes and real Emby/Jellyfin server scans or playback remain `NOT_RUN` without user credentials and live services. / 在没有用户凭据与在线服务时，真人 QR/Cookie 登录、creator/feed/detail 请求、真实小红书 CDN 字节以及真实 Emby/Jellyfin 服务器扫描或播放保持 `NOT_RUN`。
- XHS video, live photo, animation, mixed media, HTTP origin-video behavior, alternate codecs/variants, creator-feed pagination hardening beyond the locked upstream behavior, authority expiry recovery and cross-Asset content-level refresh caching are deferred. / 小红书视频、实况照片、动图、混合媒体、HTTP origin-video 行为、其他编解码/清晰度、超出锁定上游行为的 creator-feed 分页加固、权限过期恢复及跨 Asset 的 content 级刷新缓存继续延期。
- Tieba/Zhihu downloadable Asset discovery and all other unqualified platform shapes remain outside this execution. / 贴吧/知乎可下载 Asset 发现及其他尚未验收的平台形状不属于本执行。
