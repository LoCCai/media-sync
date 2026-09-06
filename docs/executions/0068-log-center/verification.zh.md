**中文** | [English](verification.md)

# 验证记录

冻结计划时确认HEAD=origin/main=d600ed5、工作区干净。未访问生产或触发登录。

## 最终源码证据

- [最终专项](artifacts/verify_final_log_center.py)：**356通过、1警告/122.43秒**，无跳过。覆盖store、API/诊断包/配置、CLI、生命周期、真实child通道/session绑定、精确登录失败关联、后台认证及supervisor。警告为既有Starlette/httpx TestClient弃用提示。
- [真实API到TypeScript契约](artifacts/verify_api_web_log_contract.py)及[内存辅助脚本](artifacts/verify_api_web_log_contract.cjs)：PASS。实际迁移DB、后台鉴权、持久片及真实前端controller/下载投影。四API匿名401，鉴权后200/no-store；/logs和/jobs匿名HTML303，登录返回接受/logs。保留200条控制事件、64个关联、截断提示、微秒及writer健康，无私密哨兵泄露。不是浏览器点击或真人平台验收。
- Web：24文件/767通过，1.36秒；检查0错误0警告，构建8.91秒，Prettier通过。含49个日志controller专项及新增登录返回用例；早期765/766已取代，不累计。
- Ruff检查/格式374文件、mypy145源码文件、compileall、上游锁定、uv lock、文档694个Markdown及git diff检查通过，提交前再次检查文档。
- 最终源码包位于系统Temp/media-sync-0068-final-4207a9834c364c93b8d511145564a2e9：wheel/sdist内160个应用Python文件与工作区逐字节一致，由0066 check_package_sources.py验证。wheel SHA256为b11fbebccdfb2e483ed8e46b0a7e04bf4d64815feef0642865651eef54027953，sdist为d1d7bd683921d059f1dfd04a47c52e3eb1587ba901f9b33e47599b2907ed3dc5。之后仅改文档/测试工具，故包已验证源码，但不是最终文档快照。没有安装/部署。

## 较早运行及修正

- [较广快照](artifacts/verify_log_center.py)：2531通过、12跳过、3失败/834.23秒，开始时尚未纳入最终store关闭修正。三处旧FixedRunner测试桩缺diagnostic_hook，导致意外错误分类；现已断言hook并将真实阶段送入实际service→store→API→诊断包，全部45项登录诊断随后通过并纳入最终356。不能把较广快照称最终全绿，不累加重叠组合。
- 较广12跳过为1项POSIX venv启动器及未设置MEDIA_SYNC_TEST_POSTGRESQL_URL的11项PostgreSQL竞态，均NOT_RUN，不是通过；历史六千余全量未重跑。
- 初始API组合3失败/47通过：新fixture使用不存在的Operation状态failed，改为failed_retryable。初始CLI2失败/93通过：旧假构造/精确kwargs断言缺event_sink，现要求正确可调用接线，均纳入最终专项。
- 审查复现idle-close退出未封片、idle同步封片绕过超时、暂时rename失败使写入持续失败及writer线程启动恢复。确定性修正已通过；最终组合含70个store用例，含Windows真实spawn及文件系统验证，没有放宽容量/schema/生命周期保证。
- 登录代理295通过/119.63秒、生命周期207通过/14.82秒为重叠证据。登录含53新例及真实离线child→service→封存片成功/超时。严格v1仍仅schema_version/status，遥测不能授予认证、伪造关联或泄露原文。
- 最后跨层审查发现/logs登录返回白名单遗漏，已补两端及精确路由测试；随后认证/API70通过/27.48秒。较早310/311项最终组合已被356取代。
- 原始JUnit在本地artifacts保留，按Git规则忽略；提交可复跑脚本和本双语脱敏记录。未复制生产秘密或trace。

## 真人与剩余边界

生产依据仍为0067只读核查：DY/KS/贴吧/WB是upstream_browser_timeout，Bili/XHS/Zhihu保存为已认证。本轮无生产浏览器操作、重试、下载、部署或supervisor恢复。当前Linux镜像、真实扫码/采集/CDN/播放及PostgreSQL均NOT_RUN，旧缺失细阶段不可恢复。

[使用说明](usage.zh.md)明确有界保留页、进程计数、并发追加遗漏、崩溃open不回收及排除原文。本中心是安全结构化证据，不是所有任意依赖message或完整异常栈。另行复现的旧Windows exporter目录pin弱点已记录待跟进，未宣称本轮修复。

## Git发布

冻结计划bfeb43f。推送前新fetch确认origin/main仍为d600ed5cdf5763a172e1f5b1dd82346652690041，无并发远端变更。实现使用双语提交与正常推送，精确revision/远端一致性在后续文档收尾记录，总体目标继续活动。
