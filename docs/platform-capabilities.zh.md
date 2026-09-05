[English](platform-capabilities.md) | **中文**

# 平台能力矩阵

- 上游：MediaCrawler `d6f7c5bb906b6dac40ddf343ef9e26438a3de092`
- 含义：可达实现；⚠ partial, unreachable or materially incomplete / 部分、不可达或明显不完整；❌ no-op or absent / 空实现或缺失。
- 验收说明：符号描述源码可达性，不代表真人账户验收；除非另有明确记录，全部真人行均保持 `NOT_RUN`。

## 登录路径

| 平台 | QR | Cookie | 源码手机号 | 主入口手机号 | 保存会话 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 小红书 `xhs` | ✅ | ✅ | 有实现 | core 传空号码 | ✅ |
| 抖音 `dy` | ✅ | ✅ | 有实现但依赖短信缓存并有滑块限制 | core 传空号码 | ✅ |
| 快手 `ks` | ✅ | ✅ | ❌ `pass` | ❌ | ✅ |
| 哔哩哔哩 `bili` | ✅ | ✅ | ❌ `pass` | ❌ | ✅ |
| 微博 `wb` | ✅ | ✅ | ❌ `pass` | ❌ | ✅ |
| 百度贴吧 `tieba` | ✅ | ✅ | ❌ `pass` | ❌ | ✅ |
| 知乎 `zhihu` | ✅ | ✅ | ❌ TODO | ❌ | ✅ |


证据位置：登录枚举位于 `cmd_arg/arg.py:52-57`；小红书调用点与实现分别位于 `media_platform/xhs/core.py:103-113`、`media_platform/xhs/login.py:87-224`；抖音调用点与实现分别位于 `media_platform/douyin/core.py:100-109`、`media_platform/douyin/login.py:53-89,124-169,266-274`；其余平台的占位实现位于各自的 `media_platform/*/login.py`。上游 WebUI 本身只开放二维码与 Cookie（`api/main.py:166-187`）。

### media-sync 0.x 对外能力

执行[0058](executions/0058-cookie-login/progress.zh.md)为**B站、小红书、微博、知乎**新增明确粘贴Cookie、远程认证验证和不可变私密保存。抖音/贴吧的本地pong标记及快手仅返回result的GraphQL不足以证明已认证身份，因此暂不开放这三平台粘贴校验。上表七平台的上游Cookie源码列不代表本UI均可验证。Cookie复用改为向全新非持久上下文注入完整键值对。B站与[微博](executions/0060-weibo-creator-profile/progress.zh.md)单作者资料均支持已验证Cookie和保存会话；其他五平台资料及真实端到端验收仍开放。

执行 0012 当前工作树已为七个平台标识开放针对一个合格初始 MediaCrawler QR 账户或精确 `saved_session/expired` 账户的显式阻塞登录命令。在读取设置、数据库或启动 child 前，必须同时提供 `--enable-mediacrawler` 与 `--accept-mediacrawler-license`。隔离的仅登录 child 强制有头浏览器并保存状态；重认证启动时原子变为 `qr/authenticating`，持久成功交接会把账户切换为派生的逐账户 `saved_session/authenticated`，非成功则留在可重试 QR 状态。Child 会一直处于 START/CANCEL/EOF 父进程控制及结果 guardian 下，直到完整树关停。Cookie 继续走非交互密钥引用，显式重认证之外的 saved session 只允许后台无头使用，且**不开放手机号登录**。这一点有意区别于上游过宽的枚举声明。

离线专项门禁证明封闭七标识协议、状态迁移、进程树 join 与脱敏行为，但不证明真人二维码可渲染或可登录。全部真人行保持 `NOT_RUN`；手机号仍为不支持，而不是仅未测试。

## 作者与内容行为

| 平台 | 作者输入 | 作者内容 | 上游数量上限 | 作者资料落库 |
| --- | --- | --- | --- | ---: |
| `xhs` | ID 或主页 URL，可能需要 token 参数 | 图文与视频笔记 | 分页检查上限 | ❌ |
| `dy` | ID 或主页 URL | 图文与视频作品 | 遍历到结束 | ❌ |
| `ks` | ID 或主页 URL | 视频作品 | 遍历到结束 | ❌ |
| `bili` | UID 或空间 URL | 投稿视频 | 30 条每页全历史 | ❌ |
| `wb` | 数字 ID | 微博内容 | 全量分页 | ❌ |
| `tieba` | 主页 URL；CLI 可接收 portrait ID | 作者主题 | 上游检查上限；执行 0020 shim 强制精确成功 `max_items` 工作量 | ❌ |
| `zhihu` | `/people/<url_token>` | 默认只抓回答，文章和视频被关闭 | 锁定循环忽略上限；执行 0019 shim 强制 Subscription `max_items` | ❌ |

七个平台均存在 creator-mode 分发（`media_platform/*/core.py:120-142`）。CLI 会把 `--creator_id` 路由到六个平台列表，但遗漏知乎（`cmd_arg/arg.py:388-402`）。多数 creator store 有意为空操作，内容只使用匿名化作者哈希（`tools/user_hash.py:11-36`；`store/{xhs,douyin,kuaishou,bilibili,weibo,tieba}/__init__.py`）。知乎 creator core 不调用 creator store，其 JSONL `store_creator` 也为空操作，因此该桥接中的任何平台都不能提供可信作者资料行。

