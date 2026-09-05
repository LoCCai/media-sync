[English](creator-profile-design.md) | **中文**

# 下一切片：自动创作者资料

状态：**设计草案，未实现、未真人验证**。记录删除/报告交付后下一项必做工作。修改资料协议或 schema 前，须另行冻结目标/计划；本文不证明现有本地预览会访问平台。

## 源码核查

锁定 MediaCrawler `d6f7c5bb906b6dac40ddf343ef9e26438a3de092` 中，B 站 client `get_creator_info` 是单资料请求，core `get_creator_details` 则继续抓动态，不能用于资料查询。其他平台虽有单资料方法，仍须分别冻结身份/认证/字段/头像合同并验收。

当前 `Author` 按平台/远端 ID 跨账户共享。`AuthorRepository.upsert` 覆盖名称、handle、主页、头像，缺失值也覆盖。直接把远程昵称写进去，可能影响另一账户显示，或在下次入库时消失。保存会话与内容 runner 已共用 `_AccountFileLock`。SafeHttpClient 固定连接已验证 DNS 端点，但默认允许重定向，头像只检查初始 URL 不够。

## 拟定有界交付

1. 首先实现 Bili saved-session 单资料能力。独立隔离 runner 进行非交互认证后只调用一次作者资料接口，仅允许有界认证/WBI 准备请求；不得回退扫码、创建订阅、抓内容/动态/评论、运行 scheduler 或提升登录状态。建议总硬期限 45 秒，无自动重试，账户忙立即返回。整个子进程树退出前保持共用账户锁，保留 checkout/模块来源校验、私密 stdin、固定结果帧。
2. 复用持久 Operation，增加独立资料查询 kind 和精确 account target。拟定 POST `/api/v1/accounts/{account_id}/creator-lookups` 与精确 GET `/api/v1/creator-lookups/{operation_id}`，闭合输入/输出并沿用鉴权/CSRF。绑定账户/平台/稳定作者 ID、前端代际、后端单调代际和 Operation ID；持久化前复核租约/取消、当前凭据/认证快照与代际。前端身份/会话隔离防止 A→B→A 和迟到覆盖。候选失败不得清空既有成功资料。
3. 增加按账户/平台/作者隔离的资料缓存和独立订阅本地别名。保存上次成功昵称、规范主页、上游 SHA、时间、版本；头像单独记录版本/时间。可用有作用域和期限的资料凭单，让创建订阅读取服务器资料，而非信任客户端声称的远端名称。首片保留旧 Author 名称/导出路径，把旧标签迁移为本地备注，不宣称远端核验；普通入库不能擦除独立的成功资料。昵称成功、头像失败时允许更新昵称，但保留并明确标识旧头像。
4. CSP 不变。鉴权同源头像接口只接受 profile ID/revision，不接受任意 URL。Bili 拟定固定 HTTPS host/path 须以 fixture/真实证据确认，未知形状显示无头像。首片禁重定向，不发送 Cookie/auth，拒绝私网 DNS/IP、userinfo 和异常端口。建议上限 2 MiB、八百万像素、单帧 JPEG/PNG/WebP、抓取十秒；隔离且有界解码并重编码为受控静态格式，拒绝 SVG/HTML。缓存使用 UUID/哈希派生路径、nofollow/普通文件校验、正确 MIME/nosniff/CORP 和私有缓存。
5. 保留本地语法预览，将远程资料查询明确区分。UI 分别展示平台昵称、本地别名、观察时间、加载/错误及保留旧资料/无头像状态；精确账户和稳定 ID 有效后可自动执行一次有界查询填充表单，不无限重试，也不把本地预览称为远程查询。

其余六平台和 Cookie 模式资料查询仍是必做扩展，不能因 Bili saved-session 首片就宣传已实现。Cookie 模式另需处理 secret reference 不变而内容被替换的私密值变更隔离。粘贴 Cookie 登录校验/保存是单独已接受需求，资料查询不能替代。

## 资格前验证

对内容/动态/评论方法全部设陷阱，验证单资料精确调用数；拒绝错账户/平台/作者/代际/凭单及取消/凭据竞争；证明 lookup/login/crawl/detail 共用锁直至子树清理。认证过期不能触发扫码或修改 LoginSession。验证新建/升级迁移、入库/失败查询不抹除别名和资料、旧导出路径不变、头像 SSRF/跳转/重绑定/超限/慢流/解码/路径攻击、合成浏览器迟到响应。完成后再单独获授权做真实 Bili 单资料验证；离线检查不是平台 PASS。
