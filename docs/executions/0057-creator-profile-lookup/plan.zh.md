[English](plan.md) | **中文**

# 冻结实施计划

基线：`87ef7fd`。先提交本计划，再修改协议/schema。锁定上游仍为 upstreams.lock.json 指定版本。

1. 新增独立 Bili saved-session runner，仅允许非交互认证/WBI准备和一次 client.get_creator_info(mid)。禁止 core.get_creator_details、内容/动态/评论、扫码回退及登录状态提升。私密 stdin、闭合结果帧、来源验证、共同账户文件锁与父死/全子树清理沿用既有安全边界。执行预算45秒（含准备，所有子步骤共享剩余预算），另有最多15秒清理预算；未确认子树退出不能释放账户锁，不宣称含操作系统清理严格45秒。
2. 新增按 account/platform/creator 隔离的 CreatorProfile 及精确 Operation 对应的 lookup 记录。后端 generation 单调递增，绑定 frontend_generation UUID、operation_id、当前凭据快照。Account.auth_revision 随认证修改递增，阻止相同时间戳或 A→B→A 状态绕过；不读取浏览器活动文件作哈希。begin/publish 与 Operation 的租约、期限及取消检查在同一事务内；资料失败/迟到不清空上次成功资料。
3. 独立 Subscription.local_alias，迁移旧作者标签为本地备注而非远端事实。新建或重放不得重命名既有 Author 或修改其 URL；已有导出路径不变。新 API 可用 profile_lookup_id 引用15分钟内、精确身份/版本/成功Operation对应的服务器资料；不能信任客户端声称的远端昵称。legacy display_name 仍作为本地备注兼容；新表单 local_alias 可选，有有效资料凭单即可创建。
4. Operation kind 为 creator-profile、target 为 account。POST /api/v1/accounts/{account_id}/creator-lookups 接收闭合 platform、creator_remote_id、frontend_generation、enable_mediacrawler、accept_mediacrawler_license；返回既有操作启动结构。GET /api/v1/creator-lookups/{operation_id} 返回闭合操作状态、精确 lookup 身份与资料投影，准备中 lookup 可为空。Operation/SSE只保存固定码、UUID、计数、摘要，不保存昵称/URL/凭据原文。API沿用现有鉴权/CSRF与许可证确认。
5. 头像固定 Bili HTTPS主机/路径合同，未知形状不获取。无Cookie/auth/代理继承、禁重定向、公网DNS/连接钉扎、2MiB输入、八百万像素、单帧JPEG/PNG/WebP、限时抓取与隔离重编码PNG。为缩小文件路径攻击面，采用有界数据库二进制缓存而非草案的文件缓存；字节至多2MiB，独立revision/observed_at。鉴权同源 /api/v1/creator-profiles/{profile_id}/avatar/{revision} 不接收任意URL，CSP不放宽；昵称成功但头像失败保留且明确标识旧头像。
6. 前端稳定输入完成（blur/Enter）后每个身份代际自动一次查询，不逐击键请求、不自动无限重试。查资料不依赖全历史确认/采集策略/本地别名。展示昵称、可选备注、远端观察时间、错误及旧头像状态；任何身份/会话/操作/请求/图片加载迟到不得覆盖新身份。其他平台/非saved-session明确当前限制，不假装远程已验证。
7. 分工：runner与合同测试；DB/迁移/别名与竞争测试；Web及隔离测试；主代理负责Operation/API/头像与集成。验证单资料调用计数及禁止方法陷阱、过期认证不扫码、同账户互斥/子树清理、租约取消与auth ABA/代际隔离、跨账户不可串资料、迁移与旧路径、头像SSRF/超限/解码、鉴权与前端迟到响应。记录所有失败、修复、跳过与未运行门；双语提交与非强制推送后fresh fetch核验。

本次不授权生产部署、登录、订阅创建/删除/恢复、重试采集、下载/导出或恢复 supervisor。后续仍须Cookie登录私密校验保存、六平台资料、正确有界覆盖与真人采集/归档/媒体服务器验收。

