<script lang="ts">
  import { onMount } from 'svelte';
  import {
    Activity,
    Archive,
    ArrowRight,
    CheckCircle2,
    CircleUserRound,
    Clock3,
    Database,
    Download,
    Play,
    RefreshCw,
    ShieldAlert,
    UsersRound
  } from '@lucide/svelte';

  import { api, apiMessage } from '$lib/api/client';
  import EmptyState from '$lib/components/EmptyState.svelte';
  import PageHeader from '$lib/components/PageHeader.svelte';
  import Panel from '$lib/components/Panel.svelte';
  import PlatformMark from '$lib/components/PlatformMark.svelte';
  import StatusBadge from '$lib/components/StatusBadge.svelte';
  import { mediaCrawlerGate, onboardingAccepted, onboardingHydrated } from '$lib/stores/onboarding';
  import { toast } from '$lib/stores/toast';
  import type {
    Account,
    Asset,
    ContentItem,
    DeepReadiness,
    Job,
    Operation,
    Settings,
    StartedOperation,
    Subscription
  } from '$lib/types/api';
  import { formatDate, operationLabel, shortId } from '$lib/utils/format';

  let accounts: Account[] = [];
  let subscriptions: Subscription[] = [];
  let jobs: Job[] = [];
  let assets: Asset[] = [];
  let contents: ContentItem[] = [];
  let operations: Operation[] = [];
  let settings: Settings | null = null;
  let deep: DeepReadiness | null = null;
  let healthOk = false;
  let databaseReady = false;
  let loading = true;
  let loadingDeep = false;
  let deepRequested = false;
  let action = '';
  let error = '';

  $: activeJobs = jobs.filter((item) =>
    ['claimed', 'queued', 'retry_wait', 'running', 'waiting_auth'].includes(item.status)
  );
  $: failedJobs = jobs.filter((item) => item.status.startsWith('failed'));
  $: verifiedAssets = assets.filter((item) => ['verified', 'exported'].includes(item.status));
  $: authAccounts = accounts.filter((item) => item.auth_status === 'authenticated');
  $: if ($onboardingHydrated && $onboardingAccepted && !deepRequested && !loadingDeep) void loadDeep(false);

  async function load(): Promise<void> {
    loading = true;
    error = '';
    try {
      const [
        health,
        ready,
        loadedSettings,
        loadedAccounts,
        loadedSubs,
        loadedJobs,
        loadedAssets,
        loadedContents,
        loadedOps
      ] = await Promise.all([
        api<{ status: string }>('/api/v1/health'),
        api<{ status: string }>('/api/v1/ready'),
        api<Settings>('/api/v1/settings'),
        api<Account[]>('/api/v1/accounts'),
        api<Subscription[]>('/api/v1/subscriptions'),
        api<Job[]>('/api/v1/scheduler/jobs?limit=12'),
        api<Asset[]>('/api/v1/assets?limit=200'),
        api<ContentItem[]>('/api/v1/contents?limit=50'),
        api<Operation[]>('/api/v1/operations?limit=8')
      ]);
      healthOk = health.status === 'ok';
      databaseReady = ready.status === 'ready';
      settings = loadedSettings;
      accounts = loadedAccounts;
      subscriptions = loadedSubs;
      jobs = loadedJobs;
      assets = loadedAssets;
      contents = loadedContents;
      operations = loadedOps;
    } catch (caught) {
      error = apiMessage(caught);
      healthOk = false;
    } finally {
      loading = false;
    }
  }

  async function loadDeep(refresh: boolean): Promise<void> {
    if (!$onboardingAccepted) return;
    loadingDeep = true;
    deepRequested = true;
    try {
      deep = await api<DeepReadiness>(
        `/api/v1/readiness/deep?accept_mediacrawler_license=true&refresh=${refresh}`,
        {},
        65_000
      );
    } catch (caught) {
      toast(apiMessage(caught), 'danger');
    } finally {
      loadingDeep = false;
    }
  }

  async function runSync(): Promise<void> {
    action = 'sync';
    try {
      await api('/api/v1/scheduler/tick', { method: 'POST', body: JSON.stringify({ limit: 100 }) });
      const started = await api<StartedOperation>('/api/v1/scheduler/run', {
        method: 'POST',
        body: JSON.stringify({ max_jobs: 1, ...mediaCrawlerGate() })
      });
      toast(`同步 Worker 已启动 · ${shortId(started.operation_id)}`);
      await load();
    } catch (caught) {
      toast(apiMessage(caught), 'danger');
    } finally {
      action = '';
    }
  }

  async function runPipeline(): Promise<void> {
    action = 'pipeline';
    try {
      const started = await api<StartedOperation>('/api/v1/pipeline/run', {
        method: 'POST',
        body: JSON.stringify({ max_jobs: 1, ...mediaCrawlerGate() })
      });
      toast(`下载 / 导出 Worker 已启动 · ${shortId(started.operation_id)}`);
      await load();
    } catch (caught) {
      toast(apiMessage(caught), 'danger');
    } finally {
      action = '';
    }
  }

  onMount(() => {
    void load();
    const timer = window.setInterval(() => void load(), 30_000);
    const accepted = () => void loadDeep(true);
    window.addEventListener('media-sync:onboarding-accepted', accepted);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener('media-sync:onboarding-accepted', accepted);
    };
  });
