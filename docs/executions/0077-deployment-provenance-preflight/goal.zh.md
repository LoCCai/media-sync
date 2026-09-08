[English](goal.md) | **中文**

# 目标：部署来源身份与 XHS 金丝雀预检

状态：在基线 `4e8d75f` 上**仅完成计划**。尚未开始 0077 实现、部署变更、平台请求、Subscription 执行或 supervisor 重启。

执行 0077 用于关闭 XHS 部署金丝雀前暴露的证据缺口。HTTP 健康和包版本 `0.1.0` 都不能识别镜像内的应用提交。2026-09-08 对当前已鉴权部署的观察显示：公开 health/readiness 通过，但设置页没有 0076 的 XHS 续跑字段，深度诊断停在 `git_inspection_failed`。这些事实否定“线上已经取得 0076 资格”，但既不能识别其精确源码 revision，也不能诊断 checkout 失败原因。

目标操作结果是一项只读、无秘密的预检，可以回答：

```text
这个镜像包含哪个 media-sync 提交？
数据库当前与预期 migration 是什么？
本进程使用什么 B 站/XHS 续跑间隔？
钉定 MediaCrawler checkout 是否真正合格？
```

## 必需行为

1. **镜像自报身份。** Docker 构建接收显式应用源码 revision，只接受完整小写 Git SHA 或封闭哨兵 `unavailable`，写入私有构建清单和 OCI 镜像元数据；不得把 media-sync `.git` 目录送入构建上下文或最终镜像。
2. **诚实向后兼容。** 未提供 revision 的镜像仍可运行，但来源状态为 `not_run`；已记录的畸形 revision 为 `fail`。两者都不能静默变成某次提交或真人资格。
3. **安全诊断投影。** 既有鉴权深度 readiness 只新增经过验证的应用 revision、来源状态、数据库当前/预期 migration 及两个整数续跑间隔；不暴露环境值、Cookie、token、作者引用、宿主路径或原始子进程输出。
4. **操作员可见证据。** 诊断页以紧凑稳定状态展示应用 revision、migration 一致性及两个续跑间隔。CLI JSON 使用同一报告，因此可分别检查 API 与 supervisor 容器并比较，无需启动任务。
5. **可复现 Compose 交接。** 示例 Compose 以构建参数传入 `MEDIA_SYNC_SOURCE_REVISION`，默认使用不阻塞的 `unavailable`，并记录合格构建应使用的精确 `git rev-parse HEAD` 导出命令。
6. **无操作副作用。** 本执行不登录、不采集、不创建/恢复/删除 Subscription、不下载媒体、不修改数据库、不重启容器，也不启动 supervisor。

## 验收证据

- 单元测试覆盖构建清单 revision 缺失、有效、unavailable 与畸形四种状态，以及新增 deep-readiness 载荷。
- Web 测试覆盖完整/缺失 revision、migration 当前/不一致状态和两项续跑值的显示。
- 静态检查证明 Dockerfile/Compose 传递、OCI revision 元数据及 `.git` 未被包含。
- 记录 focused 与完整 Python/Web 门禁、制品检查及双语文档检查，不改变真人资格。

## 明确非目标

- 部署或重建用户服务器。
- 在缺少当前容器 shell 证据时猜测修复服务器 checkout 失败。
- 执行 XHS 金丝雀或修改任何平台资格行。
- 开始后续抖音交付实现。
