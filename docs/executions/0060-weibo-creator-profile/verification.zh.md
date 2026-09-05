[English](verification.md) | **中文**

# 验证记录

基线fresh fetch：HEAD/origin均1b9b516，分歧0 0，工作区干净。上一执行已完成测试仅为历史证据，不作为本增量验证。计划冻结时尚未运行新实施测试。没有真人平台请求或生产变更。

## 增量检查

仓库/effect/迁移：`.venv/Scripts/python.exe -m pytest -q --tb=short -p no:cacheprovider tests/integration/test_creator_profile_repository.py tests/integration/test_creator_profile_effect.py tests/integration/test_creator_profile_migration.py`，67通过、5.33秒，句柄23582已终止exit0。先于最终runner/UI，不是全仓库资格。主执行者初次Ruff指出负面fixture有意使用的全角数字，改为Unicode转义后由formatter解决因此产生的长行。四个修改的应用/仓库源码mypy通过。最终lint及联合回归稍后记录。

## 专项验证及修正

主执行者联合命令初次引用不存在的tests/unit/test_api_auth.py：exit1，未运行任何测试。改正的API/profile/Cookie仓库选择88通过/1失败/1项既有warning，35.69秒（18757 exit1）；新跨账户fixture重复微博账户名称，触发有意的平台/名称唯一键。fixture改为不同名称，没有放宽生产约束。头像平台绑定修复后联合选择tests/unit/test_api_creator_profiles.py、test_api_cookie_login.py、test_creator_avatar.py、test_operator_auth_api.py、test_workbench.py、test_api_workbench.py及tests/integration/test_cookie_account_repository.py，**433通过**，1项既有Starlette/httpx弃用warning，66.89秒（12942 exit0）。

runner分工过程：既有B站unit/upstream69通过，加入WB/旧runner/process联合125通过，最终自有联合141通过、22.89秒。新锁定微博合同初次10项setup错误、2.11秒，原因是测试venv缺tenacity；改为明确禁止进入原重试装饰器的依赖陷阱，证明原decorated request未执行，不宣称测了真实tenacity。测试闭包Ruff B023改用默认参数绑定，最终变化的微博合同复跑10通过、1.74秒。合成Playwright边界覆盖保存会话/Cookie，内部使用真实锁定client与MockTransport，不作为真实浏览器/平台证明。私密两跳进程测试是真实本地guardian/worker加效果替身，不是真人认证。

头像unit281通过、5.16秒（首轮也是281通过；首次Ruff有1处长行，已修）。覆盖合成窄URL规则、保留B站专用校验器、不继承凭据/代理、静态PNG、公网DNS、重定向、大小/解码边界；后续433联合包含最终平台绑定生产修正。

Web首轮专项114通过/1失败，因Prettier折行导致静态文案断言失败，改为归一化空白，不放宽控制器门。最终`pnpm exec vitest run src/lib/utils/creator-profile.test.ts`115通过；`pnpm test`21文件635通过；`pnpm check`零错误/警告；`pnpm build`exit0（62455已终止）；`pnpm format:check`及Web diff空白检查通过。未新增浏览器UI/真人平台资格。所有专项有重叠，不累加为独立覆盖。

## 最终源码检查及打包

实施/测试源码冻结后，主执行者启动三个不重叠完整目录命令`.venv/Scripts/python.exe -m pytest -q --tb=short -p no:cacheprovider tests/unit`、tests/contract及tests/integration（92134/71009/77951），最终完成结果下方登记。Ruff `check src tests scripts`及`format --check src tests scripts`307文件通过；mypy src/media_sync126源码通过；compileall、uv lock --check、docs614及两个锁定上游检查通过，上游工作区干净。Docker不可用，MEDIA_SYNC_TEST_POSTGRESQL_URL未设置。Linux/Docker/真实PostgreSQL/真人登录/采集/下载/导出/播放仍NOT_RUN；未改生产或恢复supervisor。

独立`uv build --out-dir`使用新目录C:/Users/LoCCai/AppData/Local/Temp/media-sync-0060-package-b9e09465-de46-4f56-9725-5f339b6cd00d，77843终止exit0。Wheel608620字节/147成员，sdist2469173字节/1032成员；两归档全部140个应用Python文件与工作区逐字节一致，缺失/额外/不一致均0。成员名检查无私有env、DB、runtime、log、cache或上游checkout；允许.env.example及artifacts/README.md，不误报正常web/src/routes/jobs/+page.svelte。两次inline ZIP/TAR检查均exit0。这是文件名/源码完整性审计，不是全面秘密内容扫描。614文件快照之后仍在定稿文档，因此仅声称源码一致。

Wheel SHA256：`ee89c711b3d227231f302f0207443d9fe28346158f0b0cb10ec5fd89ff1da470`；sdist SHA256：`ac5f4a0ea4d6fd971a8e41b8a90cb2064f7a5b15f6f6c5a2a0f36c118da71af4`。

## 完整目录最终结果

三个最终句柄均终止exit0：unit92134 **3113通过、1跳过、1既有warning，335.44秒**；contract71009 **718通过、2跳过，458.06秒**；integration77951 **898通过、20跳过，368.37秒**。不重叠目录覆盖全部159个Python测试文件，合计**4729通过、23跳过**。跳过为4项Windows/POSIX差异与19项未配置PostgreSQL，不作为执行证明。最终运行期间生产/测试源码未变，之后只有文档修改。全部本次测试/构建进程均报告终态，未启动浏览器服务。

最终独立只读复核确认资料平台头像栅栏和实际锁定client两次请求合同测试，无新增可复现阻断。实施提交前fresh fetch确认远端不变，仅本地冻结计划领先（1 0）。最终双语实施/发布提交和push结果随后记录。

## 发布

双语计划`83ff442`和实施`315b2ff`已通过非force的`git -c http.sslBackend=schannel -c http.version=HTTP/1.1 push origin main`发布（exit0）。随后同传输选项fresh fetch exit0；HEAD和origin/main均`315b2ff26807ce79ac0431b18398d221482e44dc`，分歧0 0，本条最终文档记录前工作区干净。发布前docs614及Git空白检查通过；最终测试/打包后无源码修改，无部署/真人操作，整体目标保持活动。

本发布记录另行双语提交、非force推送，并fresh fetch核对相等；自身SHA交接时报告，不递归写入自身。