</script>

<div class="page">
  <PageHeader title="运行概览" description="账户、订阅、归档与媒体库的当前状态。">
    <svelte:fragment slot="actions">
      <button class="button secondary" type="button" on:click={load} disabled={loading}>
        <RefreshCw class={loading ? 'spin' : ''} size={15} />刷新
      </button>
      <button class="button" type="button" on:click={runSync} disabled={!!action || !$onboardingAccepted}>
        <Play size={15} fill="currentColor" />{action === 'sync' ? '启动中…' : '立即同步'}
      </button>
    </svelte:fragment>
  </PageHeader>

  {#if error}
    <div class="notice danger">
      <ShieldAlert size={17} />
      <div><strong class="notice-title">服务连接失败</strong>{error}</div>
    </div>
  {:else if deep && !deep.ok}
    <div class="notice warning">
      <ShieldAlert size={17} />
      <div>
        <strong class="notice-title">运行环境存在阻塞：{deep.mediacrawler.detail_code ?? deep.code}</strong>
        同步和登录会在启动前停止，不会无限等待。<a class="text-link" href="/diagnostics">查看诊断清单</a>
      </div>
    </div>
  {/if}

  <section class="summary-grid" aria-label="关键统计">
    <div class="summary-item">
      <span class="summary-label">平台账户<CircleUserRound size={16} /></span>
      <strong class="summary-value">{loading ? '—' : accounts.length}</strong>
      <span class="summary-hint">{authAccounts.length} 个已认证</span>
    </div>
    <div class="summary-item">
      <span class="summary-label">创作者订阅<UsersRound size={16} /></span>
      <strong class="summary-value">{loading ? '—' : subscriptions.length}</strong>
      <span class="summary-hint">{subscriptions.filter((item) => item.enabled).length} 个运行中</span>
    </div>
    <div class="summary-item">
      <span class="summary-label">待处理任务<Clock3 size={16} /></span>
      <strong class="summary-value">{loading ? '—' : activeJobs.length}</strong>
      <span class="summary-hint">{failedJobs.length} 个失败任务</span>
    </div>
    <div class="summary-item">
      <span class="summary-label">已归档资产<Archive size={16} /></span>
      <strong class="summary-value">{loading ? '—' : verifiedAssets.length}</strong>
      <span class="summary-hint">共发现 {assets.length} 个资产</span>
    </div>
  </section>

  <Panel title="服务状态" description="真实 API、运行时和持久目录资格">
    <svelte:fragment slot="actions">
      <button
        class="button ghost small"
        type="button"
        on:click={() => loadDeep(true)}
        disabled={loadingDeep || !$onboardingAccepted}
      >
        <RefreshCw class={loadingDeep ? 'spin' : ''} size={14} />深度预检
      </button>
    </svelte:fragment>
    <div class="service-grid">
      <a href="/diagnostics" class="service-item">
        <span class="service-icon"><Activity size={18} /></span>
        <div><strong>API 服务</strong><span>{healthOk ? '响应正常' : '无法连接'}</span></div>
        <StatusBadge status={healthOk ? 'succeeded' : 'failed'} label={healthOk ? '正常' : '异常'} />
      </a>
      <a href="/diagnostics" class="service-item">
        <span class="service-icon"><Database size={18} /></span>
        <div><strong>数据库</strong><span>{databaseReady ? '迁移与连接就绪' : '尚未就绪'}</span></div>
        <StatusBadge
          status={databaseReady ? 'succeeded' : 'failed'}
          label={databaseReady ? '就绪' : '异常'}
        />
      </a>
      <a href="/diagnostics" class="service-item">
        <span class="service-icon"><CheckCircle2 size={18} /></span>
        <div>
          <strong>MediaCrawler</strong><span
            >{deep?.mediacrawler.upstream_sha
              ? shortId(deep.mediacrawler.upstream_sha)
              : '等待资格检查'}</span
          >
        </div>
        <StatusBadge
          status={deep?.mediacrawler.ok ? 'succeeded' : deep ? 'failed' : 'pending'}
          label={deep?.mediacrawler.ok ? '就绪' : deep ? '阻塞' : '检查中'}
        />
      </a>
      <a href="/diagnostics" class="service-item">
        <span class="service-icon"><Activity size={18} /></span>
        <div><strong>Chromium</strong><span>{deep?.browser.version ?? '等待启动探针'}</span></div>
        <StatusBadge
          status={deep?.browser.status === 'pass'
            ? 'succeeded'
            : deep?.browser.status === 'fail'
              ? 'failed'
              : 'pending'}
          label={deep?.browser.status === 'pass'
            ? '可启动'
            : deep?.browser.status === 'fail'
              ? '失败'
              : '未检查'}
        />
      </a>
    </div>
  </Panel>

  <div class="content-grid">
    <Panel title="最近任务" description="订阅同步与后续处理状态" flush>
      <svelte:fragment slot="actions"
        ><a class="text-link" href="/jobs">查看全部 <ArrowRight size={13} /></a></svelte:fragment
      >
      {#if loading}
        <div class="loading-rows">
          <div class="skeleton"></div>
          <div class="skeleton"></div>
          <div class="skeleton"></div>
        </div>
      {:else if jobs.length === 0}
        <EmptyState title="还没有任务" description="添加订阅后运行调度，任务会出现在这里。">
          <a class="button secondary small" href="/subscriptions">管理订阅</a>
        </EmptyState>
      {:else}
        <div class="table-wrap">
          <table class="data-table">
            <thead><tr><th>平台 / Job</th><th>状态</th><th>尝试</th><th>更新时间</th></tr></thead>
            <tbody>
              {#each jobs.slice(0, 6) as job}
                <tr>
                  <td>
                    <div class="inline-identity">
                      {#if job.platform}<PlatformMark platform={job.platform} />{/if}
                      <div>
                        <span class="cell-main mono">{shortId(job.job_id)}</span><span class="cell-sub"
                          >订阅 {shortId(job.subscription_id)}</span
                        >
                      </div>
                    </div>
                  </td>
                  <td><StatusBadge status={job.status} /></td>
                  <td>{job.attempt} / {job.max_attempts}</td>
                  <td>{formatDate(job.updated_at)}</td>
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
      {/if}
    </Panel>

    <Panel title="快速操作" description="操作在后台运行，离开页面不会重复提交">
      <div class="quick-actions">
        <button type="button" on:click={runSync} disabled={!!action || !$onboardingAccepted}>
          <span><Play size={17} /></span>
          <div><strong>运行订阅同步</strong><small>先调度，再处理 1 个任务</small></div>
          <ArrowRight size={15} />
        </button>
        <button type="button" on:click={runPipeline} disabled={!!action || !$onboardingAccepted}>
          <span><Download size={17} /></span>
          <div><strong>运行下载 / 导出</strong><small>处理 1 个待办资产任务</small></div>
          <ArrowRight size={15} />
        </button>
        <a href="/library">
          <span><Database size={17} /></span>
          <div><strong>查看媒体库</strong><small>{contents.length} 条内容已入库</small></div>
          <ArrowRight size={15} />
        </a>
      </div>
      {#if operations.length > 0}
        <div class="latest-operation">
          <span>{operationLabel(operations[0].kind)}</span>
          <StatusBadge status={operations[0].state} />
          <small>{formatDate(operations[0].started_at)}</small>
        </div>
      {/if}
    </Panel>
  </div>

  {#if settings}
    <div class="footer-facts">
      <span>media-sync v{settings.version}</span><span>API {settings.api_bind}</span><span
        >归档 {settings.archive_dir}</span
      >
    </div>
  {/if}
</div>

<style>
  .service-grid {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 0;
  }

  .service-item {
    display: grid;
    min-width: 0;
    grid-template-columns: auto minmax(0, 1fr) auto;
    align-items: center;
    gap: 10px;
    padding: 7px 14px;
    border-right: 1px solid var(--border);
    border-radius: 7px;
  }

  .service-item:last-child {
    border-right: 0;
  }

  .service-item:hover {
    background: #f8fafc;
  }

  .service-icon {
    display: inline-flex;
    width: 35px;
    height: 35px;
    align-items: center;
    justify-content: center;
    border-radius: 8px;
    background: #f1f5f9;
    color: #52657f;
  }

  .service-item strong,
  .service-item span {
    display: block;
  }

  .service-item strong {
    overflow: hidden;
    color: #2c394e;
    font-size: 12px;
    font-weight: 610;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .service-item div > span {
    overflow: hidden;
    margin-top: 2px;
    color: var(--text-muted);
    font-size: 10.5px;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .quick-actions {
    display: grid;
    gap: 6px;
  }

  .quick-actions button,
  .quick-actions a {
    display: grid;
    width: 100%;
    grid-template-columns: auto 1fr auto;
    align-items: center;
    gap: 10px;
    border: 0;
    border-radius: 8px;
    padding: 10px;
    background: transparent;
    color: #425067;
    text-align: left;
    cursor: pointer;
  }

  .quick-actions button:hover:not(:disabled),
  .quick-actions a:hover {
    background: #f6f8fb;
  }

  .quick-actions button:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  :global(.quick-actions button > span:first-child),
  :global(.quick-actions a > span:first-child) {
    display: inline-flex;
    width: 34px;
    height: 34px;
    align-items: center;
    justify-content: center;
    border: 1px solid var(--border);
    border-radius: 8px;
    background: #fff;
    color: #4f6481;
  }

  .quick-actions strong,
  .quick-actions small {
    display: block;
  }

  .quick-actions strong {
    color: #344158;
    font-size: 12px;
    font-weight: 610;
  }

  .quick-actions small {
    margin-top: 2px;
    color: var(--text-muted);
    font-size: 10.5px;
  }

  .latest-operation {
    display: grid;
    grid-template-columns: 1fr auto auto;
    align-items: center;
    gap: 10px;
    margin-top: 13px;
    padding-top: 13px;
    border-top: 1px solid var(--border);
    color: #536178;
    font-size: 11px;
  }

  .latest-operation small {
    color: var(--text-muted);
  }

  .loading-rows {
    display: grid;
    gap: 1px;
    padding: 12px 14px;
  }

  .loading-rows .skeleton {
    height: 44px;
  }

  .footer-facts {
    display: flex;
    gap: 8px 18px;
    flex-wrap: wrap;
    padding: 2px 3px;
    color: #9aa3b1;
    font-size: 10.5px;
  }

  :global(.panel-header .text-link) {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    font-size: 11px;
  }

  @media (max-width: 1220px) {
    .service-grid {
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px;
    }

    .service-item {
      border-right: 0;
    }
  }

  @media (max-width: 620px) {
    .service-grid {
      grid-template-columns: 1fr;
    }

    .service-item {
      padding-right: 4px;
      padding-left: 4px;
    }
  }
</style>
