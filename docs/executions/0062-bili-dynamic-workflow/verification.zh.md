[English](verification.md) | **中文**

# 验证记录

fresh fetch：HEAD/origin为`76165b0`、分歧0 0、工作区干净。锁定MediaCrawler d6f7c5bb906b6dac40ddf343ef9e26438a3de092及bili-sync-up dcb5bb73b56ac45b2525da14b389e185b0ea6dbd不变。只读源发现仅使用本地文件和公开GitHub/raw固定SHA文件，未请求目标平台或接触凭据。冻结计划时未跑新测试；0061结果为历史，不继承。

探索时PowerShell传入字面通配路径被rg拒绝，另有猜测subscriptions.py路径不存在；已列出真实文件并改读subscription_policy.py。均为不写数据的源发现错误，不是产品测试失败。后续逐项记录实际验证结果。

## 实施中验证与真实失败（非最终源码全量）

- 初始并行集成时bridge先引用尚未落盘的multifeed，子任务pytest出现collection阻断；模块落盘后恢复。解析测试先出现3项字符串strip预期不符，后5项不可变mapping/tuple断言不符，修正测试而未改变领域语义。
- Root首次旧Bili bridge/入库/scheduler/CLI组合：77通过、1失败（旧无动态策略拒绝异常类型变化），修正为RepositoryError。新bridge组合先5失败/32通过（合成item漏visible=True），再5失败/5通过（测试错误复用已封存attempt），改为独立后续manifest后5通过/8.90s。
- 新scheduler首轮2失败/22通过：测试runner误写async及读取不存在outcome；改为真实同步runner接口/status后2通过/7.99s，无生产调用。
- parser/capture/normalizer聚焦284通过/4.47s；multifeed/policy/原scan聚焦154通过；refresh第一阶段53通过/1.84s、独立复核既有70通过/4.39s。都是实施中的重叠快照，不求和。独立反例仍发现OPUS缺少buvid3门、无效组件时提前取全文、重复nav与unsupported被压成generic，另行修复。
- Root CLI动态+原CLI+scheduler组合23通过/61.95s；scope成功回读修正+原bounded ingestion32通过/3.95s。新增CLI明确scope和事务内scope复核后仍需再跑最终组合。
- 中间Web全目录640通过（命令过滤参数未缩小到3个文件）；Svelte检查0错误/0警告。后续又增加UI测试，不作为最终Web数。若干Ruff行宽/import和mypy可空类型问题逐项修正；未把先前失败命令末尾的成功静态命令当成整组PASS。

最终源码冻结、最新回归、包验证、环境跳过和发布结果随后单列。以上绝不代表Docker/Linux、PostgreSQL或真实平台登录/采集/下载/Emby播放合格。

## 独立审查修正与完整目录快照

- 图片刷新子任务中间组合480通过/4失败/120.49s；4项是测试对新边界的异常类型预期不符。修正后pipeline14通过，最终refresh/detail/pipeline139通过/10.65s。相互重叠，不求和。
- scope审查复现切到v2范围后旧v1零内容artifact仍可发布。CLI现显式检查v1 None和v2范围；事务区分旧直接调用省略scope与显式传None。加载至创建Run的竞态、切范围/改数量后成功回读均补回归；中间scope/fences/capabilities/API52通过/16.07s，1项既有警告。
- 快照审查复现进程退出后留下损坏最终digest文件；现用私密完整文件fsync、原子无替换发布和目录fsync代替直接写终态。独立最终组合72通过/1项POSIX跳过/17.98s，包含真实子进程写一半、发布前/后退出；Windows未执行POSIX原语。
- 最终错误分类修正：动态不支持/身份/结构错误终止Job但不影响账户熔断；专项49通过/1.31s。

完整目录在最后快照/错误分类修正前启动，三个报告均是**中间完整目录快照**，不是最新源码全量证据：

| 目录命令 | 实际结果 | 本地报告 |
| --- | --- | --- |
| `python -m pytest tests/unit -q --tb=short` |3303通过、1失败、1跳过、1项既有警告 /295.86s|`artifacts/directory-unit-snapshot.xml`|
| `python -m pytest tests/contract -q --tb=short` |812通过、2跳过 /423.23s|`artifacts/directory-contract-snapshot.xml`|
| `python -m pytest tests/integration -q --tb=short` |1001通过、33跳过 /384.55s|`artifacts/directory-integration-snapshot.xml`|

