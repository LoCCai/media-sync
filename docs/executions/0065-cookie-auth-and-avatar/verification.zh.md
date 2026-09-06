[English](verification.md) | **中文**

# 验证过程

干净基线HEAD=origin/main9ac392f98b65a15bc88e6e7faa6b011a1e5744fb，分歧0 0。只读路径猜测失败后用rg定位。初始仅头像计划草稿在提交前被EOF空白检查拦截；新来源发现后改成本范围，冻结计划前无应用编辑。当前门全部待执行，不继承旧全量/真人PASS。

## 实现检查点及实际修正

先提交计划3ecab22。共享首轮700通过/80.83秒，另1条既有Starlette/httpx警告，涵盖精确解析/可选头像/service/凭单/订阅及旧认证保留；新增平台远端模块在实现中单独验证。本地JUnit artifacts/shared-initial.xml按既有artifacts规则忽略。随后root仅Ruff导入排序修正，不冒称该快照又跑全量。

Web初期两次各1失败/700通过：同一测试连续两处旧“仅昵称”文案断言。已改为知乎有限头像、快手/抖音仍仅昵称的实际范围。补七平台/cp.api_ph/小红书边界断言后，最终701通过/0.905秒；Svelte0错误/0警告，build通过7.33秒，Prettier通过。末尾新增的只有测试断言，构建源码未变；各次重叠Web快照不累加。

编辑中的静态快照见尚未收尾代理文件27条Ruff/8条mypy，代理自行修正；root后续1条导入排序Ruff已修。当前全Ruff检查通过、format349文件无需变动、mypy137模块通过、compileall通过；662份文档、2个干净锁定上游与uv lock62包通过。最终冻结回归/包/发布另列，不称0065完整目录全量。

## 平台与进程检查

- 抖音最终153通过/1.16秒。初始1失败/127通过因空SecretValue在适配器前被拒，测试误期待适配器类型化失败；改用非空坏请求头测试。中间128通过快照早于最终登录矛盾/网络分类补充。最终Ruff/format/mypy通过；源码SHA25689148098135633992c5b7ca9bbacf68fee15a8e65e45daeea7d625136012abad。
- 快手初始149通过/1.87秒；补传输边界后168通过/1.91秒，无pytest失败。静态行长/类型收窄/Any返回问题已修。真实锁定constructor/post、CP Cookie/body、单请求、原始JSON和返回对象替换/篡改检查通过。源码SHA2566a8d40a0369a7cb903e7fd74d43a3b813b1b2b5743b497f06e34fb0a2f7c8458。
- 独立真实script worker12通过/15.42秒，验证两平台分派、相同类型化异常、Cookie仅stdin、argv/env/公开stdout/stderr无泄露，无额外网络/文件。最初夹具过早屏蔽subprocess/socket误伤Windows asyncio/Popen初始化；修正合成护栏时机，未改应用。
- 首次33文件受影响联合为**1失败/1817通过/173.45秒**，另1既有警告。Cookie硬杀父进程测试看到两个PID结束后，立即取OS锁返回False。原结果保存在artifacts/final-affected.xml，SHA256f5c4675d6adba64fea6e95c6d020afec006159fef471065bbbf8c487af93a0e6。后来同一个失败临时fixture实际取锁成功并释放；原node单跑1通过/3.86秒。临时只读WinError诊断1通过/2.28秒，看到kill前预期共享违规32、退出后取锁成功，未复现确切瞬时失败，不能据此证明精确内核原因。
- 只将该测试立即取锁断言改为5秒内必须获得真实锁，与已有QR硬杀父进程合同一致。kill前拒绝和两个进程退出仍必需；一直占锁仍失败。未改生产锁/清理代码。process+script worker复测22通过/25.90秒。这是有界观察修正，不冒称修复生产生命周期；最终33文件重跑另列。

## 最终包审计

首轮只构建一次；审计脚本修正了Python范围顺序语义等价、已知静态artifacts/README.md路径和带换行py.typed的三处假设，不是产品缺陷。代理临时服务错误后未重复构建。测试锁等待修正后另建最终专用临时包并审计通过，已包含该最终测试字节。

