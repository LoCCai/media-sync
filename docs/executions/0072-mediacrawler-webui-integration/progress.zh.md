[English](progress.md) | [**中文**](progress.zh.md)

# 推进结果

状态：第一批薄集成已在提交 `ea64938` 实现。专项检查、Python 完整 unit 套件、media-sync Web 完整套件 782 项、锁定上游真实 React 源码临时构建及生产依赖审计均通过。当前仍未取得部署资格：当前 Docker 镜像及在线部署未经验证，且仅构建期的开发依赖图仍有 8 项审计发现。

## 第一批已实现

- 增加独立的 MediaCrawler 部署级许可证确认：默认 false，只接受精确 `true`／`false`。操作者阅读锁定版本的非商业学习许可证并明确启用前，不导入或构造上游应用；所有已认证 `/crawler` HTTP 路径（包括 start）统一返回不缓存的 `503 license_acknowledgement_required`，既有 supervisor CLI 门禁继续独立生效。
- 许可证门启用后，在 media-sync SPA fallback 之前把锁定的 MediaCrawler FastAPI 应用挂载到 `/crawler`。页面与 HTTP API 复用既有操作者 session 鉴权；Cookie 鉴权的不安全请求继续要求 media-sync CSRF，并移除上游开发用 CORS 放行。WebSocket 只放行上游精确的日志与状态路径，并且必须同时具备有效浏览器 session、配置中精确匹配的 Host 与 Origin。
- 为锁定上游 React WebUI 增加独立 Docker 构建阶段。在临时副本内，精确安全补丁选择 Axios 1.18.0、follow-redirects 1.16.0 与 form-data 4.0.6，重新生成复制出来的 lock、执行干净安装，并要求生产依赖审计通过，之后才确定性适配 `/crawler/` base、API、下载、WebSocket、CSRF、favicon 与二维码面板。最新本地执行每一步均通过，TypeScript／Vite 共构建 1,836 个 module，并核对预期的带前缀资产与 bundle 接缝。只有生成的浏览器资产会复制到最终镜像阶段；锁定 checkout 及其 lockfile 保持原样，完整 Docker 阶段本身仍未执行。
- 以 media-sync adapter 替换上游 manager 对环境 `uv run` 的假设：先校验锁定 checkout 与已配置的专用 Python，再用该精确解释器和 checkout 启动 child。上游 `/api/env/check` 探针改为报告这个已验证 commit／解释器的确定性结果；运行时缺失或不匹配时只返回固定的 `mediacrawler_webui_unavailable` 与 `Cache-Control: no-store`，不回退到其他安装。
- 以逐代 run 独立的禁用 shell 受管进程替换上游启动／读取／停止接缝。POSIX child 使用新 session，Windows child 使用新进程组与 Job object。操作者停止、正常退出、启动失败及根应用关闭都会在释放私密资源前关闭精确进程树。Starlette 不传播 mount 应用 lifespan，因此根 lifespan 会显式等待该 callback。
- 对保留的上游控制台流做有界脱敏：每条展示消息最多 8 KiB，跨读取块的超长物理行整行丢弃，历史最多保留 500 条，实时队列最多 512 条，并同时脱敏已知 Cookie 值与通用凭据形状；公开 `current_config` 会清空 Cookie。二维码／状态／日志高频轮询继续要求认证且不缓存，但不写 request-finished 日志；start 仍精确记录一次。
- 将上游数据限制在彼此分离的受管根：采集数据／媒体使用 `webui-output`，持久浏览器登录状态使用 `webui-profiles`，Cookie 交接使用 `webui-private`。Cookie 上限为 64 KiB，不出现在操作系统父进程启动参数或公开配置中，而是经独占 `0600` 一次性文件传递；参数／启动失败、child 读取后、正常完成、停止／关闭时删除精确文件，启动时还会以窄范围 sweep 清理遗留交接文件。
- child 固定 checkout 工作目录、持久化登录状态、关闭 CDP 模式、把上游并发限制为一，并同时设置锁定拼写 `ENABLE_GET_MEIDAS=True` 与向前兼容拼写 `ENABLE_GET_MEDIAS=True`。`SAVE_DATA_PATH` 与持久 profile 模式均来自 media-sync 自有路径，而不是浏览器选择的任意根。其环境按仅浏览器 allowlist 重建，排除操作者／API secret；同时安装既有 media-sync policy，选择镜像内 Playwright bundled Chromium，而不是环境 browser channel。
- 为当前单例 crawler attempt 增加最小浏览器二维码 relay。既有上游 `show_qrcode` hook 只接受有界栅格输入，经重新编码 PNG 去除元数据，在 checkout 外原子写入，并在 child 退出时清理。认证 endpoint 只返回大小不超过 2 MiB、年龄不超过 180 秒的当前普通文件，设置 `no-store`、`nosniff` 及 SHA-256 摘要；补丁后的上游面板只在二维码登录运行期间轮询，并撤销被替换的浏览器 object URL。
- 增加控制台侧栏入口、登录返回路径与双语部署说明。受支持的操作者入口为 `/crawler/`，没有新增另一条未认证上游 listener。

## 有意未连接

- 本批没有把控制台输出接到持久 Subscription 派发、历史回填状态、定时增量、任务对账、完成产物摄取或确定性文件夹／NFO 发布。后续有界摄取批次真正实现并验证前，控制台产物仍只是上游交互输出。
- media-sync 不会把任意上游日志、浏览器 profile、命令文本或上游数据浏览器能看到的所有文件摄取为持久权威记录。
- MediaCrawler 继续负责交互式登录、采集控制、平台请求及上游媒体下载；media-sync 继续负责认证，并在后续批次负责调度、监视、防御式摄取及 Emby/Jellyfin 兼容文件夹／NFO。
- 执行 [0071](../0071-remaining-runner-output-diagnostics/progress.zh.md)只是在交付顺序中暂停，并未完成；其缺失的 runner 诊断覆盖及此前已丢弃输出不会因本集成得到修复或重新分类。
- Emby/Jellyfin 服务器连接继续为可选项。本批既不要求连接，也不证明真实服务器扫描或播放结果。

## 剩余工作与资格边界

- 保持生产依赖审计为零，并跟踪或显式接受 8 个仅构建期开发依赖发现（`6 high`、`2 low`、`0 moderate`、`0 critical`）：`@babel/core`、`browserslist`、`nanoid`、`picomatch`、`postcss`、`postcss-selector-parser`、`rollup`、`vite`。它们在编译期间存在，但对应 package 不会复制进最终运行镜像。未加固的上游原始基线最初报告 11 个包条目；其中 3 个生产链条目只在隔离构建副本中消除，没有修改锁定 checkout。
- 执行完整 Docker 构建／运行路径，再验证当前精确镜像、持久性和在线部署。当前 Python unit 完整套件以 `4633 passed, 3 skipped, 1 warning` 通过，media-sync Web 完整套件 782 项通过；已通过的独立上游 React 构建及旧镜像检查不能替代其余 Docker／部署行。
- 在声称自动归档流水线前，实现控制台输出 → Subscription／历史／定时增量／摄取／NFO 的持久接缝。
- 另行授权并逐个平台执行真人二维码／Cookie 登录、采集、下载及 CDN 检查。合成 relay 测试不能证明二维码可以真实扫描，也不能证明任一平台会接受登录。
- 若以后有真实 Emby/Jellyfin 服务，可单独验证服务器发现、扫描、刷新及播放；本地兼容目录与 NFO 不以此为前提。

实际执行的检查以及所有 `PASS`、`NOT_RUN` 和依赖风险行见[验证记录](verification.zh.md)。
