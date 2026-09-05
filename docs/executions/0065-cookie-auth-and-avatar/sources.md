**English** | [中文](sources.zh.md)

# Source evidence

Locks remain MediaCrawler d6f7c5bb906b6dac40ddf343ef9e26438a3de092 and bili-sync-up dcb5bb73b56ac45b2525da14b389e185b0ea6dbd. Public source facts are not platform qualification.

- DY candidates: cv-cat/DouYin_Spider@9afaf79580b1ee84e8954ff906ff26869d5b7f1f dy_apis/douyin_api.py755–778; leaperone/MultiPost-Extension@fdbc6c3b2f3c03f57be8a59b46e33860689ba509 src/sync/account/douyin.ts3–30. Both GET creator.douyin.com/web/api/media/user/info/ with current Cookie and read returned user.sec_uid. Do not copy code, disable TLS or adopt truthiness/HTML fallback. Detailed agent review follows.

- KS: yikart/AiToEarn@d3aa8bea5b146a8675607cf0144d891aad3e9683 project/aitoearn-electron/electron/plat/Kwai/index.ts381–393 declares userInfoQuery; requestApi246–279 uses candidate Cookie's kuaishou.web.cp.api_ph in body, no query signing for this non-cp GraphQL URL. main/plat/platforms/Kwai/index.ts488–492 checks HTTP200 and returned userInfo.userId; kwai.type.ts84–95 declares userId:number/name:string. MIT. Strict positive integer/bounded raw name/no GraphQL errors are our conservative subset, not exhaustive live schema.

- Zhihu: [historical MediaCrawler help.py](https://github.com/NanmiCoder/MediaCrawler/blob/157ddfb21bd534109c0668ffeef9f643aa7c2d15/media_platform/zhihu/help.py)355–359 uses avatarUrl/urlToken. [egrcc/zhihu-python README.rst](https://github.com/egrcc/zhihu-python/blob/1e24d4dfa960eacddb566f00269eb3d1878a4e00/README.rst)293/test.py148 explicitly identify HTTPS pic2.zhimg.com/{32hex}_l.jpg as a head image; zhihu.py569–593 reads the avatar element. Consume only unchanged URL, no source person/image/fixture copied. Old shape, not current CDN-byte proof.

Source discovery encountered GitHub API rate limiting, guessed README.md404 (actual README.rst), and a DMCA-unavailable zhihu-oauth repository; no bypass. Public checkouts are task-specific temporary folders outside this repo. No platform/production requests.