### 桥接策略

当前media-sync覆盖：上表描述锁定上游，不等于产品全部能力。0059–0062增加独立有界B站投稿/动态续抓及显式投稿/动态/两者范围（旧订阅仍仅投稿），精确WORD/DRAW/完整OPUS和自有AV引用、私密整页断点、精确图片刷新及离线归档/Emby兼容目录输出。本地导出无需连接媒体服务器；图文HTML不等于原生视频播放验收。转发原文、未知/付费/直播/专栏组件及真实闭环仍按[0062](executions/0062-bili-dynamic-workflow/progress.zh.md)区分不支持与 `NOT_RUN`。

- 在独立数据库保存用户输入的远端作者 ID 与用户提供的显示名称。
- 每次任务设置硬超时和输出条数看门狗。
- 只对审计后仍然无界的creator路径要求显式确认 `allow_full_history`。0019/0020安装有界知乎回答/贴吧主题循环；0059/0062的新有界B站请求也不再要求确认，旧无界artifact仍保留门禁。
- 旧导入可能在已知ID/发布时间水位停止，但B站continuation历史不把旧水位当覆盖证明；保留独立待处理页/详情进度。不得把导入截断或本轮源末尾观察冒充完整历史。
- 在外部运行器中兼容知乎作者参数，不修改上游检出。

## 媒体行为

| 平台 | 元数据 | 上游二进制下载 | 评价 |
| --- | ---: | --- | --- |
| `xhs` | ✅ | 图片与视频 | 整体读内存，无续传/校验 |
| `dy` | ✅ | 图片与视频 | 同上 |
| `ks` | ✅ | 仅 URL | 需自有下载器 |
| `bili` | ✅ | 上游仍只下载首 CID 和单个 progressive URL | 执行 0023–0027 已捕获 1–64 项 page/CID 身份，验收兼容 progressive/DASH Asset，增加有序主/备用故障切换，并以有界 ffmpeg 把显式声明的精确单段 FLV 转封装为 MP4；多 `durl` 分段/FLV 拼接或转码、CDN 排序/竞速/跨运行缓存、超过 64 个分 P、字幕与弹幕继续延期 |
| `wb` | ✅ | 仅图片，且作者路径仍不调用上游下载器 | 执行 0016 已把封闭的静态图片 locator 形状捕获为归一化 IMAGE/GALLERY Asset |
| `tieba` | ✅ | ❌ | 执行 0020–0022 已捕获兼容单图、精确双图与有界 3–64 图的普通主题首楼 ARTICLE 行；超过 64 张的 gallery 与混合/富内容/回复媒体延期 |
| `zhihu` | ⚠ answers by default | ❌ | 执行 0019 已把普通回答精确一张静态图片捕获为 ARTICLE + IMAGE；多图/文章/zvideo 延期 |

媒体下载由拼写错误且不对 CLI 开放的开关 `ENABLE_GET_MEIDAS` 禁用（`config/base_config.py:107-108`）。实现位于 `store/*/*_store_media.py`；当前 HTTP 客户端会把完整响应读入内存，并缺少 `.part`、Range 续传、MIME/探测与校验和验证。

### media-sync 下载与导出状态

执行 0005 实现了通过离线验收的平台无关下载器与 Emby/Jellyfin layout v1。无 query 的 `direct` locator 会执行逐跳公网 DNS 验证、固定地址连接、手动重定向、严格断点续传语义、字节/时间限制、MIME/容器探测、音视频强制且有界的 `ffprobe` 结构验证、SHA-256 与不可变内容寻址发布。下载编排还提供逐资产 OS 锁、不披露路径的 work/archive scope 指纹、精确租约/reclaim CAS，以及归档提交后、数据库收尾前的重启恢复。0.x 的这些文件系统保证以运行根目录及祖先是操作员控制的专用目录为前提；同权限恶意进程替换父目录不在威胁模型内。

导出使用稳定作者/内容身份、NFO 与白名单来源、作者锁、staging 及文件系统 manifest/file CAS。受管所有权不由磁盘 manifest 单独决定：succeeded `export.emby` Job result 组成唯一 predecessor chain，并锚定精确 source/tree/manifest 哈希。发布及中断 roll-forward 会在成功或清理 journal 前复核完整 desired 受管树。发布前 intent 支持精确数据库收尾恢复，包括空快照；允许 `A → B → A`，拒绝伪造或意外 manifest，并发 sibling 只留下一个胜者，且不会删除用户修改或非受管文件。

MediaCrawler 发现的资产只持久化稳定的 `adapter_refresh` locator，因为平台/CDN URL 可能包含过期签名。执行 0009 提交 `98cf387` 已实现默认关闭、绑定精确当前 Asset/Subscription observation 的惰性刷新路径。`asset download` 必须同时传入 `--enable-mediacrawler` 与 `--accept-mediacrawler-license`；需要选择精确来源时再传 `--subscription-id`；小红书另接受一个一次性精确 note URL 的 `--xhs-detail-reference-ref`。刷新的签名 URL 只存在于私有结果/内存/HTTP 边界，不写回 SQLite。

