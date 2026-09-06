[English](goal.md) | **中文**

# 目标：把 MediaCrawler 原生登录会话认领到既有订阅主链

执行 0073 关闭执行 0072 已交付的认证原生 MediaCrawler 控制台与 media-sync 既有账户级订阅流水线之间最小的一条接缝。锁定上游 `/crawler/` 控制台成为二维码和 Cookie 登录的主要入口。操作者在其中完成登录后，显式把该平台已静止浏览器 profile 的快照认领给一个已有 media-sync Account。只有非交互式验证成功，才把 Account 发布为 `saved_session` / `authenticated`；随后继续使用既有 scheduler、JSONL 摄取、受控下载、归档、媒体库目录与 NFO 主链，不重写这些能力。WebUI 来源保留用于以后在原生界面续登，scheduler 只使用独立安装的 Account 快照。

本执行不再实现另一套登录、爬虫、下载器或发布流水线，也不声称七个平台已经通过真人登录或真实采集。认领边界复制并独立验证浏览器状态；文件存在、WebUI 成功字样或另一个平台曾经成功都不能推导出认证成功。

## 产品流程

1. 操作者为精确平台创建或选择一个已有 media-sync Account。
2. 账户页把登录操作引导到经认证的 `/crawler/` 控制台，不再把 media-sync 自定义二维码／Cookie 流程作为主入口。
3. 操作者在 `/crawler/` 中完成锁定上游原生二维码或 Cookie 登录。
4. 回到账户后，操作者显式请求认领该平台保存的 profile。
5. media-sync 在独占条件下取得已静止 WebUI profile 的快照，通过现有 saved-session 边界验证且禁止回退二维码，然后原子安装到所选 Account 的受管 profile 位置。
6. 只有验证成功，才原子发布 `login_method=saved_session` 和 `auth_status=authenticated`；随后该 Account 可供既有 Subscription scheduler 使用。
7. Subscription 沿用已经建立的历史到增量流程，即使不连接 Emby 或 Jellyfin，也会写出媒体库目录与 NFO。

## 职责与数据边界

| 关注点 | 0073 后的负责人 | 边界 |
| --- | --- | --- |
| 交互式二维码／Cookie 登录及浏览器可见采集控制 | 锁定 MediaCrawler WebUI | 经认证的 `/crawler/`；不开放第二个公共 listener |
| 已保存 profile 认领及 Account 认证状态 | media-sync | 显式、同平台、通过操作者认证及 CSRF 防护的动作 |
| 定时作者采集与归一化 | 既有 media-sync scheduler／MediaCrawler runner | 账户级 profile；既有 Subscription 策略与确认继续作为权威 |
| 媒体获取、归档及 NFO 发布 | 既有 media-sync pipeline | 暂时保留已证明的补齐能力；本执行不增加竞争路径 |
| Emby/Jellyfin 服务器刷新 | 可选集成 | 永远不是生成兼容目录和 NFO 的前置条件 |

根据仓库当前证据，锁定上游原生媒体下载只在所需范围的一部分较为完备：小红书、抖音和 B 站的部分形状；它尚未覆盖七平台及全部混合媒体形状。因此 0073 明确保留定时交付所用的既有 media-sync 摄取／下载／归档／NFO 流水线。交互式 `/crawler/` 产物不会被静默摄取或重复下载。若要以已完成上游产物替换更多兜底下载能力，必须在后续独立执行中提供证据。

## 验收标准

