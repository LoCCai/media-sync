<script lang="ts">
  import { onDestroy, onMount } from 'svelte';
  import {
    Activity,
    Ban,
    Clock3,
    Eye,
    ListRestart,
    Play,
    Radio,
    RefreshCw,
    Search,
    ShieldAlert,
    Workflow
  } from '@lucide/svelte';

  import { api, apiMessage, LatestRequestGate } from '$lib/api/client';
  import EmptyState from '$lib/components/EmptyState.svelte';
  import Modal from '$lib/components/Modal.svelte';
  import PageHeader from '$lib/components/PageHeader.svelte';
  import Panel from '$lib/components/Panel.svelte';
  import PlatformMark from '$lib/components/PlatformMark.svelte';
  import StatusBadge from '$lib/components/StatusBadge.svelte';
  import { mediaCrawlerGate } from '$lib/stores/onboarding';
  import { toast } from '$lib/stores/toast';
  import type {
    DeepReadiness,
    Job,
    Operation,
    OperationEvent,
    OperationKind,
    OperationState,
    StartedOperation
  } from '$lib/types/api';
  import { formatDate, formatDateLong, operationLabel, shortId, statusLabel } from '$lib/utils/format';
  import {
    createOperationStreamCursor,
    createOperationStreamHealth,
    markOperationSnapshotLoaded,
    mergeOperationSnapshot,
    mergeOperationSnapshots,
    mergeOperationTimeline,
    mergeSelectedOperation,
    operationCanCancel,
    operationDisplayLabel,
    operationIsActive,
    operationMatches,
    operationProgressLabel,
    operationProgressPercent,
    operationStreamConnected,
    operationStreamFailed,
    operationTruthNotice,
    parseOperationStreamMessage,
    reduceOperationStreamMessage,
    safeOperationContextRows,
    safeOperationResult
  } from '$lib/utils/operations';

  let jobs: Job[] = [];
  let operations: Operation[] = [];
  let loading = true;
  let action = '';
  let error = '';
  let tab: 'jobs' | 'operations' = 'jobs';
  let jobStatusFilter = 'all';
  let operationStateFilter: OperationState | 'all' = 'all';
  let operationKindFilter: OperationKind | 'all' = 'all';
  let operationQuery = '';

  let detailOpen = false;
  let detailTitle = '';
  let detailJob: Job | null = null;
  let selectedOperation: Operation | null = null;
  let operationEvents: OperationEvent[] = [];
  let detailLoading = false;
  let detailError = '';
  let detailRequest = 0;
  const jobsRequest = new LatestRequestGate();
  let cancellingOperationId = '';

  let jobsRefreshTimer: number | null = null;
  let fallbackTimer: number | null = null;
  let detailRefreshTimer: number | null = null;
  let operationRefreshTimer: number | null = null;
  let operationStream: EventSource | null = null;
  let streamCursor = createOperationStreamCursor();
  let streamHealth = createOperationStreamHealth();
  let snapshotLoading = false;

  $: filteredJobs = jobStatusFilter === 'all' ? jobs : jobs.filter((item) => item.status === jobStatusFilter);
  $: filteredOperations = operations.filter((operation) =>
    operationMatches(operation, {
      state: operationStateFilter,
      kind: operationKindFilter,
      query: operationQuery
    })
  );
  $: activeCount = jobs.filter((item) =>
    ['claimed', 'queued', 'retry_wait', 'running', 'waiting_auth', 'waiting_user'].includes(item.status)
  ).length;
  $: failedCount = jobs.filter((item) => item.status.startsWith('failed')).length;
  $: activeOperationCount = operations.filter((item) => operationIsActive(item.state)).length;
  $: streamCopy = streamStatusCopy();
  $: selectedTruthNotice = selectedOperation ? operationTruthNotice(selectedOperation) : null;
  $: selectedProgressPercent = selectedOperation ? operationProgressPercent(selectedOperation) : null;
  $: selectedSafeResult = selectedOperation ? safeOperationResult(selectedOperation) : null;

  function eventLabel(code: string): string {
    return (
      {
        operation_requested: '已接收请求',
        operation_started: '开始执行',
        operation_phase_changed: '阶段变化',
        operation_progressed: '进度更新',
        operation_entity_linked: '关联实体',
        operation_cancel_requested: '已请求取消',
        operation_cancel_observed: '执行者已观察取消',
        operation_succeeded: '执行成功',
        operation_failed: '执行失败',
        operation_cancelled: '已安全取消',
        operation_interrupted: '执行中断',
        operation_reconciled: '重启协调完成'
      }[code] ?? code
    );
  }

  function streamStatusCopy(): { title: string; detail: string } {
    if (streamHealth.mode === 'live') {
      return {
        title: '实时事件流已连接',
        detail: `已处理到全局事件 #${streamCursor.lastSequence}；列表按事件序列去重。`
      };
    }
    if (streamHealth.mode === 'fallback') {
      return {
        title: '实时流重连中',
        detail: `当前使用有界轮询，下一次刷新间隔最多 ${Math.round(streamHealth.pollDelayMs / 1000)} 秒。`
      };
    }
    return { title: '正在连接实时事件流', detail: '连接就绪后会先读取一次有界操作快照。' };
  }

  async function loadJobs(skipIfBusy = false): Promise<void> {
    const request = (signal: AbortSignal): Promise<Job[]> =>
      api<Job[]>('/api/v1/scheduler/jobs?limit=200', { signal });
    const result = await (skipIfBusy ? jobsRequest.runIfIdle(request) : jobsRequest.run(request));
    if (result.status === 'busy' || result.status === 'superseded') return;
    if (result.status === 'rejected') throw result.reason;
    jobs = result.value;
  }

  async function loadJobsSilently(): Promise<void> {
    try {
      await loadJobs(true);
    } catch {
      // The operation stream remains independent; the next bounded Job refresh retries.
    }
  }

  async function loadOperationSnapshot(): Promise<void> {
    const snapshot = await api<Operation[]>('/api/v1/operations?limit=200');
    operations = mergeOperationSnapshots(operations, snapshot, 200);
    if (selectedOperation) {
      const refreshed = snapshot.find((operation) => operation.id === selectedOperation?.id);
      if (refreshed && refreshed.event_sequence >= selectedOperation.event_sequence) {
        selectedOperation = mergeOperationSnapshot([selectedOperation], refreshed, 1)[0];
      }
    }
  }

  async function load(silent = false): Promise<void> {
    if (!silent) {
      loading = true;
      error = '';
    }
    const [jobResult, operationResult] = await Promise.allSettled([
      loadJobs(silent),
      loadOperationSnapshot()
    ]);
    const failures = [jobResult, operationResult].filter(
      (result): result is PromiseRejectedResult => result.status === 'rejected'
    );
    if (silent) return;
    if (failures.length > 0) error = failures.map((result) => apiMessage(result.reason)).join(' · ');
    loading = false;
  }

  async function preflight(): Promise<boolean> {
    const readiness = await api<DeepReadiness>(
      '/api/v1/readiness/deep?accept_mediacrawler_license=true&refresh=true',
      {},
      65_000
    );
    if (readiness.ok) return true;
    const code = readiness.mediacrawler.detail_code ?? readiness.code;
    toast(`操作已在预检阶段停止：${code}`, 'danger');
    return false;
  }

  async function runAction(kind: 'tick' | 'sync' | 'pipeline'): Promise<void> {
    action = kind;
    try {
      if (kind === 'tick') {
        const result = await api<{ materialized_count: number }>('/api/v1/scheduler/tick', {
          method: 'POST',
          body: JSON.stringify({ limit: 100 })
        });
        toast(`调度完成，生成 ${result.materialized_count} 个任务。`);
      } else {
        if (!(await preflight())) return;
        const endpoint = kind === 'sync' ? '/api/v1/scheduler/run' : '/api/v1/pipeline/run';
        const started = await api<StartedOperation>(endpoint, {
          method: 'POST',
          body: JSON.stringify({ max_jobs: 1, ...mediaCrawlerGate() })
        });
        toast(`${kind === 'sync' ? '同步' : '下载 / 导出'} Worker 已启动 · ${shortId(started.operation_id)}`);
        tab = 'operations';
      }
      await load(true);
    } catch (caught) {
      toast(apiMessage(caught), 'danger');
    } finally {
      action = '';
    }
  }

  async function showJob(job: Job): Promise<void> {
    detailTitle = `任务 ${shortId(job.job_id)}`;
    detailJob = null;
    selectedOperation = null;
    operationEvents = [];
    detailError = '';
    detailOpen = true;
    detailLoading = true;
    try {
      detailJob = await api<Job>(`/api/v1/scheduler/jobs/${job.job_id}`);
    } catch (caught) {
      toast(apiMessage(caught), 'danger');
      detailOpen = false;
    } finally {
      detailLoading = false;
    }
  }

  async function loadOperationDetail(operationId: string, silent = false): Promise<void> {
    const request = ++detailRequest;
    if (!silent) detailLoading = true;
    detailError = '';
    try {
      const [operation, events] = await Promise.all([
        api<Operation>(`/api/v1/operations/${operationId}`),
        api<OperationEvent[]>(`/api/v1/operations/${operationId}/events?after=0&limit=200`)
      ]);
      if (request !== detailRequest || !detailOpen) return;
      selectedOperation = mergeSelectedOperation(selectedOperation, operation);
      operations = mergeOperationSnapshot(operations, operation, 200);
      let mergedEvents = operationEvents.filter((event) => event.operation_id === operationId);
      for (const event of events) mergedEvents = mergeOperationTimeline(mergedEvents, event, 200);
      operationEvents = mergedEvents;
    } catch (caught) {
      if (request !== detailRequest) return;
      detailError = apiMessage(caught);
      if (!silent) toast(detailError, 'danger');
    } finally {
      if (request === detailRequest) detailLoading = false;
    }
  }

  function showOperation(operation: Operation): void {
    detailTitle = operationLabel(operation.kind);
    detailJob = null;
    selectedOperation = operation;
    operationEvents = [];
    detailError = '';
    detailOpen = true;
    void loadOperationDetail(operation.id);
  }

  async function cancelOperation(operation: Operation): Promise<void> {
    if (!operationCanCancel(operation) || cancellingOperationId) return;
    cancellingOperationId = operation.id;
    try {
      const cancelled = await api<Operation>(`/api/v1/operations/${operation.id}/cancel`, {
        method: 'POST'
      });
      operations = mergeOperationSnapshot(operations, cancelled, 200);
      if (selectedOperation?.id === cancelled.id) {
        selectedOperation = mergeSelectedOperation(selectedOperation, cancelled);
      }
      toast(`已请求安全取消 · ${shortId(operation.id)}`);
      if (detailOpen && selectedOperation?.id === operation.id) {
        await loadOperationDetail(operation.id, true);
      }
    } catch (caught) {
      toast(apiMessage(caught), 'danger');
    } finally {
      cancellingOperationId = '';
    }
  }

  function clearFallbackTimer(): void {
    if (fallbackTimer !== null) {
      window.clearTimeout(fallbackTimer);
      fallbackTimer = null;
    }
  }

  function scheduleFallbackPoll(): void {
    if (fallbackTimer !== null || streamHealth.mode !== 'fallback') return;
    fallbackTimer = window.setTimeout(async () => {
      fallbackTimer = null;
      if (streamHealth.mode !== 'fallback') return;
      await load(true);
      if (detailOpen && selectedOperation) await loadOperationDetail(selectedOperation.id, true);
      if (streamHealth.mode === 'fallback') {
        streamHealth = operationStreamFailed(streamHealth);
        scheduleFallbackPoll();
      }
    }, streamHealth.pollDelayMs);
  }

  async function loadReadySnapshot(): Promise<void> {
    if (snapshotLoading || streamCursor.snapshotGeneration >= streamCursor.readyGeneration) return;
    const generation = streamCursor.readyGeneration;
    snapshotLoading = true;
    try {
      await loadOperationSnapshot();
      streamCursor = markOperationSnapshotLoaded(streamCursor, generation);
    } catch {
      streamHealth = operationStreamFailed(streamHealth);
      scheduleFallbackPoll();
    } finally {
      snapshotLoading = false;
    }
    if (streamCursor.snapshotGeneration < streamCursor.readyGeneration) void loadReadySnapshot();
  }

  function scheduleDetailRefresh(operationId: string): void {
    if (detailRefreshTimer !== null) return;
    detailRefreshTimer = window.setTimeout(() => {
      detailRefreshTimer = null;
      if (detailOpen && selectedOperation?.id === operationId) {
        void loadOperationDetail(operationId, true);
      }
    }, 400);
  }

  function scheduleOperationRefresh(): void {
    if (operationRefreshTimer !== null) return;
    operationRefreshTimer = window.setTimeout(() => {
      operationRefreshTimer = null;
      void loadOperationSnapshot().catch(() => undefined);
    }, 400);
  }

  function handleStreamMessage(raw: Event): void {
    if (!(raw instanceof MessageEvent) || typeof raw.data !== 'string') return;
    const message = parseOperationStreamMessage(raw.data);
    if (!message) return;
    streamHealth = operationStreamConnected(streamHealth);
    clearFallbackTimer();
    const reduced = reduceOperationStreamMessage(streamCursor, operations, message);
    streamCursor = reduced.state;
    operations = reduced.operations;
    if (reduced.snapshotRequired) void loadReadySnapshot();
    if (!reduced.acceptedEvent) return;
    const event = reduced.acceptedEvent;
    if (!event.operation) scheduleOperationRefresh();
    if (detailOpen && selectedOperation?.id === event.operation_id) {
      operationEvents = mergeOperationTimeline(operationEvents, event, 200);
      if (event.operation && event.operation.event_sequence >= selectedOperation.event_sequence) {
        selectedOperation = mergeOperationSnapshot([selectedOperation], event.operation, 1)[0];
      }
      scheduleDetailRefresh(event.operation_id);
    }
  }

  function startOperationStream(): void {
    if (typeof EventSource === 'undefined') {
      streamHealth = operationStreamFailed(streamHealth);
      scheduleFallbackPoll();
      return;
    }
    operationStream = new EventSource('/api/v1/operations/events');
    operationStream.onopen = () => {
      streamHealth = operationStreamConnected(streamHealth);
      clearFallbackTimer();
    };
    operationStream.onerror = () => {
      streamHealth = operationStreamFailed(streamHealth);
      scheduleFallbackPoll();
    };
    operationStream.onmessage = handleStreamMessage;
    operationStream.addEventListener('ready', handleStreamMessage);
    operationStream.addEventListener('operation', handleStreamMessage);
  }

  onMount(() => {
    void load();
    startOperationStream();
    jobsRefreshTimer = window.setInterval(() => void loadJobsSilently(), 10_000);
  });

  onDestroy(() => {
    operationStream?.close();
    jobsRequest.cancel();
    if (jobsRefreshTimer !== null) window.clearInterval(jobsRefreshTimer);
    clearFallbackTimer();
    if (detailRefreshTimer !== null) window.clearTimeout(detailRefreshTimer);
    if (operationRefreshTimer !== null) window.clearTimeout(operationRefreshTimer);
  });
