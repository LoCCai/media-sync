[English](goal.md) | **中文**

# 执行 0053 目标

- 状态：已规划；尚未开始实现
- 日期：2026-09-05
- 前驱：be26cc7（执行 0052 收尾）
- 范围：内容与资产浏览、安全本地归档预览及 Web 目录升级
- 数据库 migration：计划不新增
- 计划提交：包含本记录的提交（不嵌入自身 SHA）

## 结果目标

1. 为既有有界内容/资产列表 API 增加向后兼容的服务端筛选，同时保持数组响应形状和既有安全字段。
2. 新增精确内容详情与资产详情端点，提供目录、生命周期、完整性和关联事实，但不暴露上游 raw、locator、源 URL、宿主路径、异常正文、凭据或签名 query 值。
3. 新增通过资产 UUID 寻址的 GET/HEAD 本地归档访问。路径只从权威 Asset 行解析，必须匹配精确内容寻址位置，并通过同一个已打开文件描述符完成验证和流式读取。
4. 支持单个 HTTP byte range，正确处理 200、206、416；解析有界，Content-Length/Content-Range 精确，媒体类型采用安全白名单，并设置 no-store 与浏览器安全响应头。
5. 恢复只进入既有持久 asset-download Operation。归档缺失、损坏或不安全时，预览返回固定且安全的“需要恢复”结果；UI 可提交既有下载/校验端点，但不新增 reset 快捷路径或 Operation kind。
6. 将 Contents、Assets 与 Library 路由升级为可用目录：服务端筛选、安全详情、有序关联资产、合格图片/音频/视频内联预览、恢复动作及作者下钻。

## 验收边界

- GET /api/v1/contents 与 GET /api/v1/assets 的既有客户端继续收到数组，并可继续使用原参数。新增筛选均为可选、有界、确定性。
- GET /api/v1/contents/{content_id} 返回完整纯文本正文、有序安全资产摘要和导出事实；GET /api/v1/assets/{asset_id} 返回安全生命周期与预览资格事实。
- 详情和列表 JSON 绝不包含 Content.raw、Asset.raw、Asset.locator、Asset.source_url、Asset.local_path、下载 validator、错误正文、导出 output path 或 settings 路径。
- 预览端点不接受 path 或 URL；只服务处于 verified/exported 状态、具备完整 size 与 SHA-256 元数据，并位于 archive/sha256/<前缀>/<摘要>.<扩展名> 的 Asset。
- 预览只打开配置归档根下的普通、非链接、单硬链接、只读文件；同一描述符用于 SHA-256、大小、身份检查和响应流。替换、写入变更、符号链接、硬链接、越界、缺失和损坏全部关闭失败。
- 只接受单个 bytes range；支持前缀、开放尾部和后缀范围，多范围、畸形和不可满足范围返回 416，并携带权威总大小。
- 不新增数据库 revision、缩略图缓存、归档删除、孤儿清理、Operation kind，也不允许 GET/HEAD 隐式修改状态。
- Python/Web 专项测试与仓库门禁通过。真人平台、CDN 与真实 Emby/Jellyfin 资格继续在 Execution 0047 下保持 NOT_RUN。

## 明确限制

执行 0053 不新增媒体服务器连接、扫描触发、播放资格、文件系统树浏览、生成缩略图、归档盘点清理、操作者鉴权、破坏性删除或保留策略。媒体库树与真实 Emby/Jellyfin 控制仍归 0054；鉴权、保留及破坏性动作归 0055；最终迁移与发布归 0056。
