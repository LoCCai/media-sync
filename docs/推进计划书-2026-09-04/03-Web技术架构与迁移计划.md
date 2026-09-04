# Web Console v2 技术架构与迁移计划

> 状态校准（2026-09-05）：0050-A/B/C 已由 Console v2 基础交付，原称 0050-D 的范围由 Execution 0052 交付为持久 Operation/Event、单一提交有序 SSE、跨 coordinator 两阶段取消、任务中心与有界轮询回退；冻结完整套件 2315 passed、3 skipped，全部仓库门通过。Execution 0053 已从 `be26cc7` 启动，冻结兼容筛选、安全详情、同描述符归档预览及 Contents/Assets/Library 升级。原称 0050-E 的 legacy 移除仍归 Execution 0056；独立 Logs、通用文件日志与真实 Jobs 路由浏览器 interaction/E2E 仍是后续质量债。

## 1. 推荐方案

采用：

- SvelteKit 5；
- TypeScript；
- `adapter-static`；
- Vite；
- Tailwind CSS；
- 轻量组件库；
- FastAPI 继续作为唯一后端；
- 前端构建为静态资源，由 FastAPI 同源服务；
- 生产镜像不运行 Node.js。

选择该方案的理由：

- bili-sync-up 已证明 SvelteKit 静态后台适合此类自托管控制面；
- 当前后台已经是同源 FastAPI，静态 SPA 可平滑接入；
- Svelte 编译产物小，适合单机和移动浏览器；
- 无需把业务拆成第二个运行时服务；
- 可以逐页替代当前 `console.html`。

## 2. 目录结构

```text
web/
  package.json
  src/
    lib/
      api/
      components/
      stores/
      types/
      utils/
    routes/
      +layout.svelte
      +page.svelte
      accounts/
      subscriptions/
      jobs/
      contents/
      assets/
      library/
      logs/
      settings/
      diagnostics/
  static/
  tests/

src/media_sync/interfaces/
  api/
    routers/
    schemas/
    dependencies.py
  static/
    console-v2/
```

当前 `api.py` 应逐步拆为：

```text
routers/health.py
routers/accounts.py
routers/subscriptions.py
routers/jobs.py
routers/operations.py
routers/contents.py
routers/assets.py
routers/library.py
routers/logs.py
routers/settings.py
```

这是目标目录而非当前文件清单。不要求改变模块化单体，只是逐步拆分接口文件；0052 的 Operation/SSE/支持包接线仍位于现有 `api.py`，没有为满足目录图而虚构 `routers/logs.py`。

## 3. Docker 构建

使用多阶段构建：

```dockerfile
FROM node:22-bookworm-slim AS web-build
WORKDIR /web
COPY web/package*.json ./
RUN npm ci
COPY web .
RUN npm run check && npm run build

FROM ${BASE_IMAGE} AS base
...
COPY --from=web-build /web/build /app/src/media_sync/interfaces/static/console-v2
```

生产运行层不含 Node modules。

为保证可复现：

- Node 基础镜像用 digest；
- `package-lock.json` 提交；
- `npm ci`；
- 记录前端 commit、Node、npm 和 lock 摘要；
- 前端依赖审计作为离线发布门。

## 4. API 契约

### 4.1 保持 `/api/v1`

已有 API 不应被 Web v2 私自改名。新增接口采用向后兼容方式。

### 4.2 类型生成

构建阶段从 FastAPI OpenAPI 生成 TypeScript 类型：

```text
openapi.json
  → openapi-typescript
  → web/src/lib/api/generated.ts
```

封装统一客户端：

- 超时；
- 错误码；
- request ID；
- 409 冲突；
- 422 校验错误；
- 401/403；
- 503 deep readiness；
- 操作轮询或事件流。

### 4.3 固定错误模型

```json
{
  "error": {
    "code": "tracked_blob_mismatch",
    "message": "MediaCrawler checkout 与锁定提交不一致",
    "retryable": false,
    "operation_id": null,
    "details": {
      "check": "tracked_files"
    }
  },
  "request_id": "..."
}
```

`message` 可以本地化，`code` 必须稳定。

## 5. 实时通信