执行 0017 实现提交 `2f8dbaa`（计划检查点 `9d19e7e`）在不改写执行 0009 历史边界的前提下，补齐当前小红书作者订阅自动路径。显式、瞬态的 `xhs_detail_reference_ref` 继续作为兼容覆盖项；否则刷新会从选中的精确 `AssetRefreshSource` 追溯到精确 Subscription，并只在私有运行时解析 `policy.mediacrawler.creator_input.secret_ref`。带签名作者 URL 必须匹配可信的小红书作者、host 与 path，creator 运行受该 Subscription 的 `max_items` 限制。Creator 与 detail 权限严格互斥；refresh context、父请求及 child loader 会分别要求作者 ID 一致，且只有一组唯一、非空的 `xsec_token`/`xsec_source`。返回多条 JSONL 时仍按精确 content ID、Asset kind/position 与 source hint 选取；没有新增数据库迁移，也不持久化逐 note 权限。

在执行 0017 的历史边界，离线组合只验收普通 `type="normal"` 小红书笔记的一张或多张有序静态图片，并归一化为 IMAGE/GALLERY。受控图片字节通过不携带 Cookie、Authorization、Referer 或 Origin 的 `MediaRequestProfile.DEFAULT`、不可变 SHA-256 归档及幂等 Emby/Jellyfin poster/backdrop/gallery/NFO/source 发布；重放不新增 detail、HTTP、归档或导出工作。持久 raw、SQLite、归档元数据及导出结果均不包含作者/note 权限或签名媒体 query 值。在该边界，自动小红书视频、实况照片、动图、混合媒体及权限过期恢复仍未实现或继续延期；真人登录、creator/feed/detail 流量、小红书 CDN 字节及 Emby/Jellyfin 服务器扫描/播放保持 `NOT_RUN`。

执行 0018 实现提交 `356e254`（计划检查点 `c9d3586`）是针对一条普通自动小红书 `type="video"` 行的继任验收。其 raw 标量 `video_url` 必须精确包含一个候选，raw 标量 `image_list` 包含零或一个候选，并一一映射为 position 0 的唯一 VIDEO 与可选 IMAGE。纯视频为 VIDEO；一张封面加一个视频为本次窄范围验收的 MIXED。初始 URL 必须是严格 label、默认端口、非根路径的小红书 CDN 普通有界 HTTP/HTTPS URL；畸形、外域、userinfo、fragment、多候选及容器漂移均关闭失败，重定向继续采用下载器逐跳公网策略。`MediaRequestProfile.DEFAULT`、绑定锁定 store 源码的合约、真实 fake checkout、内嵌 H.264 MP4 的独立生产 `FFprobeMediaProbe` 校验、确定性 mock 组合、SHA-256 归档、Emby `.mp4`/poster/NFO/source 输出及零工作 query 重放全部通过。多视频、多图片、更广混合媒体、实况照片、动图及权限过期恢复继续延期；真人登录、creator/feed/detail、CDN 字节及 Emby/Jellyfin 扫描/播放保持 `NOT_RUN`。

执行 0019 在计划检查点 `dc1714c` 后以实现提交 `2edb9d7` 增加知乎作者普通回答 IMAGE 形状，使知乎成为第六个拥有专项离线媒体输出的平台。校验 checkout shim 会在锁定 extractor/store 路径丢弃图片属性前捕获图片，把捕获绑定到精确返回的 Pydantic 模型，并只在嵌套 store 阶段使用 `ContextVar`。gather child → 父 store 及不序列化回归均通过。属性选择遵循 `data-original` → `data-actualsrc` → `src`；竞争性的 `srcset`、`data-src` 或 lazy 候选、重复选中属性、多图片及可播放/容器漂移均关闭失败；canonical 回答/图片 URL 门包含空分隔符拒绝。

Scheduled creator child 把 manifest/Subscription `max_items` 传给有界回答循环，并校验短页/重复页/畸形页。端到端证据把 23 映射为页面大小 `20 + 3` 的两次 API 请求与两次 callback 调用，callback 精确处理 23 行，页间执行一次节奏 sleep；达到上限后没有第三次请求或额外 sleep。知乎已从 `FULL_HISTORY_PLATFORMS` 移除，因此可使用 `allow_full_history=false`。归一化保持 ARTICLE 加唯一 `<content_id>:image:0` IMAGE，递归移除私有/瞬态权限并只持久化无 query hint；精确 canonical 权限驱动无凭据 DEFAULT-profile 刷新。知乎 IMAGE 自动启用有界静态结构资格校验：合格 JPEG/PNG/WebP 通过，GIF/APNG/animated WebP/AVIF 失败，normal/recovery/takeover 路径保留该标志；这不是完整像素解码。最终专项门通过 505 项，完整套件通过 1543 项且仅跳过一项 Windows 不适用用例，全部质量/审计门通过，独立复核未发现 P0/P1/P2。当前没有真实脱敏夹具，全部真人行保持 `NOT_RUN`。

执行 0020 在计划检查点 `df7a38a` 后以实现提交 `8a0e935` 增加第七个平台的首个可下载媒体切片，且未修改上游或新增 migration。校验 checkout 的贴吧 shim 从普通首楼 `content` 捕获精确一个当前整数 type-3 图片，把它绑定到跨 gather-child → parent-store 的精确返回模型，并只在嵌套 JSONL 存储期间使用 `ContextVar`。门禁要求普通 type-0 文本兄弟项及精确当前十键图片对象，只选择签名 HTTPS `tiebapic.baidu.com/forum/pic/item/<40-hex>.<jpg|jpeg|png|webp>?tbpicau=...` `origin_src`；零图/多图/其他/drift 形状不通过本次媒体声明。Scheduled `max_items=23` 形成 `20 + 3` 详情/callback 批次，无第三页或达到上限后的 sleep。

