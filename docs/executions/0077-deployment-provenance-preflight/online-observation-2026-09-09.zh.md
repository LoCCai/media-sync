[English](online-observation-2026-09-09.md) | **中文**

# 线上观察：当前部署早于 0077

## 状态

**在部署或金丝雀前停止。** GitHub `main` 到达 `70c041f` 后，本次只在已认证浏览器中只读检查 `https://cc.icai.top:52144/diagnostics`。没有重建或重启容器、修改数据库、启动 supervisor、登录平台、创建/恢复 Subscription、采集或下载。

## 已观察证据

页面显示的检查时间为 `2026/09/09 00:58:38`，现有部署报告：

| 证据 | 观察结果 |
| --- | --- |
| Deep readiness 总体状态 | `ready`；页面显示全部深度预检通过 |
| MediaCrawler revision | `d6f7c5bb906b6dac40ddf343ef9e26438a3de092` |
| Checkout 检查 | 许可证确认、锁文件、路径、Git 仓库根、必需文件、许可证摘要、revision、tracked blob、干净工作树及 Python runtime 均显示 `pass` |
| 运行时 Chromium | `151.0.7922.34`，显示可启动 |
| 构建浏览器/工具链 | Chromium `151.0.7922.34`、Playwright `1.62.0`、Python `3.13.15`、ffmpeg `5.1.9-0+deb12u1` |
| 必需工具与目录 | Git、ffmpeg、ffprobe、Xvfb 以及页面显示的五个持久/运行目录均为 `pass` |
| API 绑定 | `0.0.0.0:8632`，保留既有网络边界核对警告 |

对于这个现有容器，本记录取代之前的 `git_inspection_failed` 观察：它的钉定 checkout 现在通过。但这不能识别容器包含哪个 media-sync 应用提交。

## 决定性反证

页面的**构建与运行事实**区域没有实现 `d6db86a` 新增的三类行：

- `media-sync 源码 revision`；
- 数据库当前/预期 migration；
- B 站与 XHS 续跑间隔。

因此运行中的 UI 不可能是已发布 0077 bundle，也不能证明部署 revision 为 `70c041f`。精确应用提交与数据库 migration 仍未知。健康报告、包版本、上游 SHA 或相同 Chromium 版本都不能替代缺失的应用身份。

## 决策与下一步

XHS 金丝雀继续为 `NOT_RUN`，不得在这个身份未知的镜像上启动。下一步仍按[部署交接](deployment-handoff.zh.md)执行：备份 `/data`，以 fast-forward 拉取 GitHub `main`，把其精确干净 HEAD 导出为 `MEDIA_SYNC_SOURCE_REVISION`，重建并重新创建 API 容器；supervisor 继续停止时，分别使用 API 与 supervisor 服务定义比较新 deep report。

只有报告显示精确部署应用 SHA、当前/预期均为 `0015_xhs_creator_notes`、B 站/XHS 续跑值一致，并保留当前已健康的 checkout/runtime，才可以解锁有界 XHS 金丝雀。
