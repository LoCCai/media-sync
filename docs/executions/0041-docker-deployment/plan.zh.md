[English](plan.md) | **中文**

# 执行 0041 计划

- 状态：已交付；真人清单在 Linux 执行
- 日期：2026-09-03

## 交付顺序

1. 多层 Dockerfile（应用 venv + 锁定 checkout + Playwright/Chromium + ffmpeg/Xvfb/字体），构建参数与 `upstreams.lock.json` 的上游提交一致。
2. 入口脚本含 Xvfb、幂等 schema 初始化与 exec；compose 仅回环发布、数据卷、健康检查与可选 supervisor profile。
3. 双语部署文档附如实操作者清单（扫码登录、订阅、同步、pipeline、Emby），只记录实际运行的项。
4. 本工作站验证限于编排文件与仓库静态门；镜像本身在操作者的 Linux 主机构建。

## 风险与回退

- 删除 `Dockerfile`、`docker/`、`docker-compose.yml`、`.dockerignore` 与部署文档即可完整回滚；无运行时代码依赖它们。