最终目录C:/Users/LoCCai/AppData/Local/Temp/media-sync-0065-final-package-audit-c075a40a18d840029c75b0d6739ae4a9。`uv build --out-dir <新目录>`先建sdist再从中建wheel。两包各151应用Python源码，缺失/多余/字节不符0。应用树SHA256 **1017ce5f18967035bf64d58702e19b547853b3e741a9e813956d8f8d0d8957a5**；root在测试修正后独立重算匹配。算法为src相对路径ordinal排序，拼接path+NUL+文件小写SHA256+LF后整体SHA256。

| 最终包 | 字节/成员 | SHA256 |
| --- | --- | --- |
| wheel |662935字节/158|3700a52ebeae8be70d1518aa7f6bbb0800e10f7b6afa5f9613856c2a4182b6db|
| sdist |2709558字节/1124|227fbd28ce46a6b7efac69db282fc844421cb3e4491779e7bd823d2c4f62cdeb|

158条wheel RECORD哈希/大小、安全唯一非link/特殊成员、源码字节、名称/版本/Python语义、11依赖含可选keyring、CLI、py.typed和迁移Mako均通过。5个私有路径名候选为已核对的静态artifacts/docs/archive和web jobs/library源码，非运行数据；不是综合内容秘密扫描。sdist文档是本次最终验证/发布记录写入前快照，不是最终发布附件或安装/部署证明。

Docker不可用，MEDIA_SYNC_TEST_POSTGRESQL_URL未配置。当前Linux镜像/原生权限/耐久、真实PostgreSQL、平台/CDN字节、真人Cookie/登录/资料/采集/归档、原生Emby/Jellyfin播放和supervisor均NOT_RUN。无真人请求、用户Cookie、生产重试/部署/supervisor恢复。七平台本人验证有实现不等于七平台真实全流程完成。

## 最终冻结受影响回归

测试观察修正后，同一33文件受影响完整选择 **1818项通过/187.54秒**，无跳过，1条既有Starlette/httpx警告。范围为相关unit/contract/integration的Cookie/profile/avatar文件，不是全仓测试目录。此后未改应用/测试。报告artifacts/final-affected-recheck.xml，SHA256 `616caaea2fa0679ee40aa3481c11a4e7b49294f8b18551940dca79904128df3b`；首轮失败报告独立保留，不累加先前重叠模块/process/shared选择。

仓库根目录复跑：

```powershell
$task0065Tests = @(rg --files tests | Where-Object { $_ -match '(cookie|creator_profile|creator_avatar)' } | Sort-Object)
.venv/Scripts/python.exe -m pytest @task0065Tests -q --tb=short --junitxml=docs/executions/0065-cookie-auth-and-avatar/artifacts/final-affected-recheck.xml
```

最终完整Ruff检查/格式、mypy137模块、compileall、Web701/check/build/format、docs662链接、2个锁定checkout、uv lock62包及diff检查在上述冻结快照通过。原始JUnit保存在本地docs/artifacts，按既有规则Git忽略；本文版本化命令/准确结果/失败。未将任何环境跳过藏成通过，上述真实平台/OS门仍NOT_RUN。

提交前fresh fetch仅计划领先1/落后0，源码/测试修改均本任务所有，无运行数据/凭据/上游变更。GitHub发布将在实际正常push/fresh-fetch比较后另记。

## GitHub发布

双语冻结计划3ecab22与实现e149f5059a3a695eebaf5f8ddc12d91084d9550e已正常推送至https://github.com/LoCCai/media-sync的origin/main，未强推。fresh fetch确认HEAD=origin/main同一完整实现SHA，分歧0 0且工作区干净。实现仅暂存41个本任务源码/测试/Web/双语文档文件；未提交凭据、运行数据、原始JUnit、临时公开checkout或包。

本发布记录另作双语纯文档提交，再正常push/fetch核对，应用/测试保持冻结。未安装/部署、请求真实平台、重试B站canary或恢复supervisor。小红书资料、更广头像/媒体与真实环境验收仍是活动原目标的一部分。
