[English](plan.md) | **中文**

# 冻结计划

1. 先提交本计划，后实现。保留上游锁、依赖和schema；按[来源](sources.zh.md)原创协议事实并复用真实锁定方法，不复制第三方实现/响应夹具。两平台分离模块，Root负责共同身份、worker路由、头像边界、API/UI和端到端凭单测试。
2. 抖音入口lookup_douyin(checkout, profile, remote_id, deadline, cookie可选)：保留精确saved_session或全新Cookie上下文，只在本地fulfill的固定官方空白页读取必要localStorage/UA，禁止其余浏览器网络。实际导入前绑定Node的execjs编译，运行锁定get_user_info/get/参数处理/JS签名；一次固定HTTPS profile/other GET，严查身份、固定参数、headers及真实a_bogus，预算/无重定向/无代理/固定DNS。返回user.sec_uid必须字符串等于输入，原始nickname有界；status_code整数0为本方保守成功子集，不宣称来源证明所有响应皆如此。无pong/self/内容请求，不修改认证。未知签名或响应失败保持固定分类、不回显秘密、不伪造token。
3. 贴吧入口lookup_tieba同签名：真实get_creator_info_by_url→_fetch_json_by_browser→_sign_pc_params，由限一次Page适配器接管唯一签名GET /c/u/pc/homeSidebarRight。固定portrait/un/subapp_type/_client_type/sign，禁goto/tbs/feed/额外evaluate；网络仍经有界pinned HTTP。先严格解析JSON再交上游，防重复键/NaN/宽松缺字段成功。error_code必须整数0，若no存在也须整数0。extractor只接收同一实际返回对象并输出自己的原始资料DTO。
4. 身份：DY精确ASCII [A-Za-z0-9_-]{1,255}；贴吧裸现代tb.1. portrait后缀28–31字符，禁连续点/末尾点。返回portrait仅允许裸输入或裸输入加唯一?t=10位ASCII数字，再精确绑定；禁止别名/数值ID替换/任意query/输入兜底。昵称name_show优先，仅缺失或空值才取name，坏类型不隐式str。上述输入/格式是本方安全子集。统一主页为douyin.com/user/ID及tieba.baidu.com/home/main?id=portrait。
5. 贴吧头像只允许来源证明的精确https://gss0.bdstatic.com/6LZ1dD3d1sgCo2Kml5_Y_D3/sys/portrait/item/{返回portrait}，可带已证明?t=时间戳；须绑定同一portrait，未知img_url不抓取、不扩展通配域名。复用有界无Cookie隔离抓取/解码/同源PNG/CSP，失败不阻塞昵称且保留旧头像。抖音头像缺可信URL形状证据，仍待接入。
6. 拓展六平台自动昵称查询、各自输入校验、主页/身份/结果/凭单和账户页说明；B站/微博/贴吧可选头像，其余明确仅昵称。资料刷新不重命名Author/历史导出。修复旧unsupported断言而保留非法平台拒绝，长ID与平台隔离不放宽数字UID。资料查询不要求全历史采集确认，内容采集保持原门禁。
7. 小红书已查锁定和历史固定源，昵称字段可证明但返回身份仍是输入回填，不能开放成功链或写空骨架。继续来源发现作为后续必做，不把六平台称七平台完成；DY/KS本人Cookie验证及更多头像/媒体/真人验收保持开放。
8. 真实锁定方法+合成HTTP/browser验证签名、固定预算、候选Cookie隔离、重复键/坏Unicode/错身份、头像安全/可选失败、进程私密帧、API订阅回执/保留原路径/晚结果等；实施中专项，源码冻结后完整回归、Web/静态/文档/锁/打包审核。记录实际失败、精确命令/计数/跳过，不累加重叠专项。最后双语提交、普通push/fetch核对和单独发布记录；当前Linux/真实PG/平台/CDN/播放未执行则NOT_RUN。

