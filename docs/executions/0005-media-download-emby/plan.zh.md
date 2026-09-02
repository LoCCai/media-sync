[English](plan.md) | **中文**

# 执行 0005 计划

1. 冻结字段所有权与版本身份：发现只能更新 locator/raw 提示；实际 MIME、字节数、SHA-256、本地路径及生命周期只归下载器。同一 remote ID 与语义指纹保留生命周期；remote ID 或语义指纹变化时原子增加 generation 并重置下载器字段。
2. 先通过 Fake 与 MediaCrawler 两条真实入口添加重放/替换回归，再在网络代码前拆开发现 upsert、显式 generation reset 与资产生命周期 CAS。同一去 query 源站/路径的签名轮换不得重置；路径或稳定媒体身份变化必须重置。
3. 定义 locator v1、规范 JSON 指纹、`direct`/`adapter_refresh` 模式、严格解析及非密持久化测试。
4. 在现有列不足处新增 `0003_media_download_emby` 迁移，保存语义/locator 指纹、generation、下载 validator、时间与错误状态，并验证从 `0002_checkpoint` 升级保留数据。
5. 在 MediaCrawler 集成包之外实现可复用的受限路径、符号链接/reparse 与原子写入原语。
6. 实现可注入 DNS resolver、地址固定 HTTP transport、手动重定向校验、`trust_env=False`、identity 编码及固定脱敏错误分类。
7. 实现 `.part` 元数据，并绑定资产 UUID、generation、规范 locator 指纹、validator、预期总长与当前字节数；执行严格 200/206/416 规则、有界重启、字节/时长限制、续传重算哈希与 fsync。
8. 添加有界 magic/MIME/FFprobe 验证与内容寻址归档发布；不信任 URL 后缀或 `Content-Disposition`。
9. 用短事务与租约 fencing 编排 enqueue/claim/start、网络工作及最终 verify/complete，并注入旧 worker 与数据库收尾故障。
10. 实现 ExportRecord CAS、带所有权的 export job/staging token、稳定路径净化/身份键及规范 source/rendered 指纹。
11. 实现确定性 Emby 目录、XML 1.0 过滤、NFO、白名单来源、可播放副本及图文保存。在作者级锁下逐文件发布；仅替换/删除旧受管 manifest 中且字节仍匹配的路径，保留冲突与非受管文件。
12. 添加 CLI 下载/导出命令，以及离线 fixture 导入 → mock 下载 → 导出的集成链路、密钥扫描与黄金目录哈希。
13. 用本执行稳定 layout v1 替换 `docs/architecture.md` 中冲突的临时路径/ordinal 描述，并记录 0005 前没有 exporter、因此无需迁移旧媒体库；随后运行全部锁定依赖、Ruff、格式、严格 mypy、pytest/覆盖率、下载/导出专项、构建、随包迁移、文档/上游及差异门禁。

## 已冻结设计决策

- 含义不明的 query、fragment 或凭据型普通作者/媒体 URL 不会成为持久 direct locator；签名值保持瞬时，并要求 adapter refresh。
- 下载器拥有的数据库列只描述本地已验证字节，绝不存远端提示含义。
- 资产语义指纹 v1 包含平台、内容 remote type/ID、kind/position、远端资产 ID、去 query 的规范源站/路径及可用的稳定尺寸/时长提示。仅 query 轮换保留 generation；语义证据缺失、较弱或变化时宁可重置，也不复用可能陈旧的 blob。
- 网络连接使用已验证 IP；“先解析、再按域名连接”仍受 DNS rebinding 影响，因此不接受。
- 归档 blob 是不可变普通文件；导出使用原子复制，不使用硬链接或符号链接。
- 稳定文件名由平台/类型/远端身份与短哈希生成；显示名和标题只进入 NFO，不参与路径身份。
- Season 使用 UTC 发布年份，缺失时回退首次发现年份；episode 使用稳定正整数哈希，并确定性检测碰撞。
- Emby 导出器不使用 `AssetStatus.EXPORTED`；每个 exporter 的完成状态归 `ExportRecord`。
- `source.json` 使用严格白名单，不含 raw、locator、请求/响应 header 或带 query 的来源 URL。
- 导出 layout v1 在作者级文件锁下从 job-ID staging 发布；受管 manifest 保存相对路径与字节哈希，只有当前哈希仍匹配旧 manifest 时才删除陈旧受管文件。0005 前尚无 exporter，因此不存在需要迁移的旧磁盘目录。

