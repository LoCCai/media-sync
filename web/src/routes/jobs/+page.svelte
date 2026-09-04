<script lang="ts">
  import { onDestroy, onMount } from 'svelte';
  import { Activity, Clock3, Eye, ListRestart, Play, RefreshCw, ShieldAlert, Workflow } from '@lucide/svelte';

  import { api, apiMessage } from '$lib/api/client';
  import EmptyState from '$lib/components/EmptyState.svelte';
  import Modal from '$lib/components/Modal.svelte';
  import PageHeader from '$lib/components/PageHeader.svelte';
  import Panel from '$lib/components/Panel.svelte';
  import PlatformMark from '$lib/components/PlatformMark.svelte';
  import StatusBadge from '$lib/components/StatusBadge.svelte';
  import { mediaCrawlerGate } from '$lib/stores/onboarding';
  import { toast } from '$lib/stores/toast';
  import type { DeepReadiness, Job, Operation, StartedOperation } from '$lib/types/api';
  import { formatDate, formatDateLong, operationLabel, shortId } from '$lib/utils/format';

  let jobs: Job[] = [];
  let operations: Operation[] = [];
  let loading = true;
  let action = '';
  let error = '';
  let tab: 'jobs' | 'operations' = 'jobs';
  let statusFilter = 'all';
  let detailOpen = false;
  let detailTitle = '';
  let detailPayload: Record<string, unknown> | Job | Operation | null = null;
  let refreshTimer: number | null = null;

  $: filteredJobs = statusFilter === 'all' ? jobs : jobs.filter((item) => item.status === statusFilter);
  $: activeCount = jobs.filter((item) =>
    ['claimed', 'queued', 'retry_wait', 'running', 'waiting_auth', 'waiting_user'].includes(item.status)
  ).length;
  $: failedCount = jobs.filter((item) => item.status.startsWith('failed')).length;
  $: runningOperations = operations.filter((item) => item.state === 'running').length;

  async function load(silent = false): Promise<void> {
    if (!silent) loading = true;
    error = '';
    try {
      [jobs, operations] = await Promise.all([
        api<Job[]>('/api/v1/scheduler/jobs?limit=200'),
        api<Operation[]>('/api/v1/operations?limit=100')
      ]);
    } catch (caught) {
      error = apiMessage(caught);
    } finally {
      loading = false;
    }
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
    detailPayload = null;
    detailOpen = true;
    try {
      detailPayload = await api<Job>(`/api/v1/scheduler/jobs/${job.job_id}`);
    } catch (caught) {
      toast(apiMessage(caught), 'danger');
      detailOpen = false;
    }
  }

  function showOperation(operation: Operation): void {
    detailTitle = operationLabel(operation.kind);
    detailPayload = operation;
    detailOpen = true;
  }

  onMount(() => {
    void load();
    refreshTimer = window.setInterval(() => void load(true), 5_000);
  });

  onDestroy(() => {
    if (refreshTimer !== null) window.clearInterval(refreshTimer);
  });
</script>

