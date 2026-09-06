**中文** | [English](verification.md)

# 验证记录

冻结时已核对本地远端干净且均为 `5948b91`。应用测试未运行；未操作生产、凭据、目录移动或删除。

## 当前源码最终验证

- `.venv/Scripts/python.exe docs/executions/0067-output-directories/artifacts/verify_output_directories.py`：831 passed、2 skipped、1 warning，380.37秒。脚本包含准确选集；覆盖共享策略/迁移/CAS、独立worker真实输出、全部API测试、鉴权、CLI、媒体树、兼容发布、支持包和Job诊断。2项skip为未配置真实PostgreSQL的竞态测试，不算通过。warning为现有Starlette/httpx弃用提示。
- `pnpm test`：23文件、717通过，1.47秒；其中目录控制器12项验证CAS、预览失效、并发/迟到响应、保留草稿、无自动重放和安全错误。不是已运行的真实浏览器表单验收。
- `pnpm check`：0错误/0警告；`pnpm build`：通过，7.87秒；`pnpm format:check`：通过。
- `ruff check src tests scripts`、`ruff format --check`（360文件）、mypy（139源码）、compileall、upstream两锁定checkout、uv lock和diff检查通过。文档最后提交前再次核验链接；此前682文件通过。
- `uv build`及复用0066的check_package_sources.py：wheel/sdist包含新增服务/0012迁移，154应用Python文件逐字节一致；RECORD/依赖/入口/成员检查通过。构建位置为系统Temp下media-sync-0067-build-d16e477767bf4b76887225424ed70450。之后仅文档更新，因此源码验真仍成立，包不是最终文档快照；未安装部署。

## 过程中的失败与修正

- storage审计实证发现系统目录允许、旧scope/new环境根误绑定，修复后独立复核拒绝系统4路径；旧scope不符返回migration_required且policy/binding均0，恢复旧根成功且原文件不变。
- 原API媒体树测试9项使用旧构造lambda；修正测试seam支持exporter_factory，真实新factory专测不变。原4文件首轮9失败/121通过，后9全过，最终统一选集重新通过。
- runtime/CLI首轮4失败为旧head/表数断言；更新0012/21表。新API独立worker用例最初错断言html，实际契约是body.txt，修正断言后验证真实文件字节/NFO。专属联合158通过，不与最终831累加。
- 根API初次ruff发现测试4处行长，format2文件及mypy2处Literal字典key不匹配；格式化并显式str映射后静态检查全过。
- storage专项56通过/2PG跳过、library/server专项53通过、head支持包82通过和根API42通过均是重叠专项，不算最终全项目测试量。未重跑全项目六千余项历史套件。

## 线上只读核查

账户页和微博操作详情按computer-use指引检查，见[推进记录](progress.zh.md)。本次没有新登录/预检/下载/调度tick/部署/凭据操作；已有认证未修改。四平台扫码超时仍未修复，浏览器超时的精确动作未被旧版本存档。Linux容器、当前PostgreSQL竞态和真人采集/下载/播放均NOT_RUN。本轮没有把更细的错误码或离线通过当登录成功。

## Git

冻结计划提交10742c9。发布前再次fetch确认origin/main仍5948b91，无并行远端提交。实现及收尾使用双语说明正常提交/推送，最终提交编号在后续收尾记录，不伪造自引用hash。
