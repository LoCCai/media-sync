[English](deployment-handoff.md) | **中文**

# 跨服务器反代部署交接

- 日期：2026-09-05
- 应用基线：`0fd7c17`
- 状态：个人配置已交付；实际 HTTPS 入口及操作者验证待补

## 目标与计划

为应用主机及另一台局域网 HTTPS 反代提供完整 Compose。保留七平台目标、已发布应用代码、认证、数据卷和外部凭据；明确真实浏览器 HTTPS 入口，同步健康检查 Host，本地校验后由操作者先预检再重建容器。不得编造公开域名，也不把 HTTPS Origin 配置当作给 HTTP 后端启用 TLS。

## 推进与证据

操作者报告 checkout 为 `0fd7c17`，镜像为 `sha256:468ba823e582f39fd7ae79b2c0550ff3f89081ab510f102ce19d1f0a66acacd5`，运行 UID 1000，凭据 UID/GID 0、模式 0600，返回 `SECRET_UNREADABLE`，新版预检入口存在且认证预检拒绝。这支持“凭据不可读”判断，不代表部署成功。仅针对普通 rootful、无用户映射 Docker 建议单文件所有者修正；尚未收到随后预检成功结果。

对局域网 HTTP 根页面和公开 health 的两次直接只读请求均返回 403 `operator_host_forbidden`，证明网络可达，但不证明部署身份、登录成功或当前进程启动日志。先前 tail 日志可包含历史失败。

生成的个人 `docker-compose.yml` 由 Git 忽略，不对外发布。保留用户构建代理、外部 secret 路径、命名卷、tmpfs、全网卡 8632 端口及可选 supervisor profile。`MEDIA_SYNC_PUBLIC_HOST` 是 HTTPS Origin 与健康检查 Host 共用的必填 host[:port]；不含协议/路径/末尾斜杠/显式默认 :443，非默认 HTTPS 端口必须保留。supervisor 不提供 HTTP，禁用继承的 API 健康检查，不将其当作 worker 健康证据。

## 验证

- 使用既有 Prettier YAML parser 成功解析整个生成文件，格式检查通过。
- 四项应用策略纯函数检查通过：默认 HTTPS 权威与 :8443 接受相应 Host 并设置 Secure Cookie；直接策略校验拒绝显式 :443 及局域网 HTTP。健康检查使用规范化权威。
- 独立审查确认跨机 TLS 终止、HTTP 上游与代码兼容：保留真实 Host、Origin、Cookie、CSRF；转发 Host/proto 头不能替代这些检查。
- 本地无 Docker CLI；本交接未验证 Compose 插值/schema、容器重建、实际 UID 修正、反代 TLS/证书信任、浏览器登录、SSE 和真人平台/媒体服务器流程。
- 未修改应用源码、上游锁、冻结计划、用户秘密值、服务器文件或运行服务。个人配置不进 Git，仅发布脱敏双语记录。

## 操作者下一步

在原项目目录备份并替换 live Compose，保留命名卷和已有 .env 的其他项，在私有 .env 填写实际 `MEDIA_SYNC_PUBLIC_HOST`。运行 `docker-compose config --quiet`，再覆盖入口执行 `serve --check-config`；仅固定 valid 状态后执行 `docker-compose up -d --force-recreate media-sync`。仅 restart 不更新环境，本次配置不需要重建镜像。

另一台反代转发应用主机的局域网 HTTP 端口，保留完整浏览器 Host，关闭 SSE 响应缓冲。可信局域网中限制只有反代可访问后端；该链路仍为明文。通过真实 HTTPS 浏览器地址验证。不得删卷、放宽凭据权限、自动接受许可证或将这些部分结果升级为真人 PASS。
