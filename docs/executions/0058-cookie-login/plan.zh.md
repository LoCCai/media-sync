[English](plan.md) | **中文**

# 冻结计划

1. 新增闭合Cookie请求头解析器：ASCII输入最多16KiB、128个唯一键值对；只在第一个等号分割，拒绝重复、控制字符、属性、URL及不支持的JSON形状。秘密包装禁止repr暴露。不复用锁定上游会静默丢弃含等号值的解析器。输入是请求Cookie头，不是Set-Cookie或浏览器JSON导出。
2. 新增独立受监督验证器，只访问固定远端URL，无重定向/代理/任意目标；JSON和总时限有界，包含签名及运行环境检查。B站使用nav、微博使用m.weibo.cn config、小红书使用selfinfo及锁定纯算法签名、知乎使用me及锁定离线JS签名。要求明确已认证/本人身份响应；HTTP200、公开资料或本地标记不算成功。禁止crawler.start、扫码、feed、作者历史和共享浏览器资料修改。抖音/快手/贴吧未支持时固定错误返回，整体后续目标保留。
3. 已验证候选保存为state_dir/credentials下不可变`managed:UUID`文件，与只读/run/secrets分离。限制路径、拒绝符号链接、只接受普通文件、有界读取、目录/文件私密权限及原子创建，保留旧版本。扩展明确的运行时resolver，让后续新进程解析同一凭据。Cookie原文不进入Account/Operation/Event/日志或公开结果。
4. 新增account-cookie-login Operation种类及0011迁移扩展CHECK，不损失外键子表/历史。不创建或改写扫码LoginSession。Account CAS绑定backend/platform/expected auth_revision及原认证身份，拒绝活动扫码所有权；远端成功后才更新credential_ref/login_method/auth状态/修订。扩展短DB-only commit_success栅栏，Account与Operation成功同事务。失败/取消/过期/迟到保留旧账户。提交结果不明时禁止删除候选文件；保留私密未引用孤儿优于破坏已提交引用。
5. POST /api/v1/accounts/{account_id}/cookie-login严格有界流式JSON，字段恰为cookie、platform、expected_auth_revision、frontend_generation、enable_mediacrawler、accept_mediacrawler_license。继续强制鉴权/CSRF/许可证门；解析错误只返回固定码，不回显输入、字段名、异常细节。返回既有202 Operation启动合同。请求身份仅存摘要及固定身份字段，不存候选原文。共享account-login互斥，并在候选验证/发布全程持有实际账户锁。成功摘要恰为account_id/auth_status=authenticated/login_method=cookie/auth_revision，现有Operation读取提供进度结果。
6. 公开auth_revision和pasted_cookie_login能力。Accounts增加明确的粘贴/校验/保存弹窗，仅内存输入，不预览、不记录日志，固定错误指导、不自动重试。提交/关闭/登出/切换账户时清空，以账户/平台/会话/代际/Operation隔离迟到响应。失败说明原凭据未改；提交后关闭不能冒称服务端取消。允许带当前修订替换已认证账户。保留扫码选项，准确标记未支持平台。
7. 修正后续确定性复用：Cookie forward/detail使用空白非持久context及完整解析的输入头，不能被旧saved-session资料绕过注入。测试含等号值及旧浏览器会话陷阱。B站Cookie资料查询是本工作流必需的后续依赖，不冒称saved-session-only已覆盖Cookie账户。
8. 并行分工：runner/解析器/上游合同及Cookie复用；托管存储/Account CAS/迁移；Web/控制器；主代理负责Operation/API/service及集成。验证解析/泄漏哨兵、替身网络响应拒绝、进程超时取消/子树清理、坏候选保留、原子成功/ABA/取消租约、新进程凭据读取、迁移打包及UI会话竞争。双语记录实际失败与所有跳过/真人门；双语提交、非强制推送及fresh fetch。这里不授权生产登录/Cookie输入/部署/订阅变更/采集/下载导出或恢复supervisor。

四平台首批交付不代表0058或七平台整体目标完成。后三平台的已认证证据、B站Cookie资料依赖、有界历史覆盖及真实端到端验收继续为明确义务。