<div class="page">
  <PageHeader title="任务队列" description="统一查看调度任务和当前进程内后台操作。">
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
      <span class="summary-label">全部任务<Workflow size={16} /></span><strong class="summary-value"
        >{jobs.length}</strong
      ><span class="summary-hint">最近 200 个任务</span>
    </div>
    <div class="summary-item">
      <span class="summary-label">待处理<Clock3 size={16} /></span><strong class="summary-value"
        >{activeCount}</strong
      ><span class="summary-hint">排队、运行或等待</span>
    </div>
    <div class="summary-item">
      <span class="summary-label">失败<ShieldAlert size={16} /></span><strong class="summary-value"
        >{failedCount}</strong
      ><span class="summary-hint">包含可重试与终止失败</span>
    </div>
    <div class="summary-item">
      <span class="summary-label">后台操作<Activity size={16} /></span><strong class="summary-value"
        >{runningOperations}</strong
      ><span class="summary-hint">当前仍在运行</span>
    </div>
  </section>

  <div class="notice">
    <Activity size={17} />
    <div>
      <strong class="notice-title">任务自动刷新</strong>列表每 5 秒刷新一次。深度预检失败时 Worker
      会在启动前返回明确错误，不会在页面里无限等待。
    </div>
  </div>

  <Panel flush>
    <svelte:fragment slot="header">
      <div class="tabs" aria-label="任务视图">
        <button class:active={tab === 'jobs'} class="tab" type="button" on:click={() => (tab = 'jobs')}
          >调度任务 <span>{jobs.length}</span></button
        >
        <button
          class:active={tab === 'operations'}
          class="tab"
          type="button"
          on:click={() => (tab = 'operations')}>后台操作 <span>{operations.length}</span></button
        >
      </div>
    </svelte:fragment>
    <svelte:fragment slot="actions">
      {#if tab === 'jobs'}
        <select class="select status-filter" bind:value={statusFilter} aria-label="任务状态"
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

    {#if error}
      <div class="notice danger list-error">{error}</div>
    {:else if loading}
      <div class="loading-rows">
        {#each Array(5) as _}<div class="skeleton"></div>{/each}
      </div>
    {:else if tab === 'jobs'}
      {#if filteredJobs.length === 0}
        <EmptyState title="没有匹配任务" description="添加订阅并运行调度后，任务会进入这里。" />
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
    {:else if operations.length === 0}
      <EmptyState title="还没有后台操作" description="运行同步、下载、登录或媒体库导出后会显示在这里。" />
    {:else}
      <div class="table-wrap">
        <table class="data-table operations-table">
          <thead
            ><tr
              ><th>操作</th><th>状态</th><th>开始</th><th>完成</th><th>结果</th><th class="actions">操作</th
              ></tr
            ></thead
          ><tbody
            >{#each operations as operation}<tr
                ><td
                  ><span class="cell-main">{operationLabel(operation.kind)}</span><span class="cell-sub mono"
                    >{shortId(operation.id)}</span
                  ></td
                ><td><StatusBadge status={operation.state} /></td><td>{formatDate(operation.started_at)}</td
                ><td>{formatDate(operation.finished_at)}</td><td
                  >{#if operation.error_code}<span class="error-code mono">{operation.error_code}</span
                    >{:else if operation.result}<span class="success-copy">已返回结果</span>{:else}—{/if}</td
                ><td class="actions"
                  ><button class="button ghost small" type="button" on:click={() => showOperation(operation)}
                    ><Eye size={14} />详情</button
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
  description="安全摘要，不包含 Cookie、签名 URL 或 lease token"
  wide
>
  {#if detailPayload}
    <dl class="key-value-list">
      {#each Object.entries(detailPayload) as [key, value]}
        {#if !['result'].includes(key)}<div class="key-value-row">
            <dt>{key}</dt>
            <dd class:mono={key.includes('id')}>
              {typeof value === 'object' && value !== null ? JSON.stringify(value) : (value ?? '—')}
            </dd>
          </div>{/if}
      {/each}
    </dl>
    {#if 'result' in detailPayload && detailPayload.result}
      <h3 class="result-title">操作结果</h3>
      <pre>{JSON.stringify(detailPayload.result, null, 2)}</pre>
    {/if}
  {:else}
    <div class="detail-loading"><RefreshCw class="spin" size={20} />正在读取…</div>
  {/if}
  <svelte:fragment slot="footer"
    ><button class="button secondary" type="button" on:click={() => (detailOpen = false)}>关闭</button
    ></svelte:fragment
  >
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

  .inline-identity.compact {
    min-width: 80px;
  }

  .actions {
    text-align: right !important;
  }

  .error-code {
    color: #c2414b;
  }

  .success-copy {
    color: #15803d;
    font-size: 11px;
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

  .detail-loading {
    display: flex;
    min-height: 160px;
    align-items: center;
    justify-content: center;
    gap: 9px;
    color: var(--text-muted);
  }

  .result-title {
    margin: 18px 0 8px;
    font-size: 13px;
  }

  pre {
    max-height: 280px;
    overflow: auto;
    border-radius: 8px;
    padding: 12px;
    background: #111827;
    color: #dbeafe;
    font-size: 11px;
    line-height: 1.6;
  }

  @media (max-width: 900px) {
    .jobs-table,
    .operations-table {
      min-width: 920px;
    }
  }
</style>
