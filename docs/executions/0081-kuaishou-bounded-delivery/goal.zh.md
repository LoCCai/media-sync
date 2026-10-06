[English](goal.md) | **中文**

# 目标：以源生游标为依据的快手创作者作品耐久交付

状态：**已实现并离线验证**。部署、Linux 验证与任何真人采集仍未开始。

执行 0081 把 0074（B 站）、0076（小红书创作者笔记）与 0080（抖音创作者作品）交付的耐久订阅交付扩展到快手创作者作品。遵循强制的源码优先姿态：以下每一条推进、结束判定、对账与增量规则，都从钉定 MediaCrawler 的快手代码与响应形状推导，而非从抖音或 XHS 实现复制。

上游快手创作者流程（`media_platform/kuaishou/core.py`、`client.py`、`help.py`、`exception.py`）定义了本执行依赖的事实：

- 创作者作品在签名 REST 端点 `/rest/v/profile/feed` 上以请求体 `{user_id, pcursor, page: "profile"}` 分页（client.py:169-170）。不透明字符串 `pcursor` 起始为空（client.py:414），服务端在顶层回显下一游标并须逐字回放（client.py:434）。不存在客户端每页条数参数——每页大小完全由服务端决定（client.py:169 无 `count` 字段）。
- 停止信号是字符串哨兵 `no_more`：上游循环只在 `pcursor != "no_more"` 时继续（client.py:416）。服务端回显的 `no_more`（client.py:434）是首要的真实源末候选。
- 空 `feeds` 数组是第二条结束路径：客户端自行置 `pcursor = "no_more"` 并中断（client.py:436、440-442）。与抖音的空页停滞不同，上游快手在空页即终止；耐久层把这一客户端推断的结束记录为独立的停止原因，不与服务端回显者合并。
- 访问受限与流耗尽截然不同：响应为假值会被记为疑似封禁并中断循环（client.py:418-422），业务 `result != 1` 中断循环（client.py:426-432），共享 GraphQL 路径遇 `errors` 键抛 `DataFetchError`（client.py:75-76），签名通道遇 `result != 1` 抛 `DataFetchError`（client.py:158-159），而 `result == 2` 限流按指数退避至多重试三次（client.py:126、150-157）。`IPBlockError` 仅有定义，在整个快手模块中从未抛出或捕获（exception.py:28-29）。以上没有一项是源末。
- 只有列表请求才签名。签名 REST 通道 `request_rest_v2_signed`（client.py:117-159）仅被两个列表端点触达（client.py:170、189）：注入的 `KS_SIGN_CAPTURE_SCRIPT` 把页面自带签名环境钩入 `window.__ks_realm`（help.py:35-57），`get_ks_sign_from_playwright` 按请求求值 `$encode`（help.py:60-86），产出 `?__NS_hxfalcon={sign}&caver=2` 查询串（client.py:131-136、142）。签名绑定请求内容与时间窗，每次尝试都必须重新生成（client.py:130）；没有任何钉定脚本能离线签名。详情与创作者资料请求不携带签名——它们走无签名的 GraphQL 通道 `post()` → `request()`（client.py:88-92、68-78；`get_video_info` client.py:254，`get_creator_profile` client.py:290）。
- 作品身份是 feed 项与详情载荷中的 `photo.id`（core.py:448-450、234-241，store/kuaishou/__init__.py:56-57）；创作者身份是从受保护创作者 URL 解析的 `user_id`——`/profile/` URL 或纯 ID（help.py:115-138，model/m_kuaishou.py:32-34，config/ks_config.py:36-40）。上游任何位置都不存在图集/视频媒体分支：媒体事实就是扁平的 `video_cover_url = photo.coverUrl` 与 `video_play_url = photo.photoUrl` 字段（store/kuaishou/__init__.py:73-74）及 `video_type = str(item.type)`（store/kuaishou/__init__.py:63），且 `ENABLE_GET_MEIDAS` 从不被快手模块消费。
- 上游创作者循环没有总量上限（不同于 search 流的 `CRAWLER_MAX_NOTES_COUNT` 约束，core.py:149-151）；耐久层必须自带单元上限。

目标操作结果：

```text
/crawler/ 原生登录
  -> 把已保存的快手会话认领到一个 Account
  -> 添加一个创作者作品 Subscription
  -> 有界、pcursor 跟踪的历史批次
  -> 按作品身份把守的详情抓取与已验证交付
  -> 真实源末之后的头部对账
  -> 面向新作品的增量头部检查
```

## 必需行为

