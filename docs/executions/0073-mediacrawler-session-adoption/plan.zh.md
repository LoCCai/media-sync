[English](plan.md) | **中文**

# 计划

## 1. 冻结接缝并保留已工作的主链

- 确认两个受管 profile 位置并复用现有路径构造器：
  - WebUI 来源：`<runtime-root>/webui-profiles/<platform>_user_data_dir`
  - Account 目标：`<runtime-root>/accounts/<platform>/<account-id>/browser_data/<platform>_user_data_dir`
- 追踪现有 Account repository 不变量、saved-session 探针、profile／Account 锁、Subscription 交付、scheduler handler、JSONL 摄取、资产下载、不可变归档及媒体库／NFO 发布。复用这些边界，不增加第二套运行或媒体状态机。
- 本执行保持 `/crawler/` 交互式输出与定时输出分离。定时运行继续走已经建立的归一化流水线，使同一套内容身份、重试和发布合同继续作为权威。
- 准确记录原生下载限制：当前证据只覆盖小红书、抖音和 B 站的部分范围，并非七平台／媒体矩阵完整覆盖。不得移除既有下载补齐能力，也不得让同一定时资产被两条路径重复下载。

## 2. 定义狭窄的会话认领应用边界

- 增加一个类型化应用请求，只包含 Account 身份和预期 Account auth revision。平台从 Account 解析，所有 profile 路径都从可信设置和数据库状态派生；API 边界拒绝路径、平台、Cookie、凭据和任意元数据字段。
- 要求目标是合格的已有 MediaCrawler Account，并据此解析精确同平台的 WebUI profile。对已删除、revision 过期、忙碌或畸形 Account 返回固定冲突码。
- 把认领暴露为通过操作者认证和 CSRF 防护、携带 Account 预期认证 revision 的 mutation。只返回有界状态和安全下一步；绝不返回 profile 条目、Cookie 值、命令行或原始 child 输出。
- 把首次认领和以后刷新定义为相同的显式、受 revision 约束的快照动作。绝不合并活动 Chromium 树或共享运行 profile。成功刷新只原子替换该 Account 的旧快照；失败则恢复旧快照。

## 3. 让 profile 转移具备独占、受限与可恢复属性

- 增加 media-sync 自有 coordinator：先证明嵌入式 WebUI crawler／登录 child 已停止，并在取得及验证快照期间持有 WebUI profile gate；在短暂的替换／发布区间前获取目标 `MediaCrawlerAccountLock`。遇到忙碌状态就有界拒绝，不无限等待。
- 获取锁后重新读取 Account，以预期 auth revision 和平台 fencing 该操作，防止并发编辑、删除、登录、作者查询或 scheduler 派发被迟到结果覆盖。
- 使用不跟随链接的文件系统检查验证来源。来源必须是 `webui-profiles` 下精确、非空的平台目录；拒绝路径逃逸，并阻止符号链接／reparse point 或不支持的特殊条目被复制。
- 在来源静止期间，只把普通文件复制到 Account 形状的 attempt 级暂存位置且绝不跟随链接。验证这份独立快照后，通过同卷原子目录交换提升到精确目标，使 scheduler 永远看不到部分 profile。
- 为目标替换维护显式回滚记录。Account 发布前发生任何失败，都保留 WebUI 来源，只删除该 attempt 精确拥有的暂存数据，并在安全情况下恢复 Account 的旧 profile。清理失败使用独立固定分类，且绝不能把未经验证的 Account 变为已认证。

## 4. 发布前验证已认领会话

- 针对 Account 形状的暂存快照调用既有锁定 MediaCrawler saved-session 探针，使用固定 checkout 与专用解释器。强制非交互／无头 saved-session 行为，并保留禁止二维码回退的现有 fence。
- 沿用既有截止时间、受控 child 进程树、安全输出解析与秘密脱敏。只接受所请求平台精确的 authenticated 终态；expired、login-required、timed-out、cancelled、含糊及格式异常结果全部关闭失败。
- 探针成功后，在发布事务中再次检查 Operation 所有权、Account revision／平台及目标身份。复用 repository 不变量设置 `login_method=saved_session`、`auth_status=authenticated`，推进 auth revision，并清除不兼容 credential／profile-path 字段。
- 只有 Account profile 替换与数据库发布一致后才返回有界结果。若数据库发布冲突，恢复 Account 的旧 profile 且不得展示成功。重启对账必须保守：安装状态不确定不能算 authenticated Account，必须进入显式重试／恢复路径。

