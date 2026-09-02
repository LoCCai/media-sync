[English](progress.md) | **中文**

# 执行 0005 推进结果

- 状态：记录的离线范围已完成；由本次双语本地实现提交收尾
- 开始时间：2026-08-30 07:05 +08:00
- 完成时间：2026-08-30 10:45 +08:00
- 真实性边界：仅 mock、夹具与本地文件系统验收；所有真人平台、CDN、Emby 项继续为 `NOT_RUN`

## 已交付

- 新增追加式迁移 `0003_media_download_emby` 及 upgrade/downgrade/再 upgrade 覆盖。字段完整的 legacy `verified` 行保留生命周期，并规范 checksum、补齐时间；legacy `downloading`、`downloaded`、`exported` 及不完整 `verified` 会重置为 `discovered`，清空下载器字段并记录 `legacy_asset_reset`。downgrade 会清空所有 `assets.download_job_id`，删除全部 generation-bound `asset_download` Job。未成功的 Emby 身份污染会删除，但已成功的发布链 Job/record 会保留；若未成功 Job 携带结构严格有效的封闭发布 intent，该 Job 及 intent 点名的 records 也会为精确的发布后恢复而保留。资产发现与下载器现在具有明确字段所有权；语义/locator 指纹与带 fencing 的 generation reset 防止发现重放降级已验证状态或把新地址与旧字节错配。
- 将 locator schema v1 封闭为规范 `direct` 与 `adapter_refresh` 两种形式。持久化 direct URL 拒绝凭据、query、fragment 和非 HTTP(S) 协议；refresh 可在内存返回瞬时签名 URL，缺少刷新能力时固定返回 `locator_refresh_unsupported`。
- 扩展落点脱敏，覆盖 snake_case、kebab-case、camelCase 及带提供商前缀的组合 API/access-key 映射键，同时刻意保留普通 `key`、`public_key` 和 `key_id` 字段。带凭据标记的 URL 路径段与赋值会通过有界解码识别，覆盖原始、编码及双重编码形式；通用 URL 输出会脱敏路径，`direct` 解析会拒绝，资产 source hint 派生则返回空，从而持久稳定 `adapter_refresh`。`0003` legacy 回填复用同一规则，清空不安全 `source_url`，且不把凭据路径复制到 SQLite locator 状态。
- 新增同一 `work_root` 下的逐资产 OS 编排锁，从 `_begin` 前一直持有到数据库收尾。锁竞争返回 `asset_download_busy`，不会改变 job/资产/attempt。每个持久 job 只保存规范 work/archive 根的不可逆哈希；不同 scope 会在 reclaim 或 attempt 变更前拒绝。精确 owner/token 只有在 reclaim 尚未取胜时才能跨名义到期续租，因此 renew 与 reclaim 是单胜者 CAS。
- 新增严格资产/持久任务生命周期 CAS、每次领取的新 fencing token、精确任务领取、重试上限及资产/任务原子收尾；DNS、网络和文件系统工作不持有 SQLite 事务。
- 实现逐跳公网地址验证、混合公私 DNS 拒绝、固定地址且保留 Host/SNI 的连接、手动重定向、禁用环境代理、重定向上限、HTTPS 降级拒绝，以及跨源 validator 清除。
- 实现绑定 generation 的 `.part` 续传元数据，以及严格的 `200`/`206`/`416`、`Range`、`If-Range`、validator、总长度、超时、header 和字节限制，并提供有界重启。
- 新增 magic/MIME 校验和音视频强制且有界的 `ffprobe` 结构探测，再通过 SHA-256 发布为不可变 `archive/sha256/<prefix>/<digest>.<verified-extension>` blob。所有权 guard 在临时复制/fsync/重哈希之后及 no-clobber 提交前运行，复用既有 blob 也必须执行。既有 blob 会重新验证；操作时已存在的路径逃逸、符号链接/reparse、硬链接及可检测的叶节点身份替换默认拒绝。配置根目录及祖先明确属于操作员控制的可信目录；同权限恶意进程替换父目录不在 0.x 威胁模型内。
- 新增下载应用服务，以短事务完成领取/开始，以原子事务完成验证/任务结束，并提供固定脱敏错误、租约/generation fencing 与可恢复续传。`.part` 证据保留到数据库成功之后；归档已提交但数据库收尾失败时可在不访问网络、不增加 attempt 的情况下恢复，包括已到期的最后一次 attempt。验证后的清理为 best-effort，不能反转成功。verified 快速路径会复核规范 blob；损坏字节被隔离，缺失/无效的持久归档状态通过 CAS 重置，而不会继续信任。
- 实现确定性的 Emby/Jellyfin layout v1：路径身份不依赖可变标题，使用 UTC 年份 season、稳定 episode number、合法 UTF-8 NFO XML、白名单来源、已验证音视频播放文件、确定性海报选择，并保留图库/正文/附件资产。
- 新增作者级进程/OS 锁、job-ID staging、受管文件哈希、变更前 journal、no-clobber 发布、回滚/恢复，以及成功前完整 desired tree 字节复核。中断 roll-forward 会在丢弃 journal 前验证 manifest 点名的每个文件；不匹配时保留 `RECOVERY_REQUIRED`。用户修改与非受管文件会保留；无法无歧义回滚时保留证据，而不递归删除用户路径。
- 新增持久数据库发布协议。每个 succeeded `export.emby` Job result 锚定 publication scope、source/tree/manifest 哈希、受管文件数量及精确前序 Job。当前 head 由唯一 predecessor chain 决定，而非时间戳或仅从磁盘发现的 manifest。natural identity 包含 source 与精确 predecessor，因此允许 `A → B → A`，同时拒绝图分叉、成环与祖先链断裂。
- 新增发布前 Job `intent` 持久化，以及“文件系统发布成功、数据库收尾失败”的恢复。后续调用只有在 intended source/tree/manifest 与每个受管字节全部通过复核后，才会原子完成精确 records 与 Job。首次导出拒绝意外 managed manifest；自洽伪造 manifest 不能认领非受管用户文件。空快照即使没有 ExportRecord 也保持锚定；并发 sibling 发布只留下一个持久胜者，旧 loser 从新 head 重试。
- 新增严格 `ExportRecord` begin/complete/fail CAS 与导出应用服务。导出完成状态归 exporter/version/完整作者快照指纹，不会把资产全局推进到 `exported`。
- 新增脱敏安全的 `media-sync asset list`、`media-sync asset download` 和 `media-sync emby export`。`asset list` 不输出 locator、URL、归档路径和 raw。缺少强制 `ffprobe` 或 MediaCrawler refresh 不支持时，preflight 返回 `blocked`/`not_started`、未改变的 `persisted_status` 与固定错误码，不创建 Job、不修改 Asset。
- 新增专项单元/集成/契约覆盖，以及离线 Fake sync → mock 安全下载 → Emby 导出流水线。测试覆盖重放、锁/scope 零变更、renew/reclaim fencing、收尾恢复、延后清理 `.part`、SSRF/重定向、强制媒体探测、伪造/首次 manifest、空快照、来源循环、并发 sibling 发布、完整树发布/恢复竞态、密钥哨兵与幂等性。最终根门禁通过 540 项测试，分支感知覆盖率为 79%；专项、构建、随包迁移、文档、上游及保留产物哨兵证据均记录在 `verification.md`。
- 更新架构、能力真实性、路线图和运维快速开始文档，不把任何模拟结果升级为真人验收。

