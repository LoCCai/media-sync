# Platform capability matrix / 平台能力矩阵

- Upstream / 上游：MediaCrawler `d6f7c5bb906b6dac40ddf343ef9e26438a3de092`
- Meaning / 含义：✅ reachable implementation / 可达实现；⚠ partial, unreachable or materially incomplete / 部分、不可达或明显不完整；❌ no-op or absent / 空实现或缺失。

## Login paths / 登录路径

| Platform / 平台 | QR | Cookie | Phone in source / 源码手机号 | Phone through main CLI / 主入口手机号 | Saved session / 保存会话 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Xiaohongshu / 小红书 `xhs` | ✅ | ✅ | ⚠ implemented / 有实现 | ❌ core passes empty phone / core 传空号码 | ✅ |
| Douyin / 抖音 `dy` | ✅ | ✅ | ⚠ implemented with SMS cache and slider caveats / 有实现但依赖短信缓存并有滑块限制 | ❌ core passes empty phone / core 传空号码 | ✅ |
| Kuaishou / 快手 `ks` | ✅ | ✅ | ❌ `pass` | ❌ | ✅ |
| Bilibili / 哔哩哔哩 `bili` | ✅ | ✅ | ❌ `pass` | ❌ | ✅ |
| Weibo / 微博 `wb` | ✅ | ✅ | ❌ `pass` | ❌ | ✅ |
| Tieba / 百度贴吧 `tieba` | ✅ | ✅ | ❌ `pass` | ❌ | ✅ |
| Zhihu / 知乎 `zhihu` | ✅ | ✅ | ❌ TODO | ❌ | ✅ |

Evidence / 证据：login enum at `cmd_arg/arg.py:52-57`; XHS call site `media_platform/xhs/core.py:103-113` and implementation `media_platform/xhs/login.py:87-224`; Douyin call site `media_platform/douyin/core.py:100-109` and implementation `media_platform/douyin/login.py:53-89,124-169,266-274`; placeholder implementations in each remaining `media_platform/*/login.py`. The upstream WebUI itself exposes only QR and Cookie (`api/main.py:166-187`).

### media-sync 0.x exposure / media-sync 0.x 对外能力

The MediaCrawler bridge exposes QR, Cookie and a previously saved per-account browser session. It does **not** claim phone support. A future native adapter may expose phone login only after an interactive end-to-end qualification. This intentionally differs from the overly broad upstream enum.

MediaCrawler 桥接器只开放二维码、Cookie 和已保存的账户级浏览器会话，**不宣称支持手机号登录**。未来原生适配器只有通过交互式端到端验收后才能开放手机号登录。这一点有意区别于上游过宽的枚举声明。

## Creator/content behavior / 作者与内容行为

| Platform / 平台 | Creator reference / 作者输入 | Creator content / 作者内容 | Upstream cap behavior / 上游数量上限 | Profile persisted / 作者资料落库 |
| --- | --- | --- | --- | ---: |
| `xhs` | 24-char ID or profile URL; token parameters may be required / ID 或主页 URL，可能需要 token 参数 | Image/video notes / 图文与视频笔记 | ✅ page loop checks maximum / 分页检查上限 | ❌ |
| `dy` | `sec_user_id` or `/user/...` / ID 或主页 URL | Image/video aweme / 图文与视频作品 | ❌ traverses until `has_more=0` / 遍历到结束 | ❌ |
| `ks` | user ID or `/profile/...` / ID 或主页 URL | Video posts / 视频作品 | ❌ traverses until `no_more` / 遍历到结束 | ❌ |
| `bili` | UID or space URL / UID 或空间 URL | Creator videos / 投稿视频 | ❌ full history, 30 per page / 30 条每页全历史 | ❌ |
| `wb` | numeric user ID / 数字 ID | Weibo notes / 微博内容 | ❌ full mobile-container pagination / 全量分页 | ❌ |
| `tieba` | home URL; CLI also accepts portrait ID / 主页 URL；CLI 可接收 portrait ID | Author threads / 作者主题 | ✅ checks configured maximum / 检查配置上限 | ❌ |
| `zhihu` | `/people/<url_token>` | Answers only by default; article/video calls disabled / 默认只抓回答，文章和视频被关闭 | ❌ ignores cap and traverses answers until end / 忽略上限并遍历全部回答 | ❌ |

