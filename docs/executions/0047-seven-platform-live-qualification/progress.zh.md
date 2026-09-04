[English](progress.md) | **中文**

# 执行 0047 推进结果

- 状态：阶段 B 进行中——修复版镜像与运行时深度预检已通过
- 日期：2026-09-04
- 运行时修复提交：`0d73ba1f2c6b9f1c01ddab6008c745508a6ec2bb`

## 已收到的阶段 B 证据

1. 操作者在 venv launcher 修复后重建并启动了镜像。
2. 容器内 MediaCrawler doctor 返回 `ok=true`、`code=ready`，并在上游 SHA `d6f7c5bb906b6dac40ddf343ef9e26438a3de092` 下通过确认、锁文件、checkout 路径、仓库根、必需文件、规范许可证摘要、精确提交、tracked blob、干净工作树和运行时导入。
3. 深度预检返回 `ok=true`、`status=ready`：SQLite revision `0005_asset_refresh_sources`、全部 12 张必需表、Git、ffmpeg、ffprobe、Xvfb 及五个持久目录全部通过。
4. 运行时 Playwright 成功启动 Chromium `151.0.7922.34`。构建清单独立记录了相同 Chromium 版本，以及 Playwright `1.62.0`、Python `3.13.15`、uv `0.9.18`、Node `v24.20.0`、pnpm `11.19.0` 和前端锁摘要 `dc9a47134060f185a3942bac5262b0ca55e0457a4dcddade81803e069b9bf3a0`。
5. 真人资格正确保持 `NOT_RUN`。深度报告中的 `api_not_loopback` 告警指向容器内必需的 `0.0.0.0` 监听；扫码登录前仍需由操作者明确验证宿主机实际发布地址。

## 剩余阶段 B 工作

- 在 Linux 上运行并记录完整锁定 Python 套件。
- 确认宿主机端口只绑定回环或明确可信的内网地址。
- 重启容器，证明现有两条账户记录与数据库 revision 持久存在。
- 完成一次备份到文件并恢复到全新卷的演练。
- 记录空闲和容器停止时 Xvfb、Chromium 与 ffmpeg/ffprobe 的进程数量。

## 阶段 C 状态

Bilibili 与小红书扫码金丝雀尚未开始。只有剩余阶段 B 检查全部通过后才进入阶段 C。
