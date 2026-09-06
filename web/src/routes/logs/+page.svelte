<script lang="ts">
  import { onDestroy, onMount } from 'svelte';
  import { page } from '$app/stores';
  import { api, LatestRequestGate } from '$lib/api/client';
  import {
    LogCenterController,
    initialLogFilters,
    LOG_LEVELS,
    LOG_MODULES,
    LOG_PLATFORMS,
    UUID_PATTERN,
    logFailure,
    logPhase,
    logAction,
    logStream,
    logErrorType,
    logSummary,
    logDiagnosticArtifact,
    logIdentityLink,
    type LogFilters,
    type LogView
  } from '$lib/api/log-center';
  import PageHeader from '$lib/components/PageHeader.svelte';
  import Panel from '$lib/components/Panel.svelte';
  import { formatDateLong, shortId } from '$lib/utils/format';
  const controller = new LogCenterController((next) => {
    view = next;
  });
  let view: LogView = controller.view;
  let filters: LogFilters = {};
  let downloading = false;
  let downloadError = '';
  const downloadGate = new LatestRequestGate();
  let downloadUrl: string | null = null;
  let mounted = false;
  let routeQuery: string | null = null;
  $: if (mounted && $page.url.search !== routeQuery) {
    routeQuery = $page.url.search;
    downloadGate.cancel();
    downloading = false;
    downloadError = '';
    filters = initialLogFilters($page.url.searchParams);
    void controller.load(filters);
  }

  async function download(): Promise<void> {
    const id = view.filters.operation_id;
    if (downloading || view.busy || !id || !UUID_PATTERN.test(id)) return;
    downloading = true;
    downloadError = '';
    const result = await downloadGate.run((signal) =>
      api<unknown>(`/api/v1/logs/operations/${id}/diagnostic`, { signal })
    );
    if (result.status === 'superseded') return;
    downloading = false;
    if (result.status === 'rejected') {
      downloadError = logFailure(result.reason);
      return;
    }
    try {
      const artifact = logDiagnosticArtifact(result.value, id);
      if (!mounted || id !== view.filters.operation_id) return;
      if (downloadUrl) URL.revokeObjectURL(downloadUrl);
      downloadUrl = URL.createObjectURL(new Blob([artifact.text], { type: 'application/json' }));
      const link = document.createElement('a');
      link.href = downloadUrl;
      link.download = artifact.filename;
      link.click();
    } catch (error) {
      downloadError = logFailure(error);
    }
  }
  onMount(() => {
    mounted = true;
  });
  onDestroy(() => {
    mounted = false;
    controller.dispose();
    downloadGate.cancel();
    if (downloadUrl) URL.revokeObjectURL(downloadUrl);
  });
</script>

