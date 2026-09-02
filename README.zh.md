[English](README.md) | **中文**

# media-sync

`media-sync` 是一个本地优先的作者订阅与媒体归档服务。项目目标是覆盖 MediaCrawler 所支持的平台登录与创作者内容抓取，并将图文、视频和元数据整理为 Emby/Jellyfin 可识别的媒体库结构。

## 当前状态

本地功能优先链路已实现到执行 0027 实现提交 `7f99aa4`。除显式 QR/会话回收及前台 `scheduler supervise` 全链外，覆盖全部七个平台的十二个冻结媒体形状现已有专项离线证据：执行 0013 的 Bilibili 逻辑首 P 单 progressive 视频、执行 0014 的快手普通单视频与可选封面、执行 0015 的普通 numeric-ID 抖音单视频与可选封面（图片与音乐字段为空）、执行 0016 的普通原创微博静态 IMAGE/GALLERY、执行 0017 的普通 `type="normal"` 小红书静态 IMAGE/GALLERY、执行 0018 的普通 `type="video"` 小红书单个可播放视频与零或一张静态 IMAGE 封面、执行 0019 的知乎作者普通回答精确一张静态 IMAGE、执行 0020–0022 的贴吧兼容单图/双图/3–64 图首楼形状、执行 0023 的 Bilibili 兼容 2–64 分 P progressive 投稿，以及执行 0024 的 Bilibili 兼容单 P/2–64 分 P DASH 音视频生命周期。执行 0025–0027 加固或衍生既有 Bilibili DASH/progressive 形状，不会把冻结媒体形状数误增为十三个。

执行 0027 把严格 Bilibili 详情协议升级到 v7，并且只允许合法、显式的顶层播放 `format` 授予 FLV 权限；缺失/`None` 与 MP4 保持兼容普通 progressive，未知、混合与畸形格式关闭失败。Repr-safe 类型化 target 通过有界单 P/多分 P 私有桥接携带一个主地址与最多八个备用地址，随后在持久化前消失。下载器复用严格候选/续传/restart 与一次全鉴权刷新语义，要求源结构化探测为 FLV 视频，再运行固定有界的 `ffmpeg -c copy`，映射首个视频流与可选首个音频流。只有精确探测为 MP4 的成品可归档与导出；转封装/成品探测失败会保留已验证 generation 源，但绝不发布原始 FLV。生成的本地 H.264+AAC FLV 贯穿“主地址失败 → 备用 → 生产 ffprobe/ffmpeg → SHA-256 MP4 → Emby MP4/NFO/source”，并实现零工作重放。专项回归通过 `394 passed in 59.12s`；完整套件通过 `1848 passed, 1 skipped in 347.72s`；全部质量/构建/文档/上游/diff 门通过。实现 `7f99aa4` 已推送并核对。真人登录、登录态 API/CDN、真实 Bilibili FLV 字节及 Emby/Jellyfin 服务器验收保持 `NOT_RUN`。准确证据位于 [`docs/executions/0027-bilibili-single-segment-flv-remux/verification.zh.md`](docs/executions/0027-bilibili-single-segment-flv-remux/verification.zh.md)。

- 已实现并有专项离线证据：上述十二个冻结形状，包括兼容 Bilibili 单 P/2–64 分 P progressive 与 DASH 发布、有序主/备用故障切换及显式单段 FLV→MP4 转封装、知乎/贴吧有界发现及精确 canonical 刷新/归档/Emby 输出。
- 仍待实现或未验收：Bilibili 多 `durl` 分段与 FLV 拼接/转码、CDN 排序/竞速/跨运行缓存、混合/非鉴权穷尽后的新详情刷新、字幕/弹幕与超过 64 个分 P；贴吧超过 64 张的 gallery 与混合/富内容/回复媒体；知乎多图/文章/zvideo；七平台大目标中的其他形状；以及全部真人平台/CDN/真实字节/媒体服务器行。

## 基线快速开始

以下命令无需网络并使用确定性 Fake 适配器；它们不会登录真实平台，也不能作为线上平台兼容性证明。

```powershell
uv sync --all-groups --locked
uv run media-sync db init
uv run media-sync account add --platform bili --display-name local-demo --login-method cookie --json
uv run media-sync account list --json
```

使用上一步返回的账户 UUID 创建并运行测试订阅：