</script>

<div class="page">
  <PageHeader title="任务中心" description="统一查看持久后台操作、事件时间线和调度 Job。">
    <svelte:fragment slot="actions">
      <button class="button secondary" type="button" on:click={() => load()} disabled={loading}
        ><RefreshCw class={loading ? 'spin' : ''} size={15} />刷新</button
      >
      <button class="button secondary" type="button" on:click={() => runAction('tick')} disabled={!!action}
        ><ListRestart size={15} />调度 tick</button
      >
      <button class="button" type="button" on:click={() => runAction('sync')} disabled={!!action}
        ><Play size={15} fill="currentColor" />运行同步</button
      >
    </svelte:fragment>
  </PageHeader>

  <section class="summary-grid jobs-summary">
    <div class="summary-item">
      <span class="summary-label">全部 Job<Workflow size={16} /></span><strong class="summary-value"
        >{jobs.length}</strong
      ><span class="summary-hint">最近 200 个调度任务</span>
    </div>
    <div class="summary-item">
      <span class="summary-label">待处理 Job<Clock3 size={16} /></span><strong class="summary-value"
        >{activeCount}</strong
      ><span class="summary-hint">排队、运行或等待</span>
    </div>
    <div class="summary-item">
      <span class="summary-label">失败 Job<ShieldAlert size={16} /></span><strong class="summary-value"
        >{failedCount}</strong
      ><span class="summary-hint">包含可重试与终止失败</span>
    </div>
    <div class="summary-item">
      <span class="summary-label">活动操作<Activity size={16} /></span><strong class="summary-value"
        >{activeOperationCount}</strong
      ><span class="summary-hint">持久化排队或运行中</span>
    </div>
  </section>

  <div class:warning={streamHealth.mode === 'fallback'} class="notice stream-notice">
    <Radio class={streamHealth.mode === 'live' ? 'stream-pulse' : ''} size={17} />
    <div>
      <strong class="notice-title">{streamCopy.title}</strong>{streamCopy.detail} 调度 Job 每 10 秒独立刷新。
    </div>
  </div>

  <Panel flush>
    <svelte:fragment slot="header">
      <div class="tabs" aria-label="任务视图">
        <button class:active={tab === 'jobs'} class="tab" type="button" on:click={() => (tab = 'jobs')}
          >调度 Job <span>{jobs.length}</span></button
        >
        <button
          class:active={tab === 'operations'}
          class="tab"
          type="button"
          on:click={() => (tab = 'operations')}>持久操作 <span>{operations.length}</span></button
        >
      </div>
    </svelte:fragment>
    <svelte:fragment slot="actions">
      {#if tab === 'jobs'}
        <select class="select status-filter" bind:value={jobStatusFilter} aria-label="Job 状态"
          ><option value="all">全部状态</option><option value="queued">排队中</option><option value="running"
            >运行中</option
          ><option value="waiting_auth">等待认证</option><option value="retry_wait">等待重试</option><option
            value="succeeded">成功</option
          ><option value="failed_retryable">可重试</option><option value="failed_terminal">终止失败</option
          ></select
        >
      {:else}
        <button
          class="button secondary small"
          type="button"
          on:click={() => runAction('pipeline')}
          disabled={!!action}><Play size={14} />运行下载 / 导出</button
        >
      {/if}
    </svelte:fragment>

    {#if tab === 'operations'}
      <div class="operation-filters">
        <label class="filter-search">
          <span>搜索</span>
          <span class="search-input"
            ><Search size={14} /><input
              class="input"
              bind:value={operationQuery}
              placeholder="操作、关联或错误码"
            /></span
          >
        </label>
        <label>
          <span>类型</span>
          <select class="select" bind:value={operationKindFilter}>
            <option value="all">全部类型</option>
            <option value="account-login">账户登录</option>
            <option value="asset-download">资产下载</option>
            <option value="scheduler-run">订阅同步</option>
            <option value="pipeline-run">下载 / 导出</option>
            <option value="emby-export">媒体库导出</option>
            <option value="media-server-probe">媒体服务器探测</option>
            <option value="media-server-scan">媒体库定向刷新</option>
          </select>
        </label>
        <label>
          <span>状态</span>
          <select class="select" bind:value={operationStateFilter}>
            <option value="all">全部状态</option>
            <option value="queued">排队中</option>
            <option value="running">运行中</option>
            <option value="succeeded">成功</option>
            <option value="failed_retryable">可重试</option>
            <option value="failed_terminal">终止失败</option>
            <option value="cancelled">已取消</option>
            <option value="interrupted">已中断</option>
          </select>
        </label>
        <span class="filter-count">显示 {filteredOperations.length} / {operations.length}</span>
      </div>
    {/if}

    {#if error}
      <div class="notice danger list-error">{error}</div>
    {:else if loading}
      <div class="loading-rows">
        {#each Array(5) as _}<div class="skeleton"></div>{/each}
      </div>
    {:else if tab === 'jobs'}
      {#if filteredJobs.length === 0}
        <EmptyState title="没有匹配 Job" description="添加订阅并运行调度后，Job 会进入这里。" />
      {:else}
        <div class="table-wrap">
          <table class="data-table jobs-table">
            <thead
              ><tr
                ><th>Job</th><th>平台</th><th>状态</th><th>尝试</th><th>可运行时间</th><th>更新时间</th><th
                  class="actions">操作</th
                ></tr
              ></thead
            ><tbody
              >{#each filteredJobs as job}<tr
                  ><td
                    ><span class="cell-main mono">{shortId(job.job_id)}</span><span class="cell-sub mono"
                      >订阅 {shortId(job.subscription_id)}</span
                    ></td
                  ><td
                    >{#if job.platform}<div class="inline-identity compact">
                        <PlatformMark platform={job.platform} /><span>{job.platform}</span>
                      </div>{:else}—{/if}</td
                  ><td><StatusBadge status={job.status} /></td><td>{job.attempt} / {job.max_attempts}</td><td
                    >{formatDate(job.available_at)}</td
                  ><td>{formatDate(job.updated_at)}</td><td class="actions"
                    ><button class="button ghost small" type="button" on:click={() => showJob(job)}
                      ><Eye size={14} />详情</button
                    ></td
                  ></tr
                >{/each}</tbody
            >
          </table>
        </div>
      {/if}
    {:else if filteredOperations.length === 0}
      <EmptyState
        title="没有匹配操作"
        description="调整筛选，或启动同步、下载、登录、媒体库导出及服务器刷新。"
      />
    {:else}
      <div class="table-wrap">
        <table class="data-table operations-table">
          <thead
            ><tr
              ><th>操作</th><th>状态</th><th>阶段</th><th>进度</th><th>请求时间</th><th>结果</th><th
                class="actions">操作</th
              ></tr
            ></thead
          ><tbody
            >{#each filteredOperations as operation}{@const truthNotice =
                operationTruthNotice(operation)}{@const progressPercent =
                operationProgressPercent(operation)}{@const safeResult = safeOperationResult(operation)}<tr
                ><td
                  ><span class="cell-main"
                    >{operationDisplayLabel(operation) === operation.kind
                      ? operationLabel(operation.kind)
                      : operationDisplayLabel(operation)}</span
                  ><span class="cell-sub mono">{shortId(operation.id)}</span></td
                ><td
                  ><StatusBadge status={operation.state} />{#if operation.cancel_requested_at}<span
                      class="cell-sub cancel-copy">取消处理中</span
                    >{/if}</td
                ><td><span class="phase-code mono">{operation.phase ?? '—'}</span></td><td
                  ><span class="progress-copy">{operationProgressLabel(operation)}</span
                  >{#if progressPercent !== null}
                    <div
                      class="progress-track compact-progress"
                      aria-label={operationProgressLabel(operation)}
                    >
                      <div class="progress-bar" style={`width: ${progressPercent}%`}></div>
                    </div>{/if}</td
                ><td>{formatDate(operation.requested_at)}</td><td
                  >{#if operation.error_code}<span class="error-code mono">{operation.error_code}</span
                    >{#if truthNotice}<span class="cell-sub truth-copy">{truthNotice.title}</span>{/if}
                    >{:else if truthNotice}<span class="success-copy">{truthNotice.title}</span
                    >{:else if safeResult}<span class="success-copy">已有白名单摘要</span>{:else}—{/if}</td
                ><td class="actions operation-actions"
                  >{#if operationCanCancel(operation)}<button
                      class="button ghost danger-text small"
                      type="button"
                      on:click={() => cancelOperation(operation)}
                      disabled={!!cancellingOperationId}><Ban size={14} />取消</button
                    >{:else if operation.allowed_actions.includes('retry')}<span class="retry-copy"
                      >可重试</span
                    >{/if}<button
                    class="button ghost small"
                    type="button"
                    on:click={() => showOperation(operation)}><Eye size={14} />详情</button
                  ></td
                ></tr
              >{/each}</tbody
          >
        </table>
      </div>
    {/if}
  </Panel>
</div>

<Modal
  bind:open={detailOpen}
  title={detailTitle}
  description={selectedOperation
    ? '持久状态、安全结果摘要与提交有序事件；不包含 Cookie、签名 URL 或 lease token'
    : '调度 Job 的安全摘要'}
  wide
>
  {#if detailLoading && !detailJob && !selectedOperation}
    <div class="detail-loading"><RefreshCw class="spin" size={20} />正在读取…</div>
  {:else if detailJob}
    <dl class="key-value-list">
      {#each Object.entries(detailJob) as [key, value]}<div class="key-value-row">
          <dt>{key}</dt>
          <dd class:mono={key.includes('id')}>{value ?? '—'}</dd>
        </div>{/each}
    </dl>
  {:else if selectedOperation}
    <div class="operation-detail-heading">
      <div>
        <span class="eyebrow mono">{shortId(selectedOperation.id)}</span>
        <h3>
          {operationDisplayLabel(selectedOperation) === selectedOperation.kind
            ? operationLabel(selectedOperation.kind)
            : operationDisplayLabel(selectedOperation)}
        </h3>
      </div>
      <StatusBadge status={selectedOperation.state} />
    </div>

    {#if selectedOperation.progress}
      <div class="detail-progress">
        <div><span>执行进度</span><strong>{operationProgressLabel(selectedOperation)}</strong></div>
        {#if selectedProgressPercent !== null}
          <div class="progress-track">
            <div class="progress-bar" style={`width: ${selectedProgressPercent}%`}></div>
          </div>
        {/if}
      </div>
    {/if}

    {#if selectedTruthNotice}
      <div
        class="notice observation-truth"
        class:warning={selectedTruthNotice.tone === 'warning'}
        class:danger={selectedTruthNotice.tone === 'danger'}
        class:success={selectedTruthNotice.tone === 'success'}
      >
        <strong>{selectedTruthNotice.title}</strong>
        <span>{selectedTruthNotice.detail}</span>
      </div>
    {/if}

    <dl class="key-value-list compact-list">
      <div class="key-value-row">
        <dt>phase</dt>
        <dd class="mono">{selectedOperation.phase ?? '—'}</dd>
      </div>
      <div class="key-value-row">
        <dt>requested_at</dt>
        <dd>{formatDateLong(selectedOperation.requested_at)}</dd>
      </div>
      <div class="key-value-row">
        <dt>started_at</dt>
        <dd>{formatDateLong(selectedOperation.started_at)}</dd>
      </div>
      <div class="key-value-row">
        <dt>finished_at</dt>
        <dd>{formatDateLong(selectedOperation.finished_at)}</dd>
      </div>
      <div class="key-value-row">
        <dt>correlation_id</dt>
        <dd class="mono">{selectedOperation.correlation_id}</dd>
      </div>
      <div class="key-value-row">
        <dt>target</dt>
        <dd class="mono">
          {selectedOperation.target
            ? `${selectedOperation.target.type} · ${selectedOperation.target.id}`
            : '—'}
        </dd>
      </div>
      <div class="key-value-row">
        <dt>error_code</dt>
        <dd class:error-code={!!selectedOperation.error_code} class="mono">
          {selectedOperation.error_code ?? '—'}
        </dd>
      </div>
    </dl>

    {#if selectedOperation.subjects?.length}
      <section class="detail-section">
        <h3>关联实体</h3>
        <div class="subject-list">
          {#each selectedOperation.subjects as subject}<div>
              <span>{subject.type} · {subject.role}</span><code>{subject.id}</code>
            </div>{/each}
        </div>
      </section>
    {/if}

    {#if selectedSafeResult}
      <section class="detail-section">
        <h3>白名单结果摘要</h3>
        <pre>{JSON.stringify(selectedSafeResult, null, 2)}</pre>
      </section>
    {/if}

    <section class="detail-section timeline-section">
      <div class="section-heading">
        <h3>事件时间线</h3>
        <span>{operationEvents.length} 条</span>
      </div>
      {#if detailError}<div class="notice danger detail-error">{detailError}</div>{/if}
      {#if detailLoading && operationEvents.length === 0}
        <div class="timeline-loading"><RefreshCw class="spin" size={16} />正在读取事件…</div>
      {:else if operationEvents.length === 0}
        <p class="timeline-empty">尚无可显示事件。</p>
      {:else}
        <ol class="timeline">
          {#each operationEvents as event}
            {@const rows = safeOperationContextRows(event)}
            <li class:error-event={event.level === 'error'} class:warning-event={event.level === 'warning'}>
              <span class="timeline-dot"></span>
              <div class="timeline-card">
                <div class="timeline-heading">
                  <strong>{eventLabel(event.event_code)}</strong><time
                    >{formatDateLong(event.created_at)}</time
                  >
                </div>
                <div class="timeline-meta">
                  <code>#{event.stream_sequence}</code>
                  {#if event.phase}<span>phase · <code>{event.phase}</code></span>{/if}
                  {#if event.from_state || event.to_state}<span
                      >{statusLabel(event.from_state)} → {statusLabel(event.to_state)}</span
                    >{/if}
                </div>
                {#if event.subject}<div class="timeline-subject mono">
                    {event.subject.type} · {event.subject.id}
                  </div>{/if}
                {#if rows.length}<dl class="event-context">
                    {#each rows as row}<div>
                        <dt>{row.key}</dt>
                        <dd>{row.value}</dd>
                      </div>{/each}
                  </dl>{/if}
              </div>
            </li>
          {/each}
        </ol>
      {/if}
    </section>
  {/if}
  <svelte:fragment slot="footer">
    {#if selectedOperation && operationCanCancel(selectedOperation)}
      <button
        class="button danger"
        type="button"
        on:click={() => cancelOperation(selectedOperation!)}
        disabled={!!cancellingOperationId}><Ban size={14} />请求安全取消</button
      >
    {/if}
    <button class="button secondary" type="button" on:click={() => (detailOpen = false)}>关闭</button>
  </svelte:fragment>
</Modal>

<style>
  .tabs span {
    margin-left: 4px;
    color: #8994a6;
    font-size: 10px;
  }

  .status-filter {
    width: 126px;
    min-height: 32px;
    padding-top: 4px;
    padding-bottom: 4px;
    font-size: 11px;
  }

  .stream-notice {
    align-items: center;
  }

  :global(.stream-pulse) {
    color: var(--success);
    animation: stream-pulse 1.8s ease-in-out infinite;
  }

  .operation-filters {
    display: grid;
    grid-template-columns: minmax(220px, 1fr) 180px 160px auto;
    align-items: end;
    gap: 10px;
    padding: 13px 14px;
    border-bottom: 1px solid var(--border);
    background: #fbfcfe;
  }

  .operation-filters label {
    display: grid;
    gap: 5px;
    color: var(--text-muted);
    font-size: 11px;
  }

  .search-input {
    position: relative;
    display: block;
  }

  .search-input :global(svg) {
    position: absolute;
    z-index: 1;
    top: 50%;
    left: 10px;
    color: #8a96a8;
    transform: translateY(-50%);
  }

  .search-input .input {
    padding-left: 31px;
  }

  .operation-filters .input,
  .operation-filters .select {
    min-height: 34px;
    padding-top: 5px;
    padding-bottom: 5px;
    font-size: 12px;
  }

  .filter-count {
    padding: 0 0 8px 4px;
    color: var(--text-muted);
    font-size: 11px;
    white-space: nowrap;
  }

  .inline-identity.compact {
    min-width: 80px;
  }

  .actions {
    text-align: right !important;
  }

  .operation-actions {
    white-space: nowrap;
  }

  .operation-actions .button + .button {
    margin-left: 2px;
  }

  .danger-text {
    color: var(--danger) !important;
  }

  .error-code,
  .cancel-copy {
    color: var(--danger) !important;
  }

  .retry-copy {
    margin-right: 5px;
    color: var(--warning);
    font-size: 11px;
  }

  .success-copy {
    color: var(--success);
    font-size: 11px;
  }

  .truth-copy {
    margin-top: 3px;
  }

  .phase-code,
  .progress-copy {
    color: var(--text-secondary);
    font-size: 11px;
  }

  .compact-progress {
    width: 100px;
    height: 4px;
    margin-top: 6px;
  }

  .loading-rows {
    display: grid;
    gap: 2px;
    padding: 12px 14px;
  }

  .loading-rows div {
    height: 50px;
  }

  .list-error {
    margin: 16px;
  }

  .detail-loading,
  .timeline-loading {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 9px;
    color: var(--text-muted);
  }

  .detail-loading {
    min-height: 160px;
  }

  .timeline-loading {
    min-height: 100px;
  }

  .operation-detail-heading,
  .section-heading,
  .detail-progress > div:first-child,
  .timeline-heading,
  .timeline-meta {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
  }

  .operation-detail-heading {
    padding-bottom: 14px;
    border-bottom: 1px solid var(--border);
  }

  .operation-detail-heading h3 {
    margin: 2px 0 0;
    font-size: 16px;
  }

  .eyebrow {
    color: var(--text-muted);
  }

  .detail-progress {
    display: grid;
    gap: 9px;
    margin: 14px 0 3px;
    border: 1px solid #dbe4f0;
    border-radius: var(--radius);
    padding: 12px;
    background: #f8fafc;
  }

  .observation-truth {
    display: grid;
    gap: 4px;
    margin-top: 12px;
  }

  .observation-truth strong {
    font-size: 12px;
  }

  .observation-truth span {
    font-size: 11px;
    line-height: 1.55;
  }

  .detail-progress span {
    color: var(--text-muted);
    font-size: 11px;
  }

  .detail-progress strong {
    font-size: 12px;
  }

  .compact-list .key-value-row {
    padding: 9px 0;
  }

  .detail-section {
    margin-top: 20px;
  }

  .detail-section > h3,
  .section-heading h3 {
    margin: 0 0 8px;
    font-size: 13px;
  }

  .section-heading span {
    color: var(--text-muted);
    font-size: 11px;
  }

  .subject-list {
    display: grid;
    gap: 7px;
  }

  .subject-list > div {
    display: grid;
    gap: 3px;
    border: 1px solid var(--border);
    border-radius: 7px;
    padding: 9px 11px;
    background: #fafbfd;
    font-size: 11px;
  }

  .subject-list code,
  .timeline-card code {
    color: #526077;
    font-size: 10.5px;
    overflow-wrap: anywhere;
  }

  pre {
    max-height: 260px;
    overflow: auto;
    border-radius: 8px;
    padding: 12px;
    background: #111827;
    color: #dbeafe;
    font-size: 11px;
    line-height: 1.6;
  }

  .timeline-section {
    padding-top: 2px;
  }

  .timeline {
    display: grid;
    gap: 0;
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .timeline li {
    position: relative;
    padding: 0 0 13px 20px;
  }

  .timeline li:not(:last-child)::before {
    position: absolute;
    top: 10px;
    bottom: -2px;
    left: 5px;
    width: 1px;
    background: #dce2ea;
    content: '';
  }

  .timeline-dot {
    position: absolute;
    top: 7px;
    left: 2px;
    width: 7px;
    height: 7px;
    border-radius: 99px;
    background: var(--accent);
    box-shadow: 0 0 0 3px #eaf2ff;
  }

  .warning-event .timeline-dot {
    background: #f59e0b;
    box-shadow: 0 0 0 3px #fff4d6;
  }

  .error-event .timeline-dot {
    background: #ef4444;
    box-shadow: 0 0 0 3px #ffe4e6;
  }

  .timeline-card {
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 10px 11px;
    background: #fff;
  }

  .timeline-heading strong {
    font-size: 12px;
  }

  .timeline-heading time,
  .timeline-meta,
  .timeline-empty {
    color: var(--text-muted);
    font-size: 10.5px;
  }

  .timeline-meta {
    justify-content: flex-start;
    margin-top: 5px;
    flex-wrap: wrap;
  }

  .timeline-subject {
    margin-top: 7px;
    color: var(--text-secondary);
    overflow-wrap: anywhere;
  }

  .event-context {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 5px 14px;
    margin: 8px 0 0;
    border-top: 1px solid #edf0f4;
    padding-top: 8px;
  }

  .event-context > div {
    display: flex;
    justify-content: space-between;
    gap: 8px;
  }

  .event-context dt {
    color: var(--text-muted);
  }

  .event-context dd {
    margin: 0;
    color: var(--text-secondary);
    overflow-wrap: anywhere;
    text-align: right;
  }

  .detail-error {
    margin-bottom: 10px;
  }

  @keyframes stream-pulse {
    50% {
      opacity: 0.45;
    }
  }

  @media (max-width: 1050px) {
    .operation-filters {
      grid-template-columns: minmax(220px, 1fr) 170px 150px;
    }

    .filter-count {
      display: none;
    }
  }

  @media (max-width: 900px) {
    .jobs-table,
    .operations-table {
      min-width: 1040px;
    }

    .operation-filters {
      grid-template-columns: 1fr 1fr;
    }

    .filter-search {
      grid-column: 1 / -1;
    }
  }

  @media (max-width: 600px) {
    .operation-filters {
      grid-template-columns: 1fr;
    }

    .filter-search {
      grid-column: auto;
    }

    .event-context {
      grid-template-columns: 1fr;
    }
  }

  @media (prefers-reduced-motion: reduce) {
    :global(.stream-pulse) {
      animation: none;
    }
  }
</style>
