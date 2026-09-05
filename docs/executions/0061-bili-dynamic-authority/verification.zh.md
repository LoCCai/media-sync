[English](verification.md) | **中文**

# 验证记录

fresh fetch：HEAD/origin21540c6，分歧0 0，工作区干净。锁定MediaCrawler d6f7c5bb906b6dac40ddf343ef9e26438a3de092和bili-sync-up dcb5bb73b56ac45b2525da14b389e185b0ea6dbd源码审计为只读证据，不是动态能力或历史真人失败根因。计划冻结时未跑新测试；0060结果为历史，不继承作为本轮证明。

## 先复现与专项检查

新跨作者仓库回归在旧实现上失败：未抛出归属冲突异常。扩展测试初次SQL断言期望RETURNING contents.id，而SQLite输出id，仅修正测试期望。最终`tests/integration/test_content_ownership.py`：**18通过、13跳过**。真实PostgreSQL URL未配置；PG原生SQL编译是离线覆盖，不是实际事务证明。以`-k 'sqlite and (concurrent_initial or waiting_first)'`选择四项SQLite竞争测试，重复五轮每轮全通过（78149终态exit0）。覆盖全行/tombstone保留、同作者刷新、新/已有竞争作者savepoint回滚、外层事务可用、dynamic/投稿及平台命名空间、首写提交/回滚、旧ORM、条件SQL及加锁fallback。文件Ruff/格式/diff通过。

主代理执行`.venv/Scripts/python.exe -m pytest -q --tb=short -p no:cacheprovider tests/integration/test_database.py tests/integration/test_offline_media_pipeline.py tests/integration/test_emby_application.py tests/integration/test_creator_profile_repository.py`：**114通过，22.92秒**（54565 exit0）。通用同步/handler选择tests/unit/test_sync_service.py及tests/unit/test_scheduler_handlers.py：**38通过，1.47秒**，exit0。验证原数据库/本地归档导出及固定终止映射，包含恶意改写异常code/args的私密哨兵。主代理改动源码Ruff/格式/mypy通过。

分类/诊断先复现Python **9失败/204通过**、Web **3失败/97通过**。加入固定终止、不熔断分类及安全Web说明后，最终四个Python文件（test_scheduler_policy.py、test_scheduler_diagnostic_projection.py、test_job_diagnostics.py、test_api_server.py）**234通过，16.88秒**，一个既有Starlette/httpx warning。API列表/详情/订阅、Job/Run/Operation投影及可下载报告保留固定码，不泄漏私密哨兵；共享投影无需额外生产修改。Web专项**117通过**，全Web **640通过/21文件**。`pnpm check`零错误/警告；`pnpm build` exit0，仅Vite插件计时性能提示。所属Ruff/格式/mypy/Prettier/diff通过，所有已报告句柄均终止。专项集合重叠，不累加成全量覆盖。

## 完整目录验证进行中

生产实现冻结、CLI代理仅追加integration测试后，主代理启动不相交`.venv/Scripts/python.exe -m pytest -q --tb=short -p no:cacheprovider tests/unit`（40789）及tests/contract（95013）。终态结果、最终完整integration及独立静态/包检查完成后续记如下。运行中句柄及历史结果不计作通过。

## 入库检查与复核修正

首次规范化入库/scheduler/CLI专项**5失败/10通过**，均为fixture错误（AssetRefreshSource使用复合主键，没有id）。下一轮**3失败/12通过**：两个legacy漏传mode，原作者种子订阅参与了scheduler选择。修正测试mode并停用种子订阅后**15通过，24.89秒**。补旧CLI及恶意异常code/args测试；首次legacy CLI用了错误manifest路径和非规范JSON，**1失败/15通过**，仅修fixture构造。最终tests/integration/test_content_ownership_ingestion.py与test_bili_bounded_cli.py **16通过，27.31秒**，61782 exit0。四所属文件Ruff/格式及两生产文件mypy通过。测试使用合成远端输出经过真实封存scheduler/normalizer/DB，不是真人B站。

