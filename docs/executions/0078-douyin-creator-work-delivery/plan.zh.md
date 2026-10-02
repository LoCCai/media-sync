[English](plan.md) | **中文**

# 计划

状态：**冻结，本轮即实现**。本文档本身不授权任何部署、平台请求或驻留进程重启。

## 1. 落笔写状态前先追踪并记录

- 从已认领的 Account profile 出发，追踪钉定的抖音创作者流程：`parse_creator_info_from_url`、`get_user_info`、`get_user_aweme_posts` 分页（`sec_user_id`、`count: 18`、服务端回显 `max_cursor`）、按 `aweme_id` 的 `get_video_by_id` 详情、以及媒体分支 `_extract_note_image_list` / `_extract_video_download_url`。
- 复用 0076 的交付骨架（扫描单元/覆盖、续传策略、交付进度仓储、Job 级摄取、下载器、归档、库写入器），但每个参数都从抖音证据重新推导；在验证文档记录钉定 MediaCrawler SHA 与观察到的页形状。
- 明确列出 XHS 或 Bilibili 假设对抖音不成立的每个点（整数 `has_more`、回显 `max_cursor`、空页停滞、`a_bogus` 签名、`blocked` 响应体判定），把每一条写成带测试的契约。

## 2. 耐久游标与停止原因状态

- 迁移 `0016_douyin_creator_work`（revises `0015_xhs_creator_notes`）创建 `douyin_subscription_progress`，约束纪律与 0015 相同：封闭 `phase` 白名单、四个固定停止原因（`has_more_false`、`empty_page_stalled`、`access_restricted`、`unit_cap_reached`）、计数范围、交付/源末/对账三组全有或全无证据三元组、`blocked_code` 当且仅当 `phase = 'blocked'`、受护栏的下线。
- 服务端回显的 `max_cursor` 逐字持久化，封装在不透明 `dy-work-v1:` 游标命名空间下。只存储有界计数器、指纹与时间戳；绝不存储原始响应、签名材料或 Cookie。

## 3. 有栅栏单元的有界续传

- 在上一单元的发现与管线回执耐久一致后，每步至多一个按页界定的单元；遵守 `max_items`、配置的续传延迟（默认 300 秒，经 `MEDIA_SYNC_DOUYIN_SCAN_CONTINUATION_DELAY_SECONDS`，两服务一致）、暂停/删除与认证/退避状态。
- API 精确执行与驻留进程通过 0074/0076 既有耐久所有权栅栏竞争；重复提交复用权威单元。

## 4. 对账与增量头部检查

- 在保留的 `has_more_false` 证据之后，运行一次有界头部重列：必须复现记录边界（最新作品集合相同、游标回显稳定）才进入增量模式；漂移时保留已交付数据并重开对账。
- 增量循环重列有界头部页，按稳定 `aweme_id` 去重，只为未见或变化的作品抓详情；空页停滞或受限按有界重试态处理——绝不视为游标丢失。

## 5. 按完整 Content 单元的交付与发布

- 图集作品只有在每张图都在场时发布；视频作品只有在视频字节在场时发布；一条失败作品绝不阻塞无关作品；部分结果携带精确失败作品计数与固定码。
- 证明重启与零工作重放保留内容寻址字节与确定性 NFO 输出。

## 6. 操作员界面

- 订阅详情暴露阶段、游标步计数、最近源末/对账证据、下次可运行时间与精确失败作品计数。不暴露游标本体、签名材料、主机路径或原始响应。

## 7. 验证序列

1. 游标往返、四种停止原因、页尾回放、失败详情推进、头部漂移、游标绑定变更拒绝的单元测试。
2. 页解析隐私、捕获 shim 封印 coverage、受限 ≠ 源末、`douyin.js` 签名夹具经 stdin 直传钉定脚本的契约测试。
3. 集成测试：三个及以上游标步加重启栅栏、空页与被封响应体退避、源末、头部漂移、进入增量、部分交付、零工作重放、单事务摄取、钉定 `0016` 的迁移往返。
4. 更新所有头修订钉定测试（打包迁移、CLI/support-bundle 修订、表计数、离线/调度管线、部署来源）。
5. 完整 Python 与 Web 套件、Ruff、严格 mypy、文档/上游检查、包构建与 `git diff --check`；记录精确的双语结果。
6. Linux 主机构建、真实抖音会话认领与真人创作者金丝雀在操作员显式执行前保持 `NOT_RUN`。
