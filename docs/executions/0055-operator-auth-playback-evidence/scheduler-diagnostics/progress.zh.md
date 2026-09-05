[English](progress.md) | **中文**

# 推进结果

基于冻结计划 9ec7d8d 和补充 79c2168 完成实施、本地验证并发布为 **b5b6fd4**：主代理 Python 联合分别通过 368、269 项（1 项 Windows 跳过），Web 通过 343 项及静态构建。精确命令、中间修正和发布状态见[验证](verification.zh.md)。

## 已实现

1. 三个固定诊断分别标记普通心跳失败、原生类型化 SQLite BUSY/LOCKED 和首次结果收尾异常边界；全部保留终止/影响熔断语义，不改变重试、租约、超时、事务、迁移或历史数据策略。
2. 租约/清理隔离异常先于诊断收尾传播。取消时等待 handler 和正在执行的心跳，包括两者同时结束、外部取消期间清理隔离失败的组合。已提交 succeeded Run 仍是权威。
3. API/CLI 共用 Job 投影增加可空 last_error_code；CLI worker JSON 增加可空 error_code。只有六个失败/等待/重试/fenced 状态及精确识别码可展示；未知、类型错误和与成功状态矛盾的值为 null。不新增查询，不输出原始异常或私密 payload，不改 batch Operation 格式。
4. Jobs 列表/详情使用固定中文阶段/后续说明，明确 schema_invalid 的模糊性。详情只展示既有字段白名单及清洗后错误；精确身份、取消和请求代际检查防止迟到或其他 Job 响应覆盖当前详情。新 Web 兼容旧 API 缺少错误字段。
5. 真实文件 SQLite 争用和注入异常分别验证。第二写连接真实耗尽仅测试使用的短超时，handler 取消先释放锁再收尾；复现失败 Job、running/无错误 Run、零内容和 authenticated 账户不变，同时不泄漏数据库文本或路径。这不是生产根因归因。

## 待实现与待验证

- 首次生产采集仍为 FAILED，历史 schema_invalid 不改写；新诊断在部署镜像上为 NOT_RUN。本增量未进行生产登录、重试、下载、导出、部署或恢复 supervisor，测试订阅仍暂停。
- B 站作者采集仍需真正执行扫描/条数边界，现有作者路径不遵守 max_items=1。粘贴 Cookie 远程校验/私密保存/复用已接受但仍 NOT_IMPLEMENTED。
- 新进程会话复用、其他平台、真实归档/下载/增量和 Emby/Jellyfin 播放资格仍未完成；七平台完整目标不变，本诊断增量不等于总体完成。
