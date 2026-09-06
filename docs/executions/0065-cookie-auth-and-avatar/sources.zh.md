[English](sources.md) | **中文**

# 来源证据

锁保持 MediaCrawler d6f7c5bb906b6dac40ddf343ef9e26438a3de092 与 bili-sync-up dcb5bb73b56ac45b2525da14b389e185b0ea6dbd。公开源码事实不是平台验收。

- 抖音候选：cv-cat/DouYin_Spider@9afaf79580b1ee84e8954ff906ff26869d5b7f1f dy_apis/douyin_api.py755–778；leaperone/MultiPost-Extension@fdbc6c3b2f3c03f57be8a59b46e33860689ba509 src/sync/account/douyin.ts3–30。均使用当前 Cookie GET creator.douyin.com/web/api/media/user/info/ 并读返回 user.sec_uid。不复制源码、不关闭TLS、不采用truthy/HTML回退。代理详细复核待追加。

- 快手：yikart/AiToEarn@d3aa8bea5b146a8675607cf0144d891aad3e9683 project/aitoearn-electron/electron/plat/Kwai/index.ts381–393 声明 userInfoQuery；requestApi246–279 将候选 Cookie 的 kuaishou.web.cp.api_ph 放 body，对该非cp GraphQL URL 不签 query。main/plat/platforms/Kwai/index.ts488–492 检查HTTP200及返回userInfo.userId；kwai.type.ts84–95 声明userId:number/name:string。MIT。严格正整数/有界原始昵称/无GraphQL错误是本方保守子集，不是完整真人schema。