## 延期或明确未验收

- MediaCrawler 的签名/CDN locator 刷新尚未实现。所有 MediaCrawler 发现的二进制资产有意保持 `adapter_refresh`，因此 CLI 下载会返回可重试的 `blocked`/`not_started`、`locator_refresh_unsupported` 及未改变的 `persisted_status`，不创建 Job、不修改 Asset，也不会持久化即将过期的签名 URL。
- 当前归一化发现仍不完整：小红书/抖音/快手暴露部分二进制候选，B 站目前暴露封面，现有微博/贴吧/知乎夹具没有可下载资产。平台特有 DASH、多 P、字幕、弹幕，以及幻灯片/混流转换留给后续适配器或衍生物工作；当前会保留已验证原件及不可播放资产。
- 本执行未获授权使用任何用户凭据或真人账户。小红书、抖音、快手、哔哩哔哩、微博、贴吧、知乎的真人登录、作者同步和 CDN 下载全部为 `NOT_RUN`。
- 本执行没有启动或重扫 Emby/Jellyfin。只对导出文件系统/NFO 契约完成离线验收；真实媒体库识别和播放均为 `NOT_RUN`。
- 调度、限流/退避策略、REST 运维、Docker 打包和生产运维属于延期/未实现的后续阶段范围，而不是 `NOT_RUN` 验收行。
- 最终根门禁、覆盖率、构建/打包及保留密钥哨兵证据均已完成并记录。本次双语本地实现提交结束执行 0005；没有推送远端。