随后独立审查发现CLI未确认终态输出及收尾丢失后的耐久冲突恢复缺口，属于生产缺陷，不同于上述fixture修正。重新开放源码冻结，之前完整目录句柄及下列包明确作为中间快照；最终回归须包含修复后的新增耐久性案例。

中间发布检查通过Ruff/格式931文件、mypy128源码、compileall、uv lock、Web格式及两个锁定/干净上游。Docker命令不可用。PG客户端存在，但MEDIA_SYNC_TEST_POSTGRESQL_URL未配置且本地默认端口无响应，未创建服务器或数据库。首次构建目录`C:/Users/LoCCai/AppData/Local/Temp/media-sync-0061-package-c9a32281-87cd-4c4e-8483-a2a77876058b`：wheel609269字节/147成员、sdist2491227字节/1042成员，与当时140个应用Python源码相同。首审误将uv生成的目录级1字节.gitignore算作artifact，改为显式选两个归档后exit0。成员名审查通过，不是全面内容秘密扫描。这些包早于耐久性修复，不作为最终发布产物。

## 耐久性回归证据

CLI先复现**4失败，7.82秒**：写失败时Run仍ingesting而旧输出宣称failed_terminal；读失败也误报，正常/确认丢失路径缺少fresh readback。修正后四例7.55秒全通过。扩展后test_bili_bounded_cli.py **19通过，41.76秒**（54971 exit0），覆盖写失败、提交确认丢失、SQLAlchemy/RuntimeError读失败、初始发布真值不可读且不尝试写失败、存储码不匹配、保留已成功Run。既有test_cli.py、test_mediacrawler_cli_ingest.py、test_cli_workflow.py **77通过，19.89秒**。Ruff/格式、CLI mypy、diff通过，所有句柄终止。unknown仅固定CLI诊断，不注册新自动重试分类。

scheduler首次回归有一项fixture TypeError，原因漏传global_capacity；修正测试后复现**两个生产失败**：真实封存MediaCrawler Run提交冲突后抛OSError，Job变为retry_wait/unexpected_handler_failure；worker停止后租约过期，即使Run为冲突终态仍返回attempt2的新claim。后续修复及最终结果续记如下。

中间完整目录句柄现已终态exit0：unit40789 **3128通过、1跳过、1既有warning，248.39秒**；contract95013 **718通过、2跳过，369.06秒**。源码冻结已重开，因此这是中间结果，不充当最终冻结源码全量证明。审查中fresh fetch确认origin未变，分歧1 0（仅冻结计划领先）；docs622及空白检查通过。

## 最终耐久性范围与检查

scheduler严格矩阵编写中有十个fixture失败（缺少空registry mapping、updated_at在flush前取快照、queued状态未flush），修正后32例通过。复核又发现真实历史Run采用边界：非冲突结果可以绑定旧未绑定终态冲突Run，导致后续恢复误当作本次权威。最终护栏拒绝成功/重试/wait采用该Run；既有generic handler明确固定冲突仍可正常收尾绑定。该handler未使用run_attacher，因此保留这一窄兼容场景是有意设计。

最终test_content_ownership_reconciliation.py **38例**；连同test_scheduler_repository.py、test_scheduler_worker.py、test_subscription_removal.py **189通过，26.38秒**（30740 exit0）；相关handler/policy unit **71通过，1.41秒**。覆盖真实封存MC确认丢失、进程退出/租约恢复、普通收尾及fail-closed、cancel/resume/removal、旧retry/queued状态、live/stale/deleted/cancelled栅栏、字面固定终态、历史/其他订阅附件、旧ORM/CAS变化、保留失败计数/其他probe、畸形队首隔离。最终源码/测试Ruff/格式/mypy/diff通过；这些是SQLite事务，PG恢复仍NOT_RUN。

主代理第二轮完整unit/contract（2090/47887）启动时仓库SHA256为800f6254a4aedf3202015641fb89b1a998e07b84188d1e697c497c62084f925a，早于最后护栏，明确保留为快照检查。最终源码SHA256为37ac86a66543d8845bb1e1ae6d415169b27247f4bceb94f24a86a2130a773b21，未改service.py。随后启动最终完整tests/integration（68517）及受影响unit集合（17951）：test_api_operations.py、test_api_server.py、test_scheduler_supervisor.py、test_scheduler_diagnostic_projection.py、test_scheduler_handlers.py、test_scheduler_policy.py、test_job_diagnostics.py、test_sync_service.py，命令前缀均为`.venv/Scripts/python.exe -m pytest -q --tb=short -p no:cacheprovider`。终态结果续记如下；不累加重叠集合、不把快照混称同源码全量。

