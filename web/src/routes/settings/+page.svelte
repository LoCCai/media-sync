<script lang="ts">
  import { onMount } from 'svelte';
  import { ExternalLink, FolderCog, RefreshCw, RotateCcw, Server, ShieldCheck } from '@lucide/svelte';

  import { api, apiMessage } from '$lib/api/client';
  import Modal from '$lib/components/Modal.svelte';
  import PageHeader from '$lib/components/PageHeader.svelte';
  import Panel from '$lib/components/Panel.svelte';
  import StatusBadge from '$lib/components/StatusBadge.svelte';
  import { onboardingAccepted, resetOnboarding } from '$lib/stores/onboarding';
  import { toast } from '$lib/stores/toast';
  import type { Settings } from '$lib/types/api';

  let settings: Settings | null = null;
  let loading = true;
  let error = '';
  let resetOpen = false;

  $: nonLoopback = settings
    ? !settings.api_bind.startsWith('127.0.0.1:') && !settings.api_bind.startsWith('localhost:')
    : false;

  async function load(): Promise<void> {
    loading = true;
    error = '';
    try {
      settings = await api<Settings>('/api/v1/settings');
    } catch (caught) {
      error = apiMessage(caught);
    } finally {
      loading = false;
    }
  }

  function confirmReset(): void {
    resetOnboarding();
    resetOpen = false;
    toast('首次使用确认已重置，确认窗口已重新打开。', 'info');
  }

  onMount(() => void load());
</script>