归一化保持 ARTICLE 加唯一 `<note_id>:image:0` IMAGE，并只持久化无 query 的 scheme/authority/path。惰性刷新从 SQLite canonical 主题 URL 派生精确非密钥权限，通过 `TIEBA_SPECIFIED_ID_LIST` 发送 numeric ID，要求唯一匹配 ARTICLE/IMAGE/hint，并以无凭据 DEFAULT profile 只返回新校验的签名 URL。贴吧 IMAGE 自动使用同一有界结构门：合格 JPEG/PNG/WebP 通过，GIF/APNG/animated WebP/AVIF 失败；normal、recovery 与 takeover 准备链保留该标志。确定性 SQLite → fake detail → mock 公网 DNS/HTTP → SHA-256 归档 → Emby poster/backdrop/gallery/body/NFO/source 组合及 query 零工作重放通过，且不保留私有字段或 `tbpicau`。专项回归通过 368 项，完整套件通过 1650 项且仅跳过一项 Windows 不适用用例；全部质量/构建/上游/审计门通过。真人登录/作者/detail/CDN 与 Emby/Jellyfin 服务器行保持 `NOT_RUN`；首楼 gallery 与全部其他贴吧媒体/富内容类型继续延期。

执行 0021 计划 `5095ed6`、实现 `e0fb8d5` 保留 v1 单图分支，并增加独立精确双图 v2 捕获。两个 type-3 项都必须满足同一冻结结构并具有互异无 query 身份；来源顺序成为 position 0/1。双字段、重复身份、三张及以上图片及其他内容类型均关闭失败。刷新上下文冻结完整持久单图或双图元组，因此双图任一 position 都要求当前相同完整有序 gallery；缺图、重排或身份替换会在返回签名 locator 前失败。两次无凭据 DEFAULT-profile 下载通过生产 JPEG/PNG 静态资格，发布两个 SHA-256 归档并渲染 Emby poster/backdrop/两项 gallery/body/NFO/source。Query 重放不新增工作，整树断言不保留私有字段或 `tbpicau`。专项 `413 passed`；完整 `1668 passed, 1 skipped`；全部质量/构建/文档/上游/审计门通过。三张及以上/混合/富内容/回复媒体及全部真人行不在已交付边界内。

执行 0013 实现 `dd6cfec` 把当前 Bilibili 形状从仅封面扩展到一个经过离线验收的普通 numeric-aid 视频：稳定、仅 locator、`source_url=NULL` 的 `<aid>:video:0` Asset，精确首 CID 查询及精确一个 progressive `durl`。封闭的 Bilibili media profile 提供固定浏览器型 UA、Referer 与 Origin，同时拒绝 Cookie、Authorization 和任意调用方 header。签名 URL 在 detail、refresh、重定向/续传及一次 401/403 重解析中保持瞬态；合成 MP4 字节可完成受控探测、归档收尾及幂等 Emby 主媒体发布。

在执行 0013 的历史边界，由于 forward JSONL 不含 CID，持久身份也不包含 CID；因此同 aid 下后续首 CID 替换无法自动提升 generation 或使已验证字节失效。执行 0023 现为兼容多分 P 投稿增加 page/CID 捕获与 CID 绑定身份，同时为精确单 P 兼容保留 `<aid>:video:0`。

执行 0023 计划 `bd45478`、实现 `24fd41c` 在锁定 Bilibili store 丢弃 `View.pages` 前捕获规范、任务局部的 1–64 分 P 元组。畸形、不连续、重复 CID 与 65 分 P 声明均关闭失败。合格 2–64 分 P 投稿产生有序、仅 locator 的 `<aid>:video:cid:<cid>` VIDEO Asset。详情协议 v4 只发送目标 `bili_video_cid`，只接受该 CID 的精确一个 progressive `durl`，并在内存返回完整当前元组；惰性刷新要求兄弟数量/顺序/CID/position/remote ID 完全一致才返回 URL。私有分 P/播放字段与签名 URL 不会留在任何持久状态。三份不同 mock 字节流经过定向详情、固定 Bilibili media profile、DNS/HTTP、受控探测、SHA-256 归档及确定性 Emby 主媒体/两个 part/NFO/source 发布；query-only 重放零新增工作。专项 `436 passed in 53.96s`；完整 `1739 passed, 1 skipped in 321.25s`；全部质量/构建/文档/上游/审计门通过。DASH 音视频合并、FLV remux、多 `durl` 分段、字幕、弹幕、备用地址故障切换、超过 64 个分 P 及番剧/付费/直播媒体仍不支持或继续延期；全部真人登录/API/CDN/Emby/Jellyfin 行保持 `NOT_RUN`。

