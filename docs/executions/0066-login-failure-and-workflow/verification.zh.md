**中文** | [English](verification.md)

# 验证记录

## 生产证据，不反推旧失败根因

浏览器核对用户报告的抖音操作：`account-login`，阶段 `authenticating`，五条事件，约46秒后终止失败；保存 `runner_status=failed`、`login_session_status=failed`、`auth_status=failed` 及 `operation_login_failed`。账户与会话关联存在，旧通用文案不证明持久记录丢失。只读页面安全字段，未读取原始日志、Cookie 或 profile 存储。

诊断页环境预检报告锁定 MediaCrawler `d6f7c5bb906b6dac40ddf343ef9e26438a3de092`、Chromium151.0.7922.34、Playwright1.62.0、Python3.13.15、ffmpeg5.1.9。这些启动/工具检查不验收登录、作者采集或下载；页面事实不提供部署应用 Git 修订。未提交新登录、采集、下载、部署、媒体服务器请求或恢复 supervisor。

## 复现与实现验证

- 修改前，独立审计用完整锁定登录/辅助模块和模拟页面重放五项：抖音弹窗点击超时，抖音/快手/微博二维码选择器超时，贴吧两次二维码选择器均超时，全部仅得到 `failed`。这是离线控制流证据，不证明生产选择器已经变化。
- 可复跑脚本：[reproduce_login_classification.py](artifacts/reproduce_login_classification.py)。修改后同样调用轨迹得到一个 `upstream_browser_timeout`、四个 `upstream_login_exited`，无真实浏览器或网络。上游辅助函数仍会吞掉部分失败，退出状态不能细分确切原因。仓库根目录用 `.venv/Scripts/python.exe -X utf8 -B` 执行。主代理首次漏加 UTF-8，终端中文选择器文字乱码，但分类断言通过且不涉及私密数据。
- 登录单元/确认选择77通过/1.34秒；真实进程合同67通过/85.29秒。覆盖类型化与同名/内置异常、SystemExit0不认证、固定帧拒绝、私密哨兵、取消、守护清理与锁所有权。
- 主代理初始诊断/摘要/应用选择193通过/26.17秒。追加真实服务、新会话、持久操作、精确最新诊断及另一已登录账户不变测试后，诊断选择45通过/17.61秒。API及无需媒体服务器的本地库选择23通过/15.23秒。均与后续选择重叠，不累加。
- 最终登录选择397通过、0跳过/120.37秒，1条既有 Starlette/httpx 弃用警告。准确命令：

```powershell
.venv/Scripts/python.exe -m pytest tests/unit/test_login_diagnostics.py tests/unit/test_operation_payloads.py tests/unit/test_mediacrawler_login.py tests/unit/test_bilibili_login_confirmation.py tests/unit/test_login_qr_relay.py tests/integration/test_mediacrawler_login_application.py tests/contract/test_mediacrawler_login.py -q --tb=short --junitxml=docs/executions/0066-login-failure-and-workflow/artifacts/login-regression.xml
```

本地忽略的 JUnit SHA256：`33e1dba0ce3ef4b840848ca390cc4e649e9b66d00fb3077547dbeb6106f3ac4f`。

- 新续跑105单元+8集成=113通过/15.17秒，既有七文件调度选择173通过/29.49秒。密封模拟 runner 接真实入库/检查点/Worker收尾：七次300秒续跑，第八单元转普通21600秒；保留轮转、上限、提前调度拒绝、重启/取消重整及每成功任务仅一个流水线。失败不借旧pending，缺失/变更/关闭锁定及暂停均维持原行为。
- 更广最终工作流选择759通过、1跳过/172.76秒，1条既有Starlette/httpx警告。跳过位置 `test_mediacrawler_scheduler_handler.py:730`，原因是POSIX虚拟环境启动器使用符号链接。准确文件选择与命令（PowerShell）：

```powershell
$task0066WorkflowTests = @(rg --files tests | Where-Object { $_ -match '(scheduler|scheduled_offline_pipeline|subscription_application_pipeline|pipeline_runtime|bili_scan_continuation|bili_bounded|bilibili_dynamic_scheduler|test_config|test_api_server|test_api_local_export|test_subscription_removal)' } | Sort-Object)
.venv/Scripts/python.exe -m pytest @task0066WorkflowTests -q --tb=short --junitxml=docs/executions/0066-login-failure-and-workflow/artifacts/workflow-regression.xml
```

共选择26文件，本地忽略的JUnit SHA256：`1a2e8d9d8ff42082495fcec1ed12de390da9b5dbc26ca31cdf11015145f0c002`。
- 修改前只读审计另运行105后端/127Web，以及130调度/流水线验证；属于基线观察，不是额外最终源码覆盖。

## 前端、静态与构建

- 最终Web705通过/22文件/1.43秒，Svelte0错误0警告，构建通过7.52秒，Prettier通过。此前同轮Web705通过/1.19秒、构建7.86秒发生在最终文案/设置更新前，不作为累计测试。
- Ruff通过，格式352文件未变，mypy138源文件通过，compileall通过，文档672份通过，两个锁定上游通过，`uv lock --check`62包未变，`git diff --check`通过。两次文档补丁初始标题锚点不匹配，读取准确标题后重做；新测试/脚本/Svelte格式已修正，没有隐去产品测试失败。
- `uv build`在本地临时目录 `media-sync-0066-build-b45f26a7010044fda706d0618a3d3300`生成 wheel/sdist。[check_package_sources.py](artifacts/check_package_sources.py)不解压、逐字节比较全部152个应用Python文件，两包通过。wheel SHA256 `bf0f6cca9eafa2bd0f338a4832ee00fd4790dc08b60cca416208d015c248e4c5`；sdist `9d8f945aebcbbc290b1cdb4ab17851892cb17a3b1f520ce85022b1abf592d654`。仅本地构建检查，不是发布附件；包快照之后文档继续更新。
- 独立复核无阻断问题：已将失败终态阶段改为中性文案，将超时文案准确放宽为浏览器操作；确认登录端到端真实服务关联及真实入库续跑测试，并非伪造成功摘要。

## 未完成边界

不是全仓库测试。当前Linux镜像/套件、真实平台重试、真实作者/下载/目录完成、原生Emby/Jellyfin播放、新服务器部署均未运行。历史B站canary仍失败未解决；可编辑逐平台目录、永久历史完成、真实风控暂停端到端接线仍必需。不为旧记录补造原因。Git发布在验证后另记，不因本地构建而假定已发布。

## GitHub发布

计划提交 `3e50fe1`，调度补充 `bdaeb90`。实现提交 `47eeb114cffa9268760b9a51a1bba3321565328d`，标题、说明和验证摘要为中英双语。正常推送 `https://github.com/LoCCai/media-sync.git` 成功；重新fetch后HEAD与origin/main均为此完整SHA，分歧0/0、工作区干净。本后续双语文档记录另行提交并由收尾命令核对，刻意不嵌入自身SHA。推送不附带服务器部署或恢复supervisor。
