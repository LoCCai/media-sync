[English](0003-pinned-webui-build-security-override.md) | **中文**

# ADR-0003: 钉定 MediaCrawler WebUI 的构建期安全覆盖

- 状态：已接受
- 日期：2026-10-02

## 背景

钉定的 MediaCrawler 检出（d6f7c5bb）自带的 WebUI 在 npm 清单中声明 axios ^1.7.9。Docker 镜像构建会把该 WebUI 编译进同源的 `/crawler/` bundle，并以 `npm audit --omit=dev --audit-level=low` 作为 fail-closed 门禁。2026-10-02，npm 公告数据库发布了多条 axios 高危公告，波及 1.19.0 及之前的全部 axios 版本——包括钉定检出在上游 `^1.7.9` 声明下按锁文件解析安装的 axios 1.13.2——因此只有把依赖覆盖为修复版本 axios@1.20.0（该版本本身就在 `^1.7.9` 范围内），门禁才能通过。公告包括：

- GHSA-44g4-m2mj-wpvx —— CIDR 形式的 NO_PROXY 条目被忽略，导致内部 IP 段的代理排除被绕过；
- GHSA-r4gj-5m52-g5wh —— fetch adapter 未强制 `maxRedirects: 0`，允许基于重定向的 SSRF。

公告发布后的第一次无缓存重建即在该门禁上失败（audit 对 axios 1.0.0 – 1.19.0 报出十二条高危公告，并指明修复版本为 axios@1.20.0）。移除或放宽门禁不可接受，而等待上游项目自行重新钉定依赖会让部署在无限期内无法构建。

## 本地确定性实证

在本决策记录之前，门禁流程已针对钉定 WebUI 清单（`.mediacrawler-local/webui/package.json`，接缝 `axios: "^1.7.9"`、无 overrides）按 Dockerfile 构建阶段的相同步骤在本地复现：

- 采用旧覆盖（axios 1.18.0）时：`npm audit --omit=dev --audit-level=low` 报出 **1 high severity vulnerability**——axios 1.0.0 – 1.19.0 范围内的十二条公告，含 GHSA-44g4-m2mj-wpvx 与 GHSA-r4gj-5m52-g5wh——且 `npm audit fix --force` 指明修复版本为 axios@1.20.0。
- 采用新覆盖（axios 1.20.0）时：同一流程报出 **found 0 vulnerabilities**。

## 决策

`docker/mediacrawler-webui-security-patch.mjs` 为 WebUI 构建钉定精确的仅构建期依赖覆盖。脚本先断言上游接缝（若上游修改 axios `^1.7.9` 声明或已有 `overrides` 字段则显式失败），随后应用精确版本：自提交 `2df128f` 起，axios 1.20.0，附带 follow-redirects 1.16.0 与 form-data 4.0.6。当公告迫使升级时，改动就是本脚本中的一行，提交信息写明审计门禁，并以产生的精确提交重建受影响镜像。

覆盖只影响镜像内编译出的浏览器 bundle。上游 checkout 保持字节不变且通过 revision 校验：不修改任何上游文件，`scripts/check_upstreams.py` 继续通过，`npm audit` 仍是强制且未被改动的构建门禁。

## 后果

- 上游发布间隔内落地新公告时，镜像仍能 fail-closed 地构建；审计门禁永远不会发布含已知漏洞的 WebUI bundle。
- 每次覆盖升级都会改变镜像 digest，即使应用源码未变；来源身份（`org.opencontainers.image.revision`、`/opt/BUILD-MANIFEST.txt`）继续标识产出镜像的精确源码提交。
- 未来上游重新钉定 axios（或自行覆盖这些包）时，脚本的接缝断言会让构建失败；届时必须在脚本内与上游对齐覆盖版本，而不是静默跳过。
- 覆盖表是经过评审的、有意的上游依赖声明分歧；钉定 MediaCrawler 提交每次变化时都必须重新评估。
- 提交 `2df128f` 记录了本策略下的第一次升级（1.18.0 → 1.20.0），因应 2026-10-02 的公告。早于该提交构建的部署在 WebUI bundle 内携带漏洞传递版本，应予重建。0072 验证与 `docs/status.md` 记录的更早基线（axios 1.18.0、当时 "0 vulnerabilities"）早于本批公告，由本决策取代。
