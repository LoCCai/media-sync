[English](plan.md) | **中文**

# 计划

## 1. 冻结 runner 盘点与信任边界

- 追踪 `CookieLoginProcessRunner`、`MediaCrawlerCreatorProfileProcessRunner`、`MediaCrawlerDetailProcessRunner`、`creator_avatar_worker.py`、`SubprocessProbeRunner`、`FFprobeMediaProbe` 与 `FFmpegStreamCopyMuxer` 的精确进程及 stream 拓扑，包括 mux／remux／concat 调用点和 asset-download 应用边界。
- 编辑前对每条 stream 分类：Cookie／资料 guardian 与 worker 的 stdout 使用有界四字节长度 JSON 帧；detail child stdout 是有界 ASCII JSON 结果帧；头像 stdout 是原始 PNG；ffprobe／ffmpeg stdout 是解析器输入。它们都不是自由文本诊断输入。
- 记录进程内 HTTP、DNS 与文件系统流没有子进程输出，只能获得闭集生命周期事件，绝不记录请求／响应正文或媒体字节。另行记录 guardian stderr 当前是无人读取的 pipe，不能用来中继或保留 worker 诊断。
- checkout、prefetch、浏览器版本及 readiness probe 保持范围外，除非同时证明其存在证据缺口及精确可信任务身份。是否捕获由盘点决定，不能只因存在子进程就接入。

## 2. 泛化协议安全捕获

- 复用 `capture_current_process_output`、`ProcessOutputCapture`、`log_environment_for_child` 及现有受管 `LogStore`；保留当前分类器、独立事件校验、字节／行数边界与固定丢弃计数。
- 为 stdout 必须由协议或解析器独占的 helper 增加最小单诊断流模式。它可以排空获准的 stderr，但不能让现有双流 reader 接管 stdout、改变 stdout 消费方式或扩大自由文本事件字段。
- 捕获继续由经过校验的 child 环境获得父进程授权，并在 import 或调用上游代码前移除控制 envelope。授权缺失、伪造或畸形时，直接调用保持静默。
- 写入任意结果帧或 PNG 前，恢复 Python 与原生文件描述符、关闭捕获写端、排空读端并发出摘要。捕获设置、reader、分类器、store 或 flush 失败仍是尽力而为，不能替换主结果，也不能改变期限、取消与完整进程树关闭。

## 3. 接入 Cookie 校验与创作者资料

- 在持锁 Cookie worker 中，只围绕 `_verify_remote` 进入捕获；请求 Cookie 仅以内存已知秘密传给脱敏器。`_emit` 写入 worker 结果前恢复描述符。不得捕获或序列化 Cookie 请求、响应 JSON／HTML／正文、浏览器／会话状态或远程身份对象。
- 在持锁创作者资料 worker 中，只围绕选定 adapter 的平台查询捕获。Cookie 值、含秘密的创作者引用、返回昵称、头像 URL、平台标识与任意元数据都按非日志数据处理，即使异常文本包含这些内容也一样。
- 保持 guardian 与 worker 的四字节长度 framing 字节精确。不能把日志重定向到 guardian stderr：该 pipe 目前无人排空，写入可能死锁，也不能作为安全证据路径。
- 保持既有远程证明语义、资料合并规则、超时／取消行为及持久化。日志成功不能认证账户或授权资料更新；日志失败不能把业务成功或失败改成其他结果。

## 4. 接入 detail 与媒体地址解析

- 在 `detail_runner.py --child` 中，只围绕解析精确 detail 及媒体 locator 的 `_execute_child` 捕获。退出捕获并恢复 stdout 后，才能由 `_emit_child_frame` 写入有界协议结果。
- 将账户 Cookie、秘密内容引用及所有已解析或备用媒体地址标记为已知／高风险材料。绝不保留原始 detail JSONL、base64 结果内容、响应 JSON／HTML／正文、创作者／内容字段、header、locator query 或签名 URL。
- 只传播已校验的本地账户／订阅／平台身份，以及权威 lazy-refresh 调用方持有的精确 asset 身份。detail 请求本身不能为任意上下文授权，重复字段也不能覆盖本地事实。
- 保持精确 detail 权限检查、一次刷新选择、超时及清理行为。诊断不能使 locator 变有效、授权不同 content ID、触发重试或改变返回的刷新 disposition。

## 5. 接入下载、probe、头像与 remux helper

