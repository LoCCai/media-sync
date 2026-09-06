**中文** | [English](progress.md)

# 推进记录

已核查基线及0067下一版要求。当前源码确定丢失点为登录stderr/上游fd1/2静音、仅状态结果帧、不透明crawler.start和authenticating粗阶段；现有支持包仅聚合。冻结独立事件通道+受管分片方案，保留严格结果和认证终态。

## 已实现

- state_dir/logs私有JSONL分片，默认16MiB或UTC日期轮转、7天、总量1GiB、队列1024。每进程独占写者协调总容量/清理；闭集schema、目录/文件身份防护和签名受管标记保护文件操作。查询显示损坏、不可读和省略尾部；状态区分接收、持久化、丢失及未完成关闭。
- 独立有界实时登录诊断旁路，严格v1结果保持不变。浏览器启动、导航、点击、QR获取/中转、确认及清理保存可观察的阶段、动作、异常类别、代码来源类别和耗时。被捕获后fallback成功的子步骤不是终止失败；父进程绑定确切已提交account/session及API operation/correlation。通道截断明确降级，上游原文保持静音。
- Operation、订阅worker、pipeline worker和supervisor生命周期接线。API请求状态/耗时、安全标准logging类别/级别、CLI登录/worker/supervisor及手动下载/目录写入命令使用同一私有store。手动命令使用correlation，不伪造数据库Operation。这是结构化组件覆盖，不是每条shell、依赖或第三方原文的捕获。
- 四个鉴权日志接口、闭集筛选及有界游标、操作/控制事件详情和主动下载的诊断JSON。不导出数据库自由error/message/context；旧SupportBundle v1不变。中文日志页、任务直达和设置入口展示保留/证据限制。无需连接媒体服务器。

## 审查修正

前端审查发现未赋值select、等待期间筛选可变、销毁后请求、混条件分页和未校验下载数据。存储审查复现idle/close竞态导致正常关闭不封片、idle同步封片绕过close超时、一次封片rename失败阻止后续写入，已修正并增加确定性测试，含writer线程临时启动失败恢复。最后API到前端核查还发现/logs登录返回白名单遗漏，已补服务端/客户端名单及精确路由测试。主代理初始fixture用了不存在的Operation状态failed，改为failed_retryable；旧CLI假构造和断言现要求新接入的可调用event sink。精确结果见验证记录。

## 待实现与范围

当前Linux镜像、真实平台扫码重试、PostgreSQL竞态及真人历史/下载/播放均NOT_RUN。新增证据本身不修复四个平台扫码，也不授予认证；旧阶段细节不可恢复。崩溃遗留open片保留、不自动回收，计数不跨进程重启；保留清理由写入触发。七平台总体目标继续活动。

独立复核还复现了旧Windows exporter目录pin弱点：exporter.py的_open_windows_directory_handle使用零访问权限，持有句柄仍可重命名祖先。新日志store使用目录列举权限，真实Windows拒绝rename测试通过。没有静默扩大本轮修改到exporter；依赖其Windows防重命名保证前必须另做有界安全修复。此观察不等于Linux生产部署已发生故障。
