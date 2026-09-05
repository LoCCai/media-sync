[English](verification.md) | **中文**

# 验证记录

基线87ef7fd，冻结计划36e004d。使用隔离本地数据，不读取生产Cookie。

## Python与静态

- 完整离线检查点：.venv/Scripts/python.exe -m pytest -q --tb=short → 3972 passed、22 skipped、1 warning，852.47秒。跳过为3项Windows/POSIX差异和19项未配置PostgreSQL；既有Starlette/httpx弃用警告。新增Pillow依赖后原二维码Pillow跳过项已执行。
- 全量启动后的最后小幅加固（ORM修订刷新、统一UID上限、原子成功测试）另有53项资料/effect/API回归通过，13.56秒；不把原全量称为最终源码的重新完整运行。
- 最终冻结源码扩大联合选集保存在[final-tests.txt](final-tests.txt)，执行同一Python前缀加文件中逐行参数和 -q --tb=short：**575 passed、1 warning，109.47秒**，退出码0。21文件联合覆盖新增runner/process/upstream/avatar/API/effect/仓储/迁移以及既有协调器/鉴权/CLI/支持报告/工作台/登录/检查点/删除/打包合同。
- 单资料runner选集：tests/unit/test_creator_profile_runner.py、tests/contract/test_creator_profile_process.py、tests/contract/test_creator_profile_upstream.py → 68 passed/14.64秒（56协议、9真实子树、3真实锁定模块但替换网络/浏览器依赖），无残留相关进程。
- 头像tests/unit/test_creator_avatar.py → 31 passed/2.96秒；API+Operation参数124 passed/9.92秒；DB/auth/别名175 passed/35.79秒；修后CLI/报告/包迁移/API/effect143 passed/45.78秒。这些是阶段选集，不相加冒充独立总量。
- 最终收尾命令全部退出0：`.venv/Scripts/python.exe -m ruff check src tests scripts`；`-m ruff format --check src tests scripts`（明确范围内281文件）；`-m mypy src/media_sync`（117源码文件）；`-m compileall -q src scripts`；`uv lock --check`；`.venv/Scripts/python.exe scripts/check_docs.py`（590份Markdown）；`.venv/Scripts/python.exe scripts/check_upstreams.py`（两个锁定上游）；`git diff --check`。Python的`-m`命令使用同一虚拟环境解释器。此前更宽范围格式检查为871文件，两者范围不同。

## 分发打包

2026-09-05 22:37:49 +08:00，在新建GUID临时目录执行`uv build --out-dir`退出0，由sdist构建wheel。wheel为566970字节/137成员，sdist为2329354字节/977成员。`tar -tf`确认两者都包含全部六个新增生产模块：资料runner、service、头像获取器/worker、仓储和0010迁移。仅按成员文件名检查，未发现私有环境/数据库/凭据/runtime/上游/node_modules/缓存/日志制品；sdist中的公开`.env.example`明确允许。

制品保留在仓库外`C:/Users/LoCCai/AppData/Local/Temp/media-sync-0057-package-07741cfe-c951-4daf-9e44-b93f4b8ddd66`。SHA256：wheel为`57721342871718d9ec0d28eaefF6ec56e1f0fa4b13add5c4b78a78dce31106af`，sdist为`fc8b306c263d684063765f4932fe3de77c68dfbd6cc78db91a613f6ada494ffc`。sdist快照构建时文档尚在收尾，生产源码已冻结。这是归档成员检查，不是内容级凭据扫描、全新安装wheel冒烟、Docker构建或真人验收；575联合另含包迁移测试。首次PowerShell成员检查出现纯语法ParserError（退出1），修正后检查和扩大文件名审计均退出0，没有修改归档。

## Web与浏览器

- Web最终串行 pnpm test、pnpm check、pnpm format:check、pnpm build → 492 tests/19 files，零check错误/警告，格式/构建通过；只有既有构建性能提示。
- 使用computer-use技能推荐浏览器接口，访问回环8767隔离fixture。正常测试凭据登录，选择“稍后确认，仅浏览”，没有代确认许可证。输入UID/blur实际复现门禁被泛化成查询失败，随后修正为“本次未发起查询”、按钮仍为“查询作者资料”，不消耗自动机会。
- 独立脚本预置合成成功资料和暂停订阅，未连接平台。列表/详情的昵称、独立备注、头像及准确观察时间已目视检查。未在UI创建/删除/恢复订阅、扫码、发起真实查询/采集、下载/导出或打开外站主页。
- 修正版构建已完成；首次尝试刷新复验时页面出现额外导航，不能据此声称该门禁提示已完成浏览器复验。门禁修正由专属控制器测试覆盖。专用浏览器标签已关闭；核对临时脚本完整路径和Python可执行文件后停止fixture进程，确认8767端口无监听、服务句柄已结束。临时合成文件保留在仓库外；未停止任何生产进程。

## 失败、修复与审查

头像首轮29通过/4fixture错误来自超大bytes自动参数ID导致Windows临时路径超限，改短ID并用精确异常断言后通过。操作联合161通过/2失败为新增kind缺少测试参数构造；鉴权44通过/1失败为路由62→65；更广177通过/9失败为表数17→19、闭合字段/种类新增，以及0004 fixture误用当前Account ORM的auth_revision。均已按实际合同修正，历史fixture只写历史列、不给旧schema加新列。DB代理初轮171通过/2失败同样是新表清单和历史迁移目标，随后修复。误拼路径导致的零收集命令不计验证。

独立审查确认共同锁、账户隔离、认证ABA、失败保留头像、Operation→Account锁序及安全迁移。补充修复资料发布和Operation成功之间的窗口，以同事务成功取代；第二栅栏定义线性化时刻并刷新ORM避免旧修订；读取错误白名单拒绝反射未知数据库错误。最后新增作者insert-if-missing并发防覆盖。真实PostgreSQL竞争仍未验证。

## 未跑门与发布

本机Docker不可用，PostgreSQL测试URL未配置。Docker构建/生产部署、真人资料/登录/采集/归档/播放仍NOT_RUN。六平台及Cookie资料模式NOT_IMPLEMENTED；Cookie登录、正确有界覆盖和整体目标仍开放。无生产动作或supervisor重启。实现尚未提交/推送，待最终检查后记录。