优先使用 SSE：

- Operation 状态与进度；
- 安全 Operation Event 时间线；
- 任务中心有界快照刷新提示。

原因：

- 主要是服务端单向推送；
- 比 WebSocket 更容易经过反向代理；
- 断线可用 Last-Event-ID 恢复；
- 前端复杂度较低。

WebSocket 仅在未来需要双向终端或高频交互时引入。

0052 冻结并实现的端点：

```text
GET /api/v1/operations/events
```

首次连接的 ready 帧以捕获的 high-water 作为 `initial_cursor`，并配合 `GET /api/v1/operations?limit=200` 有界快照；浏览器重连在补发前保持调用方 `Last-Event-ID`，严格补发事务已提交 cursor 之后的事件。不存在已实现的通用 `/events`、Job 日志流或登录专用 SSE；二维码生命周期继续使用精确 LoginSession QR 轮询。

## 6. 静态资源服务

FastAPI：

- `/` 返回 SPA；
- `/assets/*` 返回指纹静态文件；
- 非 API 路由回退到 `index.html`；
- 缓存：
  - HTML：no-cache；
  - 指纹 JS/CSS：长期 immutable；
- 设置 CSP、X-Content-Type-Options、Referrer-Policy；
- 不使用外部 CDN，全部前端资源本地打包。

## 7. 迁移步骤

### 7.1 0050-A：基础骨架

- 创建 `web/`；
- 主题、侧栏、路由、面包屑；
- 生成 API 类型；
- 总览页读取现有 health/settings；
- 保留旧控制台 `/legacy`；
- 新旧后台可切换。

### 7.2 0050-B：只读页面

先迁移：

- 总览；
- 账户列表；
- 订阅列表；
- 任务列表；
- 资产列表。

只读页面风险最低。

### 7.3 0050-C：操作页面

再迁移：

- 登录；
- 新建订阅；
- 调度运行；
- 下载/校验；
- Emby 导出；
- 重试/取消。

### 7.4 0050-D：持久 Operation 事件流（由 0052 实现）

- migration `0006` 持久 Operation/Event/subject 与全局事务 cursor；
- 五类 API 工作流的有界列表、详情、事件、取消及单一 SSE；
- Jobs 路由任务中心、事件时间线与有界轮询回退；
- 安全 Operation Event，而不是通用文件日志或独立 Logs 页面；
- 16 KiB、仅聚合、输出后二次扫描的 JSON 支持响应。

### 7.5 0050-E：移除 legacy

只有在：

- 关键操作 E2E 全绿；
- 手机端可用；
- 旧控制台功能全部覆盖；
- 恢复入口存在；

之后才移除单文件控制台。

## 8. 前端测试

- TypeScript check；
- ESLint/Prettier；
- 组件测试；
- API mock；
- Playwright E2E：
  - 账户创建；
  - 预检失败展示；
  - 二维码状态；
  - 订阅向导；
  - 任务失败/重试；
  - 内容详情；
  - Emby 导出；
  - 未授权访问。

E2E 使用 Fake adapter 和临时 SQLite，不触发真人平台。

0052 当前证据为 17 项 Vitest（Operation 类型化状态、筛选、快照/事件合并、cursor 去重、重连与轮询回退）、零 error/零 warning 的 Svelte check 及生产构建。尚未挂载真实 Jobs 路由执行浏览器 interaction；该项明确保留为后续质量债，不能用工具函数单测替代 E2E 结论。

## 9. 性能边界

- 所有列表服务端分页；
- 首页聚合接口避免十几个请求；
- 内容缩略图延迟加载；
- 原始 payload 不直接返回；
- Operation 事件时间线有界读取与裁剪；
- SSE 连接数量有界；
- 不在浏览器中加载大媒体文件；
- 媒体预览使用 Range 和安全白名单端点。

## 10. 回退

- Web v2 静态资源可独立移除；
- `/legacy` 保留一个发布周期；
- 后端 API 与 CLI 不依赖前端；
- 前端失败不能阻止既有 scheduler/supervisor Job；0052 不声明把全部 supervisor 工作统一为 Operation；
- schema 迁移必须可前向兼容旧控制台。
