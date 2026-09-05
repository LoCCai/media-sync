<script lang="ts">
  import { onDestroy, onMount } from 'svelte';
  import { ExternalLink, FolderCog, RefreshCw, RotateCcw, Server, ShieldCheck } from '@lucide/svelte';

  import { api, apiMessage, LatestRequestGate } from '$lib/api/client';
  import Modal from '$lib/components/Modal.svelte';
  import PageHeader from '$lib/components/PageHeader.svelte';
  import Panel from '$lib/components/Panel.svelte';
  import StatusBadge from '$lib/components/StatusBadge.svelte';
  import { onboardingAccepted, resetOnboarding } from '$lib/stores/onboarding';
  import { toast } from '$lib/stores/toast';
  import type { Qualifications, Settings } from '$lib/types/api';
  import { PLATFORM_META, shortId } from '$lib/utils/format';

  let settings: Settings | null = null;
  let qualifications: Qualifications | null = null;
  let settingsLoading = true;
  let qualificationsLoading = true;
  let settingsError = '';
  let qualificationsError = '';
  let resetOpen = false;
  const settingsRequest = new LatestRequestGate();
  const qualificationsRequest = new LatestRequestGate();

  $: loading = settingsLoading || qualificationsLoading;

  $: nonLoopback = settings
    ? !settings.api_bind.startsWith('127.0.0.1:') && !settings.api_bind.startsWith('localhost:')
    : false;

  async function loadSettings(): Promise<void> {
    settingsLoading = true;
    settingsError = '';
    const result = await settingsRequest.run((signal) => api<Settings>('/api/v1/settings', { signal }));
    if (result.status === 'superseded') return;
    if (result.status === 'fulfilled') settings = result.value;
    else settingsError = apiMessage(result.reason);
    settingsLoading = false;
  }

  async function loadQualifications(): Promise<void> {
    qualificationsLoading = true;
    qualificationsError = '';
    const result = await qualificationsRequest.run((signal) =>
      api<Qualifications>('/api/v1/qualifications', { signal })
    );
    if (result.status === 'superseded') return;
    if (result.status === 'fulfilled') qualifications = result.value;
    else qualificationsError = apiMessage(result.reason);
    qualificationsLoading = false;
  }

  async function load(): Promise<void> {
    await Promise.all([loadSettings(), loadQualifications()]);
  }

  function confirmReset(): void {
    resetOnboarding();
    resetOpen = false;
    toast('首次使用确认已重置，确认窗口已重新打开。', 'info');
  }

  onMount(() => void load());

  onDestroy(() => {
    settingsRequest.cancel();
    qualificationsRequest.cancel();
  });
</script>

