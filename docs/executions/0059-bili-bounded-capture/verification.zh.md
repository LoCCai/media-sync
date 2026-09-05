[English](verification.md) | **中文**

# 验证记录

基线6eabc74：fresh fetch、分歧0 0、工作区干净。独立源码审计锁定MediaCrawler d6f7c5bb906b6dac40ddf343ef9e26438a3de092和bili-sync-up dcb5bb73b56ac45b2525da14b389e185b0ea6dbd，上游未修改。这些是代码发现，不是生产金丝雀根因或真人资格证明。计划冻结时尚未运行本次新实现验证，不继承0058结果；后续检查如下。

## 增量检查（并非最终源码全量资格）

- 旧bridge/scheduler首轮联合：8失败、80通过、2项Windows/POSIX跳过，99.46秒（maxfail8）。七平台旧替身缺新增manifest可选属性；实际B站协议替身缺要求的覆盖sidecar。修复测试替身，没有让生产接受缺失覆盖。旧handler完整复跑58通过、1跳过，50.27秒。
- 新bridge/receipt测试首轮因辅助函数缺inspected_stats参数，4失败/8通过，14.34秒；第二轮缺known_secrets参数，11失败/8通过，21.89秒。都是新测试构造错误，没有绕过receipt校验。修正后与原CLI联合20通过，24.95秒。四源码mypy初报bytes传入字符串coverage parser，改为严格UTF-8解码后通过。
- 原子入库27项新测试；与旧入库/checkpoint联合59通过，8.94秒，涵盖写竞争、精确Run回放、旧水位保持、来源、三个取消/租约栅栏、回滚及提交确认丢失。两文件Ruff/format与源码mypy通过；初始排序/格式问题已修。
- capability初始TDD：3失败/19通过，1.74秒；并行状态模块尚未落地时3项收集错误，2.26秒。修正API/capability/workbench子集51通过，7.70秒；追加投影后61通过，14.07秒；API/account/profile回归78通过，46.27秒。Web初检21文件572项通过，后续最终构建另记。Ruff初始一项__all__排序已修。
- 纯扫描初检40通过，1.61秒，已修页见证/边界两项审查发现。实际锁定客户端+store合同初检因环境缺aiofiles有6项setup错误/40通过，2.66秒；增加未执行功能的依赖替身并保证sys.modules恢复后，13项真实签名/HTTP模拟传输/store钩子测试通过，1.84秒。浏览器、数据库、实际文件writer被替换；不是整套上游真人执行。
- 新scheduler专项初轮2失败/6通过，18.13秒，原因是测试给要求str的cancel_job传UUID；修正后与新增真实CLI专项联合10通过，21.57秒。覆盖两种登录模式的8轮max_items1重建worker、封存篡改、空结果、提交确认丢失/最终提交重试、取消/租约/CAS与每成功单元一次pipeline入队，未执行下载。完整源码Ruff305文件、mypy128文件、compileall、uv锁校验通过。

这些选择有重叠，不能相加作为独立覆盖。并行子执行者在收尾时遇到配额限制，主执行者接手未完成测试和格式修正；不声称未完成的独立接线审查已通过。最终完整目录、包与发布结果待下方登记。未做线上平台请求或生产变更。

## 独立审查与最终源码修正

独立执行者恢复后完成只读接线审查，发现规范化作者来自context而非独立源证据、提交后修订号等值判断可能误报成功Run。现从已验证View.owner.mid计算私有作者指纹（不额外保存明文mid），父端严格核对；有界Run核对精确before/after/revision真值，不覆盖较新cursor。新增缺失/错误作者指纹用例，旧artifact解释不变。

新增真实bounded封存恢复穿过实际handler/原子DB，以及两种后续检查点推进场景（正常返回/丢提交确认）；scheduler全文件11通过，20.37秒。CLI现在也无论service返回或抛异常都核对耐久Run：未提交的假成功不能通过、丢提交确认可以耐久证据成功。六个新case与旧CLI联合7通过，15.50秒。另一次CLI重复调用安全拒绝，不能描述该接口为幂等成功回放。

第一轮完整目录先于这些最终源码修正。Unit89477：8失败/2795通过/1跳过/1项既有warning，251.72秒（七个dry-run替身缺bili_scan，旧B站确认门预期过时）。Contract16308：1失败/702通过/2跳过，360.02秒（browser-policy manifest替身缺bili_scan）。Integration37426：870通过/20跳过，278.07秒。三个句柄均终止后修复替身、新增实际creator入口钩子安装顺序测试，保留旧/新B站变体。修正CLI/bridge/capture/browser联合148通过，43.63秒，和早前测试有重叠。生产变更冻结且旧句柄终止后才重启最终目录验证。

## 最终门与环境

最终源码三个互不重叠命令：`.venv/Scripts/python.exe -m pytest -q --tb=short -p no:cacheprovider tests/unit`、`tests/contract`、`tests/integration`（句柄75650/30005/96895）。全部exit0：unit2803通过/1跳过/1既有warning，265.45秒；contract706通过/2跳过，381.04秒；integration877通过/20跳过，309.05秒。覆盖全部157个Python测试文件，合计**4386通过、23跳过**，一项既有Starlette/httpx warning。23项跳过为4项Windows/POSIX差异与19项未配置PostgreSQL用例。最终运行期间生产和测试源码均未变动，后续只整理文档。Ruff lint/format305文件、mypy128、compileall、uv锁、docs606通过。此前中文新增标题未补齐时docs校验正确报错，翻译已补。两个锁定上游工作区保持不变。收尾前fresh fetch确认仅本地冻结计划领先（1 0）。

最终Web文字（含额外WBI密钥读取）572测试/21文件通过，0.994秒；Svelte零错误/警告，Prettier和生产构建通过（33028 exit0，构建7.62秒）。0059未新增浏览器自动化；验证了文字/封闭投影渲染，不作为真人浏览器/平台证明。

最终源码`uv build --out-dir`在`C:/Users/LoCCai/AppData/Local/Temp/media-sync-0059-final-package-7bf33f2e-7793-4855-be04-943570a76efb`从sdist构建wheel。140个Python源码全部与工作区逐字节一致；wheel147成员/607007字节，sdist1022成员/2445471字节，含两个新模块。文件名审计无私有环境/数据库/上游/runtime/依赖缓存/log。首个过宽正则误报正常源码`web/src/routes/jobs/+page.svelte`；修正为根runtime检查后保留该路由、禁用项为零。这是文件名/源码完整性审计，不是真实秘密内容扫描或Linux/Docker资格。最终审查修复前的初步包已被替代；最终源码包快照之后仍在整理文档。

Wheel SHA256：`9ac67765ab2d4533cb34f167c31ad7501b6cfb78f8f2038e01220d244d064c6d`；sdist SHA256：`b9657f6f2b75b5bd2b6ed28a698ea24b008f436bb23cba2d1ca0645d22e7936b`。Docker不可用，MEDIA_SYNC_TEST_POSTGRESQL_URL未设置；Linux/Docker构建运行、真实PostgreSQL竞争、真人采集/下载/导出/媒体服务器播放仍NOT_RUN，未部署生产或恢复supervisor。

最终独立只读复核确认作者来源与CLI耐久真值修复满足原发现，未发现新增明显缺口；这不是额外测试运行。最终测试/构建句柄均终止；两项已被后续Web验证替代的旧代理句柄检查时已不存在，进程清单无匹配的遗留测试/构建命令。本次未打开新浏览器。
