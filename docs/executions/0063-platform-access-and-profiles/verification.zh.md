[English](verification.md) | **中文**

# 验证记录

fresh fetch确认HEAD=origin/main `cc3ab9341636d45fb8a890829f68be982a70a5b7`、分歧0 0、工作区干净。仅源审查，无生产/平台请求、凭据或浏览器操作。一次猜测creator_input.py路径不存在，已用rg定位真实capability/policy文件。冻结时未跑新测试；0062结果为历史，不继承。实施中的真实失败、最终冻结源码回归、打包、跳过与发布在此逐项记录。

## 实施中验证与真实失败

- 源码前提交冻结计划 `c75c5ed`。公开GitHub API源发现遇共享IP限流，固定raw仍可读；未反复重试API或请求平台。
- 贴吧新增解析/私密帧69及真实锁定get/HTTP32通过；子任务最终组合221通过/3.98s。较宽Cookie组合271通过/1失败/35.65s，暴露能力断言仍写死四平台；Root改五平台后API/能力68通过/24.38s，含私密保存、失败替换保留和数据库/操作输出无秘密。
- 快手独立模块及真实锁定方法/browser-transport65通过/1.87s，独立复核同组合65通过/1.72s；测试中的Ruff异常类型/闭包绑定问题已修，该组合无产品测试失败。
- 知乎首轮72通过/12失败：合成self响应使用预读取json=响应体，真实iter_raw抛StreamConsumed；改显式ByteStream后84通过/5.17s。实际执行锁定client/get/get_creator_info/help.sign及本机Node运行锁定签名JS，仅HTTP/browser为合成边界，无平台调用或真实Cookie。
- Root初始共用runner/repository/API136通过/18.40s，新身份/API85通过/21.53s。测试import/行宽问题格式化后重验，未把后续命令成功当整组成功。
- 实际脚本worker复现首轮4失败/5.74s：重复__main__/canonical类型导致成功变result_invalid、平台_LookupFailure变temporary。之后组合快照41通过/5失败/28.02s，含这4项及URL输入仍预期422（现在平台校验固定400）的旧断言。一次组合patch因API上下文不匹配未应用；正确补丁与canonical alias后4通过/5.39s。保留失败过程，不覆盖或以重跑隐藏。
- 独立复核还复现长快手/知乎合法ID被API max20拒绝；改max255、各平台独立约束和UI动态标签，补快手128/知乎255成功及超限拒绝。JSON转义孤立surrogate昵称现于成帧/入库前拒绝，正常Unicode代理对仍可用。
- 最终源码修正后worker/共用runner/API/知乎组合178通过/28.64s，1项既有Starlette/httpx警告。四平台真实双跳进程套件17通过/27.54s，Cookie不进argv/环境/公开输出，进程清理后才释放账户锁；上述组合重叠，不求和。

源码冻结时静态检查：Ruff通过、format336文件无需改、mypy133源码通过、compileall通过；uv lock62包未变、两个锁定干净上游通过。当时Web671通过、Svelte0错误/0警告、production build7.39s及格式检查通过；随后账户页旧文案修正与Web重验单列。完整Python目录在应用源码冻结后才启动，精确结果和包审查随后单列，不宣称当前Linux容器/真实PG/平台/CDN/Emby/Jellyfin或生产supervisor已通过。

## 完整目录回归与环境边界

三个完整目录均在最终应用源码冻结后启动。首轮unit为3565通过、2失败、2跳过、1项既有警告/296.33s：微博旧测试仍把新增快手/知乎断言为unsupported，实际已进入凭据检查并返回auth_expired。仅修改该测试的能力/缺凭据预期，完整文件随后49通过/1.03s；应用源码、contract和integration测试没有变化。完整unit复跑另记，不把失败首轮写成通过。

| 目录命令 | 实际结果 | 本地报告 |
| --- | --- | --- |
| `python -m pytest tests/unit -q --tb=short`（首轮） |3565通过、2失败、2跳过 /296.33s|`artifacts/final-unit.xml`|
| `python -m pytest tests/contract -q --tb=short` |890通过、2跳过 /410.66s|`artifacts/final-contract.xml`|
| `python -m pytest tests/integration -q --tb=short` |999通过、33跳过 /359.22s|`artifacts/final-integration.xml`|
| `python -m pytest tests/unit -q --tb=short`（修正旧断言后） |3567通过、2跳过 /272.83s|`artifacts/final-unit-rerun.xml`|