```powershell
uv run media-sync subscription add --account-id <ACCOUNT_UUID> --platform bili --creator-remote-id creator-001 --display-name "Fixture Creator" --max-items 30 --json
uv run media-sync subscription list --json
uv run media-sync scheduler tick --json
uv run media-sync scheduler run --max-jobs 1 --scan-limit 100 --json
uv run media-sync pipeline run --max-jobs 1 --scan-limit 100 --heartbeat-interval-seconds 20 --json
uv run media-sync scheduler job list --subscription-id <SUBSCRIPTION_UUID> --json
```

`sync run` 仍可用于显式的一次性 Fake 同步。调度控制还包括 `subscription pause|resume|run-now`、`scheduler job resume|cancel` 与 `scheduler lane list|set|reset`。成功的 scheduler Job 只 enqueue `pipeline.subscription`，不会内联下载或导出；使用有界命令时仍须另行调用 `pipeline run`。执行 0012 还提供一个显式前台循环，可推进完整本地链路并在空闲时等待：

```powershell
uv run media-sync scheduler supervise --idle-interval-seconds 1 --json
```

第一次 Ctrl+C/SIGTERM 会停止新的 tick 与 claim，取消并 join 进行中的订阅工作，并在 heartbeat 下等待一项已经 active 的线程型 pipeline 尝试。重复信号会强制退出，由持久租约/fencing 负责恢复。该命令是单主机前台监督器，不是已安装或自动重启的服务。

Pipeline heartbeat 会续租精确 Job/worker/token，并阻止旧协调器覆盖后继收尾；它不提供强制取消。生产 handler 为同步函数并通过 `asyncio.to_thread` 运行，因此常驻监督器会 shield 并等待已经启动的一项 pipeline 尝试，即使 task 被重复取消也不会冒充底层线程已经停止。同步线程强制终止与多 worker HA 仍属于后续工作。

## 交互式 QR 登录快速开始

此流程可能打开 MediaCrawler 有头浏览器并访问真人平台账户。只能使用你有权访问的账户，先审阅锁定版 MediaCrawler 的非商业学习许可证，并配置锁定 checkout/Python runtime。当前自动化证据仅为离线证据：尚无真人 QR 行完成验收。

先创建一个不带 credential 引用的 QR 账户，再同时提供两个逐次调用 gate 运行阻塞式登录。请在可见的上游浏览器中扫码；media-sync 不打印也不保存二维码字节或 token。

```powershell
uv run media-sync db init
uv run media-sync account add --platform bili --adapter mediacrawler --display-name bili-qr --login-method qr --json
uv run media-sync account login --account-id <ACCOUNT_UUID> --enable-mediacrawler --accept-mediacrawler-license --json
uv run media-sync account login-status --account-id <ACCOUNT_UUID> --json
```

成功结果会把账户原子切换为 `saved_session`。已过期的 saved-session 账户可再次使用同一显式命令：启动时原子切到 `qr/authenticating`，成功后恢复为 `saved_session/authenticated`，超时/取消/失败则留在可重试 QR 状态。如果该账户已有 `qr_required`/`waiting_auth` 调度 Job，请先查看其脱敏 ID，再显式恢复该精确 Job；登录不会静默运行或替换它。后续 scheduler worker 仍是独立且默认关闭的调用。

```powershell
uv run media-sync scheduler job list --subscription-id <SUBSCRIPTION_UUID> --json
uv run media-sync scheduler job resume --job-id <WAITING_JOB_UUID> --json
uv run media-sync scheduler run --max-jobs 1 --scan-limit 100 --enable-mediacrawler --accept-mediacrawler-license --json
```

后台 saved-session 复用会被强制为无头模式，不能回退到二维码。派生 profile 缺失或探测进入被阻止的 QR 回退时会以 `auth_expired` 关闭失败；普通 bridge 配置错误继续映射为 `configuration_invalid`。上游 `pong() == false` 也可能包含网络异常歧义，因此 `auth_expired` 是保守动作状态，不是精确远端原因诊断。应再次运行显式登录命令，不能期待 scheduler worker 打开交互挑战。登录 child 现在持续保留 START/CANCEL/EOF 父进程控制与结果 guardian：父进程被硬杀后，所属 child/浏览器树会先退出，继承的账户锁才可复用。遗留的持久 `waiting_user` 状态只会在精确 `expires_at` 截止时间后、持有同一账户锁并通过仓储 CAS 时回收；仅凭锁可获取绝不允许提前回收。

离线专项命令、执行 0012 的准确结果及七平台真人 `NOT_RUN` 矩阵记录在 [`docs/executions/0012-login-recovery-resident-supervisor/verification.zh.md`](docs/executions/0012-login-recovery-resident-supervisor/verification.zh.md)。

