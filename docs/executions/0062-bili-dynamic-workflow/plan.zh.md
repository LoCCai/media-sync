[English](plan.md) | **中文**

# 冻结实施计划

1. 保留既有policy v1及`bili-scan-v1`仅投稿行为。新增显式B站policy v2范围`uploads`、`dynamics`、`both`，不静默扩大旧订阅、不创建竞争的Account/Author订阅。复合cursor绑定账户/作者/上游SHA，保留原投稿cursor及独立动态头部/历史进展。改范围保留停用feed状态，受当前日程/Run栅栏保护，不把旧水位解释成覆盖证明。
2. 每Job一个有界feed单元，公平轮换投稿/动态及头部/历史。动态发现先持久保存有界私密不可变整页快照，再允许checkpoint引用；cursor/报告仅含范围、digest及有界进展，绝不含正文/媒体URL。允许只发现的单元发布零内容和待处理项。精确DID/type/普通作者/pub_ts详情确认后才能消费pending；整页消费完成前保留next offset，不因数量上限丢页内剩余，不把详情缺失/变化当成功消费。检测重复offset，真实报告保守重启/部分推进/源末尾。快照绑定账户/作者/SHA，私密、digest校验、路径约束；不隐式清理或跨账户复用。
3. 按固定来源原创实现协议事实，不复制GPL实现或第三方响应fixture。复用锁定Bili client/签名/浏览器账户路径：feed/space、`id=DID`动态详情，以及summary不足以证明完整正文时的同DID OPUS详情。WORD/DRAW支持旧desc/draw及OPUS文字/静态图片。普通作者MID必须匹配订阅；不把转发orig、剧集、专栏、付费或未知子型递归当作自有原创。保留真实未支持组件诊断，不宣称全媒体支持。OPUS不能静默遗漏不支持段落后称正文完整。
4. AV动态与视频保持独立身份。按既有媒体合同重新核验普通View的aid/bvid/owner/pages/CID，动态pub_ts不是视频pubdate。保留动态文字/自有DID及明确普通投稿引用，普通AID去重，不接管联合创作/转发他人视频归属。保持现有规范化记录数量上限，为AV引用预留两条记录。新动态/混合订阅max_items至少2（默认30），UI/docs明确此约束，保留仅投稿max_items1；尾部AV放回pending，不超预算。
5. 版本化封存coverage及精确身份交叉检查贯穿bridge、真实shim、normalizer、CLI、scheduler及原子有界入库。cursor、内容/资产、刷新观察与Run成功一起发布。保留取消、租约、日程、expected checkpoint、source digest及耐久成功恢复。动态image槽必须通过精确dynamic/OPUS刷新，证明当前作者/DID与完整有序图片身份；不把数字DID当AID，不允许附件变化后解析旧资产。引用AID仍走原普通投稿刷新。
6. 订阅UI/API/CLI暴露范围和真实各feed进展，不暴露原始状态或凭据。验证合成锁定client请求/签名预算、响应形状、跨页重启续抓、pending保留/删除/漂移、快照篡改/错误绑定、WORD/DRAW/OPUS/自有及他人AV、命名空间/去重、取消/CAS/恢复、离线真实下载/归档/本地导出幂等。本地输出不需要连接媒体服务器；不声称任意文字/图集文件均可在Emby/Jellyfin播放。
7. 实施中采用增量测试和独立复核，最终受影响回归前先冻结源码。完整目录快照、最终源码专项、环境跳过和失败分列，不累加或误标。保存双语goal/plan/progress/verification及来源证据，更新项目状态/部署说明，双语本地提交、非force推送GitHub及fresh-fetch相等核验。生产入口或所需输出链未接通前不宣称完成。

不操作生产登录、Cookie输入、订阅修改、真人查询/重试/采集、下载/导出、部署、媒体服务器或恢复supervisor。其他五平台资料、剩余三平台Cookie校验仍需完成，不把原目标替换为仅B站支持。
