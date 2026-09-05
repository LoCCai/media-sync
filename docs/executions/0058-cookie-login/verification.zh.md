[English](verification.md) | **中文**

# 验证记录

基线`68c4004`工作区干净，fresh fetch后HEAD/origin分歧`0 0`，冻结计划`f94d557`。测试均使用隔离/合成数据，不用生产Cookie。

## 检查点、失败与修正

- 首次完整离线检查：`.venv/Scripts/python.exe -m pytest -q --tb=short`，句柄69515终态为 **53 failed、4135 passed、23 skipped、1 warning，933.85秒**。启动早于最后修改，不算最终源码资格。失败涉及旧浏览器策略/bridge/detail夹具、supervision/安全矩阵夹具、两处历史迁移断言、新能力字段和支持包兼容。支持包是生产问题：敏感词过滤误拒新revision/kind/error；修正仅对固定字段的精确值放行，相似恶意值仍拒绝。
- 初始API/Operation：7失败/148通过，23.10秒，固定Cookie错误码与敏感词守卫冲突；添加精确白名单，不豁免任意前缀。随后2失败/153通过，22.28秒，为测试错用`error.code`而非公开`error_code`；修正后联合222通过/1警告，41.24秒。后续API/资料/effect联合169通过/1警告，27.14秒，覆盖目标漂移、CSRF、继承描述符接线、有界原始HTTP及中断候选不可重放。
- 私密存储/迁移/身份联合276通过/1个Windows与POSIX差异跳过，32.60秒。初始29错误发现keyring校验分支错位；较广275通过/1失败/1跳过发现Windows目录重命名保护缺失；均已修复。Windows和Linux目标mypy通过，但Linux静态目标不等于Linux执行。
- B站Cookie资料API及实际锁定模块43通过/1警告，21.95秒；扩展私有帧进程测试11通过，16.78秒。首跑1失败/10通过，15.69秒，是新增saved-session夹具缺父目录。实际本地parent/guardian/worker管道证明Cookie传递、不漏到argv/environment/repr/公开帧、无需saved-profile；checkout/runtime及最终远程查询被替换，不是真人验证。
- 旧pipeline/安全矩阵加资料传输/能力联合100通过，34.93秒。更早93683句柄跨续轮消失、无终态结果，不声明该次通过；核实句柄缺失且无对应活动进程后才启动替代检查。
- 支持包/API68通过/1警告，17.90秒。初跑67通过/1失败，18.89秒，是新增恶意输入测试期待500、现有实现固定503，核实API后修正。
- 账号锁加固前runner检查点：单元/实际锁定客户端105通过，进程树9通过/13.45秒，引号/Node/兼容联合122通过/23.75秒。旧bridge/detail初跑3失败/190通过/1跳过，220.76秒；修复假checkout钩子，没有放宽生产解析或保密断言。最终runner/Windows账号锁验证将在下方记录。

以上范围重叠，不相加作为唯一覆盖数。警告为已有Starlette/httpx弃用；全量23跳过中4项是Windows/POSIX差异，19项为未配置真实PostgreSQL竞争环境。

## Web与隔离浏览器

最终Web源码553测试/20文件通过，`pnpm check`零错误/警告，format/build通过。构建句柄37145在隔离浏览器检查前完成，本次收尾未再修改Web。

computer-use技能用于独立loopback8768合成服务：用公开测试凭据登录、选择仅浏览引导，检查B站/抖音账户。确认支持入口、禁用抖音入口、许可证门禁、明确替换提醒、清空/关闭/重开，以及窄面板可读布局。只输入人工头值，没有接受许可证、提交验证、平台请求或真实账户变更；不算浏览器成功流程或真人验收。

只关闭本轮tab4。清理检查时合成进程/8768监听已不存在，没有停止生产或无关进程；临时合成文件留在Git之外。成功/失败/竞争路径由控制器和API测试覆盖，不伪称实际浏览器证据。

## 静态、打包及未跑门

最终静态范围通过：Ruff lint/format（`src tests scripts`共297文件）、Windows mypy124源码、compileall、docs598文档、两个锁定上游、uv lock、diff空白。本执行未新增依赖。新增凭据模块的Linux目标检查通过；较广runner检查仍有10项既有Windows API类型问题，逐项对照HEAD源码，不假称Linux全源绿灯。

