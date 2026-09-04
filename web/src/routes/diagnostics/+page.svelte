<script lang="ts">
  import { onMount } from 'svelte';
  import { Activity, Check, CircleSlash2, Copy, RefreshCw, ShieldAlert, Terminal, X } from '@lucide/svelte';

  import { api, apiMessage } from '$lib/api/client';
  import PageHeader from '$lib/components/PageHeader.svelte';
  import Panel from '$lib/components/Panel.svelte';
  import StatusBadge from '$lib/components/StatusBadge.svelte';
  import { onboardingAccepted } from '$lib/stores/onboarding';
  import { toast } from '$lib/stores/toast';
  import type { CheckState, DeepReadiness } from '$lib/types/api';
  import { formatDateLong, shortId } from '$lib/utils/format';

  let report: DeepReadiness | null = null;
  let loading = true;
  let error = '';

  const labels: Record<string, string> = {
    license_acknowledgement: '许可证确认',
    lock: '上游锁文件',
    checkout_path: 'Checkout 路径',
    repository_root: 'Git 仓库根',
    required_files: '必需文件',
    license: '许可证摘要',
    revision: '锁定提交',
    tracked_files: 'Tracked blob',
    worktree_clean: '工作树干净',
    runtime: 'Python 运行时',
    git: 'Git',
    ffmpeg: 'ffmpeg',
    ffprobe: 'ffprobe',
    Xvfb: 'Xvfb',
    state: '状态目录',
    archive: '归档目录',
    export: '导出目录',
    jobs: '任务目录',
    mediacrawler_runtime: 'MediaCrawler 运行目录'
  };

  const remediation: Record<string, string> = {
    browser_launch_failed: '重新构建镜像并检查 Playwright Chromium、共享内存及运行用户权限。',
    checkout_missing: '先运行 scripts/fetch_mediacrawler.sh，再重新构建容器。',
    license_digest_mismatch: '当前版本已使用跨平台 LF 资格摘要；拉取最新代码并无缓存重建镜像。',
    not_repository_root: '确保 /app/.upstream/MediaCrawler 本身就是带 .git 的仓库根。',
    revision_mismatch: '重新抓取 upstreams.lock.json 锁定的完整 SHA。',
    tracked_blob_mismatch: '删除本地预取目录后重新抓取锁定提交，不要修改必需文件。',
    worktree_dirty: '重新建立干净 checkout；不要在容器中直接修改上游源码。'
  };

  $: checkoutChecks = Object.entries(report?.mediacrawler.checks ?? {});
  $: toolChecks = Object.entries(report?.tools ?? {}).map(
    ([name, value]) => [name, value.status] as [string, CheckState]
  );
  $: pathChecks = Object.entries(report?.paths ?? {}).map(
    ([name, value]) => [name, value.status] as [string, CheckState]
  );
  $: failedCode =
    report?.mediacrawler.detail_code ?? report?.browser.detail_code ?? (report?.ok ? null : report?.code);

  async function load(refresh: boolean): Promise<void> {
    if (!$onboardingAccepted) {
      loading = false;
      return;
    }
    loading = true;
    error = '';
    try {
      report = await api<DeepReadiness>(
        `/api/v1/readiness/deep?accept_mediacrawler_license=true&refresh=${refresh}`,
        {},
        65_000
      );
    } catch (caught) {
      error = apiMessage(caught);
    } finally {
      loading = false;
    }
  }

  async function copyCode(): Promise<void> {
    if (!failedCode) return;
    await navigator.clipboard.writeText(failedCode);
    toast('错误码已复制。');
  }

  function stateLabel(state: CheckState): string {
    return state === 'pass' ? '通过' : state === 'fail' ? '失败' : '未运行';
  }

  function stateIcon(state: CheckState): typeof Check {
    return state === 'pass' ? Check : state === 'fail' ? X : CircleSlash2;
  }

  function stateClass(state: CheckState): string {
    return state === 'pass' ? 'pass' : state === 'fail' ? 'fail' : 'idle';
  }

  onMount(() => {
    let loaded = false;
    return onboardingAccepted.subscribe((accepted) => {
      if (!accepted) {
        loading = false;
        return;
      }
      if (loaded) return;
      loaded = true;
      void load(false);
    });
  });
</script>

