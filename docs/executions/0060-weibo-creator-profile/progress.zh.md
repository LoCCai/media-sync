[English](progress.md) | **中文**

# 推进记录

基线已核实。只读上游审计确认微博有固定登录config接口与独立单作者接口；core后续含全历史链路，资料查询绝不调用。依赖实施前冻结本计划，保留既有B站采集发布，无生产操作。

计划冻结于`83ff442`。应用层/仓库已允许平台绑定的微博数字身份及固定主页，保留全部发布栅栏；Web与受监督runner独立实施。可选头像窄规则是以合成URL验证的设计合同，不是上游/真人已验证列表：锁定仓库只有无效头像示例，未提供真实CDN URL证据。未知图片形状跳过，昵称和旧头像保留。

剩余平台只读审计：抖音pong使用本地HasUserLogin/LOGIN_STATUS，唯一资料接口明确查他人；快手pong读取关注关系列表GraphQL，只判断result=1而没有明确本人认证；贴吧pong仅判断token存在。这些不能作为粘贴Cookie远端认证证明。小红书资料从HTML提取userPageData，但锁定源码/fixture没有建立同一响应中的精确身份/昵称/头像形状。这些仍是必须补齐的合同证据工作，不冒称已实现或放弃；不猜self端点，也不把公开数据成功提升为认证成功。

## 实施与审查结果

微博worker只导入已验证client/config/utils，不导入微博core/login/store，直接使用作用域内凭据构造真实client。在严格config→creator序列前替换有五次重试的request，保留真实get/get_creator_info_by_id方法，精确检查完整query/header/调用顺序并投影固定原始响应。Cookie候选在私密帧/HTTP头完整保留，保存会话仅读取m.weibo.cn；其他五平台资料仍unsupported。

service/仓库/UI使用平台绑定固定主页，保留账户/Operation/代际/auth_revision/凭单栅栏。可选图片失败保留昵称及旧头像。独立审查发现新通用CDN并集会把B站下载范围扩大到新浪：现由service在调用下载器之前按资料平台校验，四个API case证明跨平台URL零调用且昵称仍成功。独立复核确认修复，无新增可复现阻断；这是代码审查，不是真人资格。

Web覆盖B站/微博Cookie及保存会话，每个完成输入身份查询一次，显式手动重试，保留迟到响应/账户/平台/会话隔离，不依赖采集全历史勾选。不重命名既有作者/归档/导出路径。其余五平台资料、三平台Cookie校验及先前开放的真人闭环义务仍須完成。

最终冻结源码完整Python目录4729通过、23项环境跳过；Web635通过，静态/docs/上游及源码一致的wheel/sdist通过。验证文档保留精确命令、早期失败及真人排除范围。双语实施提交`315b2ff`已非force发布GitHub，fresh fetch确认HEAD/origin相等、工作区干净。本条最终文档记录另行双语提交，不代表部署。
