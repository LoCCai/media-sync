[English](deployment-handoff.md) | **中文**

# 跨服务器反代部署交接

- 日期：2026-09-05
- 应用基线：`0fd7c17`
- 状态：已观察到认证后后台进入；平台登录失败诊断中；完整验收未完成

## 目标与计划

为应用主机及另一台局域网 HTTPS 反代提供完整 Compose。保留七平台目标、已发布应用代码、认证、数据卷和外部凭据；明确真实浏览器 HTTPS 入口，同步健康检查 Host，本地校验后由操作者先预检再重建容器。不得编造公开域名，也不把 HTTPS Origin 配置当作给 HTTP 后端启用 TLS。

## 初次推进与证据（历史）

操作者报告 checkout 为 `0fd7c17`，镜像为 `sha256:468ba823e582f39fd7ae79b2c0550ff3f89081ab510f102ce19d1f0a66acacd5`，运行 UID 1000，凭据 UID/GID 0、模式 0600，返回 `SECRET_UNREADABLE`，新版预检入口存在且认证预检拒绝。这支持“凭据不可读”判断，不代表部署成功。仅针对普通 rootful、无用户映射 Docker 建议单文件所有者修正；尚未收到随后预检成功结果。

对局域网 HTTP 根页面和公开 health 的两次直接只读请求均返回 403 `operator_host_forbidden`，证明网络可达，但不证明部署身份、登录成功或当前进程启动日志。先前 tail 日志可包含历史失败。

生成的个人 `docker-compose.yml` 由 Git 忽略，不对外发布。保留用户构建代理、外部 secret 路径、命名卷、tmpfs、全网卡 8632 端口及可选 supervisor profile。`MEDIA_SYNC_PUBLIC_HOST` 是 HTTPS Origin 与健康检查 Host 共用的必填 host[:port]；不含协议/路径/末尾斜杠/显式默认 :443，非默认 HTTPS 端口必须保留。supervisor 不提供 HTTP，禁用继承的 API 健康检查，不将其当作 worker 健康证据。

## 初次验证（历史）

- 使用既有 Prettier YAML parser 成功解析整个生成文件，格式检查通过。
- 四项应用策略纯函数检查通过：默认 HTTPS 权威与 :8443 接受相应 Host 并设置 Secure Cookie；直接策略校验拒绝显式 :443 及局域网 HTTP。健康检查使用规范化权威。
- 独立审查确认跨机 TLS 终止、HTTP 上游与代码兼容：保留真实 Host、Origin、Cookie、CSRF；转发 Host/proto 头不能替代这些检查。
- 本地无 Docker CLI；本交接未验证 Compose 插值/schema、容器重建、实际 UID 修正、反代 TLS/证书信任、浏览器登录、SSE 和真人平台/媒体服务器流程。
- 未修改应用源码、上游锁、冻结计划、用户秘密值、服务器文件或运行服务。个人配置不进 Git，仅发布脱敏双语记录。

## 初次操作者步骤（历史）

在原项目目录备份并替换 live Compose，保留命名卷和已有 .env 的其他项，在私有 .env 填写实际 `MEDIA_SYNC_PUBLIC_HOST`。运行 `docker-compose config --quiet`，再覆盖入口执行 `serve --check-config`；仅固定 valid 状态后执行 `docker-compose up -d --force-recreate media-sync`。仅 restart 不更新环境，本次配置不需要重建镜像。

另一台反代转发应用主机的局域网 HTTP 端口，保留完整浏览器 Host，关闭 SSE 响应缓冲。可信局域网中限制只有反代可访问后端；该链路仍为明文。通过真实 HTTPS 浏览器地址验证。不得删卷、放宽凭据权限、自动接受许可证或将这些部分结果升级为真人 PASS。

## 用户提供入口后的验证

日期：2026-09-05。初次变量方案交接后，用户提供了实际 HTTPS 入口。私有、Git 忽略的 `docker-compose.yml` 已改为固定的实际 HTTPS Origin 和相同的健康检查 Host，移除 `MEDIA_SYNC_PUBLIC_HOST` 占位。完整个人 YAML 再次通过既有 parser。公开记录不保存实际域名、IP 地址或凭据文件路径。

- 正常校验证书、未跳过 TLS 验证的 HTTPS GET 请求，根页面、公开 health 和公开 ready 均返回 200。
- 独立匿名请求 `/api/v1/accounts` 和 `/api/docs` 均返回 401，固定错误为 `operator_auth_required`。这两次请求不是 HTML 导航验收。
- 真实应用内浏览器通过 HTML 导航访问 `/accounts`，到达 `/?return_to=%2Faccounts` 并显示操作者登录页。最初一次 PowerShell 独立重定向探测因 `InvalidOperationException` 中止，该失败尝试未提供重定向状态。随后独立使用禁止自动重定向的 HttpClient 探针，确认 HTML 导航访问 `/accounts` 返回 HTTP 303，且 `Location: /?return_to=%2Faccounts`。
- agent 未自动输入任何登录值，未读取 Cookie 或凭据。初次匿名检查时仍待操作者手工登录；后续观察记录见下节。
- 应用源码仍为 `0fd7c17` 基线。HTTPS 响应成功不能识别当前运行镜像，也不能证明当前 Linux 镜像、数据卷、重启及恢复门槛全部通过；本次探测未重新确认此前报告的镜像 ID。

实际 HTTPS 入口和匿名访问边界现已在上述范围内得到验证；独立配置预检成功记录仍未提供。不从页面推断 Compose schema、实际容器重建或容器身份。浏览器侧 TLS 验证结果不会改变另一台反代到应用 HTTP 上游仍为明文的事实。

## 操作者手工登录后的观察

日期：2026-09-05。用户已手工登录后台；随后只读浏览器检查进入认证后的 `/accounts`，观察到三个平台的账户认证失败状态。Jobs 页面实际载入六个失败操作，最近一次显示从 16:27:59 至 16:28:07，`runner_status=failed`、`login_session_status=failed`、`auth_status=failed`，固定错误为 `operation_login_failed`。

界面显示事件流连接指示及 cursor 30。这只是连接指示，不证明新产生事件已送达、持久化或重连后重放。agent 没有新建业务操作或启动平台登录，此处不记录凭据、账户名或 UUID。

现已观察到后台认证后访问及既有失败记录；完整登录/会话生命周期、SSE 投递/重连、平台同步成功及 Emby/Jellyfin 验收仍未完成。平台失败记录是待诊断的证据，不是真人验收通过。共同运行环境检查、源码证据及待补的部署侧证明见[登录运行环境排查](login-runtime-triage.zh.md)；未获得相应证明前，不将失败原因宣称为已确定。

## 当前下一步

重试平台登录前，先按运行环境排查执行有界、不接触凭据的检查，不自动接受许可证或启动平台/媒体服务器写操作。如需再次应用个人 Compose，应保留固定实际 Origin 和健康检查 Host、数据及秘密，先配置预检，再重建服务容器而非仅 restart。上方历史步骤中的 `MEDIA_SYNC_PUBLIC_HOST` 设置不再适用于已交付的固定配置。