执行 0024 计划 `a7d038e`、实现 `12314b9` 把严格详情协议升级到 v5。精确目标 CID 通过 WBI `/x/player/wbi/playurl` 请求，并携带 `qn=127`、`fourk=1`、`fnval=4048` 与 `platform=pc`。封闭选择器取最高受支持 DASH 视频画质，同画质依次偏好 AVC → HEV → AV1，按锁定的普通/杜比/Hi-Res 顺序选择音频，并接受合法无声视频形状。签名主、备用与组件 URL 为 repr-safe 且保持瞬态。Generation-scoped 音视频 store 提供严格 Range 续传、逐组件探测、组合字节上限、固定有界 `ffmpeg -c copy` 合并与最终 `ffprobe`；只有验证后的成品进入不可变 SHA-256 归档。合并失败会保留已验证组件，已准备且发布的成品可在不再次调用 detail/DNS/HTTP/ffmpeg 的情况下恢复。本地真实 H.264 与 AAC 组件经过生产 ffprobe/ffmpeg，产生同时含音视频流的 Emby MP4。专项 `456 passed in 66.47s`；完整 `1780 passed, 1 skipped in 333.43s`；全部质量/构建/文档/上游/审计门通过。备用 URL 已校验并建模，但故障切换尚未实现；FLV、分段 `durl`、字幕、弹幕、超过 64 个分 P 及更广 Bilibili 媒体仍不支持或继续延期。全部真人登录/API/CDN/Emby/Jellyfin 行保持 `NOT_RUN`。

执行 0025 计划 `8e9467d`、实现 `fe45abc` 把已校验的瞬态 DASH 候选列表转化为视频与可选音频各自独立的有序轮次。每轮在既有 Asset 锁、组件/组合字节上限及共享截止时间下使用主地址加最多八个互异备用地址；主地址成功时不会访问备用 DNS 或 HTTP。候选局部 DNS、timeout、传输、中断、HTTP 状态及 partial Range 不兼容可推进。禁用或混合网络地址、重定向/header/encoding、chunk/size、文件系统、探测与合并失败仍立即关闭。跨候选追加要求 Range offset、总长度及 validator 类型/值完全连续；混合候选失败会保留 partial，只有完整轮次拒绝后才执行有界丢弃/restart。仅由 `401`/`403` 构成的穷尽继续返回 `locator_refresh_auth_expired`；保留 SQLite、Job、runtime、work、归档、导出与错误状态均不含候选 URL、host 或胜出序号。生产进程组合让视频主地址返回 `503`、音频主地址返回 `403`，各自独立到达备用地址，再贯穿 ffprobe → ffmpeg → 最终 ffprobe → SHA-256 归档 → Emby 双流发布与零工作重放。专项 `466 passed in 66.96s`；完整 `1790 passed, 1 skipped in 331.33s`；全部质量/构建/文档/上游/审计门通过。progressive 备用故障切换、CDN 排序/缓存、FLV、分段 `durl`、字幕、弹幕、超过 64 个分 P 与更广 Bilibili 媒体仍不支持或继续延期。全部真人登录/API/CDN/Emby/Jellyfin 行保持 `NOT_RUN`。

执行 0026 计划 `0694934`、实现 `190488f` 把有界详情协议升级到 v6，并通过等价 `backup_url`/`backupUrl` 别名接受一个 progressive `durl` 主地址及最多八个已校验有序备用地址。冲突别名、畸形值、重复、与主地址相同及超限均关闭失败。私有单 P 备用字段与多分 P 可选 `backup_urls` 保持历史仅主地址兼容，随后在保留 raw/SQLite/Job 状态前递归消失。普通 progressive 与 DASH locator 现共用相同 Asset 锁、截止时间、字节上限及 restart 预算下的主地址优先候选轮次。DNS、timeout、传输、中断、HTTP 与 Range 不兼容可推进；网络策略、重定向/header/encoding、chunk/size、文件系统、探测、合并、归档及发布失败仍立即关闭。跨候选续传要求 offset、总长度及 validator 类型/值完全连续；混合失败保留合法 partial，且只有完整轮次拒绝后才执行破坏性 restart。Adapter 一轮全部 `401`/`403` 时重解析详情一次；第二轮仍全鉴权失败返回 `locator_refresh_auth_expired`，direct 及混合/非鉴权穷尽不刷新。单 P 与三分 P SQLite 组合均让每个主地址返回 `503`，到达有序备用地址，贯穿受控探测 → SHA-256 归档 → Emby 主媒体/part 发布并以零新增工作重放。签名候选与私有字段不存在于保留证据。专项 `490 passed in 73.31s`；完整 `1814 passed, 1 skipped in 342.33s`；两个 progressive 组合、DASH 兼容及全部质量/构建/文档/上游/审计门通过。多 `durl` 分段、FLV、CDN 排序/竞速/跨运行缓存、混合/非鉴权穷尽刷新、超过 64 个分 P 与更广 Bilibili 媒体仍不支持或继续延期。全部真人登录/API/CDN/真实 progressive 字节/Emby/Jellyfin 行保持 `NOT_RUN`。

执行 0027 计划 `ec7095a`、实现 `7f99aa4` 把有界详情协议升级到 v7，并且只允许合法、显式的顶层格式授予 FLV 权限。一个 repr-safe 类型化 target 通过防碰撞单 P/多分 P 私有桥接并保持瞬态。Generation-scoped 源 store 复用有序候选、严格续传/restart 与一次全鉴权刷新；精确源 FLV 探测先于固定有界的单输入 `ffmpeg -c copy`，且只有精确探测为 MP4 的成品可归档/导出。转封装/成品门失败会保留源并移除未准备成品。生成的本地 H.264+AAC FLV 贯穿“主地址 `503` → 备用 → 生产 ffprobe/ffmpeg → 双流 SHA-256 MP4 → Emby 输出”，并零工作重放且不发布签名/私有信息或原始 FLV。专项 `394 passed in 59.12s`；完整 `1848 passed, 1 skipped in 347.72s`；全部质量/构建/文档/上游/审计门通过。多 `durl` 分段、FLV 拼接/转码及全部真人行继续待实现或保持 `NOT_RUN`。

