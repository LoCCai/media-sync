<script lang="ts">
  import { onDestroy, onMount } from 'svelte';
  import { LoaderCircle, Plus, QrCode, RefreshCw, ShieldAlert, XCircle } from '@lucide/svelte';

  import { api, apiMessage } from '$lib/api/client';
  import EmptyState from '$lib/components/EmptyState.svelte';
  import Modal from '$lib/components/Modal.svelte';
  import PageHeader from '$lib/components/PageHeader.svelte';
  import Panel from '$lib/components/Panel.svelte';
  import PlatformMark from '$lib/components/PlatformMark.svelte';
  import StatusBadge from '$lib/components/StatusBadge.svelte';
  import { mediaCrawlerGate } from '$lib/stores/onboarding';
  import { toast } from '$lib/stores/toast';
  import type {
    Account,
    DeepReadiness,
    LoginStatus,
    Operation,
    Platform,
    StartedOperation
  } from '$lib/types/api';
  import { formatDate, PLATFORM_META, shortId, statusLabel } from '$lib/utils/format';

  let accounts: Account[] = [];
  let statuses: Record<string, LoginStatus> = {};
  let loading = true;
  let adding = false;
  let loginStarting = false;
  let error = '';
  let preflightBlock = '';
  let addOpen = false;
  let qrOpen = false;
  let formPlatform: Platform = 'bili';
  let formName = '';
  let qrAccount: Account | null = null;
  let qrOperationId = '';
  let qrImageUrl = '';
  let qrHint = '正在启动登录环境…';
  let qrState = 'running';
  let pollTimer: number | null = null;

  const platforms = Object.entries(PLATFORM_META) as Array<[Platform, { name: string; short: string }]>;

  async function load(): Promise<void> {
    loading = true;
    error = '';
    try {
      accounts = await api<Account[]>('/api/v1/accounts');
      const results = await Promise.allSettled(
        accounts.map((account) => api<LoginStatus>(`/api/v1/accounts/${account.id}/login-status`))
      );
      const next: Record<string, LoginStatus> = {};
      results.forEach((result, index) => {
        if (result.status === 'fulfilled') next[accounts[index].id] = result.value;
      });
      statuses = next;
    } catch (caught) {
      error = apiMessage(caught);
    } finally {
      loading = false;
    }
  }

  async function addAccount(): Promise<void> {
    const displayName = formName.trim();
    if (!displayName) {
      toast('请输入账户显示名。', 'danger');
      return;
    }
    adding = true;
    try {
      const created = await api<Account>('/api/v1/accounts', {
        method: 'POST',
        body: JSON.stringify({ platform: formPlatform, display_name: displayName, login_method: 'qr' })
      });
      toast(created.created ? '账户已添加。' : '账户已存在，已载入现有配置。');
      addOpen = false;
      formName = '';
      await load();
    } catch (caught) {
      toast(apiMessage(caught), 'danger');
    } finally {
      adding = false;
    }
  }

  async function startLogin(account: Account): Promise<void> {
    loginStarting = true;
    preflightBlock = '';
    try {
      const readiness = await api<DeepReadiness>(
        '/api/v1/readiness/deep?accept_mediacrawler_license=true&refresh=true',
        {},
        65_000
      );
      if (!readiness.ok) {
        preflightBlock = readiness.mediacrawler.detail_code ?? readiness.code;
        toast(`登录已在预检阶段停止：${preflightBlock}`, 'danger');
        return;
      }
      const started = await api<StartedOperation>(`/api/v1/accounts/${account.id}/login`, {
        method: 'POST',
        body: JSON.stringify({ timeout_seconds: 180, ...mediaCrawlerGate() })
      });
      qrAccount = account;
      qrOperationId = started.operation_id;
      qrState = 'running';
      qrHint = '登录进程正在生成二维码…';
      qrOpen = true;
      startPolling();
    } catch (caught) {
      toast(apiMessage(caught), 'danger');
    } finally {
      loginStarting = false;
    }
  }

  function startPolling(): void {
    stopPolling();
    void pollLogin();
    pollTimer = window.setInterval(() => void pollLogin(), 1_200);
  }

  async function pollLogin(): Promise<void> {
    if (!qrAccount || !qrOperationId) return;
    try {
      const qrResponse = await fetch(`/api/v1/accounts/${qrAccount.id}/login-qr.png?t=${Date.now()}`, {
        cache: 'no-store'
      });
      if (qrResponse.ok) {
        const blob = await qrResponse.blob();
        if (qrImageUrl) URL.revokeObjectURL(qrImageUrl);
        qrImageUrl = URL.createObjectURL(blob);
        qrHint = '请使用对应平台 App 扫码确认';
      } else if (qrResponse.status === 202) {
        qrHint = '登录环境已启动，正在等待二维码…';
      } else if (qrResponse.status === 410) {
        qrHint = '二维码已失效，正在确认最终状态…';
      }

      const operation = await api<Operation>(`/api/v1/operations/${qrOperationId}`);
      qrState = operation.state;
      if (operation.state === 'succeeded') {
        qrHint = '登录成功，账户状态已更新。';
        stopPolling();
        toast(`${qrAccount.display_name} 登录成功。`);
        await load();
      } else if (operation.state === 'failed') {
        qrHint = `登录失败：${operation.error_code ?? 'unknown'}`;
        stopPolling();
        toast(qrHint, 'danger');
        await load();
      }
    } catch {
      qrHint = '暂时无法读取登录状态，将自动重试…';
    }
  }

  function stopPolling(): void {
    if (pollTimer !== null) window.clearInterval(pollTimer);
    pollTimer = null;
  }

  function closeQr(): void {
    qrOpen = false;
    stopPolling();
    if (qrImageUrl) URL.revokeObjectURL(qrImageUrl);
    qrImageUrl = '';
    qrAccount = null;
    qrOperationId = '';
  }

  onMount(() => void load());
  onDestroy(closeQr);
