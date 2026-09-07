[English](progress.md) | **中文**

# 进展：B 站投稿耐久回填已可对账并转入增量交付

状态：本地实现已在 `9c81c4b` 完成。Docker/Linux 部署、真人 B 站访问及宿主目录验收仍待执行。

## 结果

既有精确订阅主链现在具备交付合格的 B 站生命周期：

```text
已认领的 B 站 Account profile
  -> 一个有界投稿 Run（最多观察 30 个 Content）
  -> 精确 Run 内容凭单
  -> 按完整 Content 下载、归档与发布
  -> 历史仍待处理时按节奏续跑
  -> 源末尾证据
  -> 有界头部对账
  -> 定期执行带重叠窗口的增量头部检查
```

服务不会调用 Emby/Jellyfin 服务器。耐久输出仍是配置的本地媒体库目录树及 NFO/sidecar。

## 已实现

1. **交付合格状态。** `0014_bili_delivery_baseline` 迁移增加 `bili_subscription_progress`，phase 封闭为 `backfill`、`reconciling`、`incremental`、`blocked`。证据绑定精确 Subscription、Account 认证 revision、作者指纹、投稿 scope、影响交付的策略指纹及锁定 MediaCrawler SHA。
2. **精确有界来源批次。** `sync_run_contents` 保存一次成功 Run 观察到的有序 Content 身份及资产数量。数据库和摄取路径共同维持既有 30 条上限，pipeline 不再从作者累计快照推测本轮来源。
3. **耐久历史转增量。** 已交付且证明源末尾的历史单元会重置一个有界 head lane。只有稳定交付的头部对账才发布 `baseline_snapshot_complete` 并进入 `incremental`；分页漂移或不兼容 cursor 证据会回到保守路径。
4. **安全失效与恢复。** 认证、身份、scope、策略或上游锁变化时不能复用不兼容基线。精确来源身份与 cursor 仍有效时可保留已交付历史，但必须重新对账。终态 coordinator 失败会阻止自动物化；显式精确执行可恢复同一安全 generation。
5. **按交付而非仅发现推进节奏。** 单独成功的 scan Run 不推进基线。只有封闭 pipeline 成功凭单在同一事务发布后，才安排下一次 300 秒 continuation；稳定增量头部单元之后恢复普通订阅周期。可重试积压失败也继续使用 continuation 节奏。
6. **按完整 Content 交付。** pipeline 按 Content 隔离下载失败。同一多分段 Content 只要缺少任一必需成员就不发布，其他无关完整 Content 仍可发布。已有 predecessor Content 通过已验证 manifest 保留，不会因本轮来源批次较小而被移除。
7. **精确部分成功凭单。** receipt schema v2 分别报告来源 Run 与重试积压的观察、交付和失败 Content 数、可重试/终态总数及固定失败码。`partial` 同时覆盖本轮来源与重试积压；旧 author-snapshot 凭单继续按 schema v1 读取。
8. **真实且幂等的文件链。** 受控集成 fixture 运行实际安全下载器、SHA-256 归档和 Emby 兼容 exporter。后来新增一条投稿时只下载并发布一次；内容不变的零工作 Run 复用 export Job，归档/媒体库字节与 mtime 均不改变。
9. **操作者投影。** 订阅详情 API 与 Web 页面只展示封闭且公开安全的 phase、批次、源末尾、对账、下次可运行及失败 Content 证据。原始 cursor、宿主路径、Cookie、签名 locator 和上游响应继续隐藏。

## 审查修正

完整回归门禁暴露了一个既有登录 runner 截止时间缺陷：子进程关闭 stdout 但没有退出时，父进程会立即返回 `RESULT_INVALID`，没有执行请求的超时。现在父进程只把完整 frame 或真正退出的 child 视为完成；仍在运行 child 的 EOF 会继续受取消/截止时间约束。该精确用例与完整 68 项登录契约均通过。

之后的完整运行又发现三个确定性门禁缺口：通用 Alembic schema 契约漏列 0014 的两张表；CPython 在 Windows 上对同一 NTFS 文件的路径 `stat` 与句柄 `fstat` 会给出不同 `st_ctime_ns`，从而间歇拒绝有效不可变预览——现在 named-path 通过身份、大小和 mtime 对比，已持有 descriptor 仍完整约束自身 ctime 快照；快手 JSON 嵌套原先依赖解释器抛 `RecursionError`，现在用显式 64 层词法边界，不再依赖 Python decoder 实现。

## 剩余真人工作

- 在 Linux 主机拉取并构建已发布 revision。
- 认领真人 B 站会话，并对明确授权的 UID `252671524` 执行金丝雀。
- 记录真人平台请求、下载的 CDN 字节、归档哈希、宿主最终媒体库目录/NFO，以及之后一次无变化/新增投稿的增量周期。
- 验证部署后的 supervisor 重启与调度行为。

以上四项全部为 `NOT_RUN`；确定性 fixture 不能替代真人资格。