对于已经配置好锁定版 MediaCrawler checkout/runtime、且存在经授权到期订阅的环境，外部 handler 仍默认关闭，并且每次运行都必须同时提供下列两个开关。此命令可能启动爬虫，不属于上方无需网络的 Fake 快速开始。

```powershell
uv run media-sync scheduler run --max-jobs 1 --scan-limit 100 --enable-mediacrawler --accept-mediacrawler-license --json
uv run media-sync pipeline run --max-jobs 1 --scan-limit 100 --lease-seconds 3600 --heartbeat-interval-seconds 20 --enable-mediacrawler --accept-mediacrawler-license --json
uv run media-sync scheduler supervise --enable-mediacrawler --accept-mediacrawler-license --json
```

两个 MediaCrawler 开关必须在每个有界命令上分别提供。对小红书，执行 0017 的默认路径会解析精确选中 Subscription 的不透明 `creator_input.secret_ref`；其密钥必须是 HTTPS `/user/profile/<可信作者 ID>` URL，并包含唯一非空的 `xsec_token` 与 `xsec_source`。操作员也可改为提供 `--xhs-detail-reference-ref env:MEDIA_SYNC_XHS_NOTE_DETAIL_URL`；这个优先级更高的兼容覆盖必须解析为精确目标 note URL，并满足同一封闭 `xsec` 要求。两类已解析权限都不会持久化。

`--credential-ref` 只接受 `env:MEDIA_SYNC_BILI_COOKIE`、`keyring:media-sync/bili-demo` 等不透明引用；原始 Cookie/密码会被拒绝。`uv run pytest` 会运行完整离线测试套件；完整质量门禁还包括 lint、格式、严格类型、构建/打包、文档、锁定上游、补丁与密钥哨兵检查。当前监督器的准确收尾命令及实际结果位于 [`docs/executions/0012-login-recovery-resident-supervisor/verification.zh.md`](docs/executions/0012-login-recovery-resident-supervisor/verification.zh.md)。

系统钥匙串是可选能力；使用 `keyring:` 引用前请运行 `uv sync --extra keyring`。`file:<relative-path>` 只会在 `MEDIA_SYNC_SECRET_FILE_DIR` 下解析；未配置时使用私有状态目录中的默认位置。

## 媒体下载与 Emby 快速开始

先运行确定性的离线契约。它只使用临时 SQLite/文件系统目录、mock transport 和生成的媒体字节，不访问平台/CDN，也不会启动 Emby/Jellyfin。

```powershell
uv run pytest tests/integration/test_offline_media_pipeline.py tests/contract/test_emby_export_contract.py
uv run pytest -q tests/integration/test_bilibili_playable_pipeline.py
uv run pytest -q tests/integration/test_bilibili_multipart_progressive_pipeline.py
uv run pytest -q tests/integration/test_bilibili_dash_pipeline.py
uv run pytest -q tests/integration/test_kuaishou_playable_pipeline.py
uv run pytest -q tests/integration/test_douyin_playable_pipeline.py
uv run pytest -q tests/integration/test_weibo_image_pipeline.py
uv run pytest -q tests/integration/test_xhs_creator_authority_pipeline.py
uv run pytest -q tests/integration/test_xhs_playable_video_pipeline.py
uv run pytest -q tests/integration/test_zhihu_answer_image_pipeline.py
uv run pytest -q tests/integration/test_tieba_first_floor_image_pipeline.py
```

第二至第十一条命令覆盖执行 0013/0027 的 Bilibili 单 P progressive 与显式 FLV 转封装测试、执行 0023 的多分 P progressive、执行 0024 的 DASH、执行 0014 的快手、执行 0015 的抖音、执行 0016 的微博、执行 0017 的小红书静态内容、执行 0018 的小红书可播放视频、执行 0019 的知乎回答图片及执行 0020–0022 的贴吧首楼图片组合。它们使用合成元数据、fake detail 结果、mock transport 字节及受控或生产媒体门。执行 0026 让两个 progressive 组合中的每个主地址以 `503` 失败并到达有序备用。执行 0027 另生成本地真实 H.264+AAC FLV，以生产 `ffprobe` 验源、通过有界 `ffmpeg -c copy` 转封装、验证双流 MP4，只归档/导出 MP4，并证明零工作重放。执行 0024–0025 同样验收生产 DASH 合并及独立组件备用选择。执行 0018 另验证内嵌真实 H.264 MP4，执行 0019–0022 则校验有界 JPEG/PNG/WebP 结构并拒绝已测试动图容器。贴吧命令覆盖兼容单图、精确双图与 v3 三图 ARTICLE 行，另有单元/合约覆盖 64/65 边界。这些命令只证明本地流水线契约，不证明真实 creator/feed/detail 请求、CDN/平台字节或运行中的 Emby/Jellyfin 服务器，也不宣称保留任何真实平台来源夹具。

