[English](plan.md) | **中文**

# 冻结计划

1. 独立受监督资料worker复用锁定微博client，不调用crawler.start/core作者遍历/store。一次GET /api/config明确login=true之后，才允许一次get_creator_info_by_id到精确/api/container/getIndex查询（jumpfrom=weibocom、type=uid、value=UID、containerid=100505UID）。要求原始ok=1、userInfo.id精确匹配、有界昵称及可选头像。拒绝没有新认证证明的公开资料、改变/含糊query、重定向及重试；有界资料响应附带cards仅忽略，不请求帖子/feed/评论/媒体。
2. 沿用账户锁、私密Cookie帧、checkout来源校验、父死/超时/子树清理，以及45秒执行加最多15秒清理。保存会话只使用该账户已有profile；Cookie用完整解析候选及空白非持久context，不回退旧会话。浏览器网络全部阻断，仅返回同源空文档；不扫码、不提升账户认证。网络目标闭合、公网DNS钉扎、不继承代理、JSON有界。
3. 既有数字身份合同扩展wb，不能放宽B站或启用其他五平台。主页固定https://weibo.com/u/UID。保留账户/平台/作者/Operation/代际/auth_revision绑定以及资料与Operation成功原子发布。不需要迁移，不重命名历史作者或导出路径。
4. 可选头像增加保守HTTPS微博CDN主机/路径白名单，不带凭据、query、重定向或任意目标。复用有界隔离下载解码及同源静态PNG；未知形状/失败保留文字和旧头像，不宣称所有远端头像形状已支持。保留既有B站头像API兼容。
5. 实际订阅控制器/UI启用微博saved-session及Cookie资料，与全历史采集确认分离。每个完成输入身份只查询一次，保留账户/平台/代际/会话隔离、安全主页检查及手动重试。准确说明其他五平台未接通；认证/资料成功不是采集或播放资格。
6. 真实锁定client加模拟有界传输验证方法、身份/响应/query/尝试数拒绝；两种浏览器模式及禁止调用陷阱；共用进程门；service/API/DB凭单及跨平台/账户隔离；头像安全；前端自动查询/迟到结果。专项回归及与风险相称的全静态/Web/docs/上游/打包门，记录精确命令、失败修正及环境/真人NOT_RUN。依赖代码修改前双语提交计划，再双语提交实施及进展、非force推送并fresh fetch核对。

本轮编码不授权生产登录、Cookie输入、订阅修改、重试、采集、下载/导出、部署、媒体服务器操作或恢复supervisor。剩余抖音/快手/贴吧Cookie校验器须先建立已认证本人证据，不能将本地Cookie标志或公开/关注关系资料包装为登录证明。

