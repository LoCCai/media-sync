# 内容、资产、媒体库与 Emby/Jellyfin 联动计划

## 1. 目标

当前系统已经生成大量高质量领域数据，但 Web 只显示资产表格。需要把归档结果变成操作者可浏览和验证的媒体产品。

## 2. 内容浏览器

### 列表字段

- 平台；
- 作者；
- 发布时间；
- 内容类型；
- 标题；
- 正文摘要；
- Asset 数量；
- 下载完成度；
- 归档状态；
- 导出状态；
- 来源链接。

### 视图

- 表格：适合运维；
- 卡片：适合图文/视频浏览；
- 作者时间线；
- 仅失败；
- 仅未完整归档；
- 仅待导出。

### 内容详情

- 规范化字段；
- 原始来源 URL；
- 互动指标；
- Asset 顺序；
- 每个 Asset 状态；
- 归档摘要；
- Emby 输出；
- 关联运行和任务；
- 安全的 raw envelope 摘要。

不得直接把完整 raw payload 暴露给浏览器。

## 3. Asset 工作台

显示：

- kind；
- position；
- generation；
- locator 类型；
- download Job；
- 状态；
- checksum；
- MIME；
- size；
- ffprobe 流摘要；
- archive path 的逻辑相对标识；
- 最近失败；
- allowed actions。

操作：

- 下载/校验；
- 重试 retryable；
- 校验归档；
- 重新导出所属作者；
- 将 terminal 状态提交给未来的受控恢复流程。

## 4. 媒体预览

### 图片

后端提供受限缩略图端点：

- 只读取受管 archive；
- 校验路径收容；
- 大图生成缓存缩略图；
- 不允许任意文件路径参数。

### 视频

提供本地 Range 预览：

- 只允许 verified archive；
- Content-Type 白名单；
- Content-Disposition 安全；
- 不把 CDN URL返回前端；
- 预览失败不改变归档状态。

对于 FLV/DASH 合并后的 MP4，可以直接浏览器抽样；不支持浏览器格式时给出 ffprobe 信息。

## 5. 归档视图

展示：

- SHA-256 blob 数；
- 总容量；
- 重复引用数；
- 孤儿 blob；
- 数据库有记录但文件缺失；
- 文件存在但数据库无记录；
- 最近校验；
- 校验失败。

所有修复动作先生成 dry-run 报告。

## 6. 媒体库树

按导出器真实结构展示作者/季/集：

```text
作者
  ├─ tvshow.nfo
  ├─ poster
  └─ Season 2026
      ├─ S2026E0001.mp4
      ├─ S2026E0001.nfo
      ├─ poster/backdrop
      └─ gallery
```

显示：

- source fingerprint；
- tree SHA；
- manifest SHA；
- predecessor Job；
- managed file count；
- drift 检查；
- 用户修改文件是否被保护；
- 是否需要重新发布。

## 7. Emby/Jellyfin 连接

### 配置

- server URL；
- library ID；
- API key 只保存 secret ref；
- 路径映射：
  - media-sync `/data/library`
  - Emby 容器内路径；
- TLS 验证；
- 超时；
- 是否允许自动扫描。

### API 能力

- 测试连接；
- 获取服务器版本；
- 获取媒体库；
- 触发指定媒体库扫描；
- 查询扫描进度；
- 通过 provider ID 或路径查找项目；
- 记录抽样播放资格。

### 安全

- API key 不回显；
- 不把 Emby 配置写入普通日志；
- 仅允许配置的服务器 host；
- 防止通过设置形成 SSRF；
- 扫描操作持久化为 Operation。

## 8. 资格视图

每个平台显示：

| 项目 | 状态 |
|---|---|
| 真人登录 | PASS/FAIL/NOT_RUN |
| 作者扫描 |  |
| 无变化重放 |  |
| 真实增量 |  |
| 媒体下载 |  |
| SHA 归档 |  |
| Emby 导出 |  |
| Emby 扫描 |  |
| 抽样播放 |  |
| 最终等级 | Supported 等 |

证据关联到具体 Operation、Job、Content 和媒体服务器版本。

## 9. 图文内容策略

Emby 对图文内容的展示能力有限，因此 Web 本身应成为完整图文归档浏览器：

- 正文；
- 图集；
- 实况图片和视频配对；
- 来源；
- 发布时间；
- 归档校验。

Emby 输出继续保持确定性侧车和可选视频化策略，但不能把“Emby 中不易展示”误判成“归档失败”。

## 10. 验收

- 内容列表与数据库计数一致；
- 多 Asset 顺序正确；
- 缩略图和视频预览不能越过受管根；
- 不向前端泄露签名 URL；
- 任一归档缺失能被检测；
- 媒体库树与磁盘 manifest 一致；
- Emby 扫描结果可追溯；
- Supported 平台至少有一个可播放样本；
- 图文内容在 Web 中可完整阅读。