对于已经含有发现资产的本地数据库，可先列出脱敏后的稳定 ID，再下载一个符合条件的资产，并发布一个完整作者快照：

```powershell
uv run media-sync doctor
uv run media-sync asset list --json
uv run media-sync asset list --status discovered --json
uv run media-sync asset download --asset-id <ASSET_UUID> --json
uv run media-sync emby export --author-id <AUTHOR_UUID> --json
```

`asset list` 会主动隐藏 locator、来源 URL、归档路径和原始元数据。`asset download` 会为符合条件、无 query 的 `direct` locator 发起网络请求，并把已验证文件写到 `MEDIA_SYNC_ARCHIVE_DIR`（默认 `archive/`）下。视频和音频必须通过 `ffprobe` 的结构探测才能接收；Bilibili DASH 与显式单段 FLV 衍生物还要求可启动的 `ffmpeg` 执行有界 stream-copy 合并/转封装。请安装两个 FFmpeg 可执行程序，并确认 `media-sync doctor` 报告 `ffmpeg` 与 `ffprobe` 均 ready。`emby export` 只操作本地文件系统，把 layout v1 写到 `MEDIA_SYNC_EXPORT_DIR`（默认 `exports/`）下，但要求该作者快照完整且可导出。

MediaCrawler 发现的资产只持久化稳定且不含密钥的 `adapter_refresh` locator。执行 0009 会在 `asset download` 或 pipeline 同时收到 MediaCrawler 启用/许可证开关时，从精确当前 Subscription 来源惰性解析；手工选择另接受 `--subscription-id`。对小红书，执行 0017–0018 默认使用所选 Subscription 的作者引用，并保留显式单 note 引用作为覆盖。对知乎与贴吧，执行 0019–0022 不接受操作员 detail 覆盖，而是从选中持久 ARTICLE/content 行派生精确、非密钥的 canonical 回答/主题 URL；贴吧刷新会在解析任一 position 前绑定完整的 1–64 项有序兄弟图片 hint 元组。执行 0023–0027 同样把每个 Bilibili VIDEO 刷新绑定到完整 1–64 项持久兄弟元组；详情协议 v7 只发送目标 CID，并可返回普通 progressive 主/备用 locator、类型化瞬态 FLV 衍生 target 或类型化瞬态 DASH target。在任何 child Job 或 Asset 生命周期写入前，平台权限 preflight 会绑定精确来源与权限；pipeline capability gate 会另行验证锁定 lock/checkout/Python runtime、可启动的 `ffprobe`，并在所选 Bilibili target 需要合并/转封装时验证 `ffmpeg`。无效权限或能力均以零 child 生命周期副作用失败。刷新的签名媒体结果只在内存中使用，绝不写回 SQLite。

离线刷新形状仅限小红书 image/video、抖音 image/video/audio/cover、“精确一个播放 URL”边界下的快手普通单视频与可选封面、Bilibili cover 加兼容单 P 或 2–64 分 P 且每 P 单 progressive 或 DASH 的普通投稿（包括显式单段 FLV→MP4 转封装）、普通原创 numeric-ID 微博静态 IMAGE/GALLERY、知乎普通回答精确一张静态 IMAGE，以及兼容单图、精确双图或 3–64 张静态图的贴吧普通主题首楼。组合媒体库证据仍为十二个冻结形状。Execution 0027 在实现 `7f99aa4` 中通过 394 项专项回归、1848 项完整套件（另有一项 Windows 不适用跳过）及全部质量/构建/文档/上游/审计门；它为既有 progressive 身份增加衍生处理，而不是新增形状。贴吧超过 64 张的 gallery 与混合/富内容/回复媒体，知乎多图/文章/zvideo，小红书扩展媒体，微博视频/GIF/长图/有效 `page_info`，抖音/快手扩展媒体，以及 Bilibili 多 `durl` 分段/FLV 拼接或转码/超过 64 个分 P/字幕/弹幕/CDN 排序、竞速或跨运行缓存/混合穷尽详情刷新/番剧/付费/直播媒体继续待实现。文档所列 query 轮换场景在稳定身份不变时仍无法自动发现同 origin/path 字节替换。任何平台都尚未运行真人登录、creator/feed/detail 请求、签名 CDN/代理下载或 Emby/Jellyfin 重扫/播放；这些行全部保持 `NOT_RUN`。

