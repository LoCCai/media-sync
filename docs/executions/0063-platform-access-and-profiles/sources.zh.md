[English](sources.md) | **中文**

# 来源证据

运行时仍锁定MediaCrawler `d6f7c5bb906b6dac40ddf343ef9e26438a3de092` 与bili-sync-up `dcb5bb73b56ac45b2525da14b389e185b0ea6dbd`。只读本地及公开GitHub/raw，无平台请求；源可达不等于真人验收。

- 贴吧：[aiotieba固定SHA6a32de113ba35dd4da2ec0e76540e79678f9b8d8本人API](https://github.com/Starry-OvO/aiotieba/blob/6a32de113ba35dd4da2ec0e76540e79678f9b8d8/src/aiotieba/api/get_selfinfo_moindex/_api.py)16–35证明no成功/错误处理和GET `/mo/q/newmoindex?need_user=1`；相邻 `_classdef.py`49–52映射本人data.id/portrait/name。教程 `docs/tutorial/start.md`13–15说明BDUSS认证，35–63区分不可变非零uint64 user_id与可变/可空user_name及portrait。`core/http.py`69–89按域发送BDUSS及可选STOKEN。未找到无效Cookie响应夹具/错误码证明；非零no不编造auth_expired。当前get_self_info走不同login.request，其测试不能证明moindex已实测。Unlicense，仅原创协议事实，不继承ssl=False或回显秘密错误。
- 快手：锁定 `media_platform/kuaishou/client.py`68–79已unwrap data，284–290得到visionProfile，389–396的get_creator_info漏visionProfile层。`graphql/vision_profile.graphql`1–24声明userId及profile.user_id/user_name/headurl；`help.py`115–137证明主页使用opaque ID而非数字UID。强制响应ID相等是本方拒绝歧义规则，不是已证明的上游身份转换；关注列表pong的result1不足以本人认证。[历史MediaCrawler157ddfb21bd534109c0668ffeef9f643aa7c2d15](https://github.com/NanmiCoder/MediaCrawler/blob/157ddfb21bd534109c0668ffeef9f643aa7c2d15/store/kuaishou/__init__.py)105–113消费name/headurl但user_id来自输入，不能证明响应身份。未找到非合成头像CDN样本。
- 知乎：锁定get_creator_info签名GET `/people/{token}`，extractor选 `initialState.entities.users[token]` 但匿名化name且丢弃urlToken/avatar。[历史help.py](https://github.com/NanmiCoder/MediaCrawler/blob/157ddfb21bd534109c0668ffeef9f643aa7c2d15/media_platform/zhihu/help.py)355–359消费id/name/avatarUrl/urlToken，却允许输入token兜底；该兜底不是身份权威，必须精确响应urlToken。复用真实锁定get/sign与0058 `/api/v4/me` uid/name本人合同，小写cookie及x-zst-81/x-zse-96不可丢；Node避免Cookie进入临时JS。该历史树无响应/头像夹具，单个avatarUrl字段不足以证明CDN形状。

仅作后续线索：小红书client581–604资料HTML及extractor52–69/userPageData；抖音client312–319/other资料但当前store空操作；贴吧client646–678/homeSidebarRight需返回portrait绑定。端点存在不等于已支持。
