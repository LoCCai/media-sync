[English](sources.md) | **中文**

# 协议证据及后续线索

以下是公开可读固定历史源，不是真人资格；运行依赖/锁不变。仅按协议事实原创实现，不把GPL代码或第三方响应正文复制进fixture。

## B站动态与OPUS

- API-collect提交`cfc5fddcc8a94b74d91970bb5b4eaeb349addc47`，历史文档为CC BY-NC4.0：[作者列表](https://github.com/SocialSisterYi/bilibili-API-collect/blob/cfc5fddcc8a94b74d91970bb5b4eaeb349addc47/docs/dynamic/space.md)、[动态详情](https://github.com/SocialSisterYi/bilibili-API-collect/blob/cfc5fddcc8a94b74d91970bb5b4eaeb349addc47/docs/dynamic/detail.md)、[动态对象](https://github.com/SocialSisterYi/bilibili-API-collect/blob/cfc5fddcc8a94b74d91970bb5b4eaeb349addc47/docs/dynamic/all.md)、[OPUS详情](https://github.com/SocialSisterYi/bilibili-API-collect/blob/cfc5fddcc8a94b74d91970bb5b4eaeb349addc47/docs/opus/detail.md)、[功能模块](https://github.com/SocialSisterYi/bilibili-API-collect/blob/cfc5fddcc8a94b74d91970bb5b4eaeb349addc47/docs/opus/features.md)。
- Nemo实现提交`377439476011468274d2e484257d7353dc0b8bdf`，GPLv3源码仅作协议证据：[dynamic.py](https://github.com/Nemo2011/bilibili-api/blob/377439476011468274d2e484257d7353dc0b8bdf/bilibili_api/dynamic.py)、[opus.py](https://github.com/Nemo2011/bilibili-api/blob/377439476011468274d2e484257d7353dc0b8bdf/bilibili_api/opus.py)、[API配置](https://github.com/Nemo2011/bilibili-api/blob/377439476011468274d2e484257d7353dc0b8bdf/bilibili_api/data/api/dynamic.json)。
- space5/21–25匹配锁定MediaCrawler client.py504–519：feed/space的offset、host_mid、platform；generic get130–137用WBI。detail5/18/22/44证明`id=DID`、features和data.item；Nemo dynamic737–778实际用id（其JSON描述dynamic_id不作为权威），含platform/web、timezone_offset、gaia_source及固定features；API配置221–236启用WBI。
- all46–55与features74–100证明id_str/type/modules/orig和普通作者mid/name/pub_ts/type。pub_ts是更新时间，mid可能为剧集身份，AV可能联合创作，不能仅凭请求host_mid证明每项作者。
- all278–283、390–405证明desc.text及major.draw.items[].src（不是images，draw.id不是DID）。detail82/161/179–180/207–230提供含精确身份/普通作者及图片的DRAW示例。all527–542与space244–275证明WORD/DRAW可使用MAJOR_TYPE_OPUS，含summary.text/pics[].url、可空title/live_url。WORD示例位于转发orig内部，不是原创WORD真人测试证明。
- all407–421证明archive含aid/bvid/cover/title，但没有owner/CID/pages。应复用锁定普通View详情证明实际owner/pages，绝不用动态pub_ts替换View.pubdate。
- summary未证明完整。OPUS detail5/15/60–79及Nemo opus87–119证明精确opus/detail?id=DID和basic.uid；features647–747及opus133–170证明MODULE_TYPE_CONTENT段落：文字word.words/rich.text；图片实际为paragraph.pic.pics（邻近表格pics写法与真实示例和实现不符）。公开完整OPUS响应为专栏示例，仅字段形状证据；原创WORD/DRAW权威须先来自动态详情。不能静默省略未知/付费/专栏/不支持段落。

## 后续平台工作

锁定KS vision_profile.graphql1–24证明visionProfile.userProfile.profile下user_id/user_name/headurl；client get_creator_info在request解包data后错误跳过visionProfile。关系列表pong不等于本人认证。贴吧锁定homeSidebarRight资料仍需portrait身份规则；XHS userPageData缺少足够的已消费身份字段合同；DY本地标记及未使用端点不是远程本人证明。

公开aiotieba `6a32de113ba35dd4da2ec0e76540e79678f9b8d8`的[get_selfinfo_moindex](https://github.com/Starry-OvO/aiotieba/blob/6a32de113ba35dd4da2ec0e76540e79678f9b8d8/src/aiotieba/api/get_selfinfo_moindex/_api.py)及相邻_classdef.py证明GET /mo/q/newmoindex?need_user=1与data.id/portrait/name，client1274–1280用于当前本人身份；无效Cookie错误语义尚未证明。锁定知乎get_creator_info/extractor证明按token取name，公开MediaCrawler历史`157ddfb21bd534109c0668ffeef9f643aa7c2d15` help.py证明avatarUrl/urlToken字段，不能证明当前/真人CDN形状。以上仅后续线索，不是已实现能力。