- 在 `_PerAssetDownloadRunner`／`AssetDownloadService` 中，只有权威 `_begin` 转换返回精确 asset-download Job 与 asset 后才绑定诊断。只在能够解释既有结果时，为进程内解析、HTTP／DNS、流传输、校验及发布增加闭集 phase／outcome；绝不包含 URL、header、地址、文件名、响应数据或媒体字节。
- 对使用 `SubprocessProbeRunner` 的 `FFprobeMediaProbe` 以及 `FFmpegStreamCopyMuxer` 的所有 probe／mux／remux／concat 路径，保持有界 stdout 只供当前解析器使用，仅捕获有界且策略允许的 stderr。不得记录 argv、concat 脚本、输入／输出路径、签名 locator 或 ffprobe JSON。
- 在 `creator_avatar_worker.py` 中，只用当前进程捕获包围远程取回与图片解码，并在写入 PNG 前完全恢复 stdout。stdin 接收的 URL 及抓取／解码字节绝不能成为诊断；捕获失败必须保持既有头像 fallback／保留旧值行为。
- 通用 downloader 的 HTTP／DNS 工作及只有二进制／协议输出的 helper 不接入自由文本捕获。不存在可独立确认安全的人类诊断流时，闭集生命周期证据已经足够。

## 6. 保持精确关联与日志中心行为

- 仅为盘点证明必需的规范 UUID 键扩展 `encode_process_output_context`／`decode_process_output_context`。保持版本化闭集对象，拒绝重复／额外／非规范值；任一已提供字段非法时丢弃整个 envelope。
- Cookie／资料事件绑定可信 Operation／账户／平台；detail 绑定可信账户／订阅／平台及可用 asset；下载／probe／remux／头像事件绑定调用应用拥有的精确 Job／asset／账户／创作者事实。本地权威事实优先，绝不伪造 login-session、Job、Run、asset 或 creator 身份。
- 复用闭集 `process_output`、`process_output_summary` 与 `process_output_dropped` schema，只增加区分这些边界所必需的闭集 module／phase／action／stream 值。不得增加任意 metadata 或原始输出字段。
- 仅在新闭集值需要安全标签或筛选时扩展已鉴权 API 与中文日志中心。保持分页、编码、Operation 链接及防御性未知值处理；不新增原始分片下载、文件系统浏览或未经校验的服务端文字渲染。

## 7. 执行对抗及跨进程验证

- 单测单流 adapter、描述符恢复、边界与 sink 失败。注入原始 Cookie／Authorization、`Set-Cookie`、QR／base64、签名 URL、上游 JSON/JSONL、HTML/DOM、请求／响应正文、创作者元数据、媒体字节及 Windows/POSIX 私有路径；每个哨兵在已校验事件与受管分片原始字节中都必须不存在。
- 执行真实 guardian／worker 及 detail／头像 child。断言四字节帧、detail 结果字节、ffprobe 解析器输出与头像 PNG 字节精确；捕获在协议写入前关闭；guardian stderr 不接收诊断；stdout／stderr 洪泛、非法编码、超长行、超时、取消与提前退出均不死锁。
- 证明 Cookie、资料、detail 与下载路径的精确及缺失上下文，包括额外／重复／畸形／混合 envelope 值、直接调用及并发 attempt。证明日志 store 拒绝或 state directory 不可用时，每项业务结果、持久转换及重试判断保持不变。
- 运行 output-capture、Cookie／资料／detail、下载／probe／mux／头像、API 与 Web 专项测试；再执行受影响的 Ruff／format、严格 mypy、Web type／lint／build、完整 Python 分组及 `git diff --check`。稍后准确记录命令、数量、skip 与失败；不能预先宣称通过或真人资格。

## 8. 收尾且不夸大资格

- 只在实现后新增 `progress(.zh).md`，描述精确接入及排除边界；新增 `verification(.zh).md` 记录命令、数量、失败、修复及明确 `NOT_RUN` 行；两个语言版本保持语义对齐。
- 实现与收尾历史分开；只有根工作区通过约定门禁且用户授权发布时才发布。规划不授权部署、生产检查、重启 supervisor 或重试平台操作。
- 明确说明进程诊断无法重建旧版已丢弃输出，也不会修复扫码。部署后，只有另行授权的受控操作才能产生用于选择真实平台修复的证据。
- 独立继续七平台采集／下载／归档／播放目标。不得把离线诊断测试转换为真人 Cookie、资料、detail、CDN、下载、Emby/Jellyfin 或扫码 PASS 行。
