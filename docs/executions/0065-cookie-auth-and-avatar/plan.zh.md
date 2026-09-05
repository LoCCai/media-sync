[English](plan.md) | **中文**

# 冻结计划

1. 应用编辑前提交计划，锁/依赖/schema 不变。子代理分别负责平台模块与测试，主代理负责共享流程/UI/文档。

2. 抖音：一次固定公网 HTTPS GET `https://creator.douyin.com/web/api/media/user/info/`，无目标作者，不编造 query/签名/浏览器或依赖本地 Cookie 标志。要求本人响应中精确 user.sec_uid 和昵称；复核来源后明确保守成功/游客/错误子集。依据公开协议事实原创实现，不复制代码；结果/日志不输出本人身份或响应。

3. 快手：真实锁定 KuaiShouClient.post，一次 POST `https://www.kuaishou.com/graphql`，固定 userInfoQuery、空 variables，无目标作者。来源要求候选 Cookie 中非空 kuaishou.web.cp.api_ph 写入完全同名 body 字段；不替换其他字段，不称所有 Cookie 均支持。要求 data.userInfo 正整数 userId 与原始有界 name，无错误/游客歧义。不运行浏览器、签名 query、关系/内容接口，不泄露响应正文。

4. 复用私密 framed guardian/worker、严格有界 JSON/公网固定传输/期限/禁止重定向与环境代理、凭据账户原子发布及候选失败保留旧认证。修正实际脚本模式 cookie runner 模块同一性，确保导入的类型化失败被正确处理。测试真实脚本/guardian接线、隔离和旧凭据保留。缺少运行时、来源或 Cookie 前提不能认证。

5. 知乎：仅在返回行 urlToken/昵称成功后取同一行可选 avatarUrl；首片来源子集为未改写 HTTPS pic2.zhimg.com/{32位小写hex}_l.jpg，不声称所有当前 CDN 形状。复用隔离无 Cookie 头像下载/解码、同源PNG、限制与旧头像保留，不加端点、不改认证或导出名。

6. 将两平台粘贴校验贯通能力/API/UI，明确凭据子集和本人认证/资料/采集/播放区别。记录有界小红书新来源调查，不用请求ID回填作为身份证明，其余目标仍须完成。

7. 跑受影响专项及 Web/静态/docs/锁门、独立复核和包审计。如实记录失败、数量、环境跳过及 NOT_RUN，不继承0064全量PASS。中英双语提交，正常 push/fetch 一致性核验，另记发布结果。