最终三个不重叠Python目录合计**5456通过、37项环境跳过**，unit有1项既有Starlette/httpx警告；不计首轮失败和重复专项。最后unit报告SHA256为 `f78b055692fd32ec990f4f536dadfb30b122f351e2d0de74ebe57ff33bb2cf91`。之后未改Python应用或测试；contract/integration原完整结果继续对应同一冻结应用及各自测试。

实际执行使用仓库根目录 `.venv/Scripts/python.exe`，各命令附加 `--junitxml=docs/executions/0063-platform-access-and-profiles/` 后接表中报告路径。原始JUnit按既有artifacts策略保存在本地docs但忽略Git，可复跑命令/结果随文档提交。首轮unit/contract/integration报告SHA256分别为 `81dd59cf0746561d87542c91a6c6c4e202f4399891bd93f69fbbab31412b3512`、`2da2c3d9385e532d3b72ca1707f3fbe7a3e1fd8f2e95ed0382e2ca94d97cd9c6`、`2b17dd482b807f29408c7b9728d700ea6ae7f2c841f9619dcdc1889007581ed3`；后续复跑因时间戳/耗时自然有不同哈希。

当前Docker命令不可用，`MEDIA_SYNC_TEST_POSTGRESQL_URL`未设置。集成跳过包括32项真实PostgreSQL检查和1项POSIX启动器；unit两项POSIX耐久/权限、contract两项POSIX启动器/权限跳过。Windows私密进程测试不等于Linux原生权限验收。当前Linux镜像、真实PG竞态、平台/CDN请求、真人登录/采集/归档、Emby/Jellyfin原生播放和生产supervisor均NOT_RUN。既有失败B站canary未重试或改标成功。

## 冻结应用源码打包与静态门禁

- 独立任务在0063专用临时目录执行 `uv build`，先sdist再由sdist构建wheel。两个包各147个应用Python文件逐字节与冻结工作区一致，缺失/额外/差异均0。应用树SHA256为 `55b67aa53417d19993af387047d7efcd2c2914b2788e5f0a6423c5d157993d63`。
- Wheel：154文件、646649 bytes，SHA256 `370e80932db83f2c74d615fd0a19f1bae518afd979f0cac0c3b99cc93a6b7d3e`；sdist：1091文件、2630371 bytes，SHA256 `96a0a90591eaace441584f3ef71875596d25eed79c41c4a791d8420eff75177d`。154条RECORD、Mako字节、Python `>=3.11,<3.14`、CLI入口和依赖元数据通过；无重复/大小写冲突/链接/特殊成员/危险路径。
- 私密名称筛查3个候选逐字节确认为两份docs/archive源文档和web/routes/library源文件，并非运行数据。此为成员名称/源码审核，不冒充全面内容秘密扫描。审计脚本先误选uv生成的.gitignore为tar、再将这些名称视为候选，修正筛选后通过，无构建产品缺陷。
- 命名树算法为按路径ordinal排序后拼接 UTF-8 `path + NUL + SHA256(bytes) + LF` 再SHA256，应用路径相对src。wheel完整文件树 `a1cfd2808164869a1bc9351314320d6d7b05ed8360545558e4edd690f9777f62`，sdist完整文件树 `e0ec899519bfcd4dbd391f0cea628cf8d71f9e017f629054acae96f7572ba13a`。包是应用源码冻结快照，不含随后unit断言、账户页文案及文档补录，不是发布附件或部署证明。Root最终独立重算147文件应用树完全相同；第一次PowerShell文化相关排序产生不同摘要，改Ordinal后与包审查一致，非源码漂移。
- unit旧断言修正后重验 `ruff check src tests scripts`、`ruff format --check src tests scripts`（336文件）、`mypy src/media_sync`（133源码文件）、`python -m compileall -q src tests scripts`均通过。文档初检642份通过；最终追加后再次检查。暂存前fresh fetch仍仅本地计划提交领先1/落后0。

## 最终用户文案与Web重验

只读终审发现账户页四平台条件下仍显示旧两平台提示、部署指南旧章节仍称贴吧不可用/五平台资料未实现；已修正双语指南及账户页文字，并更新既有UI接线断言。此前Web结果保留为前一快照，不冒充修改后验证。

最终在web目录依次运行 `pnpm test`（671通过/1.11s）、`pnpm check`（0错误/0警告）、`pnpm build`（通过，9.36s）及 `pnpm format:check`（通过），每一步非零立即退出。Vite输出插件耗时提示，不是构建失败。之后未改Web源码/测试；本轮没有浏览器实测或平台调用。最终docs/diff检查及发布见后续记录。
