[English](verification.md) | **中文**

# 执行 0047 验证

- 状态：阶段 B 部分通过；尚未运行任何真人平台行
- 证据日期：2026-09-04
- 深度预检时间：`2026-09-04T09:40:06.067622+00:00`

## 已验证的 Linux 容器切片

| 检查 | 结果 |
| --- | --- |
| MediaCrawler doctor | `PASS`——`ok=true`、`code=ready`、checkout/runtime ready，报告的全部 checkout/runtime 检查均通过 |
| 锁定上游 | `PASS`——精确 SHA `d6f7c5bb906b6dac40ddf343ef9e26438a3de092`、规范许可证、tracked blob 与干净工作树 |
| 数据库 | `PASS`——SQLite 可达，revision `0005_asset_refresh_sources` 为当前版本，12/12 张必需表存在 |
| 运行时工具 | `PASS`——Git、ffmpeg、ffprobe 与 Xvfb 可用 |
| 持久目录 | `PASS`——state、archive、export、jobs 与 MediaCrawler runtime 目录存在且可写 |
| 浏览器 | `PASS`——运行时 Chromium 成功启动并返回 `151.0.7922.34` |
| 构建身份 | `PASS`——Chromium `151.0.7922.34`、Playwright `1.62.0`、Python `3.13.15`、uv `0.9.18`、Node `v24.20.0`、pnpm `11.19.0`、web lock `dc9a47134060f185a3942bac5262b0ca55e0457a4dcddade81803e069b9bf3a0` |
| API 网络边界 | `REVIEW_REQUIRED`——应用监听容器内 `0.0.0.0:8632`；宿主机发布地址尚未上报 |
| 真人资格 | `NOT_RUN` |

## 尚未验证

Linux 完整套件、宿主机实际端口发布、重启持久性、恢复到全新卷、进程泄漏基线、Bilibili/小红书登录及全部抓取/下载/Emby 行仍未验证。任何夹具或 readiness 结果都不能替代这些真人行。