<div class="page">
  <PageHeader title="日志中心" description="持久组件日志、登录动作与任务关联；不读取或展示原始凭据。">
    <svelte:fragment slot="actions"
      ><button class="button secondary" disabled={view.busy || downloading} on:click={() => controller.load()}
        >刷新当前查询</button
      ></svelte:fragment
    >
  </PageHeader>
  {#if view.error}<div class="notice danger" role="alert">{view.error}</div>{/if}
  {#if view.error && view.coverage}<p class="notice warning">
      查询未更新；下方保留上次成功查询结果及关联操作。
    </p>{/if}
  {#if view.busy && view.coverage}<p class="notice">正在读取新查询；下方暂时保留上次成功查询结果。</p>{/if}
  {#if view.status}
    <Panel title="日志存储" description="计数属于当前 API 进程；片段目录由 API 与 supervisor 共享。">
      <p>
        健康：{view.status.health === 'ok'
          ? '正常'
          : view.status.health === 'degraded'
            ? '日志不完整'
            : '存储不可用或已关闭'} · 排队 {view.status.queued} · 已写 {view.status.written} · 丢失 {view
          .status.dropped} · 拒绝 {view.status.invalid}
      </p>
      <p class="muted">
        按日期或 {(view.status.segment_max_bytes / 1048576).toFixed(0)} MiB 切片 · 保留 {view.status
          .retention_days} 天 · 总上限 {(view.status.total_max_bytes / 1048576).toFixed(0)} MiB。入队不等于已写盘；进程崩溃可能丢失尚未写入的记录。
      </p>
      {#if view.status.health !== 'ok' || view.status.dropped > 0}<div class="notice warning">
          日志可能缺失，请检查共享挂载、目录权限和磁盘空间；不要将“没有日志”当作“没有发生错误”。
        </div>{/if}
      {#if view.status.health === 'closed' && !view.status.shutdown_complete}<div class="notice warning">
          日志存储已停止接收，但尚未完成排空；写线程{view.status.writer_running ? '仍在运行' : '未运行'}，
          队列{view.status.drained ? '已处理完毕' : '仍有待处理记录'}，不能视为正常关闭。
        </div>{/if}
    </Panel>
  {/if}
  <Panel title="筛选记录" description="留空表示不限；按片段顺序读取，不保证多个进程的全局时间顺序。">
    <form on:submit|preventDefault={() => controller.load(filters)}>
      <fieldset disabled={view.busy || downloading}>
        <div class="filter-grid">
          <label
            >平台<select class="input" bind:value={filters.platform}
              ><option value="">全部平台</option>{#each LOG_PLATFORMS as item}<option value={item}
                  >{item}</option
                >{/each}</select
            ></label
          >
          <label
            >组件<select class="input" bind:value={filters.module}
              ><option value="">全部组件</option>{#each LOG_MODULES as item}<option value={item}
                  >{item}</option
                >{/each}</select
            ></label
          >
          <label
            >级别<select class="input" bind:value={filters.level}
              ><option value="">全部级别</option>{#each LOG_LEVELS as item}<option value={item}>{item}</option
                >{/each}</select
            ></label
          >
          <label>操作 UUID<input class="input mono" maxlength="36" bind:value={filters.operation_id} /></label
          >
          <label>账户 UUID<input class="input mono" maxlength="36" bind:value={filters.account_id} /></label>
          <label
            >登录会话 UUID<input
              class="input mono"
              maxlength="36"
              bind:value={filters.login_session_id}
            /></label
          >
          <label>Job UUID<input class="input mono" maxlength="36" bind:value={filters.job_id} /></label>
          <label>Run UUID<input class="input mono" maxlength="36" bind:value={filters.run_id} /></label>
          <label
            >订阅 UUID<input class="input mono" maxlength="36" bind:value={filters.subscription_id} /></label
          >
          <label
            >起始时间（本地时区）<input
              class="input"
              type="datetime-local"
              step="any"
              bind:value={filters.since}
            /></label
          >
          <label
            >结束时间（本地时区）<input
              class="input"
              type="datetime-local"
              step="any"
              bind:value={filters.until}
            /></label
          >
        </div>
        <div class="button-row">
          <button class="button" type="submit">查询日志</button><button
            class="button secondary"
            type="button"
            on:click={() => {
              filters = {};
              void controller.load(filters);
            }}>清空并查询</button
          >
        </div>
      </fieldset>
    </form>
  </Panel>
  {#if view.trace}
    <Panel title="关联操作" description="数据库终态与日志子步骤分开，日志不能授予账户认证。">
      <p class="mono">
        {view.trace.operation.id} · {view.trace.operation.kind} · {view.trace.operation.state}
      </p>
      <p>
        保存的执行结果：{view.trace.operation.runner_status ?? '非登录操作或未记录'} · {logPhase(
          view.trace.operation.phase
        )}
      </p>
      {#if view.trace.operation.kind === 'account-login' && view.trace.login_stage_evidence !== 'available_in_page'}<div
          class="notice warning"
        >
          当前保留页没有登录细阶段。可能是旧版本未记录、超出本页或已过保留期，不能倒推出具体原因。
        </div>{/if}
      <div class="button-row">
        <button class="button secondary" disabled={downloading || view.busy} on:click={download}
          >下载本次操作诊断包</button
        ><a href="/jobs">查看任务队列</a>
      </div>
      {#if downloadError}<p class="notice danger">{downloadError}</p>{/if}
      <p class="muted">
        只下载有界保留片段、版本和安全控制事件；不会上传第三方，不包含原始
        Cookie、二维码、页面正文或异常变量。
      </p>
      <details>
        <summary>数据库事件时间线{view.trace.control_events_truncated ? '（已截断）' : ''}</summary
        >{#each view.trace.control_events as event}<p class="mono">
            #{event.sequence} · {formatDateLong(event.at)} · {event.event_code} · {logPhase(event.phase)} · {event.to_state ??
              '—'}
          </p>{/each}
      </details>
    </Panel>
  {/if}
  <Panel title="保留日志" description="失败的子步骤可能被上游备用流程处理，请结合终止事件和账户状态。">
    {#if view.coverage}<div class="notice">
        已读取页面的有界覆盖 · 损坏记录 {view.coverage.corrupt_records} · 截断片段 {view.coverage
          .truncated_segments} · 不可读片段 {view.coverage.unavailable_segments} · 已省略片段尾部 {view
          .coverage.omitted_segment_tails}。{view.coverage.scan_limited
          ? '扫描预算已用完，可继续下一页或缩小范围。'
          : ''} 历史记录可能已轮转过期；空页不证明没有错误。
      </div>{/if}
    {#if !view.events.length}<p class="muted">
        {view.busy ? '正在读取…' : '本页没有匹配记录；可继续分页或调整筛选。'}
      </p>{/if}
    <div class="log-list">
      {#each view.events as event (`${event.writer_id}:${event.sequence}`)}<article>
          <div class="event-heading">
            <span>{formatDateLong(event.timestamp)} · {event.module} · {event.platform ?? '—'}</span><span
              class:failed={event.level === 'error' || event.level === 'warning'}>{event.level}</span
            >
          </div>
          <strong
            >{logPhase(event.phase)} · {logAction(event.action)} · {event.outcome ?? '记录'}{event.stream
              ? ` · ${logStream(event.stream)}`
              : ''}</strong
          >
          <p>{logSummary(event)}</p>
          <p class="muted">
            {event.error_type && event.error_type !== 'none'
              ? `异常类别：${logErrorType(event.error_type)}（${event.error_type}） · `
              : ''}{event.duration_ms !== undefined ? `${event.duration_ms} ms` : ''}
            {event.source_frame ? `· 代码位置：${event.source_frame}` : ''}
            {event.count !== undefined ? ` · 行数：${event.count}` : ''}
            {event.bytes !== undefined ? ` · 字节：${event.bytes}` : ''}
          </p>
          <details>
            <summary>关联标识及固定代码</summary>
            <p class="mono">{event.event_code} · writer {shortId(event.writer_id)} · #{event.sequence}</p>
            {#each ['operation_id', 'account_id', 'login_session_id', 'job_id', 'run_id', 'subscription_id', 'correlation_id', 'asset_id'] as key}{#if event[key as keyof typeof event]}<p
                  class="mono"
                >
                  {#if logIdentityLink(key, event[key as keyof typeof event])}
                    <a href={logIdentityLink(key, event[key as keyof typeof event])!}
                      >{key}: {event[key as keyof typeof event]}</a
                    >
                  {:else}{key}: {event[key as keyof typeof event]}{/if}
                </p>{/if}{/each}
          </details>
        </article>{/each}
    </div>
    <button
      class="button secondary"
      disabled={view.busy || downloading || !view.nextCursor || view.events.length >= 2000}
      on:click={() => controller.load(view.filters, true)}>继续读取下一页</button
    >
    {#if view.events.length >= 2000}<p class="notice warning">
        页面达到 2000 条显示上限，请缩小时间范围重新查询。
      </p>{/if}
  </Panel>
</div>

<style>
  fieldset {
    margin: 0;
    padding: 0;
    border: 0;
    min-width: 0;
  }
  .filter-grid {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 12px;
    margin-bottom: 16px;
  }
  label {
    display: grid;
    gap: 6px;
    font-size: 12px;
  }
  .input {
    width: 100%;
  }
  .log-list {
    margin: 14px 0;
  }
  article {
    padding: 14px 0;
    border-bottom: 1px solid var(--border);
    overflow-wrap: anywhere;
  }
  article p {
    margin: 6px 0;
  }
  .event-heading {
    display: flex;
    justify-content: space-between;
    color: var(--text-muted);
    font-size: 11px;
    margin-bottom: 7px;
  }
  .failed {
    color: #b54708;
  }
  details {
    margin-top: 10px;
    font-size: 11px;
  }
  @media (max-width: 800px) {
    .filter-grid {
      grid-template-columns: 1fr;
    }
  }
</style>
