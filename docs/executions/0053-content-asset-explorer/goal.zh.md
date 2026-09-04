[English](goal.md) | **中文**

# 执行 0053 目标

- 状态：已完成
- 日期：2026-09-05
- 前驱：be26cc7（执行 0052 收尾）
- 范围：内容与资产浏览、安全本地归档预览及 Web 目录升级
- 数据库 migration：无
- 计划提交：`66e18ff`

## 已交付结果

1. 为既有有界内容/资产列表 API 增加了向后兼容的服务端筛选，同时保持数组响应形状、既有默认行为和安全字段。
2. 新增了精确内容详情与资产详情端点，提供目录、生命周期、完整性和关联事实，且不暴露上游 raw、locator、源 URL、宿主路径、异常正文、凭据或签名 query 值。Canonical 链接会被裁剪到匹配平台的官方公网域名边界。
3. 新增了通过资产 UUID 寻址的 GET/HEAD 本地归档访问。路径只来自权威 Asset 行，必须匹配精确内容寻址位置，并由同一个受控文件描述符完成验证和流式读取。
4. 交付了严格的完整表示与单 Range HTTP 行为，包括精确 Content-Length/Content-Range、封闭安全媒体类型、no-store 缓存和浏览器安全响应头。
5. 恢复仍只进入既有持久 asset-download Operation。归档缺失、损坏、不安全或未就绪时返回固定安全恢复结果；未新增 reset 快捷路径或 Operation kind。
6. Contents、Assets 与 Library 已升级为可用目录，提供服务端筛选、安全详情、有序关联资产、合格图片/音频/视频内联预览、恢复动作及作者下钻。

## 验收边界

- GET /api/v1/contents 与 GET /api/v1/assets 的既有客户端继续收到数组，并可继续使用原参数。新增筛选均为可选、有界、确定性。
- GET /api/v1/contents/{content_id} 返回完整纯文本正文、有序安全资产摘要和导出事实；GET /api/v1/assets/{asset_id} 返回安全生命周期与预览资格事实。
- 详情和列表 JSON 绝不包含 Content.raw、Asset.raw、Asset.locator、Asset.source_url、Asset.local_path、下载 validator、错误正文、导出 output path 或 settings 路径。
- 预览端点不接受 path 或 URL；只服务处于 verified/exported 状态、具备完整 size 与 SHA-256 元数据，并位于 archive/sha256/<前缀>/<摘要>.<扩展名> 的 Asset。
- 预览只打开配置归档根下的普通、非链接、单硬链接、只读文件；同一描述符用于 SHA-256、大小、身份检查和响应流。替换、写入变更、符号链接、硬链接、越界、缺失和损坏全部关闭失败。
- 仅 GET 处理 Range，且必须先让完整表示通过状态、路径、身份、大小和 SHA-256 验证。单个 ASCII 大小写不敏感的 `bytes` Range 支持显式、开放尾部和后缀形式；多范围、畸形和不可满足范围返回 416，并携带权威总大小。
- HEAD 忽略 Range，返回已验证完整表示的响应头且正文为空。`If-Range` 只有与当前强 ETag 精确相等时才允许 GET 返回范围；过期、弱、日期或畸形 validator 均回退完整 200 表示。
- 已验证空表示返回长度为零的完整 200；其任何 GET Range 都不可满足。表示验证失败优先于 Range 错误，并返回固定恢复结果。
- 不新增数据库 revision、缩略图缓存、归档删除、孤儿清理、Operation kind，也不允许 GET/HEAD 隐式修改状态。
- Python/Web 专项测试、本地 query/弹窗浏览器 smoke、完整 Python 套件（`2456 passed, 3 skipped`）与静态仓库门禁均通过；冻结收尾证据另行记录。真实平台、CDN 与真实 Emby/Jellyfin 资格继续在 Execution 0047 下保持 `NOT_RUN`。

## 明确限制

执行 0053 不新增媒体服务器连接、扫描触发、播放资格、文件系统树浏览、生成缩略图、归档盘点清理、操作者鉴权、破坏性删除或保留策略。媒体库树与真实 Emby/Jellyfin 控制仍归 0054；鉴权、保留及破坏性动作归 0055；最终迁移与发布归 0056。