1. **精确订阅所有权。** 每个续传、Job、Run、回执与发布都绑定到一个 Subscription、Account、作者、`profile` 形态的创作者范围以及锁定的 `user_id` 指纹。
2. **逐字游标推进。** 服务端回显的 `pcursor` 按回显逐字存储、逐字回放。任何实现都不得解析、重排、再生成或“优化”它。每个单元至多处理一个上游页，并在该单元的 `max_items` 处停止——这一上限由耐久层自持，因为上游循环是无界的，且每页大小完全由服务端决定。单元绝不截断服务端页后继续推进：当 `max_items` 在页尾之前使单元停下时，该单元以输入 `pcursor` 原样结束，下一单元以相同请求重列，按稳定 `photo.id` 跳过已交付作品，直至页尾耗尽；只有整页耗尽才按回显游标推进 feed。耐久层还必须防住上游从不检查的一类情形（client.py:416-448）：非空页的回显 `pcursor` 与请求 `pcursor` 相同即为零进展，此类停滞单元累计到有界次数后，链路以固定码进入 blocked 状态，而不是无声循环。
3. **四种停止原因，四个固定码。** `no_more_echoed`（服务端回显哨兵，首要源末候选，连同页证据保留）、`empty_page_end`（`feeds` 为空、客户端推断 `no_more`——上游终止态，同样是连同页证据保留的源末候选）、`access_restricted`（假值响应体的疑似封禁中断、业务 `result != 1`、`errors`/`result` 键引发的 `DataFetchError`、三次退避重试耗尽后的限流，以及任何传输级故障——httpx 错误、无法解析的 JSON 响应体（client.py:74、147）、代理刷新错误——它们会中止无 try/except 的上游循环 client.py:416-448），以及 `unit_cap_reached`（单元 `max_items` 上限）。当空 `feeds` 页与服务端回显 `no_more` 同时出现时，以服务端回显为准，单元记录 `no_more_echoed`——client.py:440-442 的客户端推断只服务于回显未携带哨兵的页，服务端证实的证据永远优先。只有两个结束候选可后续 qualified 为源末，且各归其码，操作员能看出是哪条路径关闭了 feed。
4. **身份把守的交付。** 作品详情按 `photo_id` 从呈现该身份的同一页抓取（上游逐页详情回调，`MAX_CONCURRENCY_NUM` 并发，core.py:453-466、220-254），经无签名的 GraphQL 通道——详情抓取不需要、不构造也不附带任何 `__NS_hxfalcon` 材料。一次失败的详情按固定码标记该作品失败，绝不阻塞无关作品。普通视频作品按单个视频形态 Content 单元发布，对记录的 `photoUrl` 字节全有或全无；图集图文作品复用 0034 冻结的图集捕获（`photo.ext_params.atlas.pics`），按单个 IMAGE/GALLERY 形态 Content 单元在全有或全无语义下发布——创作者流复用该既有分支，而非新建模一个分支。
5. **增量之前的头部对账。** 在保留的结束证据（`no_more_echoed` 或 `empty_page_end`）之后，从空 `pcursor` 出发的一次有界头部重列必须复现记录的最新边界（最新作品集合相同、回显形状稳定），订阅才可进入增量轮询。漂移保留已交付数据并重开对账；异常空页导致的结束在这里被识别，而不是被轻信。
6. **增量运行。** 增量循环重列有界头部页，按稳定 `photo.id` 去重，只为未见或变化的作品产生工作。无变化循环不写字节、不写 NFO 行。
7. **暂停、删除与恢复。** 暂停态编辑器为策略变更加栅栏；认证过期走既有 waiting-auth 路径；重启、租约丢失与重复执行对同一耐久单元加栅栏。页面签名环境丢失（reload 后再等待的路径，help.py:72-77）或任何签名/风控受限绝不丢弃耐久 `pcursor`。

## 验收证据

- 确定性捕获回放夹具逐字重放至少三个捕获的 `/rest/v/profile/feed` 页交换——各自携带自己的 `__NS_hxfalcon` 签名、绝不重新推导——记录每次回显的 `pcursor`，在步间重启后到达真实哨兵结束。
- 空 `feeds` 交换记录 `empty_page_end`；被封/受限交换（假值响应体、`result != 1`、限流耗尽或传输级故障）记录 `access_restricted` 并恢复，不伪造源末。
- 源末之后头部漂移（插入一条新作品）重开对账并随后闭合；未变化的头部进入增量模式。
- 一条新作品经抓取一次并作为一个完整视频形态 Content 单元发布；无变化重跑为零工作。
- 最终目录/NFO 校验在不配置媒体服务器的情况下通过。
- Linux 镜像、真实快手登录与真人创作者金丝雀在操作员执行前保持 `NOT_RUN`。

## 明确非目标

- 快手评论、搜索订阅或任何非创作者范围。
- 把抖音整数 `has_more`、XHS token 语义或 Bilibili 页码当作快手形状处理。
- 任何离线构造、缓存或再推导 `__NS_hxfalcon` 签名；存活页面环境是唯一签名权威。
- 超出既有暂停/退避策略的风控自动化处理。
- 任何 Emby/Jellyfin 服务器控制。