## 实现补记 — 2026-08-30

本补记保留上方冻结计划作为历史意图，但取代其中“磁盘上的旧 managed manifest 可以建立所有权”这一不完整表述。对抗审查证明，自洽伪造的 manifest 否则可能把非受管用户文件认领为受管文件。最终实现收敛如下：

- 迁移 `0003_media_download_emby` 只保留字段完整的 legacy `verified` 行，规范 checksum 并补齐时间，使其继续接受当前 exporter 的字节复核。legacy `downloading`、`downloaded`、`exported` 及不完整 `verified` 会重置为 `discovered`，清空下载器字段并记录 `legacy_asset_reset`；源码 downgrade，以及源码与解包 wheel 的 upgrade 均有覆盖。
- 脱敏会归一化 snake_case、kebab-case、camelCase 及带提供商前缀的组合 API/access-key 名称，同时保留普通 `key`、`public_key` 和 `key_id` 字段。带凭据标记的 URL 路径会经有界百分号解码脱敏，包括编码及双重编码形式；`direct` locator 和 source hint 会拒绝它们。`0003` legacy 回填会清空这类不安全 `source_url`，只生成稳定 `adapter_refresh` locator。
- `0003` downgrade 先清空所有 `assets.download_job_id`，再删除全部 generation-bound `asset_download` Job。已成功的 Emby 发布链 Job/record 会保留；携带结构严格有效的封闭发布 intent 的未成功 Job 及 intent 点名的 records 也会为精确恢复保留；其他未成功 Emby 身份污染在再升级前删除。
- 每个资产下载 Job 只保存规范 work/archive I/O scope 的哈希，不泄露两个路径。同一 `work_root` 下的资产 OS 锁在 `_begin` 前获取并持有到数据库收尾；锁竞争和 scope 不匹配均发生在 reclaim/attempt 变更前。精确 owner/token 只有在 reclaim 尚未改变 token 时才能跨名义到期续租，使 renew 与 reclaim 成为单胜者 CAS。
- 归档 guard 位于临时副本 fsync、重哈希之后和 no-clobber 提交之前，复用既有 blob 也必须执行。`.part` 证据保留到资产验证与 Job 完成原子提交之后。已提交结果可以在不访问网络、不增加 attempt 的情况下恢复，包括已到期的最后一次 attempt；成功后的清理为 best-effort，不能反转 verified 状态。这些 0.x 保证要求运行根目录及祖先是操作员控制的专用目录；同权限恶意进程替换父目录不在威胁模型内。
- 每个成功 Emby 作者发布都是一个持久 `export.emby` Job result，由 publication scope、source fingerprint、tree SHA-256、manifest SHA-256、受管文件数量和精确 `predecessor_job_id` 锚定。当前 head 由唯一 predecessor chain 决定，而非时间戳或仅从磁盘发现的 manifest。natural key 包含 source 与精确 predecessor，因此允许 `A → B → A` 等来源循环，同时拒绝 Job 图分叉、成环与断裂祖先链。
- 文件系统发布前，服务用精确 `intent` 续期所拥有的 Job 租约；intent 绑定渲染后的 source/tree/manifest 身份、受管文件数量及相关 ExportRecord 身份。如果文件系统发布成功但数据库收尾失败，后续调用会逐字节验证该 intent，并原子地把 records 与 Job 转为最终 result。活跃 owner 不会被替换，变化或篡改的树不会被接管。
- 空快照即使没有 ExportRecord，也会创建成功 Job 锚点；它只能删除数据库可信 predecessor 中仍未改变的文件，并保留非受管文件。首次发布遇到任何意外 managed manifest 都会拒绝。自洽伪造 manifest 不能取得所有权。同一 predecessor 的并发 sibling 发布在作者锁下串行化；一个成功，另一个以可重试 `stale_publish` 失败，随后从胜者的持久 head 收敛。
- CLI 在进入编排前拒绝不可用的 `adapter_refresh` 和缺失的强制 `ffprobe`，返回 `blocked`/`not_started`、`persisted_status` 与固定脱敏代码，不创建 Job、不改变 Asset。

## 回退与安全

测试只使用临时 SQLite、生成文件和内存/mock transport，不访问平台/CDN，也不启动 Emby/Jellyfin。Schema 变更保持追加并验证 downgrade；实现提交必须继续让 runtime/archive/export 根目录处于未跟踪状态。