</script>

<div class="page">
  <PageHeader title="平台账户" description="管理七个平台的登录状态与隔离会话。">
    <svelte:fragment slot="actions">
      <button class="button secondary" type="button" on:click={load} disabled={loading}>
        <RefreshCw class={loading ? 'spin' : ''} size={15} />刷新
      </button>
      <button class="button" type="button" on:click={() => (addOpen = true)}
        ><Plus size={16} />添加账户</button
      >
    </svelte:fragment>
  </PageHeader>

  {#if preflightBlock}
    <div class="notice danger">
      <ShieldAlert size={17} />
      <div>
        <strong class="notice-title">登录未启动：{preflightBlock}</strong>
        预检已快速返回，不会卡住。请先在<a class="text-link" href="/diagnostics">诊断页面</a>处理失败项。
      </div>
    </div>
  {/if}

  <Panel title="账户列表" description={`${accounts.length} 个账户 · 浏览器 profile 按账户隔离`} flush>
    {#if error}
      <div class="notice danger" style="margin:16px"><XCircle size={17} />{error}</div>
    {:else if loading}
      <div class="account-skeletons">
        {#each Array(3) as _}<div class="skeleton"></div>{/each}
      </div>
    {:else if accounts.length === 0}
      <EmptyState title="还没有平台账户" description="先添加一个哔哩哔哩或小红书账户，再扫码建立登录会话。">
        <button class="button small" type="button" on:click={() => (addOpen = true)}
          ><Plus size={14} />添加账户</button
        >
      </EmptyState>
    {:else}
      <div class="table-wrap">
        <table class="data-table account-table">
          <thead
            ><tr
              ><th>账户</th><th>认证状态</th><th>最近会话</th><th>更新时间</th><th class="action-cell"
                >操作</th
              ></tr
            ></thead
          >
          <tbody>
            {#each accounts as account}
              {@const login = statuses[account.id]}
              <tr>
                <td>
                  <div class="inline-identity">
                    <PlatformMark platform={account.platform} />
                    <div>
                      <span class="cell-main">{account.display_name}</span>
                      <span class="cell-sub"
                        >{PLATFORM_META[account.platform].name} · {account.login_method?.toUpperCase()}</span
                      >
                    </div>
                  </div>
                </td>
                <td><StatusBadge status={login?.auth_status ?? account.auth_status} /></td>
                <td>
                  <span class="cell-main">{statusLabel(login?.login_session_status)}</span>
                  <span class="cell-sub mono">{shortId(login?.login_session_id)}</span>
                </td>
                <td>{formatDate(login?.auth_updated_at ?? login?.updated_at ?? account.created_at)}</td>
                <td class="action-cell">
                  <button
                    class="button secondary small"
                    type="button"
                    on:click={() => startLogin(account)}
                    disabled={loginStarting}
                  >
                    {#if loginStarting}<LoaderCircle class="spin" size={14} />{:else}<QrCode size={14} />{/if}
                    {login?.auth_status === 'authenticated' ? '重新认证' : '扫码登录'}
                  </button>
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    {/if}
  </Panel>
</div>

<Modal bind:open={addOpen} title="添加平台账户" description="账户创建后可立即扫码登录。">
  <div class="form-grid">
    <div class="field wide">
      <label for="account-platform">平台</label>
      <select id="account-platform" class="select" bind:value={formPlatform}>
        {#each platforms as [value, meta]}<option {value}>{meta.name} · {value}</option>{/each}
      </select>
    </div>
    <div class="field wide">
      <label for="account-name">显示名</label>
      <input
        id="account-name"
        class="input"
        bind:value={formName}
        placeholder="例如：我的 B 站账户"
        maxlength="200"
      />
    </div>
  </div>
  <div class="notice" style="margin-top:16px">
    <QrCode size={17} />当前控制台优先使用扫码登录，Cookie 与 profile 内容不会显示在网页中。
  </div>
  <svelte:fragment slot="footer">
    <button class="button secondary" type="button" on:click={() => (addOpen = false)}>取消</button>
    <button class="button" type="button" on:click={addAccount} disabled={adding}
      >{adding ? '添加中…' : '添加账户'}</button
    >
  </svelte:fragment>
</Modal>

<Modal
  bind:open={qrOpen}
  title={`扫码登录${qrAccount ? ` · ${qrAccount.display_name}` : ''}`}
  description={`操作 ${shortId(qrOperationId)}`}
  dismissible={false}
>
  <div class="qr-stage" class:success={qrState === 'succeeded'} class:failed={qrState === 'failed'}>
    {#if qrImageUrl && qrState === 'running'}
      <img src={qrImageUrl} alt="平台登录二维码" />
    {:else if qrState === 'succeeded'}
      <div class="qr-result success"><QrCode size={30} /><strong>认证完成</strong></div>
    {:else if qrState === 'failed'}
      <div class="qr-result failed"><XCircle size={30} /><strong>认证失败</strong></div>
    {:else}
      <LoaderCircle class="spin" size={31} />
    {/if}
  </div>
  <p class="qr-hint">{qrHint}</p>
  <svelte:fragment slot="footer">
    <button class="button secondary" type="button" on:click={closeQr}
      >{qrState === 'running' ? '后台继续并关闭' : '关闭'}</button
    >
  </svelte:fragment>
</Modal>

<style>
  .account-skeletons {
    display: grid;
    gap: 1px;
    padding: 12px 14px;
  }

  .account-skeletons div {
    height: 50px;
  }

  .action-cell {
    width: 124px;
    text-align: right !important;
  }

  .qr-stage {
    display: flex;
    min-height: 270px;
    align-items: center;
    justify-content: center;
    border: 1px solid var(--border);
    border-radius: 11px;
    background: #fafbfd;
    color: #64748b;
  }

  .qr-stage img {
    width: min(248px, 78vw);
    height: auto;
    border: 10px solid #fff;
    border-radius: 8px;
    image-rendering: pixelated;
    box-shadow: 0 4px 18px rgba(15, 23, 42, 0.08);
  }

  .qr-stage.success {
    border-color: #ccebd6;
    background: #f0fdf4;
  }

  .qr-stage.failed {
    border-color: #fecdd3;
    background: #fff1f2;
  }

  .qr-result {
    display: flex;
    align-items: center;
    gap: 10px;
  }

  .qr-result.success {
    color: #15803d;
  }

  .qr-result.failed {
    color: #c2414b;
  }

  .qr-hint {
    margin: 13px 0 0;
    color: var(--text-secondary);
    font-size: 12px;
    text-align: center;
  }

  @media (max-width: 720px) {
    .account-table {
      min-width: 780px;
    }
  }
</style>
