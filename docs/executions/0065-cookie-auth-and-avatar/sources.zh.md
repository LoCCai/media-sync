[English](sources.md) | **中文**

# 来源证据

锁保持 MediaCrawler d6f7c5bb906b6dac40ddf343ef9e26438a3de092 与 bili-sync-up dcb5bb73b56ac45b2525da14b389e185b0ea6dbd。公开源码事实不是平台验收。

- 抖音候选：cv-cat/DouYin_Spider@9afaf79580b1ee84e8954ff906ff26869d5b7f1f dy_apis/douyin_api.py755–778；leaperone/MultiPost-Extension@fdbc6c3b2f3c03f57be8a59b46e33860689ba509 src/sync/account/douyin.ts3–30。均使用当前 Cookie GET creator.douyin.com/web/api/media/user/info/ 并读返回 user.sec_uid。不复制源码、不关闭TLS、不采用truthy/HTML回退。代理详细复核待追加。

- 快手：yikart/AiToEarn@d3aa8bea5b146a8675607cf0144d891aad3e9683 project/aitoearn-electron/electron/plat/Kwai/index.ts381–393 声明 userInfoQuery；requestApi246–279 将候选 Cookie 的 kuaishou.web.cp.api_ph 放 body，对该非cp GraphQL URL 不签 query。main/plat/platforms/Kwai/index.ts488–492 检查HTTP200及返回userInfo.userId；kwai.type.ts84–95 声明userId:number/name:string。MIT。严格正整数/有界原始昵称/无GraphQL错误是本方保守子集，不是完整真人schema。

- 知乎：[历史MediaCrawler help.py](https://github.com/NanmiCoder/MediaCrawler/blob/157ddfb21bd534109c0668ffeef9f643aa7c2d15/media_platform/zhihu/help.py)355–359使用avatarUrl/urlToken。[egrcc/zhihu-python README.rst](https://github.com/egrcc/zhihu-python/blob/1e24d4dfa960eacddb566f00269eb3d1878a4e00/README.rst)293行/test.py148明确头像HTTPS pic2.zhimg.com/{32hex}_l.jpg；zhihu.py569–593读取头像元素。仅用未改写URL，不复制来源人物/图片/夹具。旧形状不是当前CDN字节证明。

调查遇到GitHub API限流、猜测README.md404（实际README.rst）、zhihu-oauth因DMCA不可用；未绕过。公开checkout仅在仓库外本轮专用临时目录。未请求平台/生产。
