**中文** | [English](plan.md)

# 冻结计划

1. 私有state_dir/logs下JSONL分片；默认16MiB或UTC日期轮转、7天/1GiB总上限，有界队列1024。各进程独立单写者，不让多个容器争抢同一文件轮转。只清理明确受管封存片、保护活跃片和链接/reparse；写盘/队列失败、损坏/截断、保留范围不明必须可见。emit入队不冒充已持久化，flush/close有界。
2. 严格事件schema：event_code/module/level及闭集phase/action/outcome、安全异常类型、受约束代码位置、UUID关联和有界数值。时间/序号/writer身份由父日志存储生成。拒绝自由文本/URL/请求头/Cookie/二维码/locals/原始异常；标准logging只能保留允许的组件/级别和安全类别，不调用自由message格式化。
3. 登录v1结果帧不变，另加版本化、有界、实时事件旁路。child无法声明account/session/operation身份，由父服务绑定。捕获实际导航、点击、QR获取/中转、会话确认等阶段；helper吞错前有证据，fallback后成功不能算终止，清理不能覆盖主错。原锁定上游不改、不增平台请求、不绕验证；取消/父死/树join保持原保证。
4. OperationCoordinator、订阅worker、pipeline worker、supervisor以可选event_sink记录开始/阶段/终止，复用可信context关联。API/CLI注入同挂载store；不将heartbeat和每次idle写成洪泛。
5. 已鉴权日志状态/过滤分页接口，固定错误、请求范围/编码后大小/扫描预算有界。诊断包只接受operation UUID，从数据库查准确关联、版本和现有事件，附当前保留日志，不读客户端路径、不自动上传。旧support_bundle v1保持不变，旧缺阶段记录明确不可恢复。
6. 中文日志页按时间/组件/平台/级别/关联身份筛选，显示阶段/动作/结果和覆盖/丢失提示，任务详情直达，显式下载诊断包。失败与进行中可区分，不把最近子步骤失败直接当整个登录失败；只有原账户认证终态授予成功。
7. 验证导航/点击/QR/确认超时、吞错/fallback、取消与协议洪泛；多进程/队列/磁盘/轮转/截断/重启、秘密哨兵全落点、认证和路径拒绝；真实离线登录事件→持久片→API→诊断包→UI契约。记录未运行Linux/平台行。最终静态/构建/包/文档及受影响回归，双语提交推送并核对。

分工：存储代理负责events/store与安全tests；登录代理负责runner/认证服务与细阶段tests；生命周期代理负责operations/scheduler/pipeline/supervisor和标准日志安全handler；主代理负责配置/API/诊断包/UI/文档/联合验收。新问题需明确记录调整，不缩减用户目标来换PASS。