密钥落点处理会识别 `api_key`、`access_key`、带提供商前缀及 camelCase/kebab-case 变体等明确组合密钥键，同时保留 `key`、`public_key`、`key_id` 等普通字段。`/token/<value>/video.mp4` 等带凭据标记的 URL 路径（包括百分号编码及双重编码形式）会在运维/数据库落点被脱敏，且不得作为持久 `direct` locator 或 source hint；发现阶段因此回退为稳定的 `adapter_refresh` locator。`0003` 升级在回填 legacy 资产时也执行同一路径规则：清空不安全的 legacy `source_url`，且不把凭据路径复制到替换 locator 中。

同一持久资产 generation 应保持 `MEDIA_SYNC_JOB_DIR` 与 `MEDIA_SYNC_ARCHIVE_DIR` 稳定。下载 Job 只保存这些规范根目录的哈希；来自不同 I/O scope 的请求会在回收 job 或消耗 attempt 前安全失败。逐资产本地 OS 锁从数据库变更前一直持有到收尾。若归档发布先于最终数据库提交成功，绑定 generation 的 partial 证据可以在不再次请求网络的情况下精确恢复；partial 只在验证成功后清理。

0.x 的文件系统威胁边界：配置的 state、job、archive、staging、export 根目录及其祖先必须是专用、由操作员控制且不允许不可信同权限进程写入的目录。路径 guard 会拒绝操作时已存在的逃逸、符号链接/reparse、硬链接及可检测的叶节点替换，但基于路径的操作不宣称能抵御攻击者在检查间隙替换父目录。请勿把这些根目录放在对抗性共享目录中。

Emby 受管所有权来自持久数据库 Job predecessor chain，而不是单独依赖 `.media-sync-managed-v1.json`。磁盘 manifest 只是数据库锚定 predecessor 的逐字节校验描述。意外或伪造 manifest 会被保留并拒绝；空作者快照仍会获得 Job 锚点；只有 intended source、tree、manifest 与全部受管字节精确匹配时，才能恢复“发布已提交但数据库尚未收尾”的任务。

Schema 往返会主动清理与 generation 绑定的身份。从 `0003` 降级到 `0002` 时，先清空所有 `assets.download_job_id`，再删除全部 `asset_download` Job，因为 `0002` 无法表达其 generation。已成功的 Emby Job/record 作为发布链保留；其他未成功的 Emby Job/record 作为可能的身份污染会被删除，除非 Job 携带结构严格有效的封闭发布 intent；该 Job 及 intent 点名的 records 只为重新升级后的精确逐字节校验恢复而保留。

## 范围

- 平台：小红书、抖音、快手、哔哩哔哩、微博、百度贴吧、知乎。
- 登录：面向初始 QR 账户及已过期 saved-session 重认证的显式双 gate QR 命令、不透明 Cookie 引用与仅后台 saved-session 复用；手机号登录不受支持。离线七标识覆盖不代表真人验收。
- 订阅：保存作者身份、增量水位与去重状态。MediaCrawler 账户还会持久化封闭 policy v1：`schema_version`、可选 `creator_input.secret_ref`、显式 `allow_full_history`、最大为 300 的正数 `request_delay_seconds`，以及 `headless`；许可证确认独立存在、逐 worker 提供且默认关闭。`allow_full_history` 只继续用于已审计的无界 creator 路径；执行 0019 的知乎 shim 会强制 Subscription `max_items`，执行 0020 则把贴吧已有最大值检查加固为精确成功工作量。执行 0007 通过显式启用的 handler 运行 forward 定时 attempt。执行 0010 在 sync 成功时原子 enqueue 下游协调器，但只有显式有界 `pipeline run` 才执行下载/导出。已证明的 `CRAWLER_MAX_SLEEP_SEC` 配置与 `MAX_CONCURRENCY_NUM=1` 不代表逐 HTTP 请求间隔保证。
- 内容：归一化图文、视频、图片及相关元数据。
- 媒体库：输出稳定目录、媒体文件、海报/封面和 Emby/Jellyfin NFO。

## 重要许可证边界

MediaCrawler 使用定制的“非商业学习使用许可证”。本仓库只把它视为可选外部运行时，不把其源码纳入版本历史。分发或商业使用前，请先阅读 [`docs/decisions/0001-upstream-boundary.zh.md`](docs/decisions/0001-upstream-boundary.zh.md)。