- 知乎：[历史MediaCrawler help.py](https://github.com/NanmiCoder/MediaCrawler/blob/157ddfb21bd534109c0668ffeef9f643aa7c2d15/media_platform/zhihu/help.py)355–359使用avatarUrl/urlToken。[egrcc/zhihu-python README.rst](https://github.com/egrcc/zhihu-python/blob/1e24d4dfa960eacddb566f00269eb3d1878a4e00/README.rst)293行/test.py148明确头像HTTPS pic2.zhimg.com/{32hex}_l.jpg；zhihu.py569–593读取头像元素。仅用未改写URL，不复制来源人物/图片/夹具。旧形状不是当前CDN字节证明。

调查遇到GitHub API限流、猜测README.md404（实际README.rst）、zhihu-oauth因DMCA不可用；未绕过。公开checkout仅在仓库外本轮专用临时目录。未请求平台/生产。

## 快手最终来源边界与离线契约

先通过 Sourcegraph 找到公开代码，再读取固定 GitHub revision 的原文件。来源支持的子集刻意小于“任意网页 Cookie 都可用”。调查没有请求平台接口、使用真实 Cookie、操作生产账户或媒体。

- [AiToEarn Kwai client](https://github.com/yikart/AiToEarn/blob/d3aa8bea5b146a8675607cf0144d891aad3e9683/project/aitoearn-electron/electron/plat/Kwai/index.ts)381–393 行声明 POST `https://www.kuaishou.com/graphql`、`operationName: userInfoQuery`、空 `variables` 及固定查询 `userInfo { id name avatar eid userId __typename }`。249–259 行将候选 Cookie 中准确的 `kuaishou.web.cp.api_ph` 值放进同名 JSON 字段，262–265 行发送候选 Cookie。虽然通用源码计算签名数据，279 行只对 `https://cp.kuaishou.com` 选择签名 URL；本 GraphQL 使用原 URL。本方不继承多余签名副作用。
- [AiToEarn main platform](https://github.com/yikart/AiToEarn/blob/d3aa8bea5b146a8675607cf0144d891aad3e9683/project/aitoearn-electron/electron/main/plat/platforms/Kwai/index.ts)488–495 行通过 `getAccountInfo` 检查已保存 Cookie，读取 HTTP200 与返回的 `userInfo.userId`；57–73 行格式化远端 userId/name/avatar。这是当前用户，不是输入的目标作者。
- [AiToEarn types](https://github.com/yikart/AiToEarn/blob/d3aa8bea5b146a8675607cf0144d891aad3e9683/project/aitoearn-electron/electron/plat/Kwai/kwai.type.ts)84–95 行声明 `data.userInfo.userId: number` 与 `name: string`。[requestNet.ts](https://github.com/yikart/AiToEarn/blob/d3aa8bea5b146a8675607cf0144d891aad3e9683/project/aitoearn-electron/electron/plat/requestNet.ts)7–10、113–116 行区分 HTTP 状态与解码数据，实际远端 JSON 路径是 `data.userInfo`，没有额外包装层；147–149 行规定 JSON Content-Type 和序列化。该 revision 根许可证为 MIT；不复制实现、人物夹具、头像字节、宽松代理行为或日志。
- 运行时仍用锁定 MediaCrawler `d6f7c5bb906b6dac40ddf343ef9e26438a3de092`：`media_platform/kuaishou/client.py`45–66 行构造真实 `KuaiShouClient`；88–92 行紧凑序列化 JSON，再以 POST、host 加空 URI、`data` 和 `headers` 调用 `request`。闭合传输保留原 `request`68–78 行的 data 解包形状，但在暴露数据前拒绝坏 JSON。不使用 pong、关系列表、作者作品接口、浏览器、签名 query 或原无限制 HTTP 方法。

本方策略在导入/网络前要求准确且非空的 CP Cookie 键；缺失、空值或字面量引号空值返回 `result_invalid`，不谎称凭据已被平台拒绝。其他非空引号值和百分号编码原样保留，不去引号、不 URL 解码，不拿 `kuaishou.web.api_ph` 替代。严格正 JSON 整数 userId、有界可打印非空原始昵称、无未知 GraphQL errors、无矛盾的 guest/login/error 元数据，是保守接受规则，不是来源已证明的完整真人 schema。未找到无效 Cookie 响应夹具或 GraphQL 错误码映射；未知响应维持 `result_invalid`，只有 HTTP401 映射 `rejected`。顺带返回的 avatar 不保存、不抓取；快手头像工作留待以后。

新增模块的离线单元及锁定客户端契约测试 **168 项通过**，覆盖真实构造/post、私有 worker 固定状态帧、准确 Cookie/CP/query/body/空 variables、单次固定公共 DNS HTTP 请求、重定向/压缩/大小/重复 JSON/异常响应拒绝、截止时间/取消、源码来源校验、request 恢复，以及响应对象替换/变异时的对象同一性加副本相等校验。这是离线兼容与边界验证，不是真人平台验收。静态检查通过；主代理另记录最终受影响组合和发布验证。

负面来源记录：grep.app 返回429；GitHub共享API返回403限额耗尽，未登录代码搜索要求登录；未绕过。`dreammis/social-auto-upload@0012d2c355f88f683cc38dde2a2db209e14091bc` 与 `XXXXBully/social-auto-upload-tool@2918316f410ebc6438ebe5fe8ce48f2b3c53a93a` 依赖上传页/登录UI标记，不能当作当前身份。`EgooAI/BrowserPlugins-KuaishouCookie@99022a13e5f5a425bcbe4f395e81ff9beb058bb2` 观察认证回调并导出 Cookie，不是所需非变更式 self 校验，其秘密日志未采用。

## 补充固定来源复核

抖音最终主要来源：[doocs/cose detection config](https://github.com/doocs/cose/blob/e70fa9e92a71cd2f10e0c883981f324a332162d4/packages/detection/src/configs.js)57–66明确DouyinLoginConfig及status_code===0和user.uid/user_info.uid；[MultiPost账户同步](https://github.com/leaperone/MultiPost-Extension/blob/fdbc6c3b2f3c03f57be8a59b46e33860689ba509/src/sync/account/douyin.ts)3–30同一无query GET、credentials include、user.sec_uid/nickname。两者Apache2。本方仅接受单一user、整数status_code0、正uint64 uid（规范十进制字符串或整数）、ASCII sec_uid及原始有界昵称；非空user_info/error/errors或guest/login矛盾均拒绝。HTTP401为rejected，超时timed_out，HTTP传输异常verification_unavailable，未知HTTP/平台/schema为result_invalid。直接适配器为原创协议实现，不冒称锁定MediaCrawler已有self方法；guardian仍校验锁定运行时，此端点无需浏览器或JS。

小红书有界新来源：ReaJason/xhs@f4b62d9f8e4078e631fc6e4ec8e430bc711ee9f0 xhs/core.py367–375/tests/test_xhs.py99–106，以及cv-cat/Spider_XHS@e1888d712519040f5fcc294baeac4b9505b25c98 apis/xhs_pc_apis.py252–260都仅将输入ID用于otherinfo，未证明返回稳定资料身份。JoeanAmier/XHS-Downloader@3a8849c7afb215085b32da84bcdbeb7c6d26880e有界扫描无资料schema。xpzouying/xiaohongshu-mcp@332d196854a9eac0d2b8c2c0e3d0cc43139d724c xiaohongshu/user_profile.go68–104/types.go287–295独立映射user.userPageData.basicInfo的昵称/图片/redId，却无稳定返回userId；另一笔记实体User.userId不能混作资料身份，redId也不替代24位hex资料ID。GitHub API403/搜索429限制发现，固定raw/ls-remote成功。本次是新来源调查，不重复旧来源阻塞或永久排除；小红书精确资料仍必需但未实现。
