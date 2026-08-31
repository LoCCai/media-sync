# Execution 0016 progress / 执行 0016 推进结果

- Status / 状态：Frozen offline implementation and closeout evidence complete; live qualification remains `NOT_RUN` / 冻结离线实现与收尾证据已完成；真人验收保持 `NOT_RUN`
- Started / 开始时间：2026-08-31
- Plan commit / 计划提交：`b7bb818`
- Implementation commit / 实现提交：`a77ca74`

## Implemented / 已实现

- Audited the locked MediaCrawler Weibo, Tieba and Zhihu paths without modifying either upstream checkout. Weibo was selected because creator/detail already receive raw `mblog.pics`; the locked Weibo JSONL store is the boundary that discarded it. / 已在不修改任何上游 checkout 的前提下审计锁定版 MediaCrawler 微博、贴吧与知乎路径。选择微博是因为 creator/detail 已收到原始 `mblog.pics`；锁定微博 JSONL store 才是丢弃它的边界。
- Added one shared task-local Weibo media shim to the real creator and detail children after verified-checkout import. Concurrent note tasks keep independent capture state, JSONL enrichment is transient, and `.upstream` remains clean. / 在真实 creator 与 detail child 导入已验证 checkout 后增加同一个 task-local 微博媒体 shim。并发 note task 保持独立捕获状态，JSONL 增强为瞬态，且 `.upstream` 保持干净。
- Frozen a narrow ordinary-original boundary: canonical positive numeric note ID, no retweet, no media `page_info`, ordered unique `pid` values, only `sinaimg.cn` or its subdomains, and only `jpg/jpeg/png/webp`. Invalid scalar, nested, missing, duplicate, foreign-host, non-static-extension and reordered refresh shapes fail closed. / 冻结狭窄普通原创边界：规范正整数 note ID、非转发、无媒体 `page_info`、有序唯一 `pid`、源站仅 `sinaimg.cn` 或其子域、扩展名仅 `jpg/jpeg/png/webp`。非法标量、嵌套、缺字段、重复、外部源站、非静态扩展名及重排刷新形状均关闭失败。
- Normalized one picture to `ContentKind.IMAGE` and multiple pictures to `ContentKind.GALLERY`; produced ordered IMAGE Assets, stable adapter-refresh locators and exact SQLite `AssetRefreshSource` observations bound to the Account and Subscription. / 把单图归一化为 `ContentKind.IMAGE`，多图归一化为 `ContentKind.GALLERY`；生成有序 IMAGE Asset、稳定 adapter-refresh locator，以及绑定 Account 与 Subscription 的精确 SQLite `AssetRefreshSource` observation。
- Added WB image-only detail/refresh support with exact same plain numeric ID validation at three boundaries: parent request construction, resolved detail reference and child frame load. Exact content/remote ID/kind/position/source-hint matching prevents cross-item or reordered selection. / 增加 WB 仅 image 的 detail/refresh 支持，并在父请求构造、resolved detail reference 与 child frame load 三层校验完全相同的纯 numeric ID；精确 content/remote ID/kind/position/source-hint 匹配防止跨项或重排选择。
- Recursively removed the integration-private field, captured PID values and nested signed-URL drift before durable raw creation. SQLite, runtime/work roots, both archives, export staging/library and sidecar artifacts contain none of those private values. / 在创建持久 raw 前递归移除集成私有字段、捕获 PID 值及嵌套签名 URL 漂移；SQLite、runtime/work 根目录、两个归档、export staging/library 与 sidecar 产物均不含这些私有值。
- Expanded the composition test to a real two-image Gallery: two exact refreshes, two public-DNS/default-profile HTTP transfers, two distinct synthetic PNG byte streams, two independent SHA-256 archives, first-image poster, second-image backdrop, ordered gallery files 001/002, NFO references and allowlisted source metadata. / 把组合测试扩展为真实双图 Gallery：两次精确刷新、两次公网 DNS/默认 profile HTTP 传输、两份不同合成 PNG 字节流、两个独立 SHA-256 归档、首图 poster、次图 backdrop、有序 gallery 001/002、NFO 引用及白名单 source 元数据。
- Proved zero-work replay: already verified Assets and the completed export add no detail runner, HTTP, DNS, probe, archive or export work and leave both archive and library trees byte-identical. / 证明零工作重放：已验证 Asset 与已完成 export 不会新增 detail runner、HTTP、DNS、probe、archive 或 export 工作，且归档与媒体库树逐字节不变。
- Independent review directly caused four corrections: Sina authority restriction, static-extension restriction, exact WB detail-ID equality, and replacement of the single-image composition with a two-image Gallery E2E. / 独立审查直接促成四项修正：新浪 authority 限制、静态扩展名限制、WB detail ID 精确相等，以及以双图 Gallery E2E 替代单图组合。

## Verification completed / 已完成验证

- Predecessor baseline: `272 passed in 46.92s`. / 前置基线：`272 passed in 46.92s`。
- Combined focused gate across 15 files: `388 passed in 125.73s`. / 15 文件合并专项门禁：`388 passed in 125.73s`。
- Complete suite: `1251 passed, 1 skipped in 359.38s`; the skip is the Windows-inapplicable POSIX mode-bit test. / 完整套件：`1251 passed, 1 skipped in 359.38s`；跳过项是 Windows 不适用的 POSIX mode-bit 测试。
- Ruff check passes; `ruff format --check` reports 228 files formatted; strict mypy succeeds for 78 source files. / Ruff 静态检查通过；`ruff format --check` 报告 228 个文件格式正确；严格 mypy 成功检查 78 个源码文件。
- Both pinned upstream entries verify; `uv build` creates two distribution artifacts; diff checks pass. / 两个锁定上游条目校验通过；`uv build` 创建两个分发产物；diff 检查通过。
- Final documentation links pass for 80 Markdown files. The retained inventory reports 246 tracked files, zero standard-untracked or forbidden paths, 914 runtime/build files, zero execution-0016 marker hit in retained runtime data and both frozen 0007/0008 sentinel roots preserved. / 最终文档链接检查通过 80 个 Markdown 文件。保留清单报告 246 个 tracked 文件、零个标准 untracked 或禁止路径、914 个 runtime/build 文件、保留 runtime 数据中执行 0016 marker 零命中，并保留冻结的 0007/0008 两个 sentinel 根。

## Remaining / 待实现

- Weibo video, GIF/animated-image semantics, long-image special handling, media `page_info`, retweets, restricted/live media and bounded creator pagination remain unimplemented or unqualified. / 微博视频、GIF/动图语义、长图特殊处理、媒体 `page_info`、转发、受限/直播媒体及有界 creator 分页仍未实现或未验收。
- A Sina-direct request profile, third-party proxy availability qualification, same-ID media replacement detection and injected cleanup-failure quarantine remain future work. / 新浪直连请求 profile、第三方代理可用性验收、同 ID 媒体替换检测及注入清理失败 quarantine 仍为后续工作。
- Every real QR/Cookie/saved-session login, real creator scan, real detail/proxy/CDN transfer, real platform-byte probe and real Emby/Jellyfin server scan/viewing row remains `NOT_RUN`. / 全部真人 QR/Cookie/saved-session 登录、真人 creator 扫描、真实 detail/代理/CDN 传输、真实平台字节探测及真实 Emby/Jellyfin 服务器扫描/查看行均保持 `NOT_RUN`。
- The broader project objective remains active: remaining media shapes and live qualification across all MediaCrawler platforms are not made complete by this Weibo slice. / 更广的项目目标继续进行：本微博切片不代表其余媒体形状及 MediaCrawler 全平台真人验收已经完成。
