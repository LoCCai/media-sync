**中文** | [English](usage.md)

# 日志中心使用与部署

## 显式部署

开发机不能运行Docker，以下是给操作者的步骤，并未在生产执行。保留现有凭据、Origin、挂载和已认证profile；诊断登录时保持之前停止的supervisor不启动，不做批量登录/重试。

```sh
git pull --ff-only
docker-compose build media-sync
docker-compose run --rm --no-deps --entrypoint /app/.venv/bin/media-sync media-sync serve --check-config
docker-compose up -d --no-deps --force-recreate media-sync
```

只有配置校验成功后才执行最后一条。现有/data挂载将日志保存在/data/state/logs，不需要公开静态挂载或连接媒体服务器。API和supervisor必须继续共享同一state挂载，不要经反代公开这个目录。

可选环境变量，API/supervisor取相同值：MEDIA_SYNC_LOG_SEGMENT_MAX_BYTES=16777216、MEDIA_SYNC_LOG_TOTAL_MAX_BYTES=1073741824、MEDIA_SYNC_LOG_RETENTION_DAYS=7。总量必须容纳至少两片。限制由部署配置，浏览器仅查看。

## 诊断一次尝试

1. 在已登录后台打开日志中心，先检查存储健康及丢弃/非法/排队数量。
2. 部署后，由你在准备好时仅手动重试一个原先失败的平台，不为产生日志而重试已认证账户。
3. 打开该次确切任务，点日志中心链接查看阶段、动作、结果。选择器或探测失败后可能fallback成功，只有持久账户状态确立登录成功。
4. 选定操作后主动下载诊断JSON，其中包含有界保留日志页、持久控制事件/关联身份、版本及覆盖限制，不自动上传。
5. 页内出现扫描受限、省略尾部、损坏或下一页时，当前证据不完整。继续分页或缩小时间/平台/身份范围；诊断包不是无限归档，分享时保留覆盖提示。

只读接口：/api/v1/logs/status、/api/v1/logs、/api/v1/logs/operations/{operation_id}、/api/v1/logs/operations/{operation_id}/diagnostic，均要求既有operator鉴权。查询支持operation/account/login_session/job/run/subscription UUID、platform/module/level/event_code及since/until。API时间使用精确UTC微秒格式，例如2026-09-06T12:00:00.000000Z，页面自动转换本地时间；limit为1–200。未知/重复参数和任意文件路径拒绝。游标绑定同一筛选及store实例，重启或保留清理后需刷新。

## 保留范围与限制

分片按大小或新UTC日期的下一次写入轮转；保留/容量清理由写入触发，仅删除签名有效的受管已封存普通文件，保护活跃片和无关路径。队列、flush/close和读取均有界。入队不等于持久化，fsync失败可能丢记录，页面显示降级。读取按分片升序，不是全局时间排序；目录清单最多4096项，每页事件扫描最多4MiB/2秒。读取可初始化私有marker。

计数为当前进程值，重启不恢复。异常退出遗留.open可读，但不自动回收，仍计入容量并可能最终阻止新写入。没有自动删除命令：手动维护前先检查并备份精确日志目录，不删除其他活进程的活跃片。权限/磁盘问题需操作者修正。

分页不是一致性快照：游标越过较旧活跃片后，该片可能又被追加，后续页可能遗漏这些新记录；任务结束后应从头重新查询。先修正存储问题，再重启已降级写者。有界诊断页不保证包含该操作全部仍保留的历史。

只保留安全结构化类别和显式生命周期事件；不保存Cookie值、请求头、URL、二维码、远端HTML、选择器文本、原始异常、traceback局部变量和任意日志message。标准Python日志仅保留类别/级别/数量。早期启动/配置错误、Docker/Xvfb输出和未加埋点的第三方内部日志不会自动收入本中心，仍需原控制台证据。旧缺失扫码细节不可恢复，本版没有真人平台验收结论。