<div class="page">
  <PageHeader title="设置" description="查看部署路径、安全边界与控制台本地偏好。">
    <svelte:fragment slot="actions"
      ><button class="button secondary" type="button" on:click={load} disabled={loading}
        ><RefreshCw class={loading ? 'spin' : ''} size={15} />刷新</button
      ></svelte:fragment
    >
  </PageHeader>

  {#if error}<div class="notice danger">{error}</div>{/if}
  {#if nonLoopback}
    <div class="notice warning">
      <ShieldCheck size={17} />
      <div>
        <strong class="notice-title">API 绑定到非回环地址</strong>容器内绑定
        <span class="mono">{settings?.api_bind}</span> 属于正常部署方式，但宿主机端口只能发布到可信网络。
      </div>
    </div>
  {/if}

  <div class="settings-grid">
    <Panel title="运行配置" description="环境变量解析后的只读值">
      {#if loading && !settings}
        <div class="settings-skeleton">
          {#each Array(6) as _}<div class="skeleton"></div>{/each}
        </div>
      {:else if settings}
        <dl class="key-value-list">
          <div class="key-value-row">
            <dt>版本</dt>
            <dd>v{settings.version}</dd>
          </div>
          <div class="key-value-row">
            <dt>API 绑定</dt>
            <dd class="mono">{settings.api_bind}</dd>
          </div>
          <div class="key-value-row">
            <dt>状态目录</dt>
            <dd class="mono">{settings.state_dir}</dd>
          </div>
          <div class="key-value-row">
            <dt>归档目录</dt>
            <dd class="mono">{settings.archive_dir}</dd>
          </div>
          <div class="key-value-row">
            <dt>媒体库目录</dt>
            <dd class="mono">{settings.export_dir}</dd>
          </div>
          <div class="key-value-row">
            <dt>任务目录</dt>
            <dd class="mono">{settings.job_dir}</dd>
          </div>
          <div class="key-value-row">
            <dt>MediaCrawler Python</dt>
            <dd class="mono">{settings.mediacrawler_python_executable ?? '未配置'}</dd>
          </div>
        </dl>
      {/if}
    </Panel>

    <Panel title="首次使用确认" description="当前浏览器中的本地确认状态">
      <div class="preference-row">
        <span class="preference-icon"><ShieldCheck size={19} /></span>
        <div>
          <strong>MediaCrawler 操作确认</strong>
          <p>确认后，登录、同步和下载自动携带启用及许可证参数。</p>
        </div>
        <StatusBadge
          status={$onboardingAccepted ? 'succeeded' : 'required'}
          label={$onboardingAccepted ? '已确认' : '待确认'}
        />
      </div>
      <div class="notice" style="margin-top:14px">
        <Server size={17} />确认保存在浏览器 localStorage，不写入
        Cookie，不会随页面刷新丢失。换浏览器或清理站点数据后会再次出现。
      </div>
      <div class="button-row" style="margin-top:15px">
        <button class="button secondary" type="button" on:click={() => (resetOpen = true)}
          ><RotateCcw size={15} />重新查看首次引导</button
        >
      </div>
    </Panel>
  </div>

  <Panel title="迁移与维护" description="Web Console v2 与旧控制台并行一个发布周期">
    <div class="maintenance-list">
      <a href="/legacy" target="_blank" rel="noreferrer"
        ><span class="maintenance-icon"><FolderCog size={18} /></span>
        <div>
          <strong>打开旧版控制台</strong>
          <p>仅用于迁移期回退；日常操作请使用当前分页面板。</p>
        </div>
        <ExternalLink size={16} /></a
      >
      <a href="/api/docs" target="_blank" rel="noreferrer"
        ><span class="maintenance-icon"><Server size={18} /></span>
        <div>
          <strong>打开 API 文档</strong>
          <p>查看当前 FastAPI OpenAPI 契约与请求模型。</p>
        </div>
        <ExternalLink size={16} /></a
      >
      <a href="/diagnostics"
        ><span class="maintenance-icon"><ShieldCheck size={18} /></span>
        <div>
          <strong>运行部署诊断</strong>
          <p>检查 checkout、Chromium、ffmpeg 和持久目录。</p>
        </div>
        <ExternalLink size={16} /></a
      >
    </div>
  </Panel>
</div>

<Modal bind:open={resetOpen} title="重新显示首次引导？" description="这只会清除当前浏览器的确认记录。">
  <p class="reset-copy">
    下次操作前需要再次确认 MediaCrawler
    的非商业学习许可证与可信网络边界。后端安全门禁、账户和任务数据不会改变。
  </p>
  <svelte:fragment slot="footer"
    ><button class="button secondary" type="button" on:click={() => (resetOpen = false)}>取消</button><button
      class="button"
      type="button"
      on:click={confirmReset}>确认重置</button
    ></svelte:fragment
  >
</Modal>

<style>
  .settings-grid {
    display: grid;
    grid-template-columns: minmax(0, 1.1fr) minmax(320px, 0.9fr);
    gap: 18px;
  }

  .settings-skeleton {
    display: grid;
    gap: 10px;
  }

  .settings-skeleton div {
    height: 34px;
  }

  .preference-row {
    display: grid;
    grid-template-columns: auto 1fr auto;
    align-items: center;
    gap: 11px;
  }

  .preference-icon,
  .maintenance-icon {
    display: inline-flex;
    width: 36px;
    height: 36px;
    align-items: center;
    justify-content: center;
    border: 1px solid var(--border);
    border-radius: 8px;
    background: #f8fafc;
    color: #536984;
  }

  .preference-row strong,
  .preference-row p,
  .maintenance-list strong,
  .maintenance-list p {
    display: block;
    margin: 0;
  }

  .preference-row strong,
  .maintenance-list strong {
    color: #344158;
    font-size: 12px;
    font-weight: 610;
  }

  .preference-row p,
  .maintenance-list p {
    margin-top: 2px;
    color: var(--text-muted);
    font-size: 10.5px;
  }

  .maintenance-list {
    display: grid;
  }

  .maintenance-list a {
    display: grid;
    grid-template-columns: auto 1fr auto;
    align-items: center;
    gap: 12px;
    padding: 11px 7px;
    border-bottom: 1px solid #edf0f4;
    color: #728096;
  }

  .maintenance-list a:last-child {
    border-bottom: 0;
  }

  .maintenance-list a:hover {
    background: #fafbfd;
  }

  .reset-copy {
    margin: 0;
    color: var(--text-secondary);
    font-size: 12px;
    line-height: 1.7;
  }

  @media (max-width: 1050px) {
    .settings-grid {
      grid-template-columns: 1fr;
    }
  }
</style>