执行 0014 实现 `c4ab537` 验收一个包含精确一个合法播放 URL 与可选封面的快手普通单视频形状。锁定进程契约通过 `KS_SPECIFIED_ID_LIST` 接受纯视频 ID；绑定精确 Account/Subscription 的惰性刷新使用 `MediaRequestProfile.DEFAULT` 解析两项 Asset。持久 raw 与 SQLite 只保留规范 origin/path，并结构化移除 userinfo、已知/未知 query 值、fragment 与嵌套 schema 漂移。合成 MP4/PNG 字节通过无 Cookie/Authorization 的有界默认 HTTP profile、强制视频探测、SHA-256 归档收尾及幂等 Emby `.mp4`/海报/NFO/source 发布。

快手作者爬取仍会遍历到上游 `no_more`，因此本结果不证明作者分页有界。图集、多播放 URL、音频/字幕/评论、直播/付费/受限媒体、专用 CDN header 及同 ID/同 origin/path 字节替换仍不支持或继续延期；已证明 detail 成功清理，但注入清理失败仍缺少完整 quarantine/incident/账户阻断。

执行 0015 实现 `95d314d` 验收一个更窄的抖音组合形状：decimal `aweme_id`、空 `note_download_url` 与 `music_download_url`、精确一个视频 URL 及可选封面。真实隔离 fake checkout 会经过 `MediaCrawlerDetailProcessRunner`，验证 numeric `DY_SPECIFIED_ID_LIST`、媒体关闭/detail JSONL 配置、保存 profile 及成功 attempt 清理。平台组合测试有意替换为 fake detail runner、mock DNS/HTTP、合成 MP4/PNG 与受控 probe，同时仍贯穿精确 Account/Subscription/AssetRefreshSource 选择、默认 profile 媒体 HTTP、SHA-256 归档及 Emby `.mp4`/海报/NFO/source 发布。默认 profile 的媒体请求不携带 Cookie、Authorization、Referer 或 Origin；这不表示另一个 Cookie 登录 detail 契约中没有 Cookie。

四个抖音媒体 raw 字段现在只为已接受的平面 URL 保留规范 origin/path。逗号分隔的 note 标量会变为有序序列；mapping/嵌套值及含逗号的 sequence 子项按项关闭失败，含逗号的非 note 标量按字段关闭失败。该 sanitizer 回归覆盖图集/音频形状输入，但不验收图集播放、关联音乐语义或多媒体 URL。仅 query 变化的重放无法发现同一 aweme ID 与 origin/path 下的字节替换；可信 Subscription 也不是远端作者归属的独立证明。

执行 0016 实现 `a77ca74` 仅在锁定 checkout 与导入 store 来源均已验证后，才在 creator 与 detail child 中安装由集成拥有、任务局部的微博图片 shim；它绝不修改 `.upstream`。只接受具有规范正 numeric note ID、不含 `retweeted_status`、且没有有效 `page_info`（只允许缺失、`null` 或空对象）的普通原创；`pics` 必须是非空、扁平、有序且 `pid`/URL 均合法并唯一的列表。来源必须是 `sinaimg.cn` 本身或其子域上的无 query HTTPS URL，文件名扩展名不区分大小写地属于静态 `.jpg`、`.jpeg`、`.png`、`.webp`；shim 沿用锁定版 `https://i1.wp.com/<sina-host>/large/<filename>` 转换。任务局部 `ContextVar` 防止并发 note 捕获串用。单图成为 `ContentKind.IMAGE`，多图成为 `ContentKind.GALLERY`，有序 IMAGE Asset position 为 `0..N-1`。私有捕获字段会在持久 raw 元数据形成前递归移除；导入则创建稳定 `adapter_refresh` 身份及绑定精确 Account/Subscription 的 `AssetRefreshSource` observation。

微博 detail 权限分别在 refresh context、父 `MediaCrawlerDetailRequest` 与 child payload loader 三层关闭；每层只允许 `detail_reference` 为 `None`，或为与同一个规范 numeric content ID 完全相同的普通 `str`，不同 ID、URL、`SecretValue`、字符串子类或畸形值都会在该边界失败。真实隔离 fake-checkout 契约会经过 creator 与 detail process runner；另一个组合测试有意使用 fake detail payload、mock 公网 DNS/HTTP 与两份合成 PNG，同时贯穿生产来源选择、`MediaRequestProfile.DEFAULT`、图片校验、两个不可变 SHA-256 archive blob，以及幂等 Emby/Jellyfin poster/backdrop/双文件 gallery/NFO/白名单 source 布局。默认 profile 媒体请求不添加 Cookie、Authorization、Referer 或 Origin。这是离线协议证据：全部真人登录、作者扫描、detail/图片代理/CDN 字节及 Emby/Jellyfin 服务器行保持 `NOT_RUN`。