1. **原生控制台成为登录主入口** —— 账户页引导操作者前往 `/crawler/` 执行二维码或 Cookie 登录，并清楚地引导其返回执行显式认领；旧自定义登录控件不再作为正常路径展示。既有 saved-session 探针或 scheduler 仍依赖的兼容代码可以保留在内部，但不得作为并行产品流程宣传。
2. **认领必须显式且平台一致** —— 请求标识已有 Account 和平台，经过操作者认证与 CSRF 防护，并要求 Account 平台与所选 WebUI profile 精确一致。来源和目标路径都由服务端派生；客户端不得传入文件系统路径、Cookie、凭据或浏览器状态。
3. **运行 profile 绝不共享** —— WebUI 保留由操作者控制的来源 profile，每个 Account 获得独立且经过验证的快照。首次认领和以后刷新都必须是受 Account 认证 revision 约束的显式操作；scheduler 不读取活动 WebUI 目录，Account 之间也不共享 profile。
4. **只有静止状态可以跨边界** —— 上游 crawler／登录进程仍在运行，或所选 Account 的 scheduler／profile 锁被占用时，拒绝认领。复制快照时持有 WebUI runtime gate，替换／发布时持有 Account 锁，禁止并发复制或替换 Chromium 状态。
5. **文件系统处理受限且可恢复** —— 只接受位于 `webui-profiles/<platform>_user_data_dir` 的预期非空目录；拒绝路径穿越，并阻止符号链接／reparse 逃逸或不支持的条目跨越边界。暂存和替换只能发生在配置的 MediaCrawler runtime 根下。复制、验证或发布失败时保留 WebUI 来源，在安全可行的情况下恢复 Account 的旧 profile，保持 Account 认证记录不变，并产生固定、安全的失败分类。
6. **仅有文件绝不能授予认证** —— 使用固定锁定 checkout／解释器和现有非交互 saved-session 探针验证候选 profile，并封死二维码回退。缺失、过期、含糊或格式异常的结果都是失败；不得把目录存在、上游 UI 状态或其他平台成功会话当作证据。
7. **Account 发布原子且受 fencing 保护** —— 验证后必须重新检查 Account 身份、平台、认证 revision 及锁所有权，才可提交 `saved_session` / `authenticated`。按照既有不变量清除不兼容凭据引用，不保留客户端提供的 profile 路径，并且只返回有界认领证据；不得返回 Cookie 值、本地 profile 内容或敏感上游输出。
8. **已处理失败不得破坏任一侧** —— 启动前取消、探针超时/失败、Account revision 过期和发布冲突必须留下准确、可重试的结果。验证失败不得认证 Account，丢失 fence 后的迟到结果不得发布，来源保持可用，部分目标目录不得被 scheduler 选用。复制或替换期间服务/进程被强杀的恢复仍是本批次明确未验证的风险。
9. **复用既有交付主链** —— 认领后，Account 必须解析到 creator lookup、定时采集、detail refresh 和媒体下载已经使用的同一账户级 profile 路径。不得新增第二个 Subscription dispatcher、内容身份体系、下载器、归档布局或 NFO writer。
10. **文件系统输出就是产品结果** —— 有效 Subscription 即使没有配置 Emby/Jellyfin provider，也可采集历史、继续定时增量检查，并在配置的媒体库根下发布确定性兼容目录／NFO。服务器刷新和播放验证仍是可选后续证据。
11. **资格表述必须准确** —— 确定性测试覆盖路由／认证／CSRF、来源缺失／为空、WebUI 与 Account 忙碌、探针失败、revision 过期、成功验证／发布、旧 profile 恢复，以及认领后 scheduler 的精确 profile 路径。这些测试不赋予真人二维码／Cookie 登录、平台请求、CDN 字节或七平台行为资格；各真人行在逐项实际观察并记录前继续为 `NOT_RUN`。

## 明确不在本执行范围

- 在锁定 MediaCrawler WebUI 之外重新实现或修复各平台登录流程。
- 在没有真人证据时声称七平台登录、作者采集、原生媒体完整性、风控规避、CDN 获取或媒体服务器播放已经通过。
- 摄取任意交互式 `/crawler/` 输出、完整导入上游日志，或替换既有定时下载／归档／NFO 流水线。
- 在 Account 之间共享一个浏览器 profile、接受任意 profile 路径，或通过 API、日志、支持包暴露 Cookie／profile 内容。
- 除证明认领后的 Account 已进入当前 scheduler 路径外，重新设计 Subscription 历史边界、周期、退避或风控策略。

## 完成证据

只有双语进展与验证记录写明精确实现 revision、认领／UI 专项测试、相关 scheduler 与 pipeline 回归、完整仓库门禁、源码／制品一致性，以及所有真正执行过的部署检查，0073 才算完成。若未执行真人部署，则 `/crawler/` 二维码／Cookie 登录和 Account 认领只能记为本地已实现、真人 `NOT_RUN`，文档必须明确说明。
