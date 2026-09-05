[English](verification.md) | **中文**

# 验证记录

fresh fetch确认HEAD=origin/main `133e461007f92c7dd9444d4dd5e661887c5912d1`、分歧0 0、工作区干净。两上游锁不变；0063测试/发布为历史，不继承为0064证据。源发现中数次猜测command/preflight/request等不存在路径，已改定位真实policies/application文件；无写入。公开固定GitHub源只读成功，无平台/生产/凭据请求。

本轮实际失败、修正、冻结源码回归、Web/静态/打包、环境跳过及GitHub发布将在实施后逐项记录。未运行不标PASS。

## 实施中验证与真实失败

- 冻结计划先提交 `b60cccb`。DY补充发现签名urlencode(None)与默认HTTPX空值编码不同；实现发送真实签名原query，保留字面None且不猜造/补取token。它证明离线字节一致，不是平台接受资格。
- DY首轮94通过/4.26s，补13项边界后107通过/4.34s；独立复核107通过/4.19s。首次Ruff E501/B023修正，最终格式/mypy通过，无产品测试失败。真实锁定get_user_info/get/参数/help及Node中锁定JS被执行，HTTP/browser及execjs适配层是合成边界；不冒称真正完整PyExecJS/浏览器/平台已验收。
- 贴吧首轮32失败、116通过、2 errors：源AST去缩进改了多行JS字面值空格，另超大bytes参数生成Windows过长测试ID。保留源缩进解析及短ID后149通过/2.28s；再补真实返回dict被改昵称的拒绝，最终150通过/2.18s，独立复核150通过/2.06s。含旧贴吧Cookie组合251通过/3.51s，和前项重叠不求和。mypy两处Any return用显式cast修正；Ruff/格式/单源mypy通过。
- Root初轮shared avatar/identity/API/Cookie/repository630通过/68.64s，1项既有Starlette/httpx警告。Ruff先报15项行宽/重复分支/全宽字符诊断；格式化、合并等价分支及Unicode转义修正后通过。该实施快照期间有等价格式/分支修改，不冒称最终源码完整门。
- 六平台真实guardian/worker双跳与实际script-dispatch组合29通过/45.72s，覆盖精确Cookie私密帧、不进argv/环境/输出、清理后释放账户锁。头像专项扩至贴吧裸/时间戳URL、同CDN错作者、私网/混合DNS、重定向/超限及旧头像保留；API用另一个合法portrait验证跨作者凭单拒绝，而非仅格式错误。
- Web初轮699通过/0.979s及Svelte0错误/0警告；共享独立审查纠正了此前容易漏掉的Cookie弹窗提示、旧unsupported断言、Tieba不能使用123测试ID和头像同作者绑定。无生产请求或浏览器操作。

## 冻结源码静态、Web与打包

所有应用源码/测试冻结后才启动完整unit/contract/integration目录。冻结时 `ruff check src tests scripts`通过，`ruff format --check src tests scripts`342文件无需修改，`mypy src/media_sync`135源码文件通过，`python -m compileall -q src tests scripts`通过。`uv lock --check`62包未变，`python scripts/check_upstreams.py`2个锁定干净checkout通过；没有依赖、锁或schema迁移改变。

最终Web依次运行 `pnpm test`699通过/0.917s、`pnpm check`0错误/0警告、`pnpm build`通过/7.20s、`pnpm format:check`通过，各步非零立即退出。Vite插件耗时提示非错误；此后没有Web源码/测试更改。根README与docs改为当前能力/验证入口，不沿用0055测试数。

独立任务执行 `uv build --out-dir <0064专用临时目录>`，先sdist再由sdist构建wheel。两个包149个应用Python文件逐字节等于冻结工作区，缺失/额外/不一致均0。应用源码树SHA256 `595b012cc19da2a98137cfbc5a7ed0b4e7a6ccb5c910f82c3cdc0445728eb81b`（按ordinal路径排序，拼接相对src路径+NUL+文件SHA256+LF，再SHA256）。

- Wheel：156文件、657055 bytes，SHA256 `7a2ebc887f8af0826c6d1b3afc20fcaa2a599fe1ce2a884e071580218c0f1b37`。
- Sdist：1107文件、2669684 bytes，SHA256 `57c2a33f14519c2759b7b8d6e0ede6e2a6b7cd3c6771e248e65e5898c573b839`。
- 156条RECORD的hash/size、迁移Mako、名称/版本/Python约束、依赖（含keyring可选项）及CLI入口通过。无危险路径/重复/大小写冲突/链接/特殊成员；4个私密名称候选确认为静态docs/archive双语及web jobs/library源码，逐字节相同。此为成员与源码审核，不是全面秘密内容扫描。

包中的文档是构建快照，不包含随后docs/README/验证补录，不是最终发布附件或安装/部署证明。DY源码SHA256 `334ffb0722531fd8aab2de681900478f6813a51fb8c490d882486647ab4bd395`；贴吧 `ef33cda5056934c1519535541ddf08a19db95f48602cd67d1bae0c9830345354`。

## 完整目录与环境边界

最终三个互不重叠完整目录均通过，合计**5841通过、37项环境跳过**；unit另有1项既有Starlette/httpx警告。专项不重复累加；之后未改应用或测试，Root独立重算149文件应用树与包审核完全一致。

| 完整目录 | 实际结果 | 本地报告 |
| --- | --- | --- |
| unit |3875通过、2跳过、1警告 /306.36s|`artifacts/final-unit.xml`|
| contract |968通过、2跳过 /426.83s|`artifacts/final-contract.xml`|
| integration |998通过、33跳过 /353.59s|`artifacts/final-integration.xml`|

从仓库根目录复跑本次精确命令：

```powershell
.venv/Scripts/python.exe -m pytest tests/unit -q --tb=short --junitxml=docs/executions/0064-douyin-tieba-profiles/artifacts/final-unit.xml
.venv/Scripts/python.exe -m pytest tests/contract -q --tb=short --junitxml=docs/executions/0064-douyin-tieba-profiles/artifacts/final-contract.xml
.venv/Scripts/python.exe -m pytest tests/integration -q --tb=short --junitxml=docs/executions/0064-douyin-tieba-profiles/artifacts/final-integration.xml
```

原始报告保存在本地docs并按既有artifacts策略忽略Git，命令/结果入版本管理。报告SHA256依次为unit `34481aefc252c5586545da8ce5de6b02ab14f511b5e6cc71fbf85358663a341b`、contract `486e7b8bbbcd500c94fafcc4357a6740cae8c69b1b5ce7d67cee4352cab06b81`、integration `769c48bc7f519a56f18c24b1c80e63070fe262ca469e60385e948051fa76de0c`；复跑时耗时/时间戳使哈希变化属正常。跳过32项真实PG检查及5项POSIX权限/启动器/耐久检查，不把Windows替代当原生验证。最终文档652份通过、diff检查通过；独立文档终审无未解决发现。暂存前fresh fetch仅计划提交领先1/落后0。

Docker命令当前不可用，`MEDIA_SYNC_TEST_POSTGRESQL_URL`未设置。当前Linux镜像/原生权限耐久、真实PostgreSQL、平台/CDN字节、真人登录/资料/采集/归档、Emby/Jellyfin原生播放及生产supervisor均NOT_RUN。历史已授权但失败的B站canary未重试/未改标成功；六平台资料不等于七平台闭环完成。