Creator-mode dispatch exists for all seven platforms (`media_platform/*/core.py:120-142`). The CLI routes `--creator_id` into six platform lists but omits Zhihu (`cmd_arg/arg.py:388-402`). Most creator stores are deliberately no-ops and content uses an anonymized creator hash (`tools/user_hash.py:11-36`; `store/{xhs,douyin,kuaishou,bilibili,weibo,tieba}/__init__.py`). Zhihu's creator core does not call a creator store, and its JSONL `store_creator` is also a no-op, so no platform in this bridge provides a trustworthy creator profile row.

### Bridge policy / 桥接策略

- Preserve the user-supplied remote creator ID and a user-provided display label in the independent `media-sync` database.
- Give every run a hard wall-clock timeout and output-item watchdog.
- Require an explicit `allow_full_history` acknowledgement for an upstream path known to ignore its item cap until a bounded native adapter exists.
- Stop incremental ingestion at known IDs/publish watermark even if the child emitted older records; never treat downstream truncation as proof that upstream traffic was bounded.
- Work around Zhihu creator input in the external runner without editing the upstream checkout.

- 在独立数据库保存用户输入的远端作者 ID 与用户提供的显示名称。
- 每次任务设置硬超时和输出条数看门狗。
- 对已知忽略数量上限的平台，在原生适配器实现有界分页前，必须显式确认 `allow_full_history`。
- 即使子进程产生旧数据，导入也在已知内容 ID/发布时间水位处停止；但不得把“导入截断”冒充“上游请求已受限”。
- 在外部运行器中兼容知乎作者参数，不修改上游检出。

## Media behavior / 媒体行为

| Platform / 平台 | Metadata / 元数据 | Upstream binary download / 上游二进制下载 | Qualification / 评价 |
| --- | ---: | --- | --- |
| `xhs` | ✅ | Images and video / 图片与视频 | ⚠ full response in memory, no resume/checksum / 整体读内存，无续传/校验 |
| `dy` | ✅ | Images and video / 图片与视频 | ⚠ same limitations / 同上 |
| `ks` | ✅ | ❌ URL only / 仅 URL | Requires media-sync downloader / 需自有下载器 |
| `bili` | ✅ | ⚠ first CID, one progressive URL only / 仅首 CID 和单个 progressive URL | Missing DASH mux, multi-P, subtitle and danmaku / 缺 DASH 合并、多 P、字幕、弹幕 |
| `wb` | ✅ | ⚠ images only and creator path does not call it / 仅图片且作者路径未调用 | Requires normalized asset discovery / 需自有资产发现 |
| `tieba` | ✅ | ❌ | Requires attachment discovery / 需附件发现 |
| `zhihu` | ⚠ answers by default | ❌ | Article/video creator flow disabled / 作者文章与视频流程关闭 |

Media download is disabled by the misspelled non-CLI switch `ENABLE_GET_MEIDAS` (`config/base_config.py:107-108`). Implementations are under `store/*/*_store_media.py`; current HTTP clients buffer complete responses and lack `.part`, Range resume, MIME/probe and checksum validation.

## Storage and scheduling / 存储与调度

| Capability / 能力 | Upstream state / 上游现状 | media-sync response / media-sync 方案 |
| --- | --- | --- |
| Subscription table / 订阅表 | Absent / 缺失 | Independent normalized schema / 独立统一模型 |
| Run history / 任务历史 | One in-memory WebUI process / WebUI 单个内存进程 | Durable `sync_runs` and events / 持久任务与事件 |
| Incremental cursor / 增量水位 | Absent / 缺失 | Known-ID + publish watermark + optional cursor / 已知 ID + 发布时间水位 + 可选 cursor |
| Idempotent upsert / 幂等写入 | SQL path does select-then-write / SQL 先查后写 | Database unique constraints and atomic upsert / 唯一约束与原子 upsert |
| JSONL isolation / JSONL 隔离 | Per-day append / 按日追加 | Unique output root per run / 每任务独立输出根目录 |
| Multi-account profile / 多账户 profile | Per platform only / 仅按平台 | Per platform and account / 按平台与账户 |

## Qualification status / 验收状态

No live account was used during this source audit. All seven live login/sync entries are therefore `NOT_RUN`. Automated bridge/fixture tests may prove command and ingestion behavior, but they do not change live qualification status.

源码审计未使用真人账户，因此七个平台的真人登录/同步状态均为 `NOT_RUN`。桥接器和 fixture 自动测试只能证明命令与导入行为，不能改变真人验收状态。
