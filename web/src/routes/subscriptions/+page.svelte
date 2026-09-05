<script lang="ts">
  import { onDestroy, onMount } from 'svelte';
  import {
    CalendarClock,
    CheckCircle2,
    Eye,
    Pause,
    Play,
    Plus,
    RefreshCw,
    RotateCw,
    ShieldAlert,
    Trash2,
    Undo2,
    UsersRound
  } from '@lucide/svelte';

  import { api } from '$lib/api/client';
  import CreatorProfileCard from '$lib/components/CreatorProfileCard.svelte';
  import EmptyState from '$lib/components/EmptyState.svelte';
  import Modal from '$lib/components/Modal.svelte';
  import PageHeader from '$lib/components/PageHeader.svelte';
  import Panel from '$lib/components/Panel.svelte';
  import PlatformMark from '$lib/components/PlatformMark.svelte';
  import StatusBadge from '$lib/components/StatusBadge.svelte';
  import { toast } from '$lib/stores/toast';
  import { mediaCrawlerGate, onboardingAccepted } from '$lib/stores/onboarding';
  import { operatorAuth } from '$lib/stores/operator-auth';
  import type {
    Account,
    PlatformCapabilities,
    PlatformCapability,
    Subscription,
    SubscriptionDetail,
    SubscriptionLifecycleResult,
    SubscriptionPreview
  } from '$lib/types/api';
  import { formatDate, formatDateLong, intervalLabel, PLATFORM_META, shortId } from '$lib/utils/format';
  import {
    biliCaptureNotice,
    biliUnitItemLimit,
    isBiliBoundedCapture,
    safeBiliScanSummaryRows
  } from '$lib/utils/bilibili-capture';
  import {
    CREATOR_LOOKUP_NOTICE,
    CreatorLookupController,
    creatorLookupButtonLabel,
    creatorLookupEligibility,
    creatorLookupIdentity,
    initialCreatorLookupView,
    subscriptionCreatorLabel,
    subscriptionCreatorProfile
  } from '$lib/utils/creator-profile';
  import {
    capabilityByPlatform,
    safeCheckpointSummaryRows,
    safePolicySummaryRows,
    subscriptionWizardGates
  } from '$lib/utils/workbench';
  import {
    isRemovedSubscription,
    isSubscriptionId,
    LOCAL_CREATOR_PREVIEW_NOTICE,
    SUBSCRIPTION_REMOVAL_NOTICE,
    SUBSCRIPTION_RESTORE_NOTICE,
    subscriptionLifecyclePath,
    subscriptionMatchesView,
    SubscriptionRequestGate,
    validSubscriptionLifecycleResult,
    type SubscriptionFailure,
    type SubscriptionLifecycleAction
  } from '$lib/utils/subscription-lifecycle';

  let subscriptions: Subscription[] = [];
  let accounts: Account[] = [];
  let capabilities: PlatformCapability[] = [];
  let loading = true;
  let saving = false;
  let previewing = false;
  let acting = '';
  let error = '';
  let capabilityError = '';
  let addOpen = false;
  let detailOpen = false;
  let detailLoading = false;
  let detail: SubscriptionDetail | null = null;
  let detailError = '';
  let detailId = '';
  let showRemoved = false;
  let actionFailure: SubscriptionFailure | null = null;
  let wizardFailure: SubscriptionFailure | null = null;
  let confirmOpen = false;
  let confirmTarget: Subscription | null = null;
  let confirmAction: SubscriptionLifecycleAction = 'delete';
  let destroyed = false;
  const listRequests = new SubscriptionRequestGate();
  const detailRequests = new SubscriptionRequestGate();
  const previewRequests = new SubscriptionRequestGate();
  const createRequests = new SubscriptionRequestGate();
  const actionRequests = new SubscriptionRequestGate();
  let wizardStep: 1 | 2 | 3 = 1;

  let accountId = '';
  let creatorId = '';
  let creatorName = '';
  let creatorReferenceRef = '';
  let intervalSeconds = 21_600;
  let maxItems = 30;
  let requestDelaySeconds = 5;
  let fullHistory = false;
  let headless = true;
  let preview: SubscriptionPreview | null = null;
  let lookupView = initialCreatorLookupView();
  const lookupController = new CreatorLookupController(
    {
      licenseConfirmed: () => $onboardingAccepted,
      start: (scope, signal) =>
        api(`/api/v1/accounts/${scope.account_id}/creator-lookups`, {
          method: 'POST',
          body: JSON.stringify({
            platform: scope.platform,
            creator_remote_id: scope.creator_remote_id,
            frontend_generation: scope.frontend_generation,
            ...mediaCrawlerGate()
          }),
          signal
        }),
      read: (operationId, signal) => api(`/api/v1/creator-lookups/${operationId}`, { signal })
    },
    (next) => {
      const changedReceipt = lookupView.receipt !== next.receipt;
      lookupView = next;
      if (changedReceipt) invalidatePreview();
    }
  );

  $: enabledCount = subscriptions.filter((item) => item.enabled).length;
  $: if (!detailOpen) detailRequests.cancel();
  $: if (!addOpen) {
    previewRequests.cancel();
    createRequests.cancel();
  }
  $: if (!confirmOpen && !acting) confirmTarget = null;
  $: selectedAccount = accounts.find((item) => item.id === accountId) ?? null;
  $: selectedCapability = capabilityByPlatform(capabilities, selectedAccount?.platform);
  $: lookupEligibility = creatorLookupEligibility(selectedAccount);
  $: lookupBusy = lookupView.phase === 'submitting' || lookupView.phase === 'waiting';
  $: lookupController.setIdentity(
    addOpen && wizardStep >= 2 && $operatorAuth.phase === 'authenticated'
      ? creatorLookupIdentity(selectedAccount, creatorId)
      : null,
    $operatorAuth.epoch
  );
  $: wizardGates = subscriptionWizardGates({
    accountId,
    capability: selectedCapability,
    creatorId,
    creatorName,
    profileLookupId: lookupView.receipt,
    preview,
    fullHistoryAcknowledged: fullHistory
  });

  function draftPayload(): Record<string, unknown> | null {
    if (!selectedAccount) return null;
    return {
      account_id: selectedAccount.id,
      platform: selectedAccount.platform,
      creator_remote_id: creatorId.trim(),
      local_alias: creatorName.trim() || null,
      profile_lookup_id: lookupView.receipt,
      creator_reference_ref: creatorReferenceRef.trim() || null,
      interval_seconds: intervalSeconds,
      max_items: maxItems,
      allow_full_history: fullHistory,
      request_delay_seconds: requestDelaySeconds,
      headless
    };
  }

  async function load(): Promise<void> {
    const requestedView = showRemoved;
    loading = true;
    error = '';
    capabilityError = '';
    const result = await listRequests.run((signal) =>
      Promise.allSettled([
        api<Subscription[]>(`/api/v1/subscriptions${requestedView ? '?deleted=true' : ''}`, { signal }),
        api<Account[]>('/api/v1/accounts', { signal }),
        api<PlatformCapabilities>('/api/v1/platform-capabilities', { signal })
      ])
    );
    if (destroyed || requestedView !== showRemoved || result.kind === 'superseded') return;
    if (result.kind === 'failed') {
      error = result.failure.message;
      loading = false;
      return;
    }
    const [subscriptionResult, accountResult, capabilityResult] = result.value;

    if (
      subscriptionResult.status === 'fulfilled' &&
      Array.isArray(subscriptionResult.value) &&
      subscriptionResult.value.every((item) => subscriptionMatchesView(item, requestedView))
    )
      subscriptions = subscriptionResult.value;
    else {
      subscriptions = [];
      error = '订阅列表暂时不可用，请刷新后核对。';
    }

    if (accountResult.status === 'fulfilled') accounts = accountResult.value;
    else error ||= '账户列表暂时不可用，请刷新后核对。';

    if (capabilityResult.status === 'fulfilled') capabilities = capabilityResult.value.platforms;
    else {
      capabilities = [];
      capabilityError = '平台能力说明暂时不可用';
    }

    if (!accountId || !accounts.some((item) => item.id === accountId)) accountId = accounts[0]?.id ?? '';
    loading = false;
  }

  function resetWizard(): void {
    lookupController.setIdentity(null);
    previewRequests.cancel();
    createRequests.cancel();
    previewing = false;
    saving = false;
    wizardFailure = null;
    wizardStep = 1;
    accountId = accounts[0]?.id ?? '';
    creatorId = '';
    creatorName = '';
    creatorReferenceRef = '';
    intervalSeconds = 21_600;
    maxItems = 30;
    requestDelaySeconds = 5;
    fullHistory = false;
    headless = true;
    preview = null;
  }

  function openWizard(): void {
    resetWizard();
    addOpen = true;
  }

  function accountChanged(): void {
    lookupController.setIdentity(null);
    invalidatePreview();
    fullHistory = false;
    creatorReferenceRef = '';
  }

  function invalidatePreview(): void {
    previewRequests.cancel();
    previewing = false;
    preview = null;
    wizardFailure = null;
  }

  function creatorInputChanged(event: Event): void {
    creatorId = (event.currentTarget as HTMLInputElement).value;
    lookupController.setIdentity(
      $operatorAuth.phase === 'authenticated' ? creatorLookupIdentity(selectedAccount, creatorId) : null,
      $operatorAuth.epoch
    );
    invalidatePreview();
  }

  function completeCreatorInput(manual = false): void {
    if (destroyed || !addOpen || wizardStep !== 2 || saving || $operatorAuth.phase !== 'authenticated')
      return;
    lookupController.setIdentity(creatorLookupIdentity(selectedAccount, creatorId), $operatorAuth.epoch);
    void lookupController.query(manual);
  }

  function creatorInputKeydown(event: KeyboardEvent): void {
    if (event.key !== 'Enter' || event.isComposing) return;
    event.preventDefault();
    completeCreatorInput();
  }

  function previewMatchesDraft(value: SubscriptionPreview, payload: Record<string, unknown>): boolean {
    return (
      !!value &&
      value.account_id === payload.account_id &&
      value.platform === payload.platform &&
      value.creator_remote_id === payload.creator_remote_id &&
      (payload.profile_lookup_id
        ? value.profile_lookup_id === payload.profile_lookup_id && value.local_alias === payload.local_alias
        : (value.local_alias ?? value.creator_display_name) === payload.local_alias)
    );
  }

  function continueToCreator(): void {
    if (!wizardGates.canContinueFromAccount) {
      toast('请选择具有服务端能力说明的平台账户。', 'danger');
      return;
    }
    wizardStep = 2;
  }

  async function requestPreview(): Promise<SubscriptionPreview | null> {
    if (lookupView.phase === 'submitting' || lookupView.phase === 'waiting') return null;
    const payload = draftPayload();
    if (!payload || !wizardGates.canRequestPreview) {
      toast(
        wizardGates.confirmationRequired && !fullHistory
          ? '该平台必须先确认全历史边界，服务端才会接受预览。'
          : '请填写作者标识，并完成资料查询或填写本地备注。',
        'danger'
      );
      return null;
    }
    wizardFailure = null;
    previewing = true;
    const result = await previewRequests.run(
      (signal) =>
        api<SubscriptionPreview>('/api/v1/subscriptions/preview', {
          method: 'POST',
          body: JSON.stringify(payload),
          signal
        }),
      (value) => previewMatchesDraft(value, payload)
    );
    if (destroyed || !addOpen || result.kind === 'superseded') return null;
    previewing = false;
    if (JSON.stringify(draftPayload()) !== JSON.stringify(payload)) return null;
    if (result.kind === 'failed') {
      preview = null;
      wizardFailure = result.failure;
      return null;
    }
    preview = result.value;
    return result.value;
  }

  async function continueToPolicy(): Promise<void> {
    const result = await requestPreview();
    if (result) wizardStep = 3;
  }

  async function createSubscription(): Promise<void> {
    if (!wizardGates.canCreate) {
      toast(
        wizardGates.confirmationRequired && !fullHistory
          ? '该平台必须明确确认首次全历史采集。'
          : '作者预览已失效，请返回上一步重新验证。',
        'danger'
      );
      return;
    }
    const payload = draftPayload();
    if (!payload || saving) return;
    wizardFailure = null;
    saving = true;
    const result = await createRequests.run(
      async (signal) => {
        const checked = await api<SubscriptionPreview>('/api/v1/subscriptions/preview', {
          method: 'POST',
          body: JSON.stringify(payload),
          signal
        });
        if (
          !previewMatchesDraft(checked, payload) ||
          signal.aborted ||
          destroyed ||
          !addOpen ||
          JSON.stringify(draftPayload()) !== JSON.stringify(payload)
        )
          throw new Error('subscription_request_invalid');
        return api<Subscription>('/api/v1/subscriptions', {
          method: 'POST',
          body: JSON.stringify(payload),
          signal
        });
      },
      (created) =>
        subscriptionMatchesView(created, false) &&
        created.account_id === payload.account_id &&
        created.platform === payload.platform &&
        created.creator_remote_id === payload.creator_remote_id
    );
    if (destroyed || !addOpen || result.kind === 'superseded') return;
    saving = false;
    if (result.kind === 'failed') {
      wizardFailure = result.failure;
      return;
    }
    toast(result.value.created ? '订阅已添加。' : '订阅已存在，已载入现有配置。');
    addOpen = false;
    resetWizard();
    showRemoved = false;
    await load();
  }

  async function subscriptionAction(
    subscription: Subscription,
    action: 'pause' | 'resume' | 'run-now'
  ): Promise<void> {
    if (acting || !isSubscriptionId(subscription.id) || isRemovedSubscription(subscription)) return;
    actionFailure = null;
    acting = `${subscription.id}:${action}`;
    const requestedAction = acting;
    listRequests.cancel();
    const result = await actionRequests.run(
      (signal) =>
        api<{ subscription_id: string }>(`/api/v1/subscriptions/${subscription.id}/${action}`, {
          method: 'POST',
          signal
        }),
      (value) => !!value && value.subscription_id === subscription.id
    );
    if (destroyed || result.kind === 'superseded' || acting !== requestedAction) return;
    acting = '';
    if (result.kind === 'failed') {
      actionFailure = result.failure;
      return;
    }
    toast(
      action === 'run-now'
        ? '已安排同步任务；完成状态请到任务页面核对。'
        : action === 'pause'
          ? '订阅已暂停。'
          : '订阅已启用，可继续调度。'
    );
    await load();
  }

  async function showDetail(subscription: Subscription): Promise<void> {
    if (!isSubscriptionId(subscription.id)) return;
    const requestedId = subscription.id;
    detailId = requestedId;
    detailOpen = true;
    detailLoading = true;
    detail = null;
    detailError = '';
    const result = await detailRequests.run(
      (signal) => api<SubscriptionDetail>(`/api/v1/subscriptions/${requestedId}`, { signal }),
      (value) =>
        !!value &&
        value.id === requestedId &&
        value.account_id === subscription.account_id &&
        value.platform === subscription.platform
    );
    if (destroyed || !detailOpen || detailId !== requestedId || result.kind === 'superseded') return;
    detailLoading = false;
    if (result.kind === 'failed') detailError = result.failure.message;
    else detail = result.value;
  }

  async function switchView(deleted: boolean): Promise<void> {
    if (acting) return;
    showRemoved = deleted;
    subscriptions = [];
    actionFailure = null;
    detailOpen = false;
    detailRequests.cancel();
    confirmOpen = false;
    addOpen = false;
    await load();
  }

  function confirmLifecycle(subscription: Subscription, action: SubscriptionLifecycleAction): void {
    if (
      acting ||
      !subscriptionLifecyclePath(subscription.id, action) ||
      isRemovedSubscription(subscription) !== (action === 'restore')
    )
      return;
    confirmTarget = subscription;
    confirmAction = action;
    actionFailure = null;
    confirmOpen = true;
  }

  async function applyLifecycle(): Promise<void> {
    if (!confirmTarget || !confirmOpen || acting) return;
    const targetId = confirmTarget.id;
    const action = confirmAction;
    const path = subscriptionLifecyclePath(targetId, action);
    if (!path) return;
    acting = `${targetId}:${action}`;
    const requestedAction = acting;
    actionFailure = null;
    listRequests.cancel();
    detailRequests.cancel();
    detailOpen = false;
    const result = await actionRequests.run(
      (signal) =>
        api<SubscriptionLifecycleResult>(path, {
          method: action === 'delete' ? 'DELETE' : 'POST',
          signal
        }),
      (value) => validSubscriptionLifecycleResult(value, targetId, action)
    );
    if (
      destroyed ||
      result.kind === 'superseded' ||
      acting !== requestedAction ||
      confirmTarget?.id !== targetId ||
      confirmAction !== action
    )
      return;
    acting = '';
    if (result.kind === 'failed') {
      actionFailure = result.failure;
      return;
    }
    confirmOpen = false;
    toast(
      action === 'delete'
        ? `订阅${result.value.changed ? '已删除' : '此前已删除'}，媒体文件全部保留；取消未开始任务 ${result.value.cancelled_jobs} 个。`
        : '订阅已恢复并保持暂停；没有自动运行或恢复已取消任务。'
    );
    await load();
  }

  onMount(() => void load());
  onDestroy(() => {
    destroyed = true;
    lookupController.dispose();
    for (const requests of [listRequests, detailRequests, previewRequests, createRequests, actionRequests])
      requests.cancel();
  });
