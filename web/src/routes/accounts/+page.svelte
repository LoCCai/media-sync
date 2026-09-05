<script lang="ts">
  import { onDestroy, onMount } from 'svelte';
  import { LoaderCircle, Plus, QrCode, RefreshCw, ShieldAlert, XCircle } from '@lucide/svelte';

  import { api, apiBlob, apiMessage } from '$lib/api/client';
  import { AccountPreflightReader } from '$lib/api/account-preflight';
  import { initialLoginAttemptView, LoginAttemptMonitor } from '$lib/api/login-attempt';
  import { cookieLoginEligibility } from '$lib/api/cookie-login';
  import CookieLoginDialog from '$lib/components/CookieLoginDialog.svelte';
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
    accountLoginExplanation,
    LOGIN_READINESS_NOTICE,
    LOGIN_STATUS_UNAVAILABLE,
    safeLoginDiagnostic
  } from '$lib/utils/login-diagnostics';
  import {
    accountCompositeState,
    AUTHENTICATED_ACCOUNT_NOTICE,
    canStartQrLogin,
    capabilityByPlatform,
    loginPreflightDisposition,
    loginMethodLabel
  } from '$lib/utils/workbench';

  let accounts: Account[] = [];
  let capabilities: PlatformCapability[] = [];
  let capabilityVersion: number | null = null;
  let statuses: Record<string, LoginStatus> = {};
  let statusErrors: Record<string, string> = {};
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
  let cookieOpen = false;
  let cookieAccount: Account | null = null;
  let cookieCapability: PlatformCapability | null = null;
  let formPlatform: Platform = 'bili';
  let formName = '';
  let qrAccount: Account | null = null;
  let qrOperationId = '';
  let qrView = initialLoginAttemptView();
  let qrMonitor: LoginAttemptMonitor | null = null;
  let pollTimer: number | null = null;
  let destroyed = false;
  let loadRevision = 0;
  const preflightReader = new AccountPreflightReader((id, signal) =>
    api<LoginPreflight>(
      `/api/v1/accounts/${id}/login-preflight?accept_mediacrawler_license=true`,
      { signal },
      65_000
    )
  );

  $: selectedAccount = accounts.find((item) => item.id === selectedAccountId) ?? null;
  $: selectedCapability = capabilityByPlatform(capabilities, selectedAccount?.platform);
  $: selectedPreflight = selectedAccount ? (preflights[selectedAccount.id] ?? null) : null;
  $: selectedLoginStatus = selectedAccount ? (statuses[selectedAccount.id] ?? null) : null;
  $: selectedLoginExplanation =
    selectedAccount && selectedAccount.login_method !== 'cookie'
      ? accountLoginExplanation(selectedLoginStatus, selectedAccount.id)
      : null;
  $: selectedLoginDiagnostic =
    selectedAccount && selectedLoginStatus
      ? safeLoginDiagnostic(selectedLoginStatus, selectedAccount.id)
      : null;
  $: selectedComposite = selectedAccount
    ? accountCompositeState(selectedAccount, selectedLoginStatus, selectedCapability, selectedPreflight)
    : null;
  $: selectedPreflightDisposition = loginPreflightDisposition(selectedAccount, selectedLoginStatus);
  $: selectedCanStart =
    !loading && canStartQrLogin(selectedAccount, selectedCapability, selectedPreflight, selectedLoginStatus);
  $: formCapability = capabilityByPlatform(capabilities, formPlatform);
  $: if (cookieOpen && cookieAccount?.id !== selectedAccountId) cookieOpen = false;

  async function load(): Promise<void> {
    const revision = ++loadRevision;
    preflightReader.invalidate();
    preflights = {};
    preflightErrors = {};
    preflightLoading = '';
    preflightBlock = '';
    loading = true;
    error = '';
    capabilityError = '';
    const [accountResult, capabilityResult] = await Promise.allSettled([
      api<Account[]>('/api/v1/accounts'),
      api<PlatformCapabilities>('/api/v1/platform-capabilities')
    ]);
    if (destroyed || revision !== loadRevision) return;

    if (accountResult.status === 'rejected') {
      error = apiMessage(accountResult.reason);
      loading = false;
      return;
    }
    const loadedAccounts = accountResult.value;
    accounts = loadedAccounts;

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
      loadedAccounts.map((account) => api<LoginStatus>(`/api/v1/accounts/${account.id}/login-status`))
    );
    if (destroyed || revision !== loadRevision) return;
    const nextStatuses: Record<string, LoginStatus> = {};
    const nextErrors: Record<string, string> = {};
    results.forEach((result, index) => {
      const id = loadedAccounts[index].id;
      if (result.status === 'fulfilled' && result.value.account_id === id) nextStatuses[id] = result.value;
      else nextErrors[id] = LOGIN_STATUS_UNAVAILABLE;
    });
    statuses = nextStatuses;
    statusErrors = nextErrors;

    if (!selectedAccountId || !accounts.some((item) => item.id === selectedAccountId)) {
      selectedAccountId = accounts[0]?.id ?? '';
    }
    loading = false;
    if (selectedAccountId) void loadPreflight(selectedAccountId);
  }

  async function loadPreflight(accountId: string): Promise<LoginPreflight | null> {
    if (destroyed || loading || selectedAccountId !== accountId) return null;
    const account = accounts.find((item) => item.id === accountId) ?? null;
    const status = statuses[accountId] ?? null;
    if (loginPreflightDisposition(account, status) !== 'required') {
      preflightReader.invalidate();
      preflightLoading = '';
      return null;
    }
    preflightLoading = accountId;
    preflightErrors = { ...preflightErrors, [accountId]: '' };
    const result = await preflightReader.read(account, status);
    if (destroyed || result.kind === 'superseded') return null;
    if (preflightLoading === accountId) preflightLoading = '';
    if (result.kind === 'fulfilled') {
      preflights = { ...preflights, [accountId]: result.report };
      return result.report;
    }
    const next = { ...preflights };
    delete next[accountId];
    preflights = next;
    if (result.kind === 'failed') preflightErrors = { ...preflightErrors, [accountId]: result.message };
    return null;
  }

  function selectForPreflight(account: Account): void {
    cookieOpen = false;
    preflightReader.invalidate();
    preflightLoading = '';
    selectedAccountId = account.id;
    preflightBlock = '';
    void loadPreflight(account.id);
  }

  function openCookie(account: Account): void {
    const capability = capabilityByPlatform(capabilities, account.platform);
    if (destroyed || loading || cookieLoginEligibility(account, capability)) return;
    selectedAccountId = account.id;
    cookieAccount = { ...account };
    cookieCapability = capability;
    cookieOpen = true;
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
    if (destroyed || loading || loginStarting) return;
    const currentAccount = accounts.find((item) => item.id === account.id) ?? null;
    if (loginPreflightDisposition(currentAccount, statuses[account.id] ?? null) !== 'required') return;
    const revision = loadRevision;
    selectedAccountId = account.id;
    loginStarting = account.id;
    preflightBlock = '';
    try {
      const preflight = await loadPreflight(account.id);
      if (destroyed || loading || revision !== loadRevision || selectedAccountId !== account.id) return;
      const currentAccount = accounts.find((item) => item.id === account.id) ?? null;
      const currentStatus = statuses[account.id] ?? null;
      if (loginPreflightDisposition(currentAccount, currentStatus) !== 'required') return;
      const capability = capabilityByPlatform(capabilities, account.platform);
      if (!canStartQrLogin(currentAccount, capability, preflight, currentStatus)) {
        preflightBlock = preflight?.code ?? preflightErrors[account.id] ?? 'login_preflight_unavailable';
        toast(`登录已在预检阶段停止：${preflightBlock}`, 'danger');
        return;
      }
      const started = await api<StartedOperation>(`/api/v1/accounts/${account.id}/login`, {
        method: 'POST',
        body: JSON.stringify({ timeout_seconds: 180, ...mediaCrawlerGate() })
      });
      if (destroyed) return;
      qrAccount = account;
      qrOperationId = started.operation_id;
      qrView = initialLoginAttemptView();
      qrOpen = true;
      startPolling(account, started.operation_id);
    } catch (caught) {
      toast(apiMessage(caught), 'danger');
    } finally {
      loginStarting = '';
    }
  }

  function startPolling(account: Account, operationId: string): void {
    stopPolling();
    const monitor = new LoginAttemptMonitor(account.id, operationId, {
      readOperation: (id, signal) => api<Operation>(`/api/v1/operations/${id}`, { signal }),
      readQr: (sessionId, signal) =>
        apiBlob(`/api/v1/login-sessions/${sessionId}/qr.png?t=${Date.now()}`, { signal }),
      changed: (view) => {
        if (!destroyed && qrOpen && qrMonitor === monitor) qrView = view;
      },
      terminal: (view) => {
        if (destroyed || !qrOpen || qrMonitor !== monitor) return;
        if (pollTimer !== null) window.clearInterval(pollTimer);
        pollTimer = null;
        toast(
          view.explanation?.title ?? '登录操作已结束。',
          view.explanation?.tone === 'success'
            ? 'success'
            : view.explanation?.tone === 'info'
              ? 'info'
              : 'danger'
        );
        void load();
      }
    });
    qrMonitor = monitor;
    void monitor.poll();
    pollTimer = window.setInterval(() => void monitor.poll(), 1_200);
  }

  function stopPolling(): void {
    if (pollTimer !== null) window.clearInterval(pollTimer);
    pollTimer = null;
    qrMonitor?.dispose();
    qrMonitor = null;
  }

  function closeQr(): void {
    qrOpen = false;
    stopPolling();
    qrView = initialLoginAttemptView();
    qrAccount = null;
    qrOperationId = '';
  }

  onMount(() => void load());
  onDestroy(() => {
    destroyed = true;
    preflightReader.invalidate();
    closeQr();
  });