<div class="page">
  <PageHeader title="诊断" description="检查数据库、MediaCrawler checkout、Chromium、工具链和持久目录。">
    <svelte:fragment slot="actions"
      ><button
        class="button"
        type="button"
        on:click={() => load(true)}
        disabled={loading || !$onboardingAccepted}
        ><RefreshCw class={loading ? 'spin' : ''} size={15} />{loading ? '检查中…' : '运行深度预检'}</button
      ></svelte:fragment
    >
  </PageHeader>

  {#if error}
    <div class="notice danger">
      <ShieldAlert size={17} />
      <div><strong class="notice-title">预检请求失败</strong>{error}</div>
    </div>
  {:else if report && !report.ok}
    <div class="diagnostic-alert">
      <span class="alert-icon"><ShieldAlert size={23} /></span>
      <div class="alert-copy">
        <strong>运行环境被安全门禁阻塞</strong>
        <p>{remediation[failedCode ?? ''] ?? '根据失败项检查容器构建、锁定 checkout 和持久目录。'}</p>
      </div>
      <button type="button" on:click={copyCode}
        ><span class="mono">{failedCode}</span><Copy size={14} /></button
      >
    </div>
  {:else if report?.ok}
    <div class="notice success">
      <Check size={17} />
      <div>
        <strong class="notice-title">所有深度预检均已通过</strong>MediaCrawler 与 Chromium
        可以启动，目录和工具链已就绪。
      </div>
    </div>
  {/if}

  <section class="summary-grid diagnostic-summary">
    <div class="summary-item">
      <span class="summary-label">总体状态<Activity size={16} /></span><strong class="summary-state"
        >{loading ? '检查中' : report?.ok ? '可运行' : '阻塞'}</strong
      ><span class="summary-hint">{report?.cached ? '使用 60 秒缓存' : '实时检查结果'}</span>
    </div>
    <div class="summary-item">
      <span class="summary-label">Checkout<Terminal size={16} /></span><strong class="summary-state"
        >{report?.mediacrawler.checkout_ready ? '已验证' : '未通过'}</strong
      ><span class="summary-hint mono">{shortId(report?.mediacrawler.upstream_sha)}</span>
    </div>
    <div class="summary-item">
      <span class="summary-label">Chromium<Activity size={16} /></span><strong class="summary-state"
        >{report?.browser.status === 'pass'
          ? '可启动'
          : report?.browser.status === 'fail'
            ? '失败'
            : '未运行'}</strong
      ><span class="summary-hint">{report?.browser.version ?? '—'}</span>
    </div>
    <div class="summary-item">
      <span class="summary-label">网络边界<ShieldAlert size={16} /></span><strong class="summary-state"
        >{report?.security.safe ? '本机安全' : '需要核对'}</strong
      ><span class="summary-hint">{report?.security.api_host ?? '—'}:{report?.security.api_port ?? '—'}</span>
    </div>
  </section>

  <div class="content-grid diagnostic-grid">
    <Panel title="MediaCrawler checkout" description="许可证、锁定提交和 tracked blob">
      {#if loading && !report}
        <div class="check-skeletons">
          {#each Array(9) as _}<div class="skeleton"></div>{/each}
        </div>
      {:else}
        <div class="check-list">
          {#each checkoutChecks as [name, state]}
            {@const Icon = stateIcon(state)}
            <div class="check-row">
              <span class="check-icon {stateClass(state)}"><Icon size={14} strokeWidth={2} /></span><span
                >{labels[name] ?? name}</span
              ><small class={stateClass(state)}>{stateLabel(state)}</small>
            </div>
          {/each}
        </div>
      {/if}
    </Panel>

    <Panel title="工具链与目录" description="运行依赖及持久卷可写性">
      <div class="check-list split-list">
        {#each [...toolChecks, ...pathChecks] as [name, state]}
          {@const Icon = stateIcon(state)}
          <div class="check-row">
            <span class="check-icon {stateClass(state)}"><Icon size={14} strokeWidth={2} /></span><span
              >{labels[name] ?? name}</span
            ><small class={stateClass(state)}>{stateLabel(state)}</small>
          </div>
        {/each}
      </div>
    </Panel>
  </div>

  <Panel title="构建与运行事实" description="用于复现容器环境，不包含敏感路径">
    <div class="facts-grid">
      <dl class="key-value-list">
        <div class="key-value-row">
          <dt>最近检查</dt>
          <dd>{formatDateLong(report?.checked_at)}</dd>
        </div>
        <div class="key-value-row">
          <dt>锁定 upstream SHA</dt>
          <dd class="mono">{report?.mediacrawler.upstream_sha ?? '—'}</dd>
        </div>
        <div class="key-value-row">
          <dt>运行时 Chromium</dt>
          <dd>{report?.browser.version ?? '—'}</dd>
        </div>
        <div class="key-value-row">
          <dt>API 绑定</dt>
          <dd>{report?.security.api_host ?? '—'}:{report?.security.api_port ?? '—'}</dd>
        </div>
      </dl>
      <dl class="key-value-list">
        <div class="key-value-row">
          <dt>构建 Chromium</dt>
          <dd>{report?.build_manifest.facts.chromium ?? '—'}</dd>
        </div>
        <div class="key-value-row">
          <dt>Playwright</dt>
          <dd>{report?.build_manifest.facts.playwright ?? '—'}</dd>
        </div>
        <div class="key-value-row">
          <dt>Python</dt>
          <dd>{report?.build_manifest.facts.python ?? '—'}</dd>
        </div>
        <div class="key-value-row">
          <dt>ffmpeg</dt>
          <dd class="fact-clip">{report?.build_manifest.facts.ffmpeg ?? '—'}</dd>
        </div>
      </dl>
    </div>
  </Panel>
</div>

<style>
  .diagnostic-alert {
    display: grid;
    grid-template-columns: auto minmax(0, 1fr) auto;
    align-items: center;
    gap: 14px;
    border: 1px solid #fecdd3;
    border-radius: 10px;
    padding: 14px 16px;
    background: #fff6f7;
  }

  .alert-icon {
    display: inline-flex;
    width: 42px;
    height: 42px;
    align-items: center;
    justify-content: center;
    border-radius: 9px;
    background: #ffe4e6;
    color: #c2414b;
  }

  .alert-copy strong {
    color: #8f2430;
    font-size: 13px;
  }

  .alert-copy p {
    margin: 3px 0 0;
    color: #a13d48;
    font-size: 11.5px;
  }

  .diagnostic-alert button {
    display: inline-flex;
    align-items: center;
    gap: 7px;
    border: 1px solid #f2bbc1;
    border-radius: 6px;
    padding: 6px 9px;
    background: #fff;
    color: #a52d39;
    cursor: pointer;
  }

  .summary-state {
    display: block;
    margin-top: 7px;
    color: #172033;
    font-size: 19px;
    font-weight: 660;
    line-height: 1.1;
  }

  .diagnostic-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .check-list {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 7px 18px;
  }

  .check-row {
    display: grid;
    min-height: 34px;
    grid-template-columns: auto 1fr auto;
    align-items: center;
    gap: 8px;
    border-bottom: 1px solid #edf0f4;
    color: #425067;
    font-size: 11.5px;
  }

  .check-icon {
    display: inline-flex;
    width: 21px;
    height: 21px;
    align-items: center;
    justify-content: center;
    border-radius: 99px;
  }

  .check-icon.pass {
    background: #dcfce7;
    color: #15803d;
  }

  .check-icon.fail {
    background: #ffe4e6;
    color: #c2414b;
  }

  .check-icon.idle {
    background: #eef2f7;
    color: #8490a2;
  }

  .check-row small {
    font-size: 10px;
  }

  .check-row small.pass {
    color: #15803d;
  }

  .check-row small.fail {
    color: #c2414b;
  }

  .check-row small.idle {
    color: #8792a5;
  }

  .check-skeletons {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 8px;
  }

  .check-skeletons div {
    height: 33px;
  }

  .facts-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 36px;
  }

  .fact-clip {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  @media (max-width: 1050px) {
    .diagnostic-grid,
    .facts-grid {
      grid-template-columns: 1fr;
    }
  }

  @media (max-width: 620px) {
    .diagnostic-alert {
      grid-template-columns: auto 1fr;
    }

    .diagnostic-alert button {
      grid-column: 1 / -1;
      justify-content: center;
    }

    .check-list,
    .check-skeletons {
      grid-template-columns: 1fr;
    }
  }
</style>