在可能产生网络流量的 pipeline 创建或修改任何 child Job/Asset 生命周期状态前，生产 preflight 会校验锁定的 MediaCrawler lock、checkout、Python runtime，并验证强制 `ffprobe` 实际可启动。Bilibili DASH 与显式 FLV 衍生路径还会在持久 child 工作前要求 `ffmpeg` 可启动。缺失配置与无效但非空的配置都会在 child 生命周期副作用前失败。这是离线配置覆盖，不是真人 CDN 验收。

离线支持的刷新形状为小红书 image/video、抖音 image/video/audio/cover、快手普通单视频与可选封面、Bilibili cover 加兼容单 P 或 2–64 分 P 的 progressive/DASH 普通投稿（包括显式单段 FLV→MP4 衍生）、普通原创 numeric-ID 微博静态 IMAGE/GALLERY、知乎普通回答精确一张静态 IMAGE，以及兼容单图/双图/3–64 张静态图的贴吧普通主题首楼。Execution 0027 已在实现 `7f99aa4` 中通过全部离线收尾门；其 FLV 衍生处理不改变十二个形状的数量。贴吧超过 64 张及混合/富内容/回复媒体、知乎多图/文章/zvideo、微博视频/GIF/长图、小红书扩展媒体/权限过期恢复、抖音/快手扩展媒体，以及 Bilibili 多分段/FLV 拼接/转码形状继续不支持或延期。无 query 的 `direct` locator 继续使用平台无关下载器，无需启用 MediaCrawler。

执行 0010 在不扩大平台支持的前提下组合持久本地工作流。Scheduler 成功只 enqueue 一个 `pipeline.subscription` 协调器；另一个显式有界 `pipeline run` 每次 claim 最多扫描 `--scan-limit` 个候选，续租协调器，串行下载精确 Subscription 的合格资产，并仅在持久复核后调用 Emby 导出。第二个 worker 中的 MediaCrawler refresh 同样保持默认关闭并受许可证 gate 约束。它是一次性控制面，不是 daemon。

组合 API/access-key 映射名会在 snake_case、kebab-case、camelCase 及带提供商前缀的形式下脱敏，但不会删除普通 `key`、`public_key` 或 `key_id` 字段。带凭据标记的 URL 路径（包括编码及双重编码变体）会在落点脱敏，并被 `direct` locator 与 source-hint 派生同时拒绝。当前导入与 `0003` legacy 回填因此只为此类资产持久稳定 `adapter_refresh` 身份，并清空 legacy 不安全 `source_url`。`0003` downgrade 还会清空所有资产下载 FK 与 generation-bound Job，移除不可恢复的未成功 Emby 身份，同时保留已成功发布链与结构有效的发布 intent 恢复状态。

## 存储与调度

| 能力 | 上游现状 | media-sync 方案 |
| --- | --- | --- |
| 订阅表 | 缺失 | 独立统一模型 |
| 任务历史 | WebUI 单个内存进程 | 持久任务与事件 |
| 增量水位 | 缺失 | 已知 ID + 发布时间水位 + 可选 cursor |
| 幂等写入 | SQL 先查后写 | 唯一约束与原子 upsert |
| JSONL 隔离 | 按日追加 | 每任务独立输出根目录 |
| 多账户 profile | 仅按平台 | 按平台与账户 |
| 交互认证 | 平台登录代码可能退出或隐式回退二维码 | 执行 0011 新增显式双 gate QR 命令、封闭 child 真值、持久 LoginSession 状态及原子 `saved_session` 交接；专项与完整离线门禁通过，真人验收仍待完成 |
| 持久调度 | 仅内存 WebUI 队列 | 执行 0006 提供持久到期周期、重试策略与平台/账户启动 lane；执行 0007 新增默认关闭、受许可证约束的 MediaCrawler forward handler，包含 attempt 根、父进程 heartbeat/监督与精确导入 fencing。其历史 AC6/AC13 记录继续为 `PARTIAL`；执行 0008 现以两个剩余取消 barrier 与精确 33-cell 失败/落点矩阵通过继任离线收口 |
| 自动下游衔接 | 缺失 | 执行 0010 在 sync 成功时原子 enqueue；显式有界 `pipeline run` 串行下载后执行 Emby 导出；未实现常驻 daemon 或 HA supervisor |

## 验收状态

执行 0007 已为七个平台标识提供自动化离线证据：“订阅 → tick → manifest-v3 写入/读取 → 真实本地 fake child 写入版本化 JSONL → receipt-v2 写入/读取 → 受保护导入 → 重试/重启 → 幂等重放”。这只证明 media-sync/子进程文件系统协议与持久身份；没有使用浏览器、平台账户、作者端点、CDN 或媒体服务器，也不证明上游分页有界或真人兼容。

仍未使用真人账户或交互挑战。七个平台的真人二维码/Cookie/保存会话登录、作者流量及定时运行全部保持 `NOT_RUN`；手机号登录仍属于不支持，而不是仅未测试。没有运行真实签名 locator 刷新/CDN 获取，也没有在获授权真实服务器上运行连接探测、Library 发现、定向刷新接受、精确项目查找或刷新后项目观察。执行 0007 自身的 AC6/AC13 记录继续作为历史 `PARTIAL` 证据。

### 执行 0054 阶段 B 媒体服务器真值