## 5. 把账户 UI 切换为原生登录流程

- 把正常二维码／Cookie 登录操作改为简洁三步：打开 `/crawler/`、完成该 Account 平台的原生登录、返回并认领已保存会话。
- 打开同一个经认证的 `/crawler/` 路由；不得暴露上游端口或创建第二个登录表单。保留 0072 已交付的精确部署前缀／Origin 行为。
- 增加 Account 级“认领已保存会话”操作，显示精确平台和 Account，携带预期 auth revision，并展示稳定结果：无已保存 profile、crawler 忙、Account 忙、验证过期／失败、冲突、清理失败或成功。
- 成功后刷新既有 Account read model，让用户看到 `saved_session` / `authenticated` 并继续作者查询或创建 Subscription。失败时展示安全、可执行的提示；不得渲染原始日志或秘密。
- 从账户主体验中删除或降级自定义二维码／Cookie 控件。只保留探针／scheduler 所需的内部兼容接缝；本执行不要求删除 API 或执行数据库迁移。

## 6. 证明已连接既有 Subscription 主链

- 增加集成测试：建立合格 Account，通过假的 authenticated saved-session 结果认领合成 profile，创建 Subscription，并证明 scheduler 派发解析到精确的已认领账户级 profile。
- 让既有 handler 使用一个有界媒体 fixture 完成归一化摄取、归档和 Emby/Jellyfin 兼容目录／NFO 发布；断言未配置媒体服务器 profile 时发布仍成功。
- 验证本次认领没有引入替代内容 ID、输出根、资产下载器、归档 writer、导出前置条件或 provider 连接。0073 不自动摄取交互式 `/crawler/` 输出。
- 保留现有历史确认、分页边界、周期、重试／退避及账户过期行为。真实历史采集、后续增量和风控资格属于部署证据，不能从离线 fixture 推导。

## 7. 测试失败与并发边界

- 单元测试路径派生、API schema 拒绝、操作者认证／CSRF、来源缺失／为空、不安全条目、有界转移及安全响应投影。
- 集成测试 WebUI 忙与 Account 忙拒绝、auth revision 过期、预取消、探针过期／失败／畸形、数据库冲突、旧 profile 回滚及成功发布。
- 证明成功认领会保留来源并安装一份独立、由 Account 所有的快照；证明每种发布前失败都保持 Account 未认证，且 scheduler 永远观察不到部分目标。
- 只为确保隐藏的内部接缝在必需处仍工作而回归既有二维码／Cookie 兼容服务；不得把合成成功计作真人平台认证。

## 8. 准确验证、记录与发布

- 运行会话认领、API、Account repository、MediaCrawler saved-session、scheduler handler、摄取、pipeline、归档及 NFO 发布的 Python unit／contract／integration 专项。
- 运行完整 Python 套件与 Web 测试，以及 Ruff、格式、mypy、前端格式／check／build、文档、上游锁／源码完整性、打包和源码／制品一致性门禁。只在实际运行后记录精确命令与最终计数。
- 新增双语 `progress.md` / `progress.zh.md` 与 `verification.md` / `verification.zh.md`，记录实现 revision、已修正失败、环境跳过项及部署状态。全部预期文件复核后，使用中英双语 Git 提交说明并推送。
- 在部署主机上先验证 `/crawler/` 可访问，并在 scheduler 无法与 profile 转移竞争的条件下，只对一个已授权平台执行登录／认领。再使用一个有界 Subscription canary 证明 Account profile 复用、摄取、媒体字节、兼容目录／NFO 以及之后的增量行为。
- 每个未实际执行的真人平台登录／采集／CDN 行，以及 Emby/Jellyfin 扫描／播放行继续标为 `NOT_RUN`。媒体服务器连接仍为可选；文件系统发布才是必需结果。

## 停止条件

- 如果无法独占并静止 WebUI profile、profile 不安全或已有所有者、验证可能回退交互式二维码、Account fence 已变化、回滚无法确立唯一所有者，或既有 scheduler 可能观察到部分 profile，则停止而不是发布。
- 不把本执行扩大为新日志中心、任意 WebUI 输出 importer、原生下载重写、七平台修复行动或媒体服务器集成；只把相关发现连同证据记录为后续工作。
