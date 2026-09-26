[English](goal.md) | **中文**

# 执行 0079 目标

- 状态：已完成——在 Linux 部署主机上交付
- 日期：2026-09-26
- 前置：0078 收尾（`764f46b`）与 2026-09-12 服务器部署记录（`ec67097`）
- 范围：在 Linux 部署主机上复现完整本地质量门，并修复由此暴露的全部跨平台缺陷

## 目标结果

1. 全部本地门禁（Ruff lint/format、strict mypy、完整 pytest、文档与上游检查、Web 测试/检查/构建）在真正部署容器的 Linux 服务器上运行并通过，而不仅是在 Windows 编写工作站上。
2. `mypy --strict src` 在两个平台视角（`--platform linux` 与 `--platform win32`）下都通过，strict 门禁不再依赖编写端操作系统。
3. 测试夹具不再解引用 POSIX venv 启动器符号链接：伪 verifier 与 manifest 镜像生产 `normalize_python_executable` 语义，POSIX 专属启动器测试的 subprocess mock 不再泄漏进真实 git 校验。
4. Emby 导出失败记录路径在并发 worker 提交使 WAL 读快照失效时（busy-snapshot 冲突不受 busy timeout 保护），不再把 `stale_publish` 错误分类为 `export_failure_finalize_failed`。
5. 清理 0078 收尾文档债：重复的执行索引行与过期的"进行中"progress 状态。

## 验收边界

- 不改动任何 XHS/抖音投递逻辑、契约或语义；0077 冻结未被触碰。
- 全部真人平台行保持 `NOT_RUN`，继续按部署交接受操作者门槛约束。
- 生产代码守卫改动仅限把 `os.name` 检查换成 `sys.platform` 检查（在所有受支持平台上运行时等价）并加平台作用域的成对 type ignore；WAL 修复复用 operation coordinator 既有 BEGIN IMMEDIATE 有界重试模式。