<div class="page">
  <PageHeader title="设置" description="查看部署路径、安全边界与控制台本地偏好。">
    <svelte:fragment slot="actions"
      ><button class="button secondary" type="button" on:click={load} disabled={loading}
        ><RefreshCw class={loading ? 'spin' : ''} size={15} />刷新</button
      ></svelte:fragment
    >
  </PageHeader>

  {#if settingsError}<div class="notice danger">{settingsError}</div>{/if}
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
      {#if settingsLoading && !settings}
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
            <dt>本地导出目录</dt>
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

    <Panel
      title="可选媒体服务器联动"
      description="环境变量托管的只读脱敏配置；不是下载、归档或本地导出的前置条件"
    >
      <div class="notice" style="margin-bottom:14px">
        <FolderCog size={17} />
        <div>
          无需连接 API：把本地导出目录挂载给 Emby /
          Jellyfin，添加剧集库并在媒体服务器中扫描。定时扫描须由媒体服务器自行配置；本后台不会因完成导出而自动请求刷新。
        </div>
      </div>
      {#if settingsLoading && !settings}
        <div class="settings-skeleton">
          {#each Array(6) as _}<div class="skeleton"></div>{/each}
        </div>
      {:else if settings}
        <div class="preference-row">
          <span class="preference-icon"><Server size={19} /></span>
          <div>
            <strong>{settings.media_server.provider?.toUpperCase() ?? '未配置媒体服务器'}</strong>
            <p>
              {settings.media_server.origin ?? '按需配置 MEDIA_SYNC_MEDIA_SERVER_*，全部省略即可只用本地目录'}
            </p>
          </div>
          <StatusBadge
            status={settings.media_server.configured
              ? settings.media_server.operations_enabled
                ? 'enabled'
                : 'required'
              : 'not_run'}
            label={settings.media_server.configured
              ? settings.media_server.operations_enabled
                ? '操作门已开启'
                : '操作门已关闭'
              : '未配置'}
          />
        </div>
        <dl class="key-value-list server-facts">
          <div class="key-value-row">
            <dt>TLS 校验</dt>
            <dd>{settings.media_server.verify_tls ? '开启' : '关闭（需人工复核）'}</dd>
          </div>
          <div class="key-value-row">
            <dt>请求超时</dt>
            <dd>{settings.media_server.timeout_seconds} 秒</dd>
          </div>
          <div class="key-value-row">
            <dt>允许网络规则</dt>
            <dd>{settings.media_server.allowed_network_count} 条（具体范围不回显）</dd>
          </div>
          <div class="key-value-row">
            <dt>Library 身份</dt>
            <dd class="mono">{shortId(settings.media_server.library_id_digest)}</dd>
          </div>
          <div class="key-value-row">
            <dt>服务器路径映射</dt>
            <dd>{settings.media_server.library_path_configured ? '已配置，不回显路径' : '未配置'}</dd>
          </div>
          <div class="key-value-row">
            <dt>API Key</dt>
            <dd>{settings.media_server.api_key_configured ? '已配置，不回显引用或值' : '未配置'}</dd>
          </div>
        </dl>
        <div class="notice" style="margin-top:14px">
          <ShieldCheck size={17} />仅需后台探测、主动刷新或核验时再配置联动。本页不能修改
          URL、Library、网络范围或凭据；相关配置须完整填写，修改后重启才会生效。
        </div>
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

  <Panel title="资格证据" description="本地自动化事实与真人验收严格分开">
    {#if qualificationsError}<div class="notice danger qualification-error">{qualificationsError}</div>{/if}
    {#if qualificationsLoading && !qualifications}
      <div class="settings-skeleton">
        {#each Array(4) as _}<div class="skeleton"></div>{/each}
      </div>
    {:else if qualifications}
      <div class="notice qualification-policy">
        <ShieldCheck size={17} />自动测试、数据库记录和 Operation 成功不会自动变成真人 PASS；当前真人行保持
        NOT_RUN。
      </div>
      <div class="table-wrap qualification-table-wrap">
        <table class="data-table qualification-table">
          <thead>
            <tr
              ><th>平台</th><th>账户</th><th>订阅</th><th>内容</th><th>已验证资产</th><th>成功导出</th><th
                >真人状态</th
              ></tr
            >
          </thead>
          <tbody>
            {#each qualifications.platforms as row}
              <tr>
                <td>{PLATFORM_META[row.platform].name}</td>
                <td>{row.automated_evidence.account_count ?? 0}</td>
                <td>{row.automated_evidence.subscription_count ?? 0}</td>
                <td>{row.automated_evidence.content_count ?? 0}</td>
                <td>{row.automated_evidence.verified_asset_count ?? 0}</td>
                <td>{row.automated_evidence.successful_export_count ?? 0}</td>
                <td><StatusBadge status="not_run" label="真人 NOT_RUN" /></td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
      <div class="capability-grid">
        {#each qualifications.media_server.human_qualification as capability}
          <div>
            <span class="mono">{capability.capability}</span>
            <StatusBadge
              status={capability.implementation_status === 'IMPLEMENTED' ? 'not_run' : 'required'}
              label={capability.implementation_status === 'IMPLEMENTED'
                ? `真人 ${capability.human_status}`
                : 'NOT_IMPLEMENTED'}
            />
          </div>
        {/each}
      </div>
    {/if}
  </Panel>

  <Panel title="迁移与维护" description="旧版交互控制台已退役，管理操作请使用当前控制台">
    <div class="maintenance-list">
      <a href="/legacy" target="_blank" rel="noreferrer"
        ><span class="maintenance-icon"><FolderCog size={18} /></span>
        <div>
          <strong>查看旧版迁移说明</strong>
          <p>旧入口仅保留受保护的迁移提示，不再提供管理操作。</p>
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

  .server-facts {
    margin-top: 15px;
  }

  .qualification-policy {
    margin-bottom: 14px;
  }

  .qualification-table {
    min-width: 760px;
  }

  .capability-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 8px;
    margin-top: 14px;
  }

  .capability-grid > div {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    border: 1px solid var(--border);
    border-radius: 7px;
    padding: 9px 11px;
    background: #fafbfd;
    font-size: 11px;
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

  @media (max-width: 720px) {
    .capability-grid {
      grid-template-columns: 1fr;
    }
  }
</style>
