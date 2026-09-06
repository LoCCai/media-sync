[English](plan.md) | **中文**

# 计划

## 1. 冻结证据与安全边界

- 追踪通用 MediaCrawler runner 与扫码登录 runner 的全部 stdout/stderr 路径，包括父进程协议读取及子进程 import。
- 保留执行 0068 的结构化生命周期事件，只在缺少证据的位置增加进程输出；不能声称旧版本已经丢弃的输出可以恢复。
- 将“全部日志”定义为安全可分类诊断输出的完整覆盖；拒绝原始秘密、二维码材料、用户内容和任意第三方闲杂输出。

## 2. 实现一个有界捕获原语

- 在现有 `LogStore` 上新增可复用进程输出捕获模块，使用 API、CLI 与 supervisor 共用的 `state_dir/logs`。
- 通过私有 pipe 捕获子进程内部 fd 1/2，增量解码并逐行分类。当外层公开通道承载协议时，合并上游 stdout/stderr；只有来源可信时才保留原 stream。必须命中明确 level/traceback/exception 形状，关键词本身不能授权持久化；JSON/JSONL、HTML/DOM 或疑似创作者正文对象按策略过滤。
- 强制每轮字节数、行数及单行长度限制。即使没有保留自由文本，也要发出摘要与固定丢弃原因。
- 拒绝相对路径/根日志目录及路径身份变化，不跟随 symlink，也不扩大现有 store 的删除权限。

## 3. 保持协议与授权边界

- 通用采集的 stdout 继续作为严格最终状态/结果流。只有受信父进程环境才能授权捕获，并在 import 上游代码前移除控制值。
- 扫码登录复制原 stderr 供版本化 `EventWriter` 使用，stdout 继续承载结果帧，只有上游子进程 fd 输出进入私有捕获 pipe。
- 在成功、异常、取消和清理路径确定性恢复描述符。捕获失败不得改变 runner 结果、遮蔽主错误或授予登录成功。

## 4. 传播精确可信上下文

- 在启动异步登录读取工作前，从已校验 observability context 快照父 `operation_id` 与 `correlation_id`。
- 只通过专用环境变量序列化允许且规范的 UUID 键；child 在 import 上游前 pop 并严格校验完整值。任意字段非法时，整体丢弃传播上下文。
- 校验后合并作者 manifest 身份及登录 account/platform 身份。同名项以 manifest 事实为准；绝不伪造 login-session UUID。

## 5. 扩展闭集事件 schema

- 增加三种进程输出事件码、闭集 stream 字段及固定 drop/error 值。
- 有界 `message` 只能出现在 `process_output`；事件构造处再执行一次策略检查，调用者不能绕过捕获层脱敏。
- 时间、writer 身份、sequence 及持久/排队/丢失语义继续由现有 `LogStore` 管理。

## 6. 接入 API 与日志中心 UI

- 扩展 TypeScript 日志解析器，支持新 code、stream、message 与丢弃原因；保留同文件中并行的精确订阅交付修改。
- 对已保留输出展示可读的安全 message，对过滤/丢弃行展示明确摘要；未知值应防御性处理，不能直接渲染未经校验的服务端文字。
- 保持既有认证、筛选、有界分页、Operation 链接及诊断下载；不新增文件系统浏览或原始分片下载接口。

## 7. 验证与对抗复核

- 单测安全诊断分类以及敌对 Cookie object、`Set-Cookie`、Authorization、storage-state、二维码/base64、签名 URL、Windows/POSIX 路径，并覆盖非法 UTF-8、超长行、洪泛限制、sink 拒绝及目录安全。哨兵值在已校验事件及受管分片原始字节中都必须不存在。
- 用真实子进程做契约测试：通用结果 framing 保持精确；扫码结果/事件 framing 仍可解析；诊断输出进入受管分片；秘密和私有路径不泄漏。
- 测试合法 Operation 关联、无上下文、畸形/混合/恶意环境值，以及没有父授权时直接调用 runner。
- 运行日志 store/output 专项、MediaCrawler bridge/login 契约、API/前端测试、Ruff/format、mypy、受影响的 Web type/lint/build 及 `git diff --check`。稍后在 `verification(.zh).md` 准确记录结果，不能预先宣称通过。

## 8. 收尾与继续

- `progress(.zh).md` 只写已实现事实及明确待接 runner；`verification(.zh).md` 记录命令、数量、失败、修复及 `NOT_RUN` 行。
- 计划与实现/收尾分别使用中英双语提交；只有根工作区通过约定门禁且用户要求发布时才推送。
- 不自动部署、恢复 supervisor、重试登录或开始生产历史回填。部署后应先受控重试一个失败平台，通过新日志中心检查证据，再选择登录修复方案。
