[English](plan.md) | **中文**

# 冻结分阶段计划

1. 阶段A——已观察内容归属不可漂移。内容身份仍为(platform,remote_type,remote_id)；新身份绑定作者，后续同作者资料可刷新，异作者返回固定脱敏ContentOwnershipConflictError。SQLite/PostgreSQL原生upsert在实际冲突更新语句中限制existing author_id，不采用先检查后覆盖；拒绝时不能改元数据/tombstone/路径/来源。保留savepoint回滚及外层事务可用性。PostgreSQL作者创建也使用原生冲突处理，让并发首次发现到达同一归属栅栏。其他dialect fallback对已找到行加锁，不改作者。不得改写历史归属或隐式提供接管/修复。
2. 阶段A——固定content_ownership_conflict贯穿入库/scheduler/CLI与面向用户的Web诊断，不自动重试、不触发账户级熔断；说明原内容仍归原作者，检查订阅/来源，而非删除数据或盲目重登。保留精确Run/Job真值及失败清理，错误不含秘密或原始远端/账户/内容身份。旧模式已提交批次保留原有语义；冲突批次或有界单元不推进检查点，不写资产/刷新来源。不能声称旧多批次运行全部处于一个事务而回滚此前已提交工作。
3. 阶段A验收——先以回归复现原覆盖，再验证同作者刷新、异作者元数据不变及作者/savepoint回滚、dynamic/upload命名空间分离、竞争胜负、旧ORM缓存、真实规范化入库/scheduler错误与Run/Job/来源/pipeline行为。验证SQLite及可用PostgreSQL，未配置PG为NOT_RUN；固定错误/UI渲染和原媒体/归档/导出/平台回归。双语保存实际失败/检查，双语提交、非force推送并fresh fetch相等。
4. 阶段B（尚未实施）——显式版本化订阅采集范围（投稿、动态、两者）。保留旧v1仅投稿语义及旧投稿cursor；一个Account/Author订阅不能变为两个竞争订阅。复合cursor绑定账户/作者/SHA并独立保留feed进展，不复制水位或静默扩大范围。每Job一个有界feed单元、公平选择、共享max_items预算、准确部分推进/源末尾展示。
5. 阶段C（尚未实施）——建立有来源证据的动态作者/WORD/DRAW或OPUS/AV身份和附件形状，以及精确有界媒体刷新权威。锁定MediaCrawler只有feed/space offset列表，无单动态详情方法且丢附件；当前B站refresh只支持普通VIDEO/COVER。列表正文可能在重试前消失：必须先建立精确detail合同，或消费前持久保存有界私密不可变整页快照。不得max_items截断后推进offset而丢页内剩余内容，不把媒体URL放公开checkpoint，不从合成fixture猜远端端点/字段。
6. 阶段D（尚未实施）——原创文字、静态图集、自有普通投稿引用贯穿显式范围/UI/CLI、真实锁定client/shim、receipt封存和源作者证明、原子cursor入库、精确来源刷新、安全下载、归档、本地Emby/Jellyfin结构。DID与AID分离；重复AV引用去重，不重归属他人视频。未知/转发/专栏/直播/付费形状需要真实未支持/保留诊断，不递归采集无关作者。验证同秒/置顶/重排/循环offset、待办保留、快照/详情篡改、取消/租约/CAS/恢复、图片顺序/替换、视频owner/AID/BVID/CID及离线真实流水线导出幂等。生产入口可达且验证后才算阶段完成；真人资格单列。

本轮不操作生产登录、Cookie输入、订阅修改、重试、下载/导出、部署、媒体服务器或恢复supervisor。阶段A只能作为明确标注的前置条件单独发布；B–D和七平台总目标继续开放。

