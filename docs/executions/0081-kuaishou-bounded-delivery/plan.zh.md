[English](plan.md) | **中文**

# 计划

状态：**冻结待后续执行**。本文档本身不授权任何部署、平台请求或驻留进程重启。

## 1. 落笔写状态前先追踪并记录

- 从已认领的 Account profile 出发，追踪钉定的快手创作者流程：`parse_creator_info_from_url`（help.py:115-138）、`get_creator_info`/`userProfile`（client.py:389-396）、`get_all_videos_by_creator` 分页（首个空 `pcursor` client.py:414、请求体 `{user_id, pcursor, page: "profile"}` client.py:169-170、顶层回显 client.py:434）、逐页详情回调 `fetch_creator_video_detail` → `get_video_info_task` → `get_video_info`（GraphQL `visionVideoDetail`，变量 `{photoId, page: "search"}`，经无签名的 `post()`/`request()` 通道，core.py:453-466、220-254，client.py:243-254、88-92、68-78），以及扁平媒体字段 `coverUrl`/`photoUrl`（store/kuaishou/__init__.py:73-74）。
- 复用 0080 的交付骨架（扫描单元/覆盖、续传策略、交付进度仓储、Job 级摄取、下载器、归档、库写入器），但每个参数都从快手证据重新推导；在验证文档记录钉定 MediaCrawler SHA 与观察到的页形状。
- 明确列出抖音或 XHS 假设对快手不成立的每个点（字符串哨兵 `no_more` 而非整数 `has_more`、客户端推断的空页结束而非空页停滞、无客户端每页条数——抖音的固定页大小钳制 `DOUYIN_CREATOR_PAGE_SIZE` 无法照搬——签名列表通道叠加无签名的 GraphQL 详情通道、存活环境的 `__NS_hxfalcon` 签名而非钉定签名脚本、上游创作者循环无上限），把每一条写成带测试的契约。

## 2. 耐久游标与停止原因状态

- 迁移 `0017_kuaishou_creator_work`（revises `0016_douyin_creator_work`）创建 `kuaishou_subscription_progress`，约束纪律与 0016 相同：封闭 `phase` 白名单、四个固定停止原因（`no_more_echoed`、`empty_page_end`、`access_restricted`、`unit_cap_reached`）、计数范围、交付/源末/对账三组全有或全无证据三元组、`blocked_code` 当且仅当 `phase = 'blocked'`、受护栏的下线。
- 服务端回显的 `pcursor` 逐字持久化，封装在不透明 `ks-work-v1:` 游标命名空间下。只存储有界计数器、指纹与时间戳；绝不存储原始响应、签名材料或 Cookie。

## 3. 有栅栏单元的有界续传

- 在上一单元的发现与管线回执耐久一致后，每步至多一个按页界定的单元；遵守 `max_items`——此处承重，因为上游创作者循环无界（client.py:398-449）且每页大小完全由服务端决定（client.py:169 无 `count` 字段），抖音的固定页大小钳制（douyin_creator_work.py:496）无法照搬。单元绝不截断服务端页后继续推进：当 `max_items` 在页尾之前使单元停下时，耐久输入 `pcursor` 保持不变，下一单元以相同请求重列，按稳定 `photo.id` 跳过已交付作品，直至页尾耗尽；只有整页耗尽才按回显游标推进。同时遵守配置的续传延迟（默认 300 秒，经 `MEDIA_SYNC_KUAISHOU_SCAN_CONTINUATION_DELAY_SECONDS`，两服务一致）、暂停/删除与认证/退避状态。
- 只有列表请求才由存活的 Playwright 页面环境签名：签名 REST 通道 `request_rest_v2_signed`（client.py:117-159）只服务两个列表端点（client.py:170、189），经 `KS_SIGN_CAPTURE_SCRIPT`（help.py:35-57）与 `get_ks_sign_from_playwright`（help.py:60-86）每次尝试重新生成（client.py:130）；详情与创作者资料请求走无签名的 GraphQL 通道（`post()` client.py:88-92 → `request()` client.py:68-78），绝不需要也不得携带 `__NS_hxfalcon` 材料。耐久层绝不离线构造或缓存签名，环境重新捕获（reload 后再等待，help.py:72-77）是列表步的有界重试态，绝不是游标丢失。
- API 精确执行与驻留进程通过 0074/0076/0080 既有耐久所有权栅栏竞争；重复提交复用权威单元。

## 4. 对账与增量头部检查

- 在保留的结束证据（`no_more_echoed` 或 `empty_page_end`）之后，从空 `pcursor` 运行一次有界头部重列：必须复现记录边界（最新作品集合相同、回显形状稳定）才进入增量模式；漂移时保留已交付数据并重开对账。
- 增量循环重列有界头部页，按稳定 `photo.id` 去重，只为未见或变化的作品抓详情；受限或环境丢失按有界重试态处理——绝不视为游标丢失。

## 5. 按完整 Content 单元的交付与发布

- 快手作品携带单一扁平媒体形状，上游无图集/视频分支：只有当详情导出的 `photoUrl` 视频字节（及使用时的封面，store/kuaishou/__init__.py:73-74）完整时作品才发布；一条失败作品绝不阻塞无关作品；部分结果携带精确失败作品计数与固定码。
- 证明重启与零工作重放保留内容寻址字节与确定性 NFO 输出。

## 6. 操作员界面

- 订阅详情暴露阶段、游标步计数、最近源末/对账证据（包括关闭 feed 的结束路径）、下次可运行时间与精确失败作品计数。不暴露游标本体、签名材料、主机路径或原始响应。

## 7. 验证序列

1. 游标往返、四种停止原因、页尾回放（页中 `max_items` 停止后以相同 `pcursor` 重列）、失败详情推进、头部漂移、游标绑定变更拒绝的单元测试。
2. 页解析隐私、捕获 shim 封印 coverage（每个签名随其交换捕获、绝不重新推导）、受限 ≠ 源末、回显结束与空页结束证据、以及仅限列表的存活环境签名契约（列表请求签名，GraphQL 详情与资料不签名）的契约测试。
3. 集成测试：三个及以上 `pcursor` 步加重启栅栏、空页与受限退避、哨兵结束、头部漂移、进入增量、部分交付、零工作重放、单事务摄取、钉定 `0017` 的迁移往返。
4. 更新所有头修订钉定测试（打包迁移、CLI/support-bundle 修订、表计数、离线/调度管线、部署来源）。
5. 完整 Python 与 Web 套件、Ruff、严格 mypy、文档/上游检查、包构建与 `git diff --check`；记录精确的双语结果。
6. Linux 主机构建、真实快手会话认领与真人创作者金丝雀在操作员显式执行前保持 `NOT_RUN`。
