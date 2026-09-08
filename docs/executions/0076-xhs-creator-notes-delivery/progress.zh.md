[English](progress.md) | **中文**

# 进展：XHS 创作者笔记耐久交付

状态：本地实现已在 `47ca107` 完成。Docker/Linux 部署、真实 PostgreSQL、真人 XHS 流量及驻留 supervisor 验收仍待执行。

## 结果

一个 XHS 创作者笔记 Subscription 现在可以沿用 B 站同级的耐久本地交付链，同时保留 XHS 自身的来源语义：

```text
已认领 XHS Account + 受保护作者 URL
  -> 携带不透明 cursor 的单个来源页单元
  -> 每笔记新鲜 xsec token 仅在 child 内使用
  -> 精确 Run 内容导入与 pipeline receipt
  -> 归档 + 已配置平台目录 + NFO
  -> 源末尾后的头部对账
  -> 有界增量头部检查
```

不要求连接 Emby/Jellyfin。配置的共享目录或 XHS 专用目录就是产品输出；媒体服务器可独立读取该挂载目录。

## 已实现

1. **以来源页为依据的状态。** 规范 `xhs-notes-v1` cursor 绑定 Account、作者、受保护作者引用、钉定上游和唯一 `notes` 流。每个单元最多列出一个名义 30 条的来源页；当 `max_items < 30` 时，保留的页面见证与已完成笔记身份会保存未消费页尾，不透明来源 cursor 原样回放。
2. **新鲜 token 边界。** 列表页 `xsec_token` 只存在于 child 内存，以 SHA-256 绑定精确笔记，并从归一化、持久化和公开输出中移除。详情使用同页 token，依次尝试上游 API 和 HTML 回退；详情仍未完成时，后续单元重列同一保留页。token 调用期间关闭依赖日志，避免秘密进入日志。
3. **耐久所有权与恢复。** Migration `0015_xhs_creator_notes` 为每个 Subscription 增加一行受约束进度。状态与 receipt 由 Account/auth revision、作者、作者引用指纹、策略、上游 SHA、checkpoint、schedule revision、Job、Run 和 pipeline Job 共同加栅栏。作者引用变化会先作废旧 cursor，再允许新 child 使用。
4. **真实阶段。** 交付合格进度在 `backfill`、`reconciling`、`incremental` 和 `blocked` 之间推进。只有已交付的 `has_more=false` 页面能成为源末尾证据；`access_restricted`、`empty_page_stalled` 和 `unit_cap_reached` 始终分开。源末尾观察不等于“全部历史已永久落地”。
5. **稳定对账与增量。** 到达源末尾后，以新 token 重列头部。头部漂移保留已交付内容并要求再次稳定对账；只有稳定且已交付的头部才能发布增量基线。后续无变化检查不抓详情、不写新内容；新增或变化笔记只被选择一次。
6. **按 Content 交付。** 精确 `SyncRunContent` 选择把已接收的 normal/video 笔记接入既有可验证下载、SHA-256 归档和确定性 Emby 兼容目录/NFO 管线。一条不支持或不可用笔记会如实报告 partial，不丢弃无关有效笔记；真实写入失败仍终止该批次。
7. **操作员界面。** REST 与 Web 只公开白名单内的阶段、计数、停止原因、证据时间、下次资格和固定阻塞/部分状态。精确执行遇到 `xhs_access_restricted`、`xhs_empty_page_stalled` 或 `xhs_note_detail_partial` 时报告失败，不再显示成功。token、opaque cursor、作者 URL、原始响应和宿主路径保持私密。
8. **共用续跑配置。** `MEDIA_SYNC_XHS_SCAN_CONTINUATION_DELAY_SECONDS` 默认 `300`，仅接受 `0` 或 `60..604800`，API 与 supervisor 必须相同。`0` 只关闭快速续跑，不会关闭上游绑定、耐久进度或普通订阅周期调度。

## 复核修正

- 精确 API 执行不再把进度阻塞或部分失败的 XHS 已交付单元报告为成功。
- XHS 快速间隔为零时不再关闭进度绑定，而是按普通 Subscription 周期安排下一单元。
- Child 归一化可单独拒绝一条不支持笔记而不隐藏有效同页笔记；写入开始后的失败仍为终态。
- 旧结构 runner double 即使没有 `xhs_scan`，也不会使非 XHS 路径崩溃。
- Pipeline worker 只为 MediaCrawler Account 解析 MediaCrawler 策略，保留其他 adapter 契约。
- 当前 B 站来源测试已加入生产 Run manifest 要求的作者指纹。

## 剩余工作

- 在 Linux 宿主拉取并重建已发布 revision；先备份状态，应用 migration `0015`，并在两个服务设置相同 XHS 续跑间隔。
- 使用一个已授权、作品较少的 XHS 作者完成真人金丝雀：原生会话认领、历史单元、本地下载/归档/NFO、重启，再到 supervisor 调度。
- 执行可选的真实 PostgreSQL schema/竞态验收。
- 本执行中的 Linux/Docker、真人 XHS 登录/API/CDN 字节、宿主目录权限与内容、进程重启、驻留 supervisor 及可选媒体服务器读取全部为 `NOT_RUN`。
- 选择下个平台前遵循[下一交付](next-delivery.zh.md)。执行 0077 尚未开始。
