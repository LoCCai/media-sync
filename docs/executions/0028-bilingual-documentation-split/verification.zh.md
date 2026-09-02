[English](verification.md) | **中文**

# 执行 0028 验证

- 状态：文档语言范围通过迁移工作站上可用的全部门禁；常规 Python 质量门与 GitHub 推送核对仍需在常规环境复跑
- 日期：2026-09-02
- 前置：`539395a483f4f368895fb0f35205c903dc2bd43d`
- 计划/实现/收尾：包含本记录的提交（自引用 SHA 有意只保留在 Git 历史中）

## 前置环境

Windows 10（win32 10.0.26200）、Git Bash、Perl 5.42.2（cygwin）。本工作站未安装 Python/uv 运行时，因此下方所有 `uv run ...` 门禁如实记录为 `NOT_RUN`，而不是静默跳过。

## 已实现证据

| 检查 | 命令 | 退出码 | 结果 |
| --- | --- | ---: | --- |
| 语料可行性 | `perl .tmp_analyze.pl .`（会话临时脚本；逻辑并入已提交工具） | 0 | 124 份文件；3371 行恰好一个有效行内边界；0 行多边界；21 行特例 |
| 迁移工具干跑 | `perl scripts/split_bilingual_docs.pl --dry-run .` | 0 | 最终报告：3933 行内拆分、356 标签对头部、531 竖排配对单元、173 未配对英文单元（两版保留）、6 未配对中文单元（翻译缺口，已人工补齐） |
| 迁移写入 | `perl scripts/split_bilingual_docs.pl --write .` | 0 | 124 份英文版就地改写；124 份中文版新建 |
| 链接+成对+纯度 | `perl .tmp_validate.pl .`（会话临时脚本；移植 `scripts/check_docs.py` 链接契约并新增成对/纯度检查） | 0 | `checked 128 en + 128 zh markdown files — all link, parity and purity checks passed` |
| 中性行保全 | 会话 Perl 扫描：把每个无 CJK、无配对的源行与两版逐一比对 | 0 | `checked 4490 neutral lines, lost 0`（检查 4490 行中性行，丢失 0 行） |
| 未拆分残留 | 会话 Perl 扫描：检查中文版残留的 `EN / ZH` 边界 | 0 | 仅 1 行：`Emby / Jellyfin` 为合法英文产品名，有意保留 |
| 范围审计 | `git status --short` | 0 | 仅 `*.md`、`*.zh.md`、`scripts/split_bilingual_docs.pl` 与已删除的会话临时文件变化；`src/`、`tests/`、`alembic.ini`、`pyproject.toml`、`upstreams.lock.json` 零变化 |

## 测试与质量门禁

| 检查 | 命令 | 结果 |
| --- | --- | --- |
| 文档链接（常规门） | `uv run python scripts/check_docs.py` | 本机无 Python，`NOT_RUN`；推送前必须通过。上方 Perl 门禁已在同一文件集上实现同一链接契约 |
| Ruff、格式、mypy、编译、构建 | `uv run ruff check .`; `uv run ruff format --check .`; `uv run mypy --strict src`; `uv run python -m compileall -q src/media_sync`; `uv build` | 本机 `NOT_RUN`；本执行未修改任何 Python 文件，这些门仅覆盖既有代码 |
| 完整套件 | `uv run pytest -q` | 本机 `NOT_RUN`；不声明任何源代码变化 |
| 上游锁 | `uv run python scripts/check_upstreams.py` | 本机 `NOT_RUN`；锁文件与 `.upstream/` 未动 |

## Git 核对

计划、实现与收尾为 `main` 上按仓库“启动/闭环/收尾”约定的三个提交；执行 0028 索引行与日志摘要是这些提交的一部分。本地 `main`、`origin/main` 与 GitHub 由本节之后的推送核对。

## 真人与常规环境验收

| 验收行 | 结果 |
| --- | --- |
| 256 文件双档布局上的常规文档门 `uv run python scripts/check_docs.py` | 本机 `NOT_RUN`；推送前必须执行 |
| 完整 Python 质量/构建/测试套件 | 本机 `NOT_RUN`；不声明源代码变化 |
| GitHub 推送与核对 | 收尾提交后尝试；结果见会话记录 |

离线文档证据不能代表上述任何 `NOT_RUN` 行通过。
