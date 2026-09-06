[English](plan.md) | **中文**

# 计划

## 1. 冻结转向与职责边界

- 把执行 0071 记录为暂停而非完成；保留已有证据与未解决发现，但在执行 0072 中停止扩大自定义 child 输出捕获。
- 盘点 `upstreams.lock.json` 所锁 commit 中的 MediaCrawler WebUI 应用、crawler API、WebSocket 路径、单例进程管理器、登录模式、采集模式、数据视图及媒体 store。
- 冻结职责分工：MediaCrawler 负责 WebUI／控制／登录／采集／下载；media-sync 负责认证壳、Subscription 调度、任务监视、完成产物摄取及 Emby/Jellyfin 文件夹／NFO。
- 不编辑锁定 checkout，也不在 media-sync 中重复实现其 UI、进程管理器、登录 handler、平台 crawler 或媒体 downloader。

## 2. 建立唯一固定的上游运行时

- 为经过校验的 checkout 及一个专用虚拟环境 Python 增加类型化配置。在开放集成前校验绝对路径、checkout 身份、锁定 commit、许可证确认及所需入口。
- 增加默认关闭、只接受精确 `true`／`false` token 的部署级许可证确认。未显式确认时不导入或构造上游应用；每个已认证 `/crawler` HTTP 路径（包括 `/crawler/api/crawler/start`）统一返回不缓存的 `503 license_acknowledgement_required`。常驻 supervisor 继续使用相互独立的显式 CLI 门禁。
- 通过 media-sync 自有 adapter 启动上游 API 与 crawler child，始终选择固定解释器和 checkout 工作目录。在集成接缝替换上游管理器对环境 `uv run` 的假设，但不修改上游文件。
- 为启动、关闭及 child 终止设置有界行为。checkout、解释器或已构建 WebUI 缺失／不匹配时返回固定不可用状态，绝不回退到其他安装。
- Starlette 不会传播已挂载 FastAPI 应用的 lifespan，因此在挂载应用 state 暴露一个 media-sync 自有异步关闭 callback，并在释放共享运行状态前由根 lifespan 显式等待它完成。
- 上游服务只存在于 media-sync 进程／网络私有边界；受支持入口是 `/crawler`，而不是第二个未认证 listener。

## 3. 挂载经认证的 `/crawler` 入口

- 在 `/crawler` 下路由锁定 WebUI、必需 API、静态资源及 WebSocket。通过外部 mount／proxy／base-path adapter 处理上游对根相对 `/api`、`/assets`、`/logos`、`/static` 的假设，不 fork 源码。
- 对初始页面及每个 HTTP/WebSocket 控制端点应用现有 media-sync 操作员认证与请求防护；在转发任何采集内容或命令前拒绝未认证访问。
- 在前缀后保留上游启动／停止／状态及 UI 行为。media-sync 可以转换健康／不可用状态，但不另造第二套 crawler 状态机。
- 本批路由不得把上游自由文本日志、命令字符串、Cookie 或浏览器状态复制进持久 media-sync 任务／日志记录。

## 4. 限制输出并启用上游媒体

- 为集成分配一个受管输出根，并在其下派生逐任务位置。拒绝穿越、symlink 逃逸、checkout 相对输出及浏览器请求提供的任意路径。
- 通过 media-sync 自有 bootstrap／adapter 传入上游 `SAVE_DATA_PATH` 支持的精确输出位置，同时保持锁定源树干净。
- 为 crawler child 显式设置锁定上游拼写错误的 `ENABLE_GET_MEIDAS=True`，由 MediaCrawler 执行其现有图片／视频下载。测试实际应用到 child 的配置；只有 UI 勾选或保存格式选择不能证明媒体下载已经启用。
- 任务输出、浏览器 profile 状态及 media-sync 媒体库输出使用彼此独立的根。crawler 完成不能授权读取其指定输出目录以外的位置。

## 5. 保持 media-sync 集成层轻薄

- 在 media-sync 保留持久 Subscription 调度，并把每次派发映射到一个受监视的上游任务／输出根。按照上游管理器真实的单进程容量串行化或拒绝启动，不能假装它支持并行工作。
- 以有界轮询／对账观察上游 start、running、stop 及 terminal 状态。监视只记录闭集本地状态，不把任意上游日志文字持久化为权限依据。
- 成功终态之后，只通过有界、防御式 parser 摄取指定根中的已识别完成产物。失败或部分运行必须可区分，不能发布为完整媒体。
- 把接受的产物送入现有确定性 Emby/Jellyfin 文件夹与 NFO 边界。即使没有可用媒体服务器连接，文件系统／NFO 发布仍须可用；不得把服务器凭据或成功 scan 作为前置条件。

## 6. 先交付第一批，再连接后续流程

- 第一批只实现：认证 `/crawler` 路由、上游前缀／静态资源／WebSocket 可达性、固定虚拟环境／checkout 选择、受管输出根注入、`ENABLE_GET_MEIDAS=True`、最小二维码 relay、有界生命周期及专项配置／路由／relay 测试。
- 使用假 ASGI／上游进程和临时根证明认证、转发、命令／运行时选择、路径限制及媒体开关应用；不打开浏览器，也不访问平台／CDN。
- 增加源码／合约断言，证明 checkout 保持未修改且 adapter 不选择环境 `uv`／Python；验证运行时不可用和 child 启动失败会产生固定安全结果。
- 在后续批次真正实现并测试这些接缝前，不得把 Subscription → 摄取 → NFO 端到端标为完成。

## 7. 交付最小二维码 relay，并准确记录资格

- 记录并测试当前限制：选择二维码会进入上游登录代码，但其原生显示路径调用 `PIL.Image.show()`，不会向浏览器 UI 提供二维码字节。
- 在 media-sync 自有 bootstrap 接缝只拦截上游 `show_qrcode`，保持上游登录状态机不变。校验并限制一张二维码图片，再把它原子写入 checkout 之外的 attempt 级临时位置。
- 增加绑定任务／attempt 的认证 endpoint，只返回当前二维码并设置 `Cache-Control: no-store`；缺失、过期或 attempt 不匹配时拒绝，并在替换、完成、过期、取消及关闭时删除精确临时文件。
- 在挂载的上游 React UI 中加入最小集成视图，让发起操作的用户看到 relay 图片；不增加并行登录表单，也不暴露公开／静态二维码 URL。
- 使用合成 PNG 字节测试 hook、边界、认证、no-store 响应、attempt 隔离、UI 状态及清理。这些测试只能证明 relay 实现，不能证明真人平台扫码。
- 运行 Python/Web 路由与配置专项、格式／类型／lint 及 `git diff --check`；只在命令实际执行后记录精确结果。
- 真人二维码、Cookie、七平台采集／下载、CDN 字节及 Emby/Jellyfin 服务器扫描／播放在另行授权并观察前继续为 `NOT_RUN`。mock WebUI 测试通过只属于实现证据。