资格 schema v3 将自动化证据、实现状态与真人资格分开。既有平台计数及 probe/scan 事实不授予真人 PASS。Playback evidence 已 IMPLEMENTED，未选择作者或无精确当前确认则为 NOT_RUN；只有选定作者的新完整稳定 lookup 与匹配持久确认才能产生该范围 PASS。Provider completion 仍 NOT_IMPLEMENTED（`provider_api_unsupported`），导出后自动扫描仍 NOT_IMPLEMENTED，二者真人状态为空。

Legacy `{}` scan 成功只证明定向刷新已接受。作者观察只证明 absent baseline、一次被接受的刷新，以及间隔两次观察到同一唯一 provider/path 项目；这是后置条件证据，不是 provider task completion 或可播放。阶段 B 本地门禁通过 7 个文件中的 69 项 Web 测试，以及格式、Svelte check 与生产构建；11 项真实 PostgreSQL Operation 竞态测试通过；完整 Python 套件为 2763 passed、3 skipped、1 个既有 warning。PostgreSQL fixture 只在隔离 schema 中创建生产 Operation/Event/Subject/StreamState 四张 metadata 表；这不代表全应用 schema 或部署已经支持 PostgreSQL。这些本地/mock 证据没有使用真实 Emby/Jellyfin 凭据，不会授予真人 PASS。执行 0055 的后端单操作者访问控制边界已在提交 `f19bfaa` 中实现；190 项 auth/API 专项与完整离线回归（`2811 passed, 14 skipped, 1 warning`）通过，其中 11 项真实 PostgreSQL 测试因本工作站没有测试 URL 而跳过。它提供绑定前关闭失败的类型化凭据、精确 Host/Origin 与默认拒绝的路由保护、带 CSRF 的轮换式 HttpOnly session，以及可选且不同的 Bearer 凭据。

执行 0055 现已实现鉴权、observation 身份、revision `0008`、append-only replay、仅浏览器确认、有界作者证据 GET 与资格 v3。读取路径在打开短事务前重验 publication/profile 及完整 observation；当前证据独立于历史查询，历史默认 20、最多 50 行，账本总物化行数不超过 limit + 2。远端不确定使历史未知。响应只含本地 ID、时间戳、安全状态与分页边界。投影历史证据见[投影记录](executions/0055-operator-auth-playback-evidence/evidence-projection/verification.zh.md)。Console v2 的 login/session／内存 CSRF、退出／过期／401 与 QR／SSE 现已实现，启动前增加 `serve --check-config`；当前[本地合成浏览器验证](executions/0055-operator-auth-playback-evidence/secure-console/verification.zh.md)已通过。Legacy 为受保护迁移提示，确认 UI 仍待 P1 实现且不阻塞 CLI 真人金丝雀。全部真人行保持 NOT_RUN，可写设置、多配置、保留／破坏性维护与自动扫描仍不属于本阶段。

执行 0011 本地提交 `8bb16f6` 建立了显式 QR 登录、已过期 saved-session 重认证及非交互 saved-session 复用的历史离线状态与正常进程边界。执行 0012 提交 `28655f8` 现已增加有界请求/结果 framing、持续父进程控制、结果 guardian、父进程硬终止时的完整树收容，以及在同一账户锁下受截止时间 fencing 保护的遗留会话回收。登录启动、脱敏状态查询和常驻 sweep 使恢复路径可达；轮转游标避免早期 busy 候选饿死后续账户。0012 专项门禁通过 283 项并有 1 项 Windows 不适用的跳过，完整套件通过 1156 项并跳过同一项。上游 saved-session 探测为 false 仍可能包含网络异常歧义，因此 `auth_expired` 继续是保守动作而非精确远端原因诊断。这些证据不会改变任何真人资格行。

执行 0009 刷新 MVP、执行 0010 显式有界下游 pipeline、执行 0012 本地前台监督器及截至执行 0024 建立的十二个冻结媒体形状均已完成各自冻结离线范围；执行 0025–0026 增加有序备用可靠性，执行 0027 增加显式单段 FLV→MP4 衍生。Execution 0027 专项回归通过 394 项，完整套件通过 1848 项且仅跳过一项 Windows 不适用用例，Bilibili 兼容/生产组合及全部质量/审计门通过。在该历史边界，证据覆盖全部七个平台的十二个冻结媒体形状，但不证明任何真人平台/CDN/媒体服务器行。生产 pipeline handler 当时是通过 `asyncio.to_thread` 运行的同步函数，因此监督器会在 heartbeat 下等待一项已经 active 的尝试，而不是取消它。底层线程强制终止与多 worker HA 当时尚未验收。

在同一历史边界，微博视频/有效 `page_info`、GIF/动图语义、长图专用处理、有界 creator 分页、直连新浪 request profile、同 ID 媒体替换检测及注入清理失败 quarantine 尚不可用或延期。更大的产品还缺贴吧超过 64 张的 gallery、混合/富内容/回复媒体与替换语义、知乎多图/文章/zvideo 媒体、七平台完整媒体形状覆盖、小红书扩展媒体/权限过期恢复、Bilibili 多分段 progressive 与 FLV 拼接/转码、超过 64 个分 P、字幕/弹幕、CDN 排序/竞速/跨运行缓存及混合/非鉴权穷尽后的新详情刷新、其他平台衍生物、逐 HTTP 请求间隔，以及同步线程强制取消/多 worker HA。这些是实现差距，不是 `NOT_RUN` 结果；该边界的全部真人验收行保持 `NOT_RUN`。当时交付的监督器是显式单主机前台进程，不是生产服务。