</script>

<div class="page">
  <PageHeader title="平台账户" description="按服务端能力契约管理七个平台的认证、登录组合与隔离会话。">
    <svelte:fragment slot="actions">
      <button class="button secondary" type="button" on:click={load} disabled={loading}>
        <RefreshCw class={loading ? 'spin' : ''} size={15} />刷新本地状态
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

  {#if preflightBlock && selectedPreflightDisposition === 'required'}
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
      title="账户登录工作台"
      description={`能力契约 v${capabilityVersion ?? '—'} · ${selectedAccount.display_name}`}
    >
      <svelte:fragment slot="actions">
        <button
          class="button secondary small"
          type="button"
          on:click={() => openCookie(selectedAccount)}
          disabled={loading ||
            !!loginStarting ||
            !!cookieLoginEligibility(selectedAccount, selectedCapability)}
          title={cookieLoginEligibility(selectedAccount, selectedCapability) ||
            '明确粘贴后校验并保存，支持替换当前认证'}>粘贴 Cookie</button
        >
        {#if selectedPreflightDisposition !== 'required'}
          <button class="button secondary small" type="button" on:click={load} disabled={loading}>
            <RefreshCw class={loading ? 'spin' : ''} size={14} />刷新本地状态
          </button>
          {#if selectedPreflightDisposition === 'not_needed'}
            <a class="button small" href="/subscriptions">管理订阅</a>
          {/if}
        {:else}
          <button
            class="button secondary small"
            type="button"
            on:click={() => loadPreflight(selectedAccount.id)}
            disabled={loading || preflightLoading === selectedAccount.id || !!loginStarting}
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
            启动扫码登录
          </button>
        {/if}
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
                <dt>粘贴 Cookie 校验</dt>
                <dd>{selectedCapability.pasted_cookie_login === true ? '可用' : '尚未接入'}</dd>
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
          {#if selectedPreflightDisposition === 'not_needed'}
            <div class="preflight-heading"><div><strong>无需启动登录预检</strong></div></div>
            <p class="capability-note">{AUTHENTICATED_ACCOUNT_NOTICE}</p>
          {:else if selectedPreflightDisposition === 'status_unavailable'}
            <div class="preflight-heading"><div><strong>本地登录状态待确认</strong></div></div>
            <p class="capability-note">{LOGIN_STATUS_UNAVAILABLE}</p>
          {:else}
            <div class="preflight-heading">
              <div>
                <strong>登录专用预检</strong>
                <span>仅检查数据库、许可证、运行时、浏览器、profile 与账户锁。</span>
                <span>{LOGIN_READINESS_NOTICE}</span>
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
                  {selectedPreflight.code}{selectedPreflight.retryable
                    ? ' · 可修复后重试'
                    : ' · 需要人工处理'}
                </p>
              {/if}
            {:else}
              <div class="preflight-loading">选择账户并运行预检后才会开放登录按钮。</div>
            {/if}
          {/if}
        </section>
      </div>
      {#if selectedAccount.login_method === 'cookie'}
        <div class="notice login-result-notice" role="status">
          <strong>当前认证方式：Cookie · {statusLabel(selectedAccount.auth_status)}</strong>
          <span
            >以账户当前认证记录为准；最近扫码会话仅为历史，不覆盖本次 Cookie 认证。保存成功不代表内容已采集。</span
          >
          {#if selectedAccount.platform === 'bili'}<span
              >B 站 Cookie 作者资料查询已接入，请到订阅页面单独查询；不代表真实平台端到端验收完成。</span
            >{/if}
        </div>
      {:else if statusErrors[selectedAccount.id]}
        <div class="notice warning login-result-notice" role="status">{LOGIN_STATUS_UNAVAILABLE}</div>
      {:else if selectedLoginExplanation}
        <section
          class="notice login-result-notice"
          class:danger={selectedLoginExplanation.tone === 'danger'}
          class:warning={selectedLoginExplanation.tone === 'warning'}
          class:success={selectedLoginExplanation.tone === 'success'}
          aria-live="polite"
        >
          <strong>最近登录结果 · {selectedLoginExplanation.title}</strong>
          <span>{selectedLoginExplanation.detail}</span>
          <span>下一步：{selectedLoginExplanation.next}</span>
          <span
            ><a class="text-link" href="/jobs">查看任务记录</a> ·
            <a class="text-link" href="/diagnostics">检查运行环境</a>
            {#if selectedLoginDiagnostic}
              · 操作 <code>{shortId(selectedLoginDiagnostic.operation_id)}</code>{/if}
          </span>
        </section>
      {/if}
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
              {@const loginExplanation =
                account.login_method === 'cookie' ? null : accountLoginExplanation(login ?? null, account.id)}
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
                  <span class="cell-sub"
                    >认证：{statusLabel(
                      account.login_method === 'cookie'
                        ? account.auth_status
                        : (login?.auth_status ?? account.auth_status)
                    )}</span
                  >
                </td>
                <td>
                  <span class="cell-main">{statusLabel(login?.login_session_status)}</span>
                  {#if account.login_method === 'cookie'}<span class="cell-sub"
                      >历史扫码会话，不是当前 Cookie 结果</span
                    >{/if}
                  <span class="cell-sub mono">{shortId(login?.login_session_id)}</span>
                  {#if statusErrors[account.id]}<span class="cell-sub">最近结果读取失败，请刷新确认</span>
                  {:else if loginExplanation}<span class="cell-sub">{loginExplanation.title}</span>{/if}
                </td>
                <td>
                  <span class="cell-main">{capability?.qr_login ? 'QR 可用' : 'QR 未开放'}</span>
                  <span class="cell-sub"
                    >{capability?.pasted_cookie_login === true
                      ? 'Cookie 校验可用'
                      : 'Cookie 校验未接入'}</span
                  >
                  <span class="cell-sub">{capability?.offline_shapes.length ?? 0} 种离线形状</span>
                </td>
                <td>{formatDate(login?.auth_updated_at ?? login?.updated_at ?? account.created_at)}</td>
                <td class="action-cell">
                  <button
                    class="button secondary small"
                    type="button"
                    on:click={() => openCookie(account)}
                    disabled={loading || !!loginStarting || !!cookieLoginEligibility(account, capability)}
                    title={cookieLoginEligibility(account, capability) || '校验并保存 Cookie'}
                    >粘贴 Cookie</button
                  >
                  <button
                    class="button secondary small"
                    type="button"
                    on:click={() => selectForPreflight(account)}
                    disabled={loading || preflightLoading === account.id || !!loginStarting}
                  >
                    {#if preflightLoading === account.id}<LoaderCircle
                        class="spin"
                        size={14}
                      />{:else}<ShieldAlert size={14} />{/if}
                    {loginPreflightDisposition(account, login ?? null) === 'not_needed'
                      ? '查看状态'
                      : account.id === selectedAccountId
                        ? '重新检查'
                        : '登录准备'}
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

{#if cookieOpen && cookieAccount}
  <CookieLoginDialog
    bind:open={cookieOpen}
    account={cookieAccount}
    capability={cookieCapability}
    on:saved={() => void load()}
  />
{/if}

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
          可用方式：{formCapability.login_methods
            .map(loginMethodLabel)
            .join('、')}。添加仅建立账户，不会自动扫码。
          {formCapability.pasted_cookie_login === true
            ? '添加后可明确选择粘贴 Cookie 校验并保存。'
            : '此平台暂未接入粘贴 Cookie 校验。'}
          已保存的 Cookie、会话内容与 profile 路径不会回显。
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
  description={qrView.sessionId ? `会话 ${shortId(qrView.sessionId)}` : `操作 ${shortId(qrOperationId)}`}
  dismissible={false}
>
  <div
    class="qr-stage"
    class:success={qrView.terminal && qrView.explanation?.tone === 'success'}
    class:failed={qrView.terminal && qrView.explanation?.tone === 'danger'}
  >
    {#if qrView.terminal}
      <div
        class="qr-result"
        class:success={qrView.explanation?.tone === 'success'}
        class:failed={qrView.explanation?.tone === 'danger'}
      >
        {#if qrView.explanation?.tone === 'success'}<QrCode size={30} />{:else}<XCircle size={30} />{/if}
        <strong>{qrView.explanation?.title ?? '登录操作已结束'}</strong>
      </div>
    {:else if qrView.imageUrl}
      <img src={qrView.imageUrl} alt="平台登录二维码" />
    {:else}
      <LoaderCircle class="spin" size={31} />
    {/if}
  </div>
  <p class="qr-hint" aria-live="polite">{qrView.hint}</p>
  {#if qrView.explanation}<p class="qr-hint">下一步：{qrView.explanation.next}</p>{/if}
  {#if qrView.sessionId}
    <p class="session-bound">本次操作关联会话 <span class="mono">{shortId(qrView.sessionId)}</span></p>
  {/if}
  <svelte:fragment slot="footer">
    <button class="button secondary" type="button" on:click={closeQr}>
      {qrView.terminal ? '关闭' : '后台继续并关闭'}
    </button>
  </svelte:fragment>
</Modal>

<style>
  .workbench-grid {
    display: grid;
    grid-template-columns: minmax(250px, 0.72fr) minmax(360px, 1.28fr);
    gap: 14px;
  }

  .login-result-notice {
    display: grid;
    gap: 5px;
    margin-top: 14px;
    font-size: 12px;
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
