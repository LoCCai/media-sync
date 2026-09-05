[English](sources.md) | **中文**

# 来源证据

仍锁定MediaCrawler d6f7c5bb906b6dac40ddf343ef9e26438a3de092及bili-sync-up dcb5bb73b56ac45b2525da14b389e185b0ea6dbd。仅本地/公开GitHub固定源，无平台请求；代码协议事实不等于真人响应资格。

- 抖音锁定client.py70–124、312–319：get_user_info固定profile/other端点，sec_user_id及两个策略参数，localStorage.xmst/common params/本地webid/真实a_bogus。help.py40在导入时compile，86–89调用sign_datail，须预先选Node管道执行。F2 [固定7dab3e2ffffaa2535834d28fca99dbc2e89fa9d3](https://github.com/Johnserf-Seed/f2/blob/7dab3e2ffffaa2535834d28fca99dbc2e89fa9d3/f2/apps/douyin/filter.py)UserProfileFilter80–93证明user.nickname与返回user.sec_uid；12–13仅证明avatar_larger.url_list[0]字段，无可信头像URL形状。该资料链未证明status_code0，作为本方保守接受条件单列，不冒称来源断言。
- 贴吧锁定client.py646–678、82–131、67–74：真实作者请求、PC签名及浏览器evaluate取JSON。tests/test_tieba_extractor.py163–178提供data.user.id/name/name_show/portrait，其中返回portrait含?t=10位数字。help.py222–237对昵称脱敏，故自己校验原始字段且不用输入兜底；helper110–122保留精确gss0.bdstatic.com固定头像路径。
- 贴吧[固定历史f328ee35b55e25e8aaeb9c847fe8b622e3f3447f](https://github.com/NanmiCoder/MediaCrawler/blob/f328ee35b55e25e8aaeb9c847fe8b622e3f3447f/media_platform/tieba/help.py)109–121及240–244证明creator曾消费该头像helper：可选user_show_info.feed_head.image_data.img_url，否则固定路径加returned portrait。只允许有证据固定形状，不继承任意URL或复制实现。无真实头像字节验收。
- 小红书锁定client581–604/extractor52–69只证明单HTML请求与user.userPageData容器。访问错误测试中的user_id=input是stub，不是响应。已只读补查[历史157ddfb21bd534109c0668ffeef9f643aa7c2d15](https://github.com/NanmiCoder/MediaCrawler/blob/157ddfb21bd534109c0668ffeef9f643aa7c2d15/store/xhs/__init__.py)：185取basicInfo，207的user_id仍来自函数输入，208证明nickname，210仅images字段。未证明返回身份/头像URL；仍需后续源发现，不猜basicInfo.userId或user.userId。

