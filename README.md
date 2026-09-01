# media-sync

`media-sync` is a local-first author subscription and media archiving service. It is being designed around the platform coverage of [MediaCrawler](https://github.com/NanmiCoder/MediaCrawler) and the media-library workflow of [bili-sync-up](https://github.com/NeeYoonc/bili-sync-up).

`media-sync` 是一个本地优先的作者订阅与媒体归档服务。项目目标是覆盖 MediaCrawler 所支持的平台登录与创作者内容抓取，并将图文、视频和元数据整理为 Emby/Jellyfin 可识别的媒体库结构。

## Current status / 当前状态

The local function-first path is implemented through execution 0017 implementation commit `2f8dbaa`, following plan commit `9d19e7e`. In addition to explicit QR/session recovery and the foreground `scheduler supervise` chain, five frozen platform shapes now reach qualified offline media output: execution 0013's Bilibili logical-first-page single-progressive video, execution 0014's Kuaishou ordinary single video plus optional cover, execution 0015's ordinary numeric-ID Douyin single video plus optional cover with empty image/music fields, execution 0016's ordinary-original Weibo static IMAGE/GALLERY, and execution 0017's ordinary `type="normal"` XHS static IMAGE/GALLERY.

Execution 0017 follows the selected Asset's exact `AssetRefreshSource → Subscription → Account` provenance. With no explicit note override, it resolves only that Subscription's `policy.mediacrawler.creator_input.secret_ref`, bounds creator lookup by `subscription.max_items` and watchdog limits, and selects one unique matching content ID and exact IMAGE Asset from the returned records. `xhs_detail_reference_ref` remains a higher-priority single-note compatibility override. Detail and creator authority are mutually exclusive and are revalidated at the refresh context, parent request and deserialized child frame: exact XHS host/path and trusted note/author ID, with exactly one non-empty `xsec_token` and `xsec_source`. The offline composition proves default-profile mock HTTP, image validation, immutable SHA-256 archives and idempotent Emby/Jellyfin poster/backdrop/gallery/NFO/source output; the default profile adds no Cookie, Authorization, Referer or Origin. XHS verified-archive repair also preflights the same exact authority before quarantine or durable generation reset. XHS authority and signed media queries remain ephemeral: durable SQLite raw removes `xsec_token`/`xsec_source` and query-strips `note_url`, `image_list` and `video_url`; archive metadata, Emby output and completed attempt roots retain no signed authority. Automated XHS video, live photo, animation and mixed-media qualification are not claimed. No coverage run is claimed. Real login, creator/feed/detail requests, CDN transfer, platform bytes and Emby/Jellyfin server validation all remain `NOT_RUN`. This is not seven-platform complete download, an auto-restarting daemon, Windows Service/systemd unit, forced synchronous-thread cancellation or cross-host HA. Exact verification is recorded in [`docs/executions/0017-xhs-creator-authority/verification.md`](docs/executions/0017-xhs-creator-authority/verification.md).

本地功能优先链路已实现到执行 0017 实现提交 `2f8dbaa`，其计划提交为 `9d19e7e`。除显式 QR/会话回收及前台 `scheduler supervise` 全链外，五个冻结的平台形状现已产生通过验收的离线媒体输出：执行 0013 的 Bilibili 逻辑首 P 单 progressive 视频、执行 0014 的快手普通单视频与可选封面、执行 0015 的普通 numeric-ID 抖音单视频与可选封面（图片与音乐字段为空）、执行 0016 的普通原创微博静态 IMAGE/GALLERY，以及执行 0017 的普通 `type="normal"` 小红书静态 IMAGE/GALLERY。

执行 0017 遵循所选 Asset 的精确 `AssetRefreshSource → Subscription → Account` 来源链。没有显式 note 覆盖时，只解析该 Subscription 的 `policy.mediacrawler.creator_input.secret_ref`，以 `subscription.max_items` 与 watchdog 上限约束作者查找，并从返回记录中选出唯一匹配的 content ID 与精确 IMAGE Asset；`xhs_detail_reference_ref` 继续作为优先级更高的单 note 兼容覆盖。detail 与 creator 权限严格互斥，并在 refresh context、父 request 和反序列化 child frame 三层重复验证：要求精确的小红书 host/path、可信 note/author ID，以及唯一非空的 `xsec_token` 与 `xsec_source`。离线组合证明 DEFAULT profile mock HTTP、图片校验、不可变 SHA-256 归档及幂等 Emby/Jellyfin poster/backdrop/gallery/NFO/source 输出；默认 profile 不添加 Cookie、Authorization、Referer 或 Origin。小红书已验证归档修复也会在隔离或持久 generation 重置前预检同一精确权限。小红书权限与签名媒体 query 始终是瞬态数据：持久 SQLite raw 会移除 `xsec_token`/`xsec_source`，并清除 `note_url`、`image_list`、`video_url` 的 query；归档元数据、Emby 输出与已完成 attempt root 不保留签名权限。不宣称已验收小红书自动视频、实况照片、动图或混合媒体，也不宣称运行过覆盖率。真人登录、creator/feed/detail 请求、CDN 传输、真实平台字节及 Emby/Jellyfin 服务器验收全部保持 `NOT_RUN`。这不代表七平台完整下载，也不是自动重启 daemon、Windows Service/systemd 服务，不提供同步线程强停或跨主机 HA。准确验证记录位于 [`docs/executions/0017-xhs-creator-authority/verification.md`](docs/executions/0017-xhs-creator-authority/verification.md)。

- Implemented offline / 已实现离线：the five frozen shapes above, including automatic XHS creator-authority lookup for ordinary static IMAGE/GALLERY through archive and Emby filesystem publication / 上述五个冻结形状，包括小红书普通静态 IMAGE/GALLERY 的自动作者权限查找、归档与 Emby 文件系统发布。
- Still pending or unclaimed / 仍待实现或未验收：other platform/media shapes across the larger seven-platform goal, including automated XHS video/live-photo/animation/mixed media, Weibo video/retweets/effective `page_info`/animation, stronger creator pagination and expiry recovery, and live platform/CDN/real-byte/media-server qualification / 七平台大目标中的其他平台与媒体形状，包括小红书自动视频/实况照片/动图/混合媒体、微博视频/转发/有效 `page_info`/动图、更强的作者分页与权限过期恢复，以及真人平台/CDN/真实字节/媒体服务器验收。

## Foundation quickstart / 基线快速开始

The commands below are network-free and use the deterministic Fake adapter. They do not log in to a real platform or prove live platform compatibility.

以下命令无需网络并使用确定性 Fake 适配器；它们不会登录真实平台，也不能作为线上平台兼容性证明。

```powershell
uv sync --all-groups --locked
uv run media-sync db init
uv run media-sync account add --platform bili --display-name local-demo --login-method cookie --json
uv run media-sync account list --json
```

Use the account UUID returned above to create and run the fixture subscription:

使用上一步返回的账户 UUID 创建并运行测试订阅：

```powershell
uv run media-sync subscription add --account-id <ACCOUNT_UUID> --platform bili --creator-remote-id creator-001 --display-name "Fixture Creator" --max-items 30 --json
uv run media-sync subscription list --json
uv run media-sync scheduler tick --json
uv run media-sync scheduler run --max-jobs 1 --scan-limit 100 --json
uv run media-sync pipeline run --max-jobs 1 --scan-limit 100 --heartbeat-interval-seconds 20 --json
uv run media-sync scheduler job list --subscription-id <SUBSCRIPTION_UUID> --json
```

`sync run` remains available for an explicit one-off Fake synchronization. Scheduler controls also include `subscription pause|resume|run-now`, `scheduler job resume|cancel`, and `scheduler lane list|set|reset`. A successful scheduler Job only enqueues `pipeline.subscription`; it does not download or export inline. With the bounded commands, `pipeline run` must still be invoked separately. Execution 0012 also provides an explicit foreground loop that advances the complete local chain and waits when idle:

`sync run` 仍可用于显式的一次性 Fake 同步。调度控制还包括 `subscription pause|resume|run-now`、`scheduler job resume|cancel` 与 `scheduler lane list|set|reset`。成功的 scheduler Job 只 enqueue `pipeline.subscription`，不会内联下载或导出；使用有界命令时仍须另行调用 `pipeline run`。执行 0012 还提供一个显式前台循环，可推进完整本地链路并在空闲时等待：

```powershell
uv run media-sync scheduler supervise --idle-interval-seconds 1 --json
```

The first Ctrl+C/SIGTERM stops new ticks and claims, cancels and joins active subscription work, and drains one already-active thread-backed pipeline attempt under heartbeat. A repeated signal force-exits and leaves durable leases/fencing to recovery. This command is a single-host foreground supervisor, not an installed or auto-restarting service. / 第一次 Ctrl+C/SIGTERM 会停止新的 tick 与 claim，取消并 join 进行中的订阅工作，并在 heartbeat 下等待一项已经 active 的线程型 pipeline 尝试。重复信号会强制退出，由持久租约/fencing 负责恢复。该命令是单主机前台监督器，不是已安装或自动重启的服务。

The pipeline heartbeat renews exact Job/worker/token ownership and prevents a stale coordinator from finalizing over a successor. It does not provide forced cancellation: the production handler is synchronous and runs through `asyncio.to_thread`. The resident supervisor therefore shields and drains an already-started pipeline attempt—even under repeated task cancellation—instead of claiming that the underlying thread stopped. Forced synchronous-thread termination and multi-worker HA remain follow-up work.

Pipeline heartbeat 会续租精确 Job/worker/token，并阻止旧协调器覆盖后继收尾；它不提供强制取消。生产 handler 为同步函数并通过 `asyncio.to_thread` 运行，因此常驻监督器会 shield 并等待已经启动的一项 pipeline 尝试，即使 task 被重复取消也不会冒充底层线程已经停止。同步线程强制终止与多 worker HA 仍属于后续工作。

## Interactive QR login quickstart / 交互式 QR 登录快速开始

This flow can open a headed MediaCrawler browser and access a real platform account. Use only an account you are authorized to access, review the pinned MediaCrawler non-commercial learning license, and configure the pinned checkout/Python runtime first. The current automated evidence is offline only: no real QR row has been qualified. / 此流程可能打开 MediaCrawler 有头浏览器并访问真人平台账户。只能使用你有权访问的账户，先审阅锁定版 MediaCrawler 的非商业学习许可证，并配置锁定 checkout/Python runtime。当前自动化证据仅为离线证据：尚无真人 QR 行完成验收。

Create one QR account without a credential reference, then run the blocking login with both per-invocation gates. Scan the QR code in the visible upstream browser; QR bytes and tokens are not printed or stored by media-sync. / 先创建一个不带 credential 引用的 QR 账户，再同时提供两个逐次调用 gate 运行阻塞式登录。请在可见的上游浏览器中扫码；media-sync 不打印也不保存二维码字节或 token。

```powershell
uv run media-sync db init
uv run media-sync account add --platform bili --adapter mediacrawler --display-name bili-qr --login-method qr --json
uv run media-sync account login --account-id <ACCOUNT_UUID> --enable-mediacrawler --accept-mediacrawler-license --json
uv run media-sync account login-status --account-id <ACCOUNT_UUID> --json
```

A successful result atomically changes the account to `saved_session`. An expired saved-session account may use the same explicit command again: start atomically moves it to `qr/authenticating`, success restores `saved_session/authenticated`, and timeout/cancellation/failure leaves a retryable QR state. If that account already has a `qr_required`/`waiting_auth` scheduler Job, inspect its redaction-safe ID and resume that exact Job explicitly; login does not silently run or replace it. The later scheduler worker remains a separate, default-off invocation. / 成功结果会把账户原子切换为 `saved_session`。已过期的 saved-session 账户可再次使用同一显式命令：启动时原子切到 `qr/authenticating`，成功后恢复为 `saved_session/authenticated`，超时/取消/失败则留在可重试 QR 状态。如果该账户已有 `qr_required`/`waiting_auth` 调度 Job，请先查看其脱敏 ID，再显式恢复该精确 Job；登录不会静默运行或替换它。后续 scheduler worker 仍是独立且默认关闭的调用。

```powershell
uv run media-sync scheduler job list --subscription-id <SUBSCRIPTION_UUID> --json
uv run media-sync scheduler job resume --job-id <WAITING_JOB_UUID> --json
uv run media-sync scheduler run --max-jobs 1 --scan-limit 100 --enable-mediacrawler --accept-mediacrawler-license --json
```

Background saved-session reuse is forced headless and cannot fall back to QR. A missing derived profile or a probe that reaches the blocked QR fallback fails closed as `auth_expired`; ordinary bridge configuration faults remain `configuration_invalid`. Upstream `pong() == false` can also include network ambiguity, so `auth_expired` is a conservative action state, not a precise remote-cause diagnosis. Run the explicit login command again rather than expecting a scheduler worker to open a challenge. The login child now keeps START/CANCEL/EOF parent control and a post-result guardian: hard parent death terminates the owned child/browser tree before its inherited account lock becomes reusable. Any abandoned durable `waiting_user` state is recovered only after its exact `expires_at` deadline, while holding that same account lock and passing repository CAS; lock availability alone never authorizes early recovery. / 后台 saved-session 复用会被强制为无头模式，不能回退到二维码。派生 profile 缺失或探测进入被阻止的 QR 回退时会以 `auth_expired` 关闭失败；普通 bridge 配置错误继续映射为 `configuration_invalid`。上游 `pong() == false` 也可能包含网络异常歧义，因此 `auth_expired` 是保守动作状态，不是精确远端原因诊断。应再次运行显式登录命令，不能期待 scheduler worker 打开交互挑战。登录 child 现在持续保留 START/CANCEL/EOF 父进程控制与结果 guardian：父进程被硬杀后，所属 child/浏览器树会先退出，继承的账户锁才可复用。遗留的持久 `waiting_user` 状态只会在精确 `expires_at` 截止时间后、持有同一账户锁并通过仓储 CAS 时回收；仅凭锁可获取绝不允许提前回收。

Focused offline commands, exact execution 0012 results and the seven-platform live `NOT_RUN` matrix are recorded in [`docs/executions/0012-login-recovery-resident-supervisor/verification.md`](docs/executions/0012-login-recovery-resident-supervisor/verification.md). / 离线专项命令、执行 0012 的准确结果及七平台真人 `NOT_RUN` 矩阵记录在 [`docs/executions/0012-login-recovery-resident-supervisor/verification.md`](docs/executions/0012-login-recovery-resident-supervisor/verification.md)。

For an already configured pinned MediaCrawler checkout/runtime and an authorized due subscription, the external handler remains default-off and requires both per-run switches below. This command can launch the crawler; it is not part of the network-free Fake quickstart.

对于已经配置好锁定版 MediaCrawler checkout/runtime、且存在经授权到期订阅的环境，外部 handler 仍默认关闭，并且每次运行都必须同时提供下列两个开关。此命令可能启动爬虫，不属于上方无需网络的 Fake 快速开始。

```powershell
uv run media-sync scheduler run --max-jobs 1 --scan-limit 100 --enable-mediacrawler --accept-mediacrawler-license --json
uv run media-sync pipeline run --max-jobs 1 --scan-limit 100 --lease-seconds 3600 --heartbeat-interval-seconds 20 --enable-mediacrawler --accept-mediacrawler-license --json
uv run media-sync scheduler supervise --enable-mediacrawler --accept-mediacrawler-license --json
```

The two MediaCrawler switches are required independently on each bounded command. For XHS, the default execution 0017 path resolves the exact selected Subscription's opaque `creator_input.secret_ref`; its secret must be an HTTPS `/user/profile/<trusted-author-id>` URL with unique non-empty `xsec_token` and `xsec_source`. An operator may instead provide `--xhs-detail-reference-ref env:MEDIA_SYNC_XHS_NOTE_DETAIL_URL`; this higher-priority compatibility override must resolve to the exact target note URL with the same closed `xsec` requirements. Neither resolved authority is persisted.

两个 MediaCrawler 开关必须在每个有界命令上分别提供。对小红书，执行 0017 的默认路径会解析精确选中 Subscription 的不透明 `creator_input.secret_ref`；其密钥必须是 HTTPS `/user/profile/<可信作者 ID>` URL，并包含唯一非空的 `xsec_token` 与 `xsec_source`。操作员也可改为提供 `--xhs-detail-reference-ref env:MEDIA_SYNC_XHS_NOTE_DETAIL_URL`；这个优先级更高的兼容覆盖必须解析为精确目标 note URL，并满足同一封闭 `xsec` 要求。两类已解析权限都不会持久化。

Only opaque secret references such as `env:MEDIA_SYNC_BILI_COOKIE` or `keyring:media-sync/bili-demo` may be passed to `--credential-ref`; raw Cookie/password values are rejected. Run the complete offline test suite with `uv run pytest`; the complete quality gate also includes lint, format, strict types, build/package, documentation, pinned-upstream, patch and secret-sentinel checks. See [`docs/executions/0012-login-recovery-resident-supervisor/verification.md`](docs/executions/0012-login-recovery-resident-supervisor/verification.md) for the current supervisor closeout commands and results.

OS-keyring lookup is optional; install it with `uv sync --extra keyring` before using a `keyring:` reference. Confined `file:<relative-path>` references resolve below `MEDIA_SYNC_SECRET_FILE_DIR` (or the private state-directory default).

`--credential-ref` 只接受 `env:MEDIA_SYNC_BILI_COOKIE`、`keyring:media-sync/bili-demo` 等不透明引用；原始 Cookie/密码会被拒绝。`uv run pytest` 会运行完整离线测试套件；完整质量门禁还包括 lint、格式、严格类型、构建/打包、文档、锁定上游、补丁与密钥哨兵检查。当前监督器的准确收尾命令及实际结果位于 [`docs/executions/0012-login-recovery-resident-supervisor/verification.md`](docs/executions/0012-login-recovery-resident-supervisor/verification.md)。

系统钥匙串是可选能力；使用 `keyring:` 引用前请运行 `uv sync --extra keyring`。`file:<relative-path>` 只会在 `MEDIA_SYNC_SECRET_FILE_DIR` 下解析；未配置时使用私有状态目录中的默认位置。

## Media download and Emby quickstart / 媒体下载与 Emby 快速开始

First run the deterministic offline contract. It uses temporary SQLite/filesystem roots, a mock transport, and generated media bytes; it does not contact a platform/CDN or start Emby/Jellyfin.

先运行确定性的离线契约。它只使用临时 SQLite/文件系统目录、mock transport 和生成的媒体字节，不访问平台/CDN，也不会启动 Emby/Jellyfin。

```powershell
uv run pytest tests/integration/test_offline_media_pipeline.py tests/contract/test_emby_export_contract.py
uv run pytest -q tests/integration/test_bilibili_playable_pipeline.py
uv run pytest -q tests/integration/test_kuaishou_playable_pipeline.py
uv run pytest -q tests/integration/test_douyin_playable_pipeline.py
uv run pytest -q tests/integration/test_weibo_image_pipeline.py
uv run pytest -q tests/integration/test_xhs_creator_authority_pipeline.py
```

The second through sixth commands are the execution 0013 Bilibili, execution 0014 Kuaishou, execution 0015 Douyin, execution 0016 Weibo and execution 0017 XHS compositions. They use synthetic metadata, fake detail results, mock transport bytes and controlled media validation; they prove local pipeline contracts, not a real creator/feed/detail request, CDN, platform bytes, FFmpeg against platform video or a running Emby/Jellyfin server. / 第二至第六条命令分别是执行 0013 的 Bilibili、执行 0014 的快手、执行 0015 的抖音、执行 0016 的微博及执行 0017 的小红书组合测试。它们使用合成元数据、fake detail 结果、mock transport 字节及受控媒体校验；只证明本地流水线契约，不证明真实 creator/feed/detail 请求、CDN、平台字节、针对平台视频的 FFmpeg 或运行中的 Emby/Jellyfin 服务器。

For a local database that already contains discovered assets, list redaction-safe IDs, download one eligible asset, and publish one complete author snapshot with:

对于已经含有发现资产的本地数据库，可先列出脱敏后的稳定 ID，再下载一个符合条件的资产，并发布一个完整作者快照：

```powershell
uv run media-sync doctor
uv run media-sync asset list --json
uv run media-sync asset list --status discovered --json
uv run media-sync asset download --asset-id <ASSET_UUID> --json
uv run media-sync emby export --author-id <AUTHOR_UUID> --json
```

`asset list` deliberately omits locators, source URLs, archive paths, and raw metadata. `asset download` performs network access for an eligible query-free `direct` locator and writes verified blobs below `MEDIA_SYNC_ARCHIVE_DIR` (default `archive/`). Video and audio are accepted only after mandatory structural probing by `ffprobe`; install FFmpeg/ffprobe and confirm `media-sync doctor` reports it ready. `emby export` is local filesystem work and writes layout v1 below `MEDIA_SYNC_EXPORT_DIR` (default `exports/`), but it requires a complete exportable author snapshot.

`asset list` 会主动隐藏 locator、来源 URL、归档路径和原始元数据。`asset download` 会为符合条件、无 query 的 `direct` locator 发起网络请求，并把已验证文件写到 `MEDIA_SYNC_ARCHIVE_DIR`（默认 `archive/`）下。视频和音频必须通过 `ffprobe` 的结构探测才能接收；请安装 FFmpeg/ffprobe，并确认 `media-sync doctor` 报告 ready。`emby export` 只操作本地文件系统，把 layout v1 写到 `MEDIA_SYNC_EXPORT_DIR`（默认 `exports/`）下，但要求该作者快照完整且可导出。

MediaCrawler-discovered assets persist only the stable, secret-free `adapter_refresh` locator. Execution 0009 resolves it lazily from the exact current Subscription source when `asset download` or the pipeline receives both MediaCrawler enable/license switches; manual selection also accepts `--subscription-id`. For XHS, execution 0017 uses the selected Subscription creator reference by default and retains the explicit one-note reference as an override. Before any child Job or Asset lifecycle write, XHS authority preflight binds the exact source and authority; the pipeline's existing capability gate separately validates the pinned lock/checkout/Python runtime plus an actually launchable mandatory `ffprobe` when required. Invalid authority fails with zero child lifecycle side effects. If an already-verified XHS archive is missing or invalid, authority preflight also runs before quarantine or durable repair reset. The signed result is used in memory by the safe downloader and is never written back to SQLite.

MediaCrawler 发现的资产只持久化稳定且不含密钥的 `adapter_refresh` locator。执行 0009 会在 `asset download` 或 pipeline 同时收到 MediaCrawler 启用/许可证开关时，从精确当前 Subscription 来源惰性解析；手工选择另接受 `--subscription-id`。对小红书，执行 0017 默认使用所选 Subscription 的作者引用，并保留显式单 note 引用作为覆盖。在任何 child Job 或 Asset 生命周期写入前，小红书权限 preflight 会绑定精确来源与权限；pipeline 既有 capability gate 会另行验证锁定 lock/checkout/Python runtime，以及需要时实际可启动的强制 `ffprobe`。无效权限以零 child 生命周期副作用失败。若已验证的小红书归档缺失或无效，也会在隔离或持久修复重置前运行权限 preflight。签名结果只在安全下载器内存中使用，绝不写回 SQLite。

Offline refresh shapes are limited to XHS image/video, Douyin image/video/audio/cover, Kuaishou ordinary single video plus optional cover under an exact-one-play-URL boundary, Bilibili cover and logical-first-page single-progressive video, plus ordinary-original numeric-ID Weibo static IMAGE/GALLERY. Composed media-library qualification is narrower: the three frozen video slices, the Weibo two-image static gallery and the XHS ordinary `type="normal"` two-image static gallery with automatic creator-authority fallback. Automatic XHS video/live-photo/animation/mixed media is not qualified; the earlier explicit-note XHS video refresh behavior is not an automatic-video claim. Tieba and Zhihu currently have no normalized downloadable Asset. Weibo video, GIF/animation, long-image-specific handling and effective `page_info`; Douyin galleries, associated-music semantics and multiple media URLs; Kuaishou galleries/multiple URLs; and Bilibili DASH/mux, FLV remux, multiple segments/pages, subtitles, danmaku, backup failover and bangumi/paid/live media are not implemented or not qualified. Query-only Douyin/Kuaishou rotation, same-aid Bilibili replay and same-ID Weibo replay cannot automatically detect byte replacement under the same stable identity. No real login, creator/feed/detail request, signed CDN/proxy download or Emby/Jellyfin rescan/playback has run for any platform; all such rows remain `NOT_RUN`.

离线刷新形状仅限小红书 image/video、抖音 image/video/audio/cover、“精确一个播放 URL”边界下的快手普通单视频与可选封面、Bilibili cover 与逻辑首 P 单 progressive 视频，以及普通原创 numeric-ID 微博静态 IMAGE/GALLERY。组合媒体库验收范围更窄：上述三个冻结视频切片、微博普通原创双图静态 gallery，以及使用自动作者权限回退的小红书普通 `type="normal"` 双图静态 gallery。小红书自动视频/实况照片/动图/混合媒体尚未验收；此前显式 note 小红书视频刷新行为不代表自动视频能力。贴吧与知乎当前没有已归一化的可下载 Asset。微博视频、GIF/动图、长图专用处理与有效 `page_info`，抖音图集、关联音乐语义与多媒体 URL，快手图集/多 URL，以及 Bilibili DASH/mux、FLV remux、多段/多 P、字幕、弹幕、备用地址故障切换及番剧/付费/直播媒体尚未实现或未验收。仅 query 变化的抖音/快手轮换、同 aid Bilibili 重放及同 ID 微博重放都无法在稳定身份不变时自动检测字节替换。任何平台都尚未运行真人登录、creator/feed/detail 请求、签名 CDN/代理下载或 Emby/Jellyfin 重扫/播放；这些行全部保持 `NOT_RUN`。

Secret-sink handling recognizes explicit composite credential keys such as `api_key`, `access_key`, provider-prefixed and camelCase/kebab-case variants, while preserving ordinary fields such as `key`, `public_key` and `key_id`. Credential-marker URL paths such as `/token/<value>/video.mp4`, including percent-encoded and double-encoded forms, are redacted in operator/database sinks and rejected as durable `direct` locators or source hints. Discovery therefore falls back to a stable `adapter_refresh` locator. The `0003` upgrade applies the same path rule while backfilling legacy assets: it clears an unsafe legacy `source_url` and does not copy the credential path into the replacement locator.

密钥落点处理会识别 `api_key`、`access_key`、带提供商前缀及 camelCase/kebab-case 变体等明确组合密钥键，同时保留 `key`、`public_key`、`key_id` 等普通字段。`/token/<value>/video.mp4` 等带凭据标记的 URL 路径（包括百分号编码及双重编码形式）会在运维/数据库落点被脱敏，且不得作为持久 `direct` locator 或 source hint；发现阶段因此回退为稳定的 `adapter_refresh` locator。`0003` 升级在回填 legacy 资产时也执行同一路径规则：清空不安全的 legacy `source_url`，且不把凭据路径复制到替换 locator 中。

Keep `MEDIA_SYNC_JOB_DIR` and `MEDIA_SYNC_ARCHIVE_DIR` stable for a durable asset generation. A download Job stores only a hash of those canonical roots; a request from a different I/O scope fails safely before reclaiming the job or consuming an attempt. A local per-asset OS lock is held from before database mutation through finalization. If archive publication succeeds before the final database commit, the generation-bound partial evidence permits exact recovery without another network request; partial cleanup happens only after verification succeeds.

同一持久资产 generation 应保持 `MEDIA_SYNC_JOB_DIR` 与 `MEDIA_SYNC_ARCHIVE_DIR` 稳定。下载 Job 只保存这些规范根目录的哈希；来自不同 I/O scope 的请求会在回收 job 或消耗 attempt 前安全失败。逐资产本地 OS 锁从数据库变更前一直持有到收尾。若归档发布先于最终数据库提交成功，绑定 generation 的 partial 证据可以在不再次请求网络的情况下精确恢复；partial 只在验证成功后清理。

Filesystem threat boundary for the 0.x line: the configured state, job, archive, staging and export roots—and their ancestors—must be dedicated, operator-controlled directories that are not writable by an untrusted same-permission process. The path guards reject escapes, links/reparse points/hardlinks present at operation time and detected leaf replacement, but path-based operations do not claim to survive an attacker swapping a parent directory between checks. Do not place these roots in a shared adversarial directory.

0.x 的文件系统威胁边界：配置的 state、job、archive、staging、export 根目录及其祖先必须是专用、由操作员控制且不允许不可信同权限进程写入的目录。路径 guard 会拒绝操作时已存在的逃逸、符号链接/reparse、硬链接及可检测的叶节点替换，但基于路径的操作不宣称能抵御攻击者在检查间隙替换父目录。请勿把这些根目录放在对抗性共享目录中。

Emby managed ownership comes from a durable database Job predecessor chain, not from `.media-sync-managed-v1.json` alone. The disk manifest remains a byte-checked description of the database-anchored predecessor. An unexpected or forged manifest is preserved and rejected; an empty author snapshot still receives a Job anchor, and a publish that committed before database finalization can be recovered only when the exact intended source, tree, manifest and managed bytes match.

Emby 受管所有权来自持久数据库 Job predecessor chain，而不是单独依赖 `.media-sync-managed-v1.json`。磁盘 manifest 只是数据库锚定 predecessor 的逐字节校验描述。意外或伪造 manifest 会被保留并拒绝；空作者快照仍会获得 Job 锚点；只有 intended source、tree、manifest 与全部受管字节精确匹配时，才能恢复“发布已提交但数据库尚未收尾”的任务。

Schema round trips deliberately clean generation-bound identities. Downgrading `0003` to `0002` first clears every `assets.download_job_id`, then removes all `asset_download` Jobs because `0002` cannot represent their generation. Succeeded Emby Jobs/records remain as the publication chain. Other non-succeeded Emby Jobs/records are removed as identity poison unless a Job carries a structurally valid closed publication intent; that Job and the records named by its intent are retained only for exact byte-validated recovery after re-upgrade.

Schema 往返会主动清理与 generation 绑定的身份。从 `0003` 降级到 `0002` 时，先清空所有 `assets.download_job_id`，再删除全部 `asset_download` Job，因为 `0002` 无法表达其 generation。已成功的 Emby Job/record 作为发布链保留；其他未成功的 Emby Job/record 作为可能的身份污染会被删除，除非 Job 携带结构严格有效的封闭发布 intent；该 Job 及 intent 点名的 records 只为重新升级后的精确逐字节校验恢复而保留。

## Scope / 范围

- Platforms / 平台: Xiaohongshu, Douyin, Kuaishou, Bilibili, Weibo, Tieba and Zhihu. / 小红书、抖音、快手、哔哩哔哩、微博、百度贴吧、知乎。
- Authentication / 登录: explicit double-gated QR command for initial QR accounts and expired saved-session reauthentication, opaque Cookie references, and background-only saved-session reuse; phone login is unsupported. Offline seven-identifier coverage does not imply live qualification. / 面向初始 QR 账户及已过期 saved-session 重认证的显式双 gate QR 命令、不透明 Cookie 引用与仅后台 saved-session 复用；手机号登录不受支持。离线七标识覆盖不代表真人验收。
- Subscription / 订阅：stores author identity, incremental watermarks and deduplication state. MediaCrawler accounts additionally persist closed policy v1: `schema_version`, optional `creator_input.secret_ref`, explicit `allow_full_history`, positive `request_delay_seconds` bounded at 300, and `headless`; license acknowledgement is separate, per-worker and default-off. Execution 0007 runs forward scheduled attempts through the opt-in handler. Execution 0010 atomically enqueues a downstream coordinator on sync success, but only an explicit bounded `pipeline run` performs download/export. The proven `CRAWLER_MAX_SLEEP_SEC` setting with `MAX_CONCURRENCY_NUM=1` is not a per-request HTTP-spacing guarantee. / 保存作者身份、增量水位与去重状态。MediaCrawler 账户还会持久化封闭 policy v1：`schema_version`、可选 `creator_input.secret_ref`、显式 `allow_full_history`、最大为 300 的正数 `request_delay_seconds`，以及 `headless`；许可证确认独立存在、逐 worker 提供且默认关闭。执行 0007 通过显式启用的 handler 运行 forward 定时 attempt。执行 0010 在 sync 成功时原子 enqueue 下游协调器，但只有显式有界 `pipeline run` 才执行下载/导出。已证明的 `CRAWLER_MAX_SLEEP_SEC` 配置与 `MAX_CONCURRENCY_NUM=1` 不代表逐 HTTP 请求间隔保证。
- Content / 内容: normalized posts, videos, images and related metadata. / 归一化图文、视频、图片及相关元数据。
- Media library / 媒体库: stable directories, media files, posters/covers and Emby/Jellyfin NFO. / 输出稳定目录、媒体文件、海报/封面和 Emby/Jellyfin NFO。

## Important license boundary / 重要许可证边界

MediaCrawler uses a custom non-commercial learning license. Its checkout is treated as an optional external runtime and is not vendored into this repository. See [`docs/decisions/0001-upstream-boundary.md`](docs/decisions/0001-upstream-boundary.md) before distributing or using this project commercially.

MediaCrawler 使用定制的“非商业学习使用许可证”。本仓库只把它视为可选外部运行时，不把其源码纳入版本历史。分发或商业使用前，请先阅读 [`docs/decisions/0001-upstream-boundary.md`](docs/decisions/0001-upstream-boundary.md)。