独立审计确认实际采集/调度/详情/资料路径均明确注入managed解析器，公开Account/Operation/支持包不新增凭据引用。进程审计发现硬退出锁缺口，验证器已继承持有描述符；新测试又证明Windows进程级字节锁不能跨父描述符关闭保留，因此Windows `_AccountFileLock`改用独占共享模式的原生HANDLE生命周期，同时保留不跟随链接、常规单链接文件检查及CRT转换失败清理。同实例重复获取不会丢失旧描述符；POSIX仍用原flock分支。

扩大runner/QR/浏览器策略联合 **237通过、1个仅POSIX跳过，111.10秒**；旧失败/新锁重点43通过，7.68秒。下述完整目录检查启动后，唯一源码修改是在Windows helper前明确添加`sys.platform != 'win32'`门，Windows行为不变；最终6个锁/继承用例2.88秒通过、4源文件Windows mypy通过。不能隐瞒此时间差，冒充最终字节又跑了一次全量。

完整离线复查使用相同Python执行器的三个不重叠命令：`-m pytest -q --tb=short -p no:cacheprovider tests/unit`、`tests/integration`、`tests/contract`，涵盖全部151个Python测试文件；browser目录无Python测试，并发禁用共享cache。单元63799终态 **2752通过、1跳过、1警告，286.38秒**；集成79959终态 **833通过、20跳过，300.35秒**；契约58524终态 **671通过、2跳过，398.61秒**。三组均退出0，不重叠目录合计 **4256通过、23跳过**、1个已有警告；晚加平台门与单独最终源码检查已在上文披露，无活动测试句柄。

首次打包成功，但wheel与当前源码逐字节比较发现仅晚加的runner门不同（138个Python源文件中137个一致），该包不是最终交付。重新`uv build --out-dir`到`C:/Users/LoCCai/AppData/Local/Temp/media-sync-0058-final-package-eeba9c63-4e29-4bf1-8b2e-0bcabbc5a846`退出0，由sdist构建wheel；最终wheel全部 **138个Python源文件**与当前源码逐字节一致。wheel592768字节/145成员，sdist2394843字节/1004成员，两者均含8个新增生产模块/迁移。仅文件名审计发现0个私密环境、数据库、secrets目录、运行/upstream/依赖缓存或日志产物；公开`.env.example`有意允许。这是分发组成/源码比对，不是真实秘密内容扫描或Docker资格，打包快照时文档仍在收尾。

最终SHA256：wheel `6d1a577ab983a65b084abea9578db0e9d5e7bf0b5456cc2910f6870689a53503`；sdist `23203e5ec7abe5725853eaa0d0a6787edfe7623e4e939a1fe74bcbfa3eed2a32`。集成套另覆盖安装wheel的迁移可用性。首次PowerShell混合表形状导致元数据列没显示，改为明确JSON只读比对后取得完整结果，没有改包。

本机无Docker可执行文件，未配置`MEDIA_SYNC_TEST_POSTGRESQL_URL`。Docker构建/Linux运行、生产部署、真实PostgreSQL竞争、四平台真人Cookie验证/复用、采集/归档/媒体服务器播放均NOT_RUN。抖音/快手/贴吧验证器和六平台资料仍NOT_IMPLEMENTED，七平台范围不变。未生产登录、未重试订阅/采集、未下载/导出、未恢复supervisor。

## 发布

已用非force `git push origin main`发布冻结计划`f94d557`和双语实现`3dc8905`（退出0，远端从`68c4004`前进）。新执行`git -c http.sslBackend=schannel -c http.version=HTTP/1.1 fetch --prune origin`退出0：HEAD和origin/main均为`3dc89056150a6651f813d7df03036031163a932b`，分歧`0 0`，本次仅文档发布记录前`git status --porcelain=v1`为空。全部测试/构建句柄已终止。这是GitHub源码发布，不是生产部署。发布记录提交随后再次非force推送并fresh fetch核对；自身结果在交付时报告，不递归改写本记录。
