[English](progress.md) | **中文**

# 推进结果：原生 MediaCrawler 登录现已接入订阅主链

状态：本地实现已在提交 `165516a` 中完成；该 revision 的服务器部署与真人平台验收仍待执行。

## 结果

产品边界已经修正并收敛：

```text
/crawler/（MediaCrawler 原生 QR/Cookie 登录及爬虫控制）
    -> 显式认领已保存 profile
    -> Account 级已验证会话快照
    -> 既有 Subscription scheduler
    -> Job 级 JSONL 摄取
    -> 下载/归档
    -> 配置的媒体库根/<platform>/<creator>/ + NFO
```

media-sync 不再把自建扫码、粘贴 Cookie、登录预检和登录诊断工作台作为 Accounts 正常流程。账户页现在只有三个直接步骤：打开原生爬虫控制台、在那里完成登录、把已保存会话认领给同平台的本地 Account。

## 已实现

1. **原生控制台负责登录。** 锁定的 MediaCrawler WebUI 继续挂载在经过鉴权的 `/crawler/`，直接使用其平台、QR/Cookie、creator/detail/search、启动/停止、实时日志与数据预览控件；没有再增加第二套平台登录界面。
2. **显式认领 Account 会话。** `POST /api/v1/accounts/{account_id}/crawler-profile` 只接受 `expected_auth_revision`。Account 身份与平台来自数据库；浏览器不能提交 profile 路径或 Cookie 内容。
3. **验证 profile 快照。** 内嵌 crawler 静止时，media-sync 不跟随链接，只复制普通 profile 文件到临时 Account 形状目录，再用现有锁定版非交互 saved-session 探针校验，并禁止二维码回退。只有已认证结果才能继续。
4. **原子替换与回滚。** 获取真实 Account profile 锁后，已验证快照原子替换该 Account 的旧 profile；数据库 revision 冲突会恢复旧 profile。WebUI 来源保留，方便以后在原生界面续登并再次显式认领。
5. **恢复订阅。** 认领成功发布 `saved_session / authenticated`、递增 `auth_revision`、清除不兼容的 credential/profile 覆盖，并且只恢复该 Account 的 `waiting_auth` 同步 Job；不会恢复 `waiting_user`。
6. **公开错误契约。** API 把内部失败映射成 `crawler_busy`、`account_busy`、`crawler_profile_not_found`、`crawler_profile_auth_failed`、`account_revision_conflict` 等少量稳定错误；Web 只展示固定中文操作提示，不回显路径、Cookie 或原始异常。
7. **调度贯通证据。** 新集成测试先认领合成 WebUI profile，再创建 B 站 Subscription，证明 scheduler 以 `saved_session` 使用精确安装的 Account profile、不解析 Cookie secret，随后成功完成规范化摄取。
8. **知乎 WebUI 薄兼容。** 锁定上游 CLI 会为六个平台映射 `--creator_id`，但遗漏 `ZHIHU_CREATOR_URL_LIST`。child 薄兼容层现在只补 `zhihu + creator` 的这个赋值，保持上游 argv 不变，也不修改 `.upstream`。

## 直接复用而非重写

- MediaCrawler 负责交互式平台登录与爬虫操作。
- 既有 media-sync scheduler 负责 Subscription 历史/增量运行及限速/退避策略。
- 既有 Job 级 receipt 与摄取继续作为权威；共享 `/data/mediacrawler/webui-output` 仍只是交互控制台输出区，不会被静默导入。
- 既有下载、SHA-256 归档、输出目录与 Emby/Jellyfin NFO 代码仍是唯一的定时交付路径。
- Emby/Jellyfin 服务器连接是可选项；未配置 provider 时仍会向配置目录写入兼容文件与 NFO。

## 2026-09-06 的历史 0072 部署观察

在部署 `165516a` 之前，操作者打开既有 0072 部署的 `/crawler/`，观察到 `{"detail":"license_acknowledgement_required"}`。API 服务本身缺少 `MEDIA_SYNC_MEDIACRAWLER_LICENSE_ACKNOWLEDGED=true` 时，许可证门按设计保持关闭；supervisor 命令行的确认不能配置 API 容器。必须把该变量加入 `services.media-sync.environment` 并强制重建该服务容器。该观察不能识别或赋予 0073 镜像资格，且尚未收到修改后的页面结果。

## 待执行的真人工作

- 在 Linux 主机拉取并构建最终发布 revision。
- API 容器确认许可证后，验证 `/crawler/` 正常加载。
- 七个平台逐项执行原生 QR 或 Cookie 登录，停止/等待 crawler 完成，再认领同平台 Account 会话并记录真实结果。
- 用一个有界 Subscription 金丝雀贯通作者查询、采集、媒体下载和最终目录/NFO 检查，再验证之后的一次增量周期。
- 所有未观察的平台/CDN/历史完整性行继续标记 `NOT_RUN`，不能从离线测试推导七平台成功。
