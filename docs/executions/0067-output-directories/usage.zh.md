**中文** | [English](usage.md)

# 使用与升级注意

这是0067目录功能，不是扫码修复版。未代用户部署。

1. 升级前备份数据库和已有媒体。新schema为0012_library_output_policy；已有策略或绑定时拒绝降级，不能直接回滚旧schema丢掉位置记录。
2. 保留现有/data挂载。需要独立宿主机媒体盘时，在media-sync和supervisor两个服务都增加相同容器路径，例如宿主机`/srv/media-sync-library`挂载到容器`/media-library`。不要把整个/data替换成新空盘；凭据、数据库和原归档仍在那里。
3. 启动更新后的API与supervisor使用同一数据库；在设置→自动下载·媒体目录填写`/media-library`。七平台覆盖留空时，默认使用`/media-library/bili`、`/media-library/dy`等；独立平台盘同理先挂载再填写覆盖路径。
4. 预览显示生效目录但不创建文件；保存后新工作读取共享设置，不依赖服务启动快照。挂载目录仍需允许容器运行用户写入。
5. 既有媒体保持原位置，通常是/data/library下作者目录。受保护平台需要保留该根，例如总根改到/media-library时显式填写B站覆盖/data/library；其它新平台可使用新目录。已有内容的物理迁移尚未提供，不要自行改数据库位置。
6. 若初始化提示output_directory_migration_required，且尚未保存策略，先恢复部署原先的MEDIA_SYNC_EXPORT_DIR及挂载。已保存Job的scope只有哈希，程序不能倒推出旧路径；多个历史根需要后续显式迁移审计。
7. 将这些实际目录只读挂载给Emby/Jellyfin并添加对应媒体库，由其扫描目录即可。无需连接服务器API或另点导出；文本/图集保留不代表媒体服务器能把它们当视频播放。可选服务器联动仍只支持既有单根映射，新平台根不能自动套用旧映射。

保存/预览不会启动登录、历史扫描、批量下载或服务器刷新。supervisor如仍处于用户此前暂停状态，不会被此设置恢复。
