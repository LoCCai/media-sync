[English](plan.md) | **中文**

# 冻结计划

1. 不改上游锁、依赖或数据库schema。按[来源](sources.zh.md)原创协议事实，不复制受限实现或第三方响应夹具。新增平台资料独立模块；主线程负责共用runner/身份/repository/API/Web，代理负责互不重叠的平台模块/测试。
2. 贴吧：通过锁定client/get仅请求一次 `https://tieba.baidu.com/mo/q/newmoindex?need_user=1`，完整保留候选Cookie，不带目标用户。要求明确成功信封、正数有界不可变本人ID和本人端点返回的有效非空portrait；缺失/游客/歧义字段不算登录。已知HTTP401可拒绝；未证明的平台错误码归result_invalid，不编造认证过期语义。本地BDUSS标记、单纯HTTP成功、任意资料查询或pong均不足以认证。复用私密guardian、账户互斥、不可变候选存储和Account/Operation原子成功；失败保留旧凭据。真实runner接线及测试后才开放第五平台UI/capability。
3. 共用作者身份：B站/微博保留uint64规范数字ID；快手为精确ASCII `[A-Za-z0-9_-]{1,128}`，知乎为精确ASCII url_token `[A-Za-z0-9._-]{1,255}` 且排除单独点/双点路径段。长度为本方保护，不宣称平台全集。request/result/repository/API/UI按平台校验、派生固定官方主页；保留账户/generation/凭据/租约/取消/receipt约束及已有媒体/导出路径，不把别名/返回数字ID转换成opaque ID。
4. 快手：仅现有本地已认证保存会话或既有Cookie账户；一次锁定 `visionProfile` GraphQL、精确ID/query及有界无重定向/无环境代理/固定DNS POST。解析 `data.visionProfile`，严格整数result1、`userProfile.profile.user_id`为字符串并逐字等于输入、非空有界user_name。不调用关注列表pong、不修改认证；这是精确作者观察，不是远程本人登录证明，身份缺失/变化拒绝。headurl仅走现有可选头像边界，不增加无证CDN抓取规则，不宣称头像完成。
5. 知乎：全新Cookie上下文或精确保存会话，锁定真实Node签名且保留小写cookie/签名头；一次不含邮箱手机号include的 `/api/v4/me` 本人检查，再一次精确签名 `/people/{token}` HTML。严格有界JSON/HTML传输，无重试/浏览器信息流导航。读精确 `initialState.entities.users[token]`，强制行自身 `urlToken==token` 和原始有界name，不沿用匿名化或输入身份兜底。缺失/改名/跳转均不发布；可选avatarUrl不等于允许抓取未知CDN，其他页面实体/附带内容不进入结果和存储。
6. UI扩展两平台自动单次查询和严格主页/结果校验，保留身份变化/晚结果/取消/receipt规则；解释数字UID、快手ID及知乎token、昵称已接入但头像证据仍缺。查询不采集、不要求全历史确认。贴吧粘贴沿用私密提交/清空行为，Cookie不进入日志/错误/历史。
7. 用真实锁定方法加合成transport/browser陷阱验证：错/缺身份、公开资料冒充本人、坏信封、多余请求/URL、跳转/私网、超限响应、签名头丢失、Cookie替换、解析兜底、过期发布均拒绝；贯通应用/repository/API/订阅receipt和前端。边改边专项，冻结后最终受影响回归；完整目录快照/环境跳过与最终证据分列，核对打包源码，更新双语状态/部署/能力矩阵/执行文档。
8. 实现前提交冻结计划；双语实现提交、非强制推送、fresh-fetch一致性并另记发布。未实际执行的Linux/真实PG/平台/CDN/播放均NOT_RUN，本轮不操作生产。后续仍完成其他校验/资料/头像/媒体及实测，不重新定义七平台目标。