各命令均附加此执行目录下的 `--junitxml`；源码变化后将原final-*改名directory-*-snapshot。唯一unit失败为新增第67条路由后认证清单仍断言66；修正名称/计数，同时保留精确公开白名单及逐路由默认拒绝断言。认证完整文件随后20通过/9.40s，有1项既有Starlette/httpx弃用警告。原始报告按项目既有artifact策略留在本地docs并忽略Git；可复跑命令、结果和最终文件清单已入文档管理，不含生产执行证据。

## 冻结源码静态、Web与打包门禁

最终应用源码冻结包含快照崩溃修正和不熔断分类；`bilibili_multifeed.py` SHA256为 `8b7ad3afca4876b8fc5b20e788b81c4ac7efa7287817724de6eeb2d525782509`。

- `ruff check src tests scripts`通过；`ruff format --check src tests scripts`325文件无需修改；`mypy src/media_sync`130源码文件通过；`python -m compileall -q src tests scripts`通过。
- `uv lock --check`62包、未变；`python scripts/check_upstreams.py`两个锁定干净上游通过。无依赖/锁文件/schema迁移变化。
- 最终Web `pnpm check`0错误/0警告；`pnpm test`642通过；`pnpm build`通过（构建9.55s）；随后 `pnpm format:check`通过。此后未修改Web，未新开浏览器或操作生产。
- 独立任务在新临时目录执行 `uv build`，先sdist再由sdist构建wheel。两包包含144个当前应用Python文件（2,838,221 bytes），逐文件字节相等，缺失/额外/不一致均0。命名源码树digest为 `a45097974b8417b8e87077e2791f39f796c80c611782680cb2ec3e621a0df35f`。
- Wheel：151成员、635,968 bytes，SHA256 `e1970bf9e8bd0a88c4b7526076a5e68390db5be99434147ec26d21d89f4f551d`。Sdist：1068成员、2,585,459 bytes，SHA256 `3128fe193618fd2743cbb7bf36a8b6aac3e10e6aa5943a4a23b849f8842b1d70`。CLI入口和Python>=3.11,<3.14元数据正确；危险路径/重名/链接/特殊成员/私密runtime名称候选均0。此为成员名称及源码字节审核，不是全面内容秘密扫描。Sdist文档是构建时快照，不含随后验证追加；临时包不是发布附件或部署证明。

Docker不可用，`MEDIA_SYNC_TEST_POSTGRESQL_URL`未设置。Linux/macOS原生文件系统耐久、真实PostgreSQL竞态、当前容器、平台请求/CDN字节、真人登录/采集、Emby/Jellyfin原生播放及supervisor运行均NOT_RUN。之前已授权但失败的B站canary未重试，也未改标PASS。

## 最终冻结源码受影响回归

[affected-tests.txt](affected-tests.txt)中的34个文件在最终冻结应用源码上同次运行：**1250通过、15跳过、1项既有警告，340.04s**。跳过为13项真实PostgreSQL归属测试和2项Windows不适用POSIX测试；警告为既有Starlette/httpx弃用提示，无失败。覆盖全部0062新增测试、投稿兼容、范围编辑/成功回读竞态、scheduler/归属/安全及67路由认证清单；不冒充新一轮完整目录全量。之后未改源码或测试。

在仓库根目录PowerShell复跑（已提交的文件精确列出本次执行范围）：

```powershell
$affectedTests = Get-Content docs/executions/0062-bili-dynamic-workflow/affected-tests.txt
.venv/Scripts/python.exe -m pytest @affectedTests -q --tb=short --junitxml=docs/executions/0062-bili-dynamic-workflow/artifacts/final-affected.xml
```

本地报告SHA256：最终affected `2353b945d6f39219d002721e7ed3adba19e7b206b0feaa1a4d36723f16d6a970`；目录unit `debdea55f1b594491dae229860f07e265ba6eaf02d3a2148d191f5e7ee8bc344`；contract `3c2e91f6d8032679e5d3e09012626d87c2b1bdf3f0068637fc327b3bb8530ec3`；integration `1d5ed212a96f99d762fa74cdd3616799aa75680594808231381a2fe8928dca01`。以后复跑受时间戳/耗时影响，报告哈希自然不同。`python scripts/check_docs.py`632份Markdown通过，`git diff --check`通过。暂存前fresh fetch确认本地仅计划提交领先1/落后0；发布另记。