</script>

<div class="page">
  <PageHeader title="创作者订阅" description="按平台能力分三步确认账户、作者输入与有界同步策略。">
    <svelte:fragment slot="actions">
      <button class="button secondary" type="button" on:click={load} disabled={loading || !!acting}>
        <RefreshCw class={loading ? 'spin' : ''} size={15} />刷新
      </button>
      <button
        class="button"
        type="button"
        on:click={openWizard}
        disabled={accounts.length === 0 || capabilities.length === 0 || !!acting}
      >
        <Plus size={16} />添加订阅
      </button>
    </svelte:fragment>
  </PageHeader>

  <div class="view-controls" aria-label="订阅视图">
    <button
      class="button secondary"
      class:selected-view={!showRemoved}
      type="button"
      aria-pressed={!showRemoved}
      disabled={!!acting}
      on:click={() => switchView(false)}>当前订阅</button
    >
    <button
      class="button secondary"
      class:selected-view={showRemoved}
      type="button"
      aria-pressed={showRemoved}
      disabled={!!acting}
      on:click={() => switchView(true)}>已删除</button
    >
    <a class="text-link" href="/jobs">查看任务与执行结果</a>
  </div>
  <div class="notice">
    <ShieldAlert size={17} />
    <div>
      {showRemoved
        ? SUBSCRIPTION_RESTORE_NOTICE
        : '删除订阅默认保留所有已抓取内容、媒体文件和历史，可从“已删除”视图恢复。'}
    </div>
  </div>
  {#if actionFailure && !confirmOpen}
    <div class="notice danger" role="alert">
      <div>
        {actionFailure.message}
        {#if actionFailure.destination === 'jobs'}
          <a class="text-link" href="/jobs">查看任务</a>
        {:else if actionFailure.destination === 'deleted'}
          <button class="button ghost small" type="button" on:click={() => switchView(true)}
            >查看已删除</button
          >
        {/if}
      </div>
    </div>
  {/if}

  <section class="summary-grid subscription-summary">
    <div class="summary-item">
      <span class="summary-label">{showRemoved ? '已删除订阅' : '当前订阅'}<UsersRound size={16} /></span
      ><strong class="summary-value">
        {subscriptions.length}
      </strong><span class="summary-hint"
        >跨 {new Set(subscriptions.map((item) => item.platform)).size} 个平台</span
      >
    </div>
    <div class="summary-item">
      <span class="summary-label">已启用<Play size={16} /></span><strong class="summary-value">
        {enabledCount}
      </strong><span class="summary-hint"
        >{showRemoved ? '已删除订阅不参与调度' : `${subscriptions.length - enabledCount} 个已暂停`}</span
      >
    </div>
    <div class="summary-item">
      <span class="summary-label">近期成功<CalendarClock size={16} /></span><strong class="summary-value">
        {subscriptions.filter((item) => item.last_success_at).length}
      </strong><span class="summary-hint">有成功水位的订阅</span>
    </div>
    <div class="summary-item">
      <span class="summary-label">待首次运行<RotateCw size={16} /></span><strong class="summary-value">
        {subscriptions.filter((item) => !item.last_success_at).length}
      </strong><span class="summary-hint">尚未建立同步水位</span>
    </div>
  </section>

  {#if accounts.length === 0 && !loading}
    <div class="notice warning">
      <UsersRound size={17} />
      <div>
        <strong class="notice-title">先添加平台账户</strong>订阅必须绑定一个同平台账户。<a
          class="text-link"
          href="/accounts">前往账户页面</a
        >
      </div>
    </div>
  {/if}

  {#if capabilityError}
    <div class="notice danger">
      <ShieldAlert size={17} />
      <div>
        <strong class="notice-title">平台能力契约不可用</strong
        >{capabilityError}。订阅列表仍可查看，但创建向导已停用。
      </div>
    </div>
  {/if}

  <Panel
    title={showRemoved ? '已删除订阅' : '订阅列表'}
    description={showRemoved
      ? '保留历史和媒体 · 恢复后先暂停'
      : `${enabledCount} 个启用 · 调度按订阅独立维护`}
    flush
  >
    {#if error}
      <div class="notice danger list-error">{error}</div>
    {:else if loading}
      <div class="loading-rows">
        {#each Array(3) as _}<div class="skeleton"></div>{/each}
      </div>
    {:else if subscriptions.length === 0}
      <EmptyState
        title={showRemoved ? '没有已删除订阅' : '还没有创作者订阅'}
        description={showRemoved
          ? '删除后的订阅会出现在这里，可查看历史或恢复原订阅。'
          : '通过三步向导进行本地格式校验后建立订阅。'}
      >
        {#if !showRemoved && accounts.length && capabilities.length}
          <button class="button small" type="button" on:click={openWizard}><Plus size={14} />添加订阅</button>
        {/if}
      </EmptyState>
    {:else}
      <div class="table-wrap">
        <table class="data-table subscription-table">
          <thead>
            <tr>
              <th>创作者</th><th>状态</th><th>同步策略</th><th>上次成功</th><th>下次运行</th><th
                class="actions">操作</th
              >
            </tr>
          </thead>
          <tbody>
            {#each subscriptions as subscription}
              {@const savedProfile = subscriptionCreatorProfile(subscription)}
              {@const boundedBili =
                subscription.policy_summary?.adapter === 'mediacrawler' &&
                isBiliBoundedCapture(capabilityByPlatform(capabilities, subscription.platform))}
              <tr>
                <td>
                  <div class="inline-identity">
                    <PlatformMark platform={subscription.platform} />
                    <div>
                      <span class="cell-main">{subscriptionCreatorLabel(subscription)}</span>
                      {#if savedProfile}
                        <CreatorProfileCard
                          profile={savedProfile}
                          contextKey={`${subscription.id}:${$operatorAuth.epoch}`}
                          compact
                        />
                      {/if}
                      <span class="cell-sub">
                        {subscription.account_display_name} · {subscription.creator_remote_id}
                      </span>
                    </div>
                  </div>
                </td>
                <td
                  ><StatusBadge
                    status={showRemoved ? 'cancelled' : subscription.enabled ? 'enabled' : 'paused'}
                    label={showRemoved ? '已删除' : null}
                  /></td
                >
                <td>
                  <span class="cell-main">每 {intervalLabel(subscription.interval_seconds)}</span>
                  <span class="cell-sub"
                    >单次最多 {boundedBili
                      ? biliUnitItemLimit(subscription.max_items)
                      : subscription.max_items} 条{boundedBili ? '普通投稿详情' : ''}</span
                  >
                  {#if boundedBili}<span class="cell-sub">分轮更新/回填；不是下载上限</span>{/if}
                </td>
                <td>{formatDate(subscription.last_success_at, '尚未成功')}</td>
                <td
                  >{showRemoved
                    ? '不再调度'
                    : formatDate(subscription.next_run_at, subscription.enabled ? '等待调度' : '已暂停')}</td
                >
                <td class="actions">
                  <div class="row-actions">
                    <button
                      class="button ghost small"
                      type="button"
                      on:click={() => showDetail(subscription)}
                      disabled={!!acting}
                    >
                      <Eye size={14} />详情
                    </button>
                    {#if showRemoved}
                      <button
                        class="button secondary small"
                        type="button"
                        disabled={!!acting}
                        on:click={() => confirmLifecycle(subscription, 'restore')}
                        ><Undo2 size={14} />恢复为暂停</button
                      >
                    {:else}
                      <button
                        class="button ghost small"
                        type="button"
                        on:click={() => subscriptionAction(subscription, 'run-now')}
                        disabled={!!acting}
                      >
                        <RotateCw size={14} />立即
                      </button>
                      <button
                        class="button secondary small"
                        type="button"
                        on:click={() =>
                          subscriptionAction(subscription, subscription.enabled ? 'pause' : 'resume')}
                        disabled={!!acting}
                      >
                        {#if subscription.enabled}<Pause size={14} />暂停{:else}<Play size={14} />启用{/if}
                      </button>
                      <button
                        class="button ghost small danger-text"
                        type="button"
                        disabled={!!acting}
                        on:click={() => confirmLifecycle(subscription, 'delete')}
                        ><Trash2 size={14} />删除</button
                      >
                    {/if}
                  </div>
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    {/if}
  </Panel>
</div>

<Modal
  bind:open={addOpen}
  title="添加创作者订阅"
  description={`第 ${wizardStep} 步，共 3 步 · ${['选择账户', '作者资料与校验', '确认策略'][wizardStep - 1]}`}
  dismissible={!saving}
  wide
>
  <ol class="wizard-steps" aria-label="订阅创建进度">
    {#each ['账户与平台', '作者资料与校验', '策略确认'] as label, index}
      <li class:active={wizardStep === index + 1} class:complete={wizardStep > index + 1}>
        <span>{wizardStep > index + 1 ? '✓' : index + 1}</span>
        <strong>{label}</strong>
      </li>
    {/each}
  </ol>

  {#if wizardFailure}
    <div class="notice danger" role="alert">
      <div>
        {wizardFailure.message}
        {#if wizardFailure.destination === 'deleted'}
          <button class="button ghost small" type="button" on:click={() => switchView(true)}
            >查看已删除并恢复</button
          >
        {/if}
      </div>
    </div>
  {/if}

  <fieldset class="wizard-fields" disabled={saving}>
    {#if wizardStep === 1}
      <section class="wizard-stage">
        <div class="field">
          <label for="subscription-account">平台账户</label>
          <select id="subscription-account" class="select" bind:value={accountId} on:change={accountChanged}>
            {#each accounts as account}
              <option value={account.id}>
                {capabilityByPlatform(capabilities, account.platform)?.display_name ??
                  PLATFORM_META[account.platform].name} · {account.display_name}
              </option>
            {/each}
          </select>
        </div>

        {#if selectedAccount && selectedCapability}
          <div class="selection-card">
            <div class="selection-heading">
              <PlatformMark platform={selectedAccount.platform} />
              <div>
                <strong>{selectedCapability.display_name}</strong>
                <span>{selectedAccount.display_name} · {selectedAccount.auth_status}</span>
              </div>
              <StatusBadge status="succeeded" label="能力已载入" />
            </div>
            <dl class="selection-facts">
              <div>
                <dt>作者输入</dt>
                <dd>{selectedCapability.creator_input.label}</dd>
              </div>
              <div>
                <dt>全历史确认</dt>
                <dd>
                  {selectedCapability.requires_full_history_acknowledgement
                    ? '创建前必需'
                    : isBiliBoundedCapture(selectedCapability)
                      ? '新格式有界投稿扫描无需确认；旧产物仍受门控'
                      : '不强制'}
                </dd>
              </div>
              <div>
                <dt>离线形状</dt>
                <dd>{selectedCapability.offline_shapes.length} 种</dd>
              </div>
              <div>
                <dt>真人资格</dt>
                <dd>{selectedCapability.live_qualification}</dd>
              </div>
            </dl>
            <div class="shape-list" aria-label="已验证离线形状">
              {#each selectedCapability.offline_shapes as shape}<span>{shape}</span>{/each}
            </div>
            {#if selectedCapability.limitations.length}
              <div class="notice warning capability-limit">
                <ShieldAlert size={16} />{selectedCapability.limitations.join('；')}
              </div>
            {/if}
          </div>
        {:else}
          <div class="notice danger"><ShieldAlert size={16} />所选账户没有匹配的平台能力，不能继续。</div>
        {/if}
      </section>
    {:else if wizardStep === 2}
      <section class="wizard-stage">
        {#if selectedAccount && selectedCapability}
          <div class="stage-context">
            <PlatformMark platform={selectedAccount.platform} />
            <div>
              <strong>{selectedCapability.display_name} · {selectedAccount.display_name}</strong>
              <span>平台资料查询与本地订阅校验相互独立，不会在此采集内容。</span>
            </div>
          </div>
          <div class="form-grid">
            <div class="field">
              <label for="creator-id">{selectedCapability.creator_input.label}</label>
              <input
                id="creator-id"
                class="input"
                bind:value={creatorId}
                placeholder={selectedCapability.creator_input.placeholder}
                maxlength="255"
                on:input={creatorInputChanged}
                on:blur={() => completeCreatorInput()}
                on:keydown={creatorInputKeydown}
              />
              {#if selectedCapability.creator_input.examples.length}
                <span class="field-help">示例：{selectedCapability.creator_input.examples.join(' · ')}</span>
              {/if}
            </div>
            <div class="field">
              <label for="creator-name">本地备注（有查询资料时可不填）</label>
              <input
                id="creator-name"
                class="input"
                bind:value={creatorName}
                placeholder="可选别名，不会被平台昵称覆盖"
                maxlength="200"
                on:input={invalidatePreview}
              />
              <span class="field-help">备注由你填写；没有有效查询结果时，需要填写备注才能继续。</span>
            </div>
            {#if selectedCapability.creator_input.allows_secret_reference}
              <div class="field wide">
                <label for="creator-reference">作者权限引用（可选）</label>
                <input
                  id="creator-reference"
                  class="input mono"
                  type="password"
                  bind:value={creatorReferenceRef}
                  placeholder="例如 env:MEDIA_SYNC_XHS_CREATOR_URL"
                  maxlength="512"
                  autocomplete="off"
                  spellcheck="false"
                  on:input={invalidatePreview}
                />
                <span class="field-help"
                  >仅发送不透明引用；预览和详情只显示“已配置/未配置”，不会回显其值。</span
                >
              </div>
            {/if}
          </div>
          <div class="creator-lookup" aria-live="polite" aria-busy={lookupBusy}>
            {#if lookupEligibility}
              <div class="notice warning">{lookupEligibility}</div>
              {#if selectedAccount.platform === 'bili'}<a class="field-help" href="/accounts"
                  >到账户页面核对登录</a
                >{/if}
            {:else}
              <p class="field-help">{CREATOR_LOOKUP_NOTICE}</p>
              {#if lookupBusy}
                <p class="lookup-state">
                  <RefreshCw class="spin" size={15} />{lookupView.phase === 'submitting'
                    ? '正在提交资料查询…'
                    : '正在等待本次作者资料…'}
                </p>
              {:else if lookupView.phase === 'succeeded'}
                <p class="lookup-state">
                  <CheckCircle2 size={15} />本次平台资料查询成功，创建时使用服务器保存的资料凭单。
                </p>
              {:else if lookupView.phase === 'idle'}
                <p class="field-help">填写有效数字 UID 后离开输入框或按 Enter，将自动查询一次。</p>
              {/if}
              {#if lookupView.message}
                <div class="notice warning" role="status">{lookupView.message}</div>
              {/if}
              {#if lookupView.profile}
                <CreatorProfileCard
                  profile={lookupView.profile}
                  contextKey={`${lookupView.scope?.frontend_generation}:${lookupView.operation_id}:${lookupView.generation}:${$operatorAuth.epoch}`}
                  previous={lookupView.profile_source === 'previous_success'}
                />
              {/if}
              <div class="lookup-actions">
                <button
                  class="button secondary small"
                  type="button"
                  disabled={!lookupView.scope || lookupBusy || previewing}
                  on:click={() => completeCreatorInput(true)}
                >
                  <RefreshCw size={14} />{creatorLookupButtonLabel(lookupView.phase)}
                </button>
                {#if lookupView.operation_id}<a class="button ghost small" href="/jobs">到任务页面核对</a
                  >{/if}
              </div>
            {/if}
          </div>
          {#if wizardGates.confirmationRequired}
            <label class="checkbox-row history-preview-confirmation">
              <input type="checkbox" bind:checked={fullHistory} />
              <span>
                <strong>确认订阅的全历史边界</strong>
                <span>
                  {selectedCapability.display_name}
                  的作者路径当前仍可能遍历完整历史。本地校验不会联网或写入订阅，第三步还会再次确认此策略。
                </span>
              </span>
            </label>
          {/if}
          <div class="notice preview-notice">
            <Eye size={16} />{LOCAL_CREATOR_PREVIEW_NOTICE}
          </div>
        {/if}
      </section>
    {:else}
      <section class="wizard-stage">
        {#if selectedAccount && selectedCapability && preview}
          <div class="preview-card">
            <div class="preview-title">
              <div><CheckCircle2 size={18} /><strong>已通过本地格式与策略校验</strong></div>
              <StatusBadge
                status={preview.exists ? 'warning' : 'succeeded'}
                label={preview.exists ? '已有订阅' : '可创建'}
              />
            </div>
            <dl class="preview-facts">
              <div>
                <dt>平台 / 账户</dt>
                <dd>{selectedCapability.display_name} · {preview.account_display_name}</dd>
              </div>
              <div>
                <dt>{selectedCapability.creator_input.label}</dt>
                <dd class="mono">{preview.creator_remote_id}</dd>
              </div>
              <div>
                <dt>本地备注名称</dt>
                <dd>{creatorName.trim() || '未设置（使用已查询的平台昵称）'}</dd>
              </div>
              <div>
                <dt>作者权限引用</dt>
                <dd>
                  {preview.policy_summary.creator_reference_configured ? '已配置（值已隐藏）' : '未配置'}
                </dd>
              </div>
            </dl>
          </div>
          {#if lookupView.profile}
            <CreatorProfileCard
              profile={lookupView.profile}
              contextKey={`${lookupView.scope?.frontend_generation}:${lookupView.operation_id}:${lookupView.generation}:${$operatorAuth.epoch}`}
              previous={lookupView.profile_source === 'previous_success'}
            />
          {/if}
          <p class="field-help">{LOCAL_CREATOR_PREVIEW_NOTICE}</p>

          <div class="form-grid policy-grid">
            <div class="field">
              <label for="interval">采集间隔</label>
              <select id="interval" class="select" bind:value={intervalSeconds}>
                <option value={3600}>每 1 小时</option>
                <option value={21600}>每 6 小时</option>
                <option value={43200}>每 12 小时</option>
                <option value={86400}>每天</option>
              </select>
            </div>
            <div class="field">
              <label for="max-items">单次上限</label>
              <input id="max-items" class="input" type="number" min="1" max="1000" bind:value={maxItems} />
              {#if isBiliBoundedCapture(selectedCapability)}
                <span class="field-help"
                  >本轮实际最多 {biliUnitItemLimit(maxItems)} 条普通投稿详情；不是下载上限。</span
                >
              {/if}
            </div>
            <div class="field">
              <label for="request-delay">请求间隔（秒）</label>
              <input
                id="request-delay"
                class="input"
                type="number"
                min="0.1"
                max="120"
                step="0.5"
                bind:value={requestDelaySeconds}
              />
            </div>
            <div class="field">
              <label for="browser-mode">浏览器模式</label>
              <select id="browser-mode" class="select" bind:value={headless}>
                <option value={true}>后台运行（Headless）</option>
                <option value={false}>可见浏览器</option>
              </select>
            </div>
            {#if !isBiliBoundedCapture(selectedCapability)}
              <label
                class:required-confirmation={wizardGates.confirmationRequired}
                class="checkbox-row wide history-confirmation"
              >
                <input type="checkbox" bind:checked={fullHistory} />
                <span>
                  <strong>
                    {wizardGates.confirmationRequired
                      ? '必须确认：允许首次全历史采集'
                      : '允许首次全历史采集（可选）'}
                  </strong>
                  <span>
                    {wizardGates.confirmationRequired
                      ? `${selectedCapability.display_name} 的当前作者路径仍可能遍历完整历史；未确认不能创建。`
                      : '该平台当前具备有界作者路径；只有确实需要时再开启。'}
                  </span>
                </span>
              </label>
            {/if}
          </div>

          {#if isBiliBoundedCapture(selectedCapability)}
            <p class="notice warning">{biliCaptureNotice(maxItems)}</p>
          {/if}

          <div class="policy-summary">
            <span>每 {intervalLabel(intervalSeconds)}</span>
            <span
              >最多 {isBiliBoundedCapture(selectedCapability) ? biliUnitItemLimit(maxItems) : maxItems} 条{isBiliBoundedCapture(
                selectedCapability
              )
                ? '普通投稿详情'
                : ''}</span
            >
            <span>请求间隔 {requestDelaySeconds} 秒</span>
            <span>{headless ? '后台浏览器' : '可见浏览器'}</span>
            <span>真人验收 {selectedCapability.live_qualification}</span>
          </div>
        {:else}
          <div class="notice danger">
            <ShieldAlert size={16} />安全预览已失效，请返回作者输入步骤重新验证。
          </div>
        {/if}
      </section>
    {/if}
  </fieldset>

  <svelte:fragment slot="footer">
    <button class="button secondary" type="button" on:click={() => (addOpen = false)} disabled={saving}
      >取消</button
    >
    {#if wizardStep > 1}
      <button
        class="button secondary"
        type="button"
        on:click={() => (wizardStep = wizardStep === 3 ? 2 : 1)}
        disabled={saving || previewing}>返回上一步</button
      >
    {/if}
    {#if wizardStep === 1}
      <button
        class="button"
        type="button"
        on:click={continueToCreator}
        disabled={!wizardGates.canContinueFromAccount}
      >
        下一步：作者输入
      </button>
    {:else if wizardStep === 2}
      <button
        class="button"
        type="button"
        on:click={continueToPolicy}
        disabled={!wizardGates.canRequestPreview || previewing || lookupBusy}
      >
        {previewing ? '本地校验中…' : '校验格式并继续'}
      </button>
    {:else}
      <button
        class="button"
        type="button"
        on:click={createSubscription}
        disabled={!wizardGates.canCreate || saving}
      >
        {saving ? '复验并保存中…' : '确认并添加订阅'}
      </button>
    {/if}
  </svelte:fragment>
</Modal>

<Modal
  bind:open={detailOpen}
  title={detail ? subscriptionCreatorLabel(detail) : '订阅详情'}
  description={detail ? `${PLATFORM_META[detail.platform].name} · ${shortId(detail.id)}` : '正在读取…'}
  wide
>
  {#if detailLoading}
    <div class="detail-loading"><RefreshCw class="spin" size={20} />读取订阅运行记录…</div>
  {:else if detailError}
    <div class="notice danger" role="alert">{detailError}</div>
  {:else if detail}
    {@const savedProfile = subscriptionCreatorProfile(detail)}
    {#if savedProfile}
      <CreatorProfileCard profile={savedProfile} contextKey={`${detail.id}:${$operatorAuth.epoch}`} />
    {/if}
    <dl class="key-value-list">
      <div class="key-value-row">
        <dt>本地备注</dt>
        <dd>{detail.local_alias ?? '未设置'}</dd>
      </div>
      <div class="key-value-row">
        <dt>状态</dt>
        <dd>
          <StatusBadge
            status={isRemovedSubscription(detail) ? 'cancelled' : detail.schedule.status}
            label={isRemovedSubscription(detail) ? '已删除' : null}
          />
        </dd>
      </div>
      {#if isRemovedSubscription(detail)}
        <div class="key-value-row">
          <dt>删除时间</dt>
          <dd>{formatDateLong(detail.deleted_at)}</dd>
        </div>
      {/if}
      <div class="key-value-row">
        <dt>创作者 ID</dt>
        <dd class="mono">{detail.creator_remote_id}</dd>
      </div>
      <div class="key-value-row">
        <dt>采集策略</dt>
        <dd>每 {intervalLabel(detail.interval_seconds)}，最多 {detail.max_items} 条</dd>
      </div>
      <div class="key-value-row">
        <dt>下次运行</dt>
        <dd>{formatDateLong(detail.schedule.next_run_at)}</dd>
      </div>
      <div class="key-value-row">
        <dt>最近成功</dt>
        <dd>{formatDateLong(detail.schedule.last_success_at)}</dd>
      </div>
      <div class="key-value-row">
        <dt>连续失败</dt>
        <dd>{detail.schedule.consecutive_failures}</dd>
      </div>
      <div class="key-value-row">
        <dt>调度修订</dt>
        <dd>{detail.schedule.schedule_revision}</dd>
      </div>
    </dl>

    <div class="safe-summary-grid">
      {#if detail.policy_summary}
        <section class="safe-summary">
          <h3>安全策略摘要</h3>
          <dl>
            {#each safePolicySummaryRows(detail.policy_summary) as row}
              <div>
                <dt>{row.label}</dt>
                <dd>{row.value}</dd>
              </div>
            {/each}
          </dl>
        </section>
      {/if}
      {#if detail.checkpoint_summary}
        <section class="safe-summary">
          <h3>安全检查点摘要</h3>
          <dl>
            {#each safeCheckpointSummaryRows(detail.checkpoint_summary) as row}
              <div>
                <dt>{row.label}</dt>
                <dd>{row.value}</dd>
              </div>
            {/each}
          </dl>
        </section>
      {/if}
    </div>
    {#if detail.platform === 'bili' && detail.checkpoint_summary?.bili_scan}
      <section class="safe-summary" aria-label="B站有界采集覆盖">
        <h3>B站有界采集覆盖</h3>
        <p class="field-help">{biliCaptureNotice(detail.max_items)}</p>
        <dl>
          {#each safeBiliScanSummaryRows(detail.checkpoint_summary.bili_scan) as row}
            <div>
              <dt>{row.label}</dt>
              <dd>{row.value}</dd>
            </div>
          {/each}
        </dl>
      </section>
    {/if}
    {#if detail.policy_summary || detail.checkpoint_summary}
      <p class="redaction-note">
        仅展示服务端白名单摘要；secret reference、原始 cursor、签名 URL 与本地路径均不返回。
      </p>
    {/if}

    <h3 class="detail-heading">最近同步运行</h3>
    {#if detail.recent_runs.length === 0}
      <p class="detail-empty">暂无同步运行记录。</p>
    {:else}
      <div class="table-wrap">
        <table class="data-table">
          <thead><tr><th>Run</th><th>状态</th><th>发现</th><th>资产</th><th>开始</th></tr></thead>
          <tbody>
            {#each detail.recent_runs as run}
              <tr>
                <td class="mono">{shortId(run.run_id)}</td><td><StatusBadge status={run.status} /></td><td>
                  {run.discovered_count}
                </td><td>{run.asset_count}</td><td>{formatDate(run.started_at)}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    {/if}
  {/if}
  <svelte:fragment slot="footer">
    <a class="button secondary" href="/jobs">查看任务与执行结果</a>
    <button class="button secondary" type="button" on:click={() => (detailOpen = false)}>关闭</button>
  </svelte:fragment>
</Modal>

<Modal
  bind:open={confirmOpen}
  title={confirmAction === 'delete' ? '删除订阅，保留媒体' : '恢复订阅并保持暂停'}
  description={confirmTarget
    ? `${subscriptionCreatorLabel(confirmTarget)} · ${shortId(confirmTarget.id)}`
    : null}
  dismissible={!acting}
>
  <p>{confirmAction === 'delete' ? SUBSCRIPTION_REMOVAL_NOTICE : SUBSCRIPTION_RESTORE_NOTICE}</p>
  {#if confirmAction === 'delete'}
    <p>
      若存在已领取或正在执行的任务，或相关活动操作，服务端会拒绝本次删除且不做部分修改。删除不是强制终止进程。
    </p>
  {/if}
  {#if actionFailure}
    <div class="notice danger" role="alert">
      <div>
        {actionFailure.message}
        {#if actionFailure.destination === 'jobs'}
          <a class="text-link" href="/jobs">查看任务</a>{/if}
        {#if actionFailure.destination === 'deleted'}
          <button class="button ghost small" type="button" on:click={() => switchView(true)}
            >查看已删除</button
          >
        {/if}
      </div>
    </div>
  {/if}
  <svelte:fragment slot="footer">
    <button class="button secondary" type="button" disabled={!!acting} on:click={() => (confirmOpen = false)}
      >取消</button
    >
    <button class="button" type="button" disabled={!!acting || !confirmTarget} on:click={applyLifecycle}>
      {acting ? '正在确认结果…' : confirmAction === 'delete' ? '确认删除订阅，保留文件' : '确认恢复为暂停'}
    </button>
  </svelte:fragment>
</Modal>

<style>
  .creator-lookup {
    margin-top: 16px;
  }
  .lookup-state,
  .lookup-actions {
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .lookup-state {
    font-size: 12px;
    color: var(--text-secondary);
  }
  .lookup-actions {
    margin-top: 10px;
  }
  .view-controls {
    display: flex;
    align-items: center;
    gap: 10px;
    flex-wrap: wrap;
  }
  .selected-view {
    border-color: var(--accent);
    color: var(--accent);
  }
  .wizard-fields {
    border: 0;
    margin: 0;
    padding: 0;
    min-width: 0;
  }
  .subscription-summary {
    margin-bottom: 0;
  }

  .actions {
    text-align: right !important;
  }

  .row-actions {
    display: flex;
    justify-content: flex-end;
    gap: 3px;
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

  .wizard-steps {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 8px;
    margin: 0 0 22px;
    padding: 0;
    list-style: none;
  }

  .wizard-steps li {
    display: flex;
    min-width: 0;
    align-items: center;
    gap: 8px;
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 8px 9px;
    background: #fafbfd;
    color: var(--text-muted);
  }

  .wizard-steps li > span {
    display: inline-flex;
    width: 22px;
    height: 22px;
    flex: 0 0 auto;
    align-items: center;
    justify-content: center;
    border-radius: 999px;
    background: #e8edf3;
    font-size: 10px;
    font-weight: 700;
  }

  .wizard-steps strong {
    overflow: hidden;
    font-size: 11px;
    font-weight: 580;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .wizard-steps li.active {
    border-color: #bfdbfe;
    background: var(--accent-soft);
    color: #1d4ed8;
  }

  .wizard-steps li.complete {
    border-color: #ccebd6;
    background: var(--success-soft);
    color: var(--success);
  }

  .wizard-steps li.active > span {
    background: var(--accent);
    color: #fff;
  }

  .wizard-steps li.complete > span {
    background: #22c55e;
    color: #fff;
  }

  .wizard-stage {
    min-height: 315px;
  }

  .selection-card,
  .preview-card {
    margin-top: 16px;
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 14px;
    background: #fafbfd;
  }

  .selection-heading,
  .stage-context,
  .preview-title,
  .preview-title > div {
    display: flex;
    align-items: center;
    gap: 10px;
  }

  .selection-heading > div,
  .stage-context > div {
    min-width: 0;
    flex: 1;
  }

  .selection-heading strong,
  .stage-context strong,
  .preview-title strong {
    display: block;
    color: var(--text);
    font-size: 12px;
    font-weight: 620;
  }

  .selection-heading span,
  .stage-context span {
    display: block;
    margin-top: 2px;
    color: var(--text-muted);
    font-size: 11px;
  }

  .selection-facts,
  .preview-facts {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 8px 18px;
    margin: 15px 0 0;
  }

  .selection-facts div,
  .preview-facts div {
    display: flex;
    min-width: 0;
    justify-content: space-between;
    gap: 12px;
    border-top: 1px solid #e8edf3;
    padding-top: 8px;
  }

  .selection-facts dt,
  .selection-facts dd,
  .preview-facts dt,
  .preview-facts dd {
    min-width: 0;
    margin: 0;
    overflow-wrap: anywhere;
    font-size: 11px;
  }

  .selection-facts dt,
  .preview-facts dt {
    color: var(--text-muted);
  }

  .selection-facts dd,
  .preview-facts dd {
    color: #344158;
    text-align: right;
  }

  .shape-list,
  .policy-summary {
    display: flex;
    gap: 6px;
    margin-top: 13px;
    flex-wrap: wrap;
  }

  .shape-list span,
  .policy-summary span {
    border: 1px solid var(--border);
    border-radius: 999px;
    padding: 3px 8px;
    background: #fff;
    color: var(--text-secondary);
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    font-size: 10px;
  }

  .capability-limit,
  .preview-notice,
  .history-preview-confirmation {
    margin-top: 14px;
  }

  .history-preview-confirmation {
    border-color: #f3ddb0;
    background: var(--warning-soft);
  }

  .stage-context {
    margin-bottom: 18px;
    border-bottom: 1px solid var(--border);
    padding-bottom: 13px;
  }

  .field-help {
    color: var(--text-muted);
    font-size: 10.5px;
  }

  .preview-title {
    justify-content: space-between;
  }

  .preview-title > div {
    color: var(--success);
  }

  .policy-grid {
    margin-top: 18px;
  }

  .history-confirmation.required-confirmation {
    border-color: #f3ddb0;
    background: var(--warning-soft);
  }

  .detail-loading {
    display: flex;
    min-height: 180px;
    align-items: center;
    justify-content: center;
    gap: 9px;
    color: var(--text-muted);
    font-size: 12px;
  }

  .safe-summary-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 12px;
    margin-top: 18px;
  }

  .safe-summary {
    min-width: 0;
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 12px;
    background: #fafbfd;
  }

  .safe-summary h3 {
    margin: 0 0 8px;
    color: #344158;
    font-size: 12px;
    font-weight: 620;
  }

  .safe-summary dl {
    display: grid;
    gap: 6px;
    margin: 0;
  }

  .safe-summary dl div {
    display: flex;
    justify-content: space-between;
    gap: 12px;
    border-top: 1px solid #edf0f4;
    padding-top: 6px;
  }

  .safe-summary dt,
  .safe-summary dd {
    min-width: 0;
    margin: 0;
    overflow-wrap: anywhere;
    font-size: 10.5px;
  }

  .safe-summary dt {
    color: var(--text-muted);
  }

  .safe-summary dd {
    color: #344158;
    text-align: right;
  }

  .redaction-note {
    margin: 9px 0 0;
    color: var(--text-muted);
    font-size: 10.5px;
  }

  .detail-heading {
    margin: 22px 0 8px;
    color: #344158;
    font-size: 13px;
    font-weight: 620;
  }

  .detail-empty {
    margin: 0;
    padding: 18px;
    border: 1px dashed var(--border-strong);
    border-radius: 8px;
    color: var(--text-muted);
    font-size: 12px;
    text-align: center;
  }

  @media (max-width: 880px) {
    .subscription-table {
      min-width: 920px;
    }
  }

  @media (max-width: 620px) {
    .wizard-steps strong {
      display: none;
    }

    .wizard-steps li {
      justify-content: center;
    }

    .selection-facts,
    .preview-facts,
    .safe-summary-grid {
      grid-template-columns: 1fr;
    }

    .selection-heading,
    .preview-title {
      align-items: flex-start;
      flex-wrap: wrap;
    }
  }
</style>