## 队列阻塞修正及已完成快照

独立内存SQLite复现表明：retry_wait/failed_retryable冲突Job含损坏payload会中断claim_next，而queued坏记录已被隔离。新增三个回归还包含过期running，先均以terminal scheduler job payload is invalid失败。七行修正在精确冲突CAS后仅捕获纯payload ValueError：保留Job终态，不写任何订阅日程字段，继续其他任务。审查者独立验证三个修复状态。严格矩阵**41通过，10.11秒**（24143 exit0）；扩展scheduler/removal组合**192通过，25.12秒**（26527 exit0）。静态通过；最终仓库hash为`cee10a1e20edce7f8ae6d2c0690ce564773d679a8f4a3bdf5e0263f11b024bc4`，测试hash为9ee5c3c9e090ad05c0eef5ef90fbf4b041f73ee60f5dd35c161cd48624e78b5b。

所有完整目录句柄均终态exit0：第二轮unit2090 **3128通过、1跳过、1既有warning，310.30秒**；第二轮contract47887 **718通过、2跳过，442.49秒**；integration68517 **972通过、33跳过，378.59秒**。受影响unit17951 **317通过、1既有warning，29.20秒**。这些早于最后七行修正及/或历史护栏，因此保留为完整目录/受影响范围快照，不混称最新源码的一次全量。目录快照共四项Windows/POSIX差异及32项未配置PG跳过，不算实际执行证明。

随后主代理以相同pytest参数跑最新冻结源码受影响综合集合（27151）：test_content_ownership.py、test_content_ownership_ingestion.py、test_content_ownership_reconciliation.py、test_bili_bounded_cli.py、test_scheduler_repository.py、test_scheduler_worker.py、test_subscription_removal.py及上述八个unit文件，综合覆盖最终仓库/CLI/入库/worker/删除/API/诊断路径。其终态结果及最终包审计续记如下。

## 最终源码门禁完成

最终受影响综合27151已终态exit0：**551通过、13项未配置PG跳过、1个既有Starlette/httpx warning，94.37秒**。该运行及打包期间源码未变，仓库SHA256保持cee10a1e20edce7f8ae6d2c0690ce564773d679a8f4a3bdf5e0263f11b024bc4。这是最终源码路径回归，用来补充上述目录快照，不累加成另一个全量总数。完整Web保持**640通过**，此后无Web修改。本执行所有测试/构建句柄现已终止。

独立最终`uv build --out-dir`在`C:/Users/LoCCai/AppData/Local/Temp/media-sync-0061-final-package-affd4800-c109-4407-b762-1e1539888789`完成exit0，8.99秒。wheel610852字节/147成员、sdist2510358字节/1043成员，各包含全部140个应用Python文件，与最终工作区源码逐字节相同，缺少/多出/不一致均零。成员名检查未发现重复、路径穿越、符号链接或可疑私密runtime/env/DB/log/cache/upstream成员。这是成员名及应用源码审计，不是全面秘密内容扫描；包内docs为构建时快照，之后仍有文档收尾。

wheel SHA256：`bdb5fa0a3d7c27887220123c065cf9e6d39af78a24715bb2cf956c565754af6a`；sdist SHA256：`0a1920fee11ff2b1a1023b039397e788f0b0ebdd3870561bb03cad951ad860c4`。

最终Ruff check/格式932文件、mypy128源码、compileall src/tests/scripts、uv lock62包、两个锁定/干净上游、Web Prettier及Git diff通过。docs622通过，提交前再检查。真实Docker/Linux镜像、PG事务、真人平台登录/采集/下载/导出/媒体服务器/播放资格仍NOT_RUN。未改凭据、生产状态或supervisor。阶段A已实现并离线验证，B–D及总目标继续开放。
