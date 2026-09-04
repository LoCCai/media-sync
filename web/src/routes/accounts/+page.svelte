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
    LoginPreflight,
    LoginStatus,
    Operation,
    Platform,
    PlatformCapabilities,
    PlatformCapability,
    StartedOperation
  } from '$lib/types/api';
  import { formatDate, PLATFORM_META, shortId, statusLabel } from '$lib/utils/format';
  import {
    accountCompositeState,
    canStartQrLogin,
    capabilityByPlatform,
    loginMethodLabel
  } from '$lib/utils/workbench';

  let accounts: Account[] = [];
  let capabilities: PlatformCapability[] = [];
  let capabilityVersion: number | null = null;
  let statuses: Record<string, LoginStatus> = {};
  let preflights: Record<string, LoginPreflight> = {};
  let preflightErrors: Record<string, string> = {};
  let loading = true;
  let adding = false;
  let loginStarting = '';
  let preflightLoading = '';
  let error = '';
  let capabilityError = '';
  let preflightBlock = '';
  let selectedAccountId = '';
  let addOpen = false;
  let qrOpen = false;
  let formPlatform: Platform = 'bili';
  let formName = '';
  let qrAccount: Account | null = null;
  let qrOperationId = '';
  let qrLoginSessionId = '';
  let qrImageUrl = '';
  let qrHint = '正在启动登录环境…';
  let qrState = 'running';
  let pollTimer: number | null = null;
  let pollBusy = false;

  $: selectedAccount = accounts.find((item) => item.id === selectedAccountId) ?? null;
  $: selectedCapability = capabilityByPlatform(capabilities, selectedAccount?.platform);
  $: selectedPreflight = selectedAccount ? (preflights[selectedAccount.id] ?? null) : null;
  $: selectedLoginStatus = selectedAccount ? (statuses[selectedAccount.id] ?? null) : null;
  $: selectedComposite = selectedAccount
    ? accountCompositeState(selectedAccount, selectedLoginStatus, selectedCapability, selectedPreflight)
    : null;
  $: selectedCanStart = canStartQrLogin(selectedAccount, selectedCapability, selectedPreflight);
  $: formCapability = capabilityByPlatform(capabilities, formPlatform);

  async function load(): Promise<void> {
    loading = true;
    error = '';
    capabilityError = '';
    const [accountResult, capabilityResult] = await Promise.allSettled([
      api<Account[]>('/api/v1/accounts'),
      api<PlatformCapabilities>('/api/v1/platform-capabilities')
    ]);

    if (accountResult.status === 'rejected') {
      error = apiMessage(accountResult.reason);
      loading = false;
      return;
    }
    accounts = accountResult.value;

    if (capabilityResult.status === 'fulfilled') {
      capabilities = capabilityResult.value.platforms;
      capabilityVersion = capabilityResult.value.version;
      if (!capabilityByPlatform(capabilities, formPlatform) && capabilities.length) {
        formPlatform = capabilities[0].platform;
      }
    } else {
      capabilities = [];
      capabilityVersion = null;
      capabilityError = apiMessage(capabilityResult.reason);
    }

    const results = await Promise.allSettled(
      accounts.map((account) => api<LoginStatus>(`/api/v1/accounts/${account.id}/login-status`))
    );
    const nextStatuses: Record<string, LoginStatus> = {};
    results.forEach((result, index) => {
      if (result.status === 'fulfilled') nextStatuses[accounts[index].id] = result.value;
    });
    statuses = nextStatuses;

    if (!selectedAccountId || !accounts.some((item) => item.id === selectedAccountId)) {
      selectedAccountId = accounts[0]?.id ?? '';
    }
    loading = false;
    if (selectedAccountId) void loadPreflight(selectedAccountId);
  }

  async function loadPreflight(accountId: string): Promise<LoginPreflight | null> {
    preflightLoading = accountId;
    preflightErrors = { ...preflightErrors, [accountId]: '' };
    try {
      const result = await api<LoginPreflight>(
        `/api/v1/accounts/${accountId}/login-preflight?accept_mediacrawler_license=true`,
        {},
        65_000
      );
      preflights = { ...preflights, [accountId]: result };
      return result;
    } catch (caught) {
      const next = { ...preflights };
      delete next[accountId];
      preflights = next;
      preflightErrors = { ...preflightErrors, [accountId]: apiMessage(caught) };
      return null;
    } finally {
      if (preflightLoading === accountId) preflightLoading = '';
    }
  }

  function selectForPreflight(account: Account): void {
    selectedAccountId = account.id;
    preflightBlock = '';
    void loadPreflight(account.id);
  }

  function openAdd(): void {
    addOpen = true;
    if (!formCapability && capabilities.length) formPlatform = capabilities[0].platform;
  }

  async function addAccount(): Promise<void> {
    const displayName = formName.trim();
    if (!displayName || !formCapability?.qr_login) {
      toast(!displayName ? '请输入账户显示名。' : '该平台当前未开放扫码登录。', 'danger');
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
      selectedAccountId = created.id;
      await load();
    } catch (caught) {
      toast(apiMessage(caught), 'danger');
    } finally {
      adding = false;
    }
  }

  async function startLogin(account: Account): Promise<void> {
    selectedAccountId = account.id;
    loginStarting = account.id;
    preflightBlock = '';
    try {
      const preflight = await loadPreflight(account.id);
      const capability = capabilityByPlatform(capabilities, account.platform);
      if (!canStartQrLogin(account, capability, preflight)) {
        preflightBlock = preflight?.code ?? preflightErrors[account.id] ?? 'login_preflight_unavailable';
        toast(`登录已在预检阶段停止：${preflightBlock}`, 'danger');
        return;
      }
      const started = await api<StartedOperation>(`/api/v1/accounts/${account.id}/login`, {
        method: 'POST',
        body: JSON.stringify({ timeout_seconds: 180, ...mediaCrawlerGate() })
      });
      qrAccount = account;
      qrOperationId = started.operation_id;
      qrLoginSessionId = '';
      qrState = 'running';
      qrHint = '登录进程正在生成二维码…';
      qrOpen = true;
      startPolling();
    } catch (caught) {
      toast(apiMessage(caught), 'danger');
    } finally {
      loginStarting = '';
    }
  }

  function startPolling(): void {
    stopPolling();
    void pollLogin();
    pollTimer = window.setInterval(() => void pollLogin(), 1_200);
  }

  async function pollLogin(): Promise<void> {
    if (!qrAccount || !qrOperationId || pollBusy) return;
    pollBusy = true;
    try {
      const login = await api<LoginStatus>(`/api/v1/accounts/${qrAccount.id}/login-status`);
      statuses = { ...statuses, [qrAccount.id]: login };
      if (login.login_session_id) qrLoginSessionId = login.login_session_id;

      const qrPath = qrLoginSessionId
        ? `/api/v1/login-sessions/${encodeURIComponent(qrLoginSessionId)}/qr.png`
        : `/api/v1/accounts/${qrAccount.id}/login-qr.png`;
      const [qrResponse, operation] = await Promise.all([
        fetch(`${qrPath}?t=${Date.now()}`, { cache: 'no-store' }),
        api<Operation>(`/api/v1/operations/${qrOperationId}`)
      ]);

      if (qrResponse.ok) {
        const blob = await qrResponse.blob();
        if (qrImageUrl) URL.revokeObjectURL(qrImageUrl);
        qrImageUrl = URL.createObjectURL(blob);
        qrHint = '请使用对应平台 App 扫码确认';
      } else if (qrResponse.status === 202) {
        qrHint = '登录环境已启动，正在等待二维码…';
      } else if (qrResponse.status === 410) {
        qrHint = '二维码已失效，正在确认最终状态…';
      } else if (qrResponse.status === 404) {
        qrHint = '登录会话已建立，二维码尚未可用…';
      }

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
    } finally {
      pollBusy = false;
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
    qrLoginSessionId = '';
  }

  onMount(() => void load());
  onDestroy(closeQr);
</script>

<div class="page">
  <PageHeader title="平台账户" description="按服务端能力契约管理七个平台的认证、登录组合与隔离会话。">
    <svelte:fragment slot="actions">
      <button class="button secondary" type="button" on:click={load} disabled={loading}>
        <RefreshCw class={loading ? 'spin' : ''} size={15} />刷新
      </button>
      <button class="button" type="button" on:click={openAdd} disabled={!capabilities.length}>
        <Plus size={16} />添加账户
      </button>
    </svelte:fragment>
  </PageHeader>

  {#if capabilityError}
    <div class="notice danger">
      <ShieldAlert size={17} />
      <div>
        <strong class="notice-title">平台能力契约不可用</strong
        >{capabilityError}。为避免猜测平台规则，新增账户与登录启动已停用。
      </div>
    </div>
  {/if}

  {#if preflightBlock}
    <div class="notice danger">
      <ShieldAlert size={17} />
      <div>
        <strong class="notice-title">登录未启动：{preflightBlock}</strong>
        预检已在创建 Operation 和登录会话之前停止。请按下方失败项处理，或前往<a
          class="text-link"
          href="/diagnostics">诊断页面</a
        >。
      </div>
    </div>
  {/if}

  {#if selectedAccount}
    <Panel
      title="登录启动前工作台"
      description={`能力契约 v${capabilityVersion ?? '—'} · ${selectedAccount.display_name}`}
    >
      <svelte:fragment slot="actions">
        <button
          class="button secondary small"
          type="button"
          on:click={() => loadPreflight(selectedAccount.id)}
          disabled={preflightLoading === selectedAccount.id || loginStarting === selectedAccount.id}
        >
          <RefreshCw class={preflightLoading === selectedAccount.id ? 'spin' : ''} size={14} />重新预检
        </button>
        <button
          class="button small"
          type="button"
          on:click={() => startLogin(selectedAccount)}
          disabled={!selectedCanStart || !!preflightLoading || !!loginStarting}
          title={selectedCanStart ? '重新执行预检并启动扫码登录' : '所有必需预检通过后才能启动'}
        >
          {#if loginStarting === selectedAccount.id}<LoaderCircle class="spin" size={14} />{:else}<QrCode
              size={14}
            />{/if}
          {selectedLoginStatus?.auth_status === 'authenticated' ? '重新认证' : '启动扫码登录'}
        </button>
      </svelte:fragment>

      <div class="workbench-grid">
        <section class="capability-card">
          <div class="card-heading">
            <PlatformMark platform={selectedAccount.platform} />
            <div>
              <strong
                >{selectedCapability?.display_name ?? PLATFORM_META[selectedAccount.platform].name}</strong
              >
              <span>{selectedComposite?.detail}</span>
            </div>
            {#if selectedComposite}
              <StatusBadge status={selectedComposite.status} label={selectedComposite.label} />
            {/if}
          </div>
          {#if selectedCapability}
            <dl class="mini-facts">
              <div>
                <dt>登录方式</dt>
                <dd>{selectedCapability.login_methods.map(loginMethodLabel).join(' · ')}</dd>
              </div>
              <div>
                <dt>扫码能力</dt>
                <dd>{selectedCapability.qr_login ? '可用' : '未开放'}</dd>
              </div>
              <div>
                <dt>离线形状</dt>
                <dd>{selectedCapability.offline_shapes.length} 种已验证</dd>
              </div>
              <div>
                <dt>真人验收</dt>
                <dd>{selectedCapability.live_qualification}</dd>
              </div>
            </dl>
            {#if selectedCapability.limitations.length}
              <p class="capability-note">{selectedCapability.limitations.join('；')}</p>
            {/if}
          {/if}
        </section>

        <section class="preflight-card" aria-live="polite">
          <div class="preflight-heading">
            <div>
              <strong>登录专用预检</strong>
              <span>仅检查数据库、许可证、运行时、浏览器、profile 与账户锁。</span>
            </div>
            {#if selectedPreflight}
              <StatusBadge
                status={selectedPreflight.ok ? 'succeeded' : 'failed'}
                label={selectedPreflight.ok ? '允许启动' : '已阻塞'}
              />
            {/if}
          </div>
          {#if preflightLoading === selectedAccount.id}
            <div class="preflight-loading"><LoaderCircle class="spin" size={16} />正在检查登录条件…</div>
          {:else if preflightErrors[selectedAccount.id]}
            <div class="notice danger"><XCircle size={16} />{preflightErrors[selectedAccount.id]}</div>
          {:else if selectedPreflight}
            <div class="check-grid">
              {#each selectedPreflight.checks as check}
                <div class:failed={check.status === 'fail'} class="check-row">
                  <div>
                    <strong>{check.name}</strong>
                    <span>{check.detail_code ?? (check.status === 'pass' ? '检查通过' : '尚未运行')}</span>
                  </div>
                  <StatusBadge
                    status={check.status === 'pass'
                      ? 'succeeded'
                      : check.status === 'fail'
                        ? 'failed'
                        : 'pending'}
                    label={`${check.required ? '必需' : '可选'} · ${statusLabel(check.status)}`}
                  />
                </div>
              {/each}
            </div>
            {#if !selectedPreflight.ok}
              <p class="preflight-code">
                {selectedPreflight.code}{selectedPreflight.retryable ? ' · 可修复后重试' : ' · 需要人工处理'}
              </p>
            {/if}
          {:else}
            <div class="preflight-loading">选择账户并运行预检后才会开放登录按钮。</div>
          {/if}
        </section>
      </div>
    </Panel>
  {/if}

  <Panel title="账户列表" description={`${accounts.length} 个账户 · 浏览器 profile 按账户隔离`} flush>
    {#if error}
      <div class="notice danger" style="margin:16px"><XCircle size={17} />{error}</div>
    {:else if loading}
      <div class="account-skeletons">
        {#each Array(3) as _}<div class="skeleton"></div>{/each}
      </div>
    {:else if accounts.length === 0}
      <EmptyState title="还没有平台账户" description="先从能力清单选择一个平台，再建立隔离登录会话。">
        <button class="button small" type="button" on:click={openAdd} disabled={!capabilities.length}>
          <Plus size={14} />添加账户
        </button>
      </EmptyState>
    {:else}
      <div class="table-wrap">
        <table class="data-table account-table">
          <thead>
            <tr>
              <th>账户</th><th>组合状态</th><th>最近会话</th><th>平台能力</th><th>更新时间</th><th
                class="action-cell">操作</th
              >
            </tr>
          </thead>
          <tbody>
            {#each accounts as account}
              {@const login = statuses[account.id]}
              {@const capability = capabilityByPlatform(capabilities, account.platform)}
              {@const composite = accountCompositeState(
                account,
                login ?? null,
                capability,
                preflights[account.id] ?? null
              )}
              <tr class:selected-row={account.id === selectedAccountId}>
                <td>
                  <div class="inline-identity">
                    <PlatformMark platform={account.platform} />
                    <div>
                      <span class="cell-main">{account.display_name}</span>
                      <span class="cell-sub">
                        {capability?.display_name ?? PLATFORM_META[account.platform].name} · {loginMethodLabel(
                          account.login_method
                        )}
                      </span>
                    </div>
                  </div>
                </td>
                <td>
                  <StatusBadge status={composite.status} label={composite.label} />
                  <span class="cell-sub">认证：{statusLabel(login?.auth_status ?? account.auth_status)}</span>
                </td>
                <td>
                  <span class="cell-main">{statusLabel(login?.login_session_status)}</span>
                  <span class="cell-sub mono">{shortId(login?.login_session_id)}</span>
                </td>
                <td>
                  <span class="cell-main">{capability?.qr_login ? 'QR 可用' : 'QR 未开放'}</span>
                  <span class="cell-sub">{capability?.offline_shapes.length ?? 0} 种离线形状</span>
                </td>
                <td>{formatDate(login?.auth_updated_at ?? login?.updated_at ?? account.created_at)}</td>
                <td class="action-cell">
                  <button
                    class="button secondary small"
                    type="button"
                    on:click={() => selectForPreflight(account)}
                    disabled={preflightLoading === account.id}
                  >
                    {#if preflightLoading === account.id}<LoaderCircle
                        class="spin"
                        size={14}
                      />{:else}<ShieldAlert size={14} />{/if}
                    {account.id === selectedAccountId ? '重新检查' : '登录准备'}
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

<Modal bind:open={addOpen} title="添加平台账户" description="平台与登录规则来自当前服务端能力契约。">
  {#if capabilityError || !capabilities.length}
    <div class="notice danger"><ShieldAlert size={17} />能力契约不可用，暂时不能新增账户。</div>
  {:else}
    <div class="form-grid">
      <div class="field wide">
        <label for="account-platform">平台</label>
        <select id="account-platform" class="select" bind:value={formPlatform}>
          {#each capabilities as capability}
            <option value={capability.platform}>{capability.display_name} · {capability.platform}</option>
          {/each}
        </select>
      </div>
      <div class="field wide">
        <label for="account-name">显示名</label>
        <input
          id="account-name"
          class="input"
          bind:value={formName}
          placeholder="例如：我的主账号"
          maxlength="200"
        />
      </div>
    </div>
    {#if formCapability}
      <div class:warning={!formCapability.qr_login} class="notice add-capability-note">
        <QrCode size={17} />
        <div>
          <strong class="notice-title">
            {formCapability.qr_login ? '支持隔离扫码登录' : '扫码登录尚未开放'}
          </strong>
          可用方式：{formCapability.login_methods.map(loginMethodLabel).join('、')}。Cookie、会话内容与
          profile 路径不会显示在网页中。
        </div>
      </div>
    {/if}
  {/if}
  <svelte:fragment slot="footer">
    <button class="button secondary" type="button" on:click={() => (addOpen = false)}>取消</button>
    <button class="button" type="button" on:click={addAccount} disabled={adding || !formCapability?.qr_login}>
      {adding ? '添加中…' : '添加账户'}
    </button>
  </svelte:fragment>
</Modal>

<Modal
  bind:open={qrOpen}
  title={`扫码登录${qrAccount ? ` · ${qrAccount.display_name}` : ''}`}
  description={qrLoginSessionId ? `会话 ${shortId(qrLoginSessionId)}` : `操作 ${shortId(qrOperationId)}`}
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
  {#if qrLoginSessionId}
    <p class="session-bound">二维码已绑定到会话 <span class="mono">{shortId(qrLoginSessionId)}</span></p>
  {/if}
  <svelte:fragment slot="footer">
    <button class="button secondary" type="button" on:click={closeQr}>
      {qrState === 'running' ? '后台继续并关闭' : '关闭'}
    </button>
  </svelte:fragment>
</Modal>

<style>
  .workbench-grid {
    display: grid;
    grid-template-columns: minmax(250px, 0.72fr) minmax(360px, 1.28fr);
    gap: 14px;
  }

  .capability-card,
  .preflight-card {
    min-width: 0;
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 14px;
    background: #fafbfd;
  }

  .card-heading,
  .preflight-heading {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 12px;
  }

  .card-heading > div:nth-child(2),
  .preflight-heading > div {
    min-width: 0;
    flex: 1;
  }

  .card-heading strong,
  .preflight-heading strong {
    display: block;
    color: var(--text);
    font-size: 12px;
    font-weight: 620;
  }

  .card-heading span,
  .preflight-heading span {
    display: block;
    margin-top: 2px;
    color: var(--text-muted);
    font-size: 11px;
  }

  .mini-facts {
    display: grid;
    gap: 7px;
    margin: 14px 0 0;
  }

  .mini-facts div {
    display: flex;
    justify-content: space-between;
    gap: 12px;
    border-top: 1px solid #edf0f4;
    padding-top: 7px;
  }

  .mini-facts dt,
  .mini-facts dd {
    margin: 0;
    font-size: 11px;
  }

  .mini-facts dt {
    color: var(--text-muted);
  }

  .mini-facts dd {
    color: #344158;
    text-align: right;
  }

  .capability-note,
  .preflight-code {
    margin: 12px 0 0;
    border-top: 1px solid #edf0f4;
    padding-top: 9px;
    color: var(--text-muted);
    font-size: 11px;
  }

  .preflight-loading {
    display: flex;
    min-height: 104px;
    align-items: center;
    justify-content: center;
    gap: 8px;
    color: var(--text-muted);
    font-size: 12px;
  }

  .check-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 7px;
    margin-top: 13px;
  }

  .check-row {
    display: flex;
    min-width: 0;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    border: 1px solid var(--border);
    border-radius: 7px;
    padding: 8px 9px;
    background: #fff;
  }

  .check-row.failed {
    border-color: #fecdd3;
    background: #fff8f8;
  }

  .check-row > div {
    min-width: 0;
  }

  .check-row strong,
  .check-row span {
    display: block;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .check-row strong {
    color: #344158;
    font-size: 11px;
    font-weight: 600;
  }

  .check-row span {
    margin-top: 1px;
    color: var(--text-muted);
    font-size: 10px;
  }

  .account-skeletons {
    display: grid;
    gap: 1px;
    padding: 12px 14px;
  }

  .account-skeletons div {
    height: 50px;
  }

  .selected-row td {
    background: #f8fbff !important;
  }

  .action-cell {
    width: 124px;
    text-align: right !important;
  }

  .add-capability-note {
    margin-top: 16px;
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

  .qr-hint,
  .session-bound {
    margin: 13px 0 0;
    color: var(--text-secondary);
    font-size: 12px;
    text-align: center;
  }

  .session-bound {
    margin-top: 4px;
    color: var(--text-muted);
    font-size: 11px;
  }

  @media (max-width: 900px) {
    .workbench-grid {
      grid-template-columns: 1fr;
    }

    .account-table {
      min-width: 990px;
    }
  }

  @media (max-width: 560px) {
    .check-grid {
      grid-template-columns: 1fr;
    }

    .card-heading,
    .preflight-heading {
      flex-wrap: wrap;
    }
  }
</style>
