<script lang="ts">
  import { onMount } from 'svelte';
  import { CalendarClock, Eye, Pause, Play, Plus, RefreshCw, RotateCw, UsersRound } from '@lucide/svelte';

  import { api, apiMessage } from '$lib/api/client';
  import EmptyState from '$lib/components/EmptyState.svelte';
  import Modal from '$lib/components/Modal.svelte';
  import PageHeader from '$lib/components/PageHeader.svelte';
  import Panel from '$lib/components/Panel.svelte';
  import PlatformMark from '$lib/components/PlatformMark.svelte';
  import StatusBadge from '$lib/components/StatusBadge.svelte';
  import { toast } from '$lib/stores/toast';
  import type { Account, Subscription, SubscriptionDetail } from '$lib/types/api';
  import { formatDate, formatDateLong, intervalLabel, PLATFORM_META, shortId } from '$lib/utils/format';

  let subscriptions: Subscription[] = [];
  let accounts: Account[] = [];
  let loading = true;
  let saving = false;
  let acting = '';
  let error = '';
  let addOpen = false;
  let detailOpen = false;
  let detailLoading = false;
  let detail: SubscriptionDetail | null = null;

  let accountId = '';
  let creatorId = '';
  let creatorName = '';
  let intervalSeconds = 21_600;
  let maxItems = 30;
  let requestDelaySeconds = 5;
  let fullHistory = false;
  let headless = true;

  $: enabledCount = subscriptions.filter((item) => item.enabled).length;
  $: selectedAccount = accounts.find((item) => item.id === accountId) ?? null;

  async function load(): Promise<void> {
    loading = true;
    error = '';
    try {
      [subscriptions, accounts] = await Promise.all([
        api<Subscription[]>('/api/v1/subscriptions'),
        api<Account[]>('/api/v1/accounts')
      ]);
      if (!accountId && accounts.length) accountId = accounts[0].id;
    } catch (caught) {
      error = apiMessage(caught);
    } finally {
      loading = false;
    }
  }

  async function createSubscription(): Promise<void> {
    if (!selectedAccount || !creatorId.trim() || !creatorName.trim()) {
      toast('请选择账户并填写创作者 ID 与名称。', 'danger');
      return;
    }
    saving = true;
    try {
      const created = await api<Subscription>('/api/v1/subscriptions', {
        method: 'POST',
        body: JSON.stringify({
          account_id: selectedAccount.id,
          platform: selectedAccount.platform,
          creator_remote_id: creatorId.trim(),
          display_name: creatorName.trim(),
          interval_seconds: intervalSeconds,
          max_items: maxItems,
          allow_full_history: fullHistory,
          request_delay_seconds: requestDelaySeconds,
          headless
        })
      });
      toast(created.created ? '订阅已添加。' : '订阅已存在，已载入现有配置。');
      addOpen = false;
      creatorId = '';
      creatorName = '';
      fullHistory = false;
      await load();
    } catch (caught) {
      toast(apiMessage(caught), 'danger');
    } finally {
      saving = false;
    }
  }

  async function subscriptionAction(
    subscription: Subscription,
    action: 'pause' | 'resume' | 'run-now'
  ): Promise<void> {
    acting = `${subscription.id}:${action}`;
    try {
      await api(`/api/v1/subscriptions/${subscription.id}/${action}`, { method: 'POST' });
      toast(action === 'run-now' ? '已安排立即同步。' : action === 'pause' ? '订阅已暂停。' : '订阅已恢复。');
      await load();
    } catch (caught) {
      toast(apiMessage(caught), 'danger');
    } finally {
      acting = '';
    }
  }

  async function showDetail(subscription: Subscription): Promise<void> {
    detailOpen = true;
    detailLoading = true;
    detail = null;
    try {
      detail = await api<SubscriptionDetail>(`/api/v1/subscriptions/${subscription.id}`);
    } catch (caught) {
      toast(apiMessage(caught), 'danger');
      detailOpen = false;
    } finally {
      detailLoading = false;
    }
  }

  onMount(() => void load());
</script>

<div class="page">
  <PageHeader title="创作者订阅" description="配置采集范围、频率与单次边界，查看每位创作者的运行水位。">
    <svelte:fragment slot="actions">
      <button class="button secondary" type="button" on:click={load} disabled={loading}>
        <RefreshCw class={loading ? 'spin' : ''} size={15} />刷新
      </button>
      <button class="button" type="button" on:click={() => (addOpen = true)} disabled={accounts.length === 0}>
        <Plus size={16} />添加订阅
      </button>
    </svelte:fragment>
  </PageHeader>

  <section class="summary-grid subscription-summary">
    <div class="summary-item">
      <span class="summary-label">全部订阅<UsersRound size={16} /></span><strong class="summary-value"
        >{subscriptions.length}</strong
      ><span class="summary-hint">跨 {new Set(subscriptions.map((item) => item.platform)).size} 个平台</span>
    </div>
    <div class="summary-item">
      <span class="summary-label">运行中<Play size={16} /></span><strong class="summary-value"
        >{enabledCount}</strong
      ><span class="summary-hint">{subscriptions.length - enabledCount} 个已暂停</span>
    </div>
    <div class="summary-item">
      <span class="summary-label">近期成功<CalendarClock size={16} /></span><strong class="summary-value"
        >{subscriptions.filter((item) => item.last_success_at).length}</strong
      ><span class="summary-hint">有成功水位的订阅</span>
    </div>
    <div class="summary-item">
      <span class="summary-label">待首次运行<RotateCw size={16} /></span><strong class="summary-value"
        >{subscriptions.filter((item) => !item.last_success_at).length}</strong
      ><span class="summary-hint">尚未建立同步水位</span>
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

  <Panel title="订阅列表" description={`${enabledCount} 个启用 · 调度按订阅独立维护`} flush>
    {#if error}
      <div class="notice danger list-error">{error}</div>
    {:else if loading}
      <div class="loading-rows">
        {#each Array(3) as _}<div class="skeleton"></div>{/each}
      </div>
    {:else if subscriptions.length === 0}
      <EmptyState title="还没有创作者订阅" description="添加订阅后，可以从任务队列触发首次同步。">
        {#if accounts.length}<button class="button small" type="button" on:click={() => (addOpen = true)}
            ><Plus size={14} />添加订阅</button
          >{/if}
      </EmptyState>
    {:else}
      <div class="table-wrap">
        <table class="data-table subscription-table">
          <thead
            ><tr
              ><th>创作者</th><th>状态</th><th>同步策略</th><th>上次成功</th><th>下次运行</th><th
                class="actions">操作</th
              ></tr
            ></thead
          >
          <tbody>
            {#each subscriptions as subscription}
              <tr>
                <td>
                  <div class="inline-identity">
                    <PlatformMark platform={subscription.platform} />
                    <div>
                      <span class="cell-main">{subscription.creator_display_name}</span><span class="cell-sub"
                        >{subscription.account_display_name} · {subscription.creator_remote_id}</span
                      >
                    </div>
                  </div>
                </td>
                <td><StatusBadge status={subscription.enabled ? 'enabled' : 'paused'} /></td>
                <td
                  ><span class="cell-main">每 {intervalLabel(subscription.interval_seconds)}</span><span
                    class="cell-sub">单次最多 {subscription.max_items} 条</span
                  ></td
                >
                <td>{formatDate(subscription.last_success_at, '尚未成功')}</td>
                <td>{formatDate(subscription.next_run_at, subscription.enabled ? '等待调度' : '已暂停')}</td>
                <td class="actions">
                  <div class="row-actions">
                    <button class="button ghost small" type="button" on:click={() => showDetail(subscription)}
                      ><Eye size={14} />详情</button
                    >
                    <button
                      class="button ghost small"
                      type="button"
                      on:click={() => subscriptionAction(subscription, 'run-now')}
                      disabled={!!acting}><RotateCw size={14} />立即</button
                    >
                    <button
                      class="button secondary small"
                      type="button"
                      on:click={() =>
                        subscriptionAction(subscription, subscription.enabled ? 'pause' : 'resume')}
                      disabled={!!acting}
                    >
                      {#if subscription.enabled}<Pause size={14} />暂停{:else}<Play size={14} />恢复{/if}
                    </button>
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
  description="使用稳定创作者 ID；不要粘贴带参数的主页 URL。"
  wide
>
  <div class="form-grid">
    <div class="field wide">
      <label for="subscription-account">平台账户</label>
      <select id="subscription-account" class="select" bind:value={accountId}>
        {#each accounts as account}<option value={account.id}
            >{PLATFORM_META[account.platform].name} · {account.display_name}</option
          >{/each}
      </select>
    </div>
    <div class="field">
      <label for="creator-id">创作者 ID</label>
      <input
        id="creator-id"
        class="input"
        bind:value={creatorId}
        placeholder="例如 B 站 UID"
        maxlength="512"
      />
    </div>
    <div class="field">
      <label for="creator-name">显示名称</label>
      <input
        id="creator-name"
        class="input"
        bind:value={creatorName}
        placeholder="便于识别的名称"
        maxlength="200"
      />
    </div>
    <div class="field">
      <label for="interval">采集间隔</label>
      <select id="interval" class="select" bind:value={intervalSeconds}>
        <option value={3600}>每 1 小时</option><option value={21600}>每 6 小时</option><option value={43200}
          >每 12 小时</option
        ><option value={86400}>每天</option>
      </select>
    </div>
    <div class="field">
      <label for="max-items">单次上限</label>
      <input id="max-items" class="input" type="number" min="1" max="1000" bind:value={maxItems} />
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
      <select id="browser-mode" class="select" bind:value={headless}
        ><option value={true}>后台运行（Headless）</option><option value={false}>可见浏览器</option></select
      >
    </div>
    <label class="checkbox-row wide">
      <input type="checkbox" bind:checked={fullHistory} />
      <span
        ><strong>允许首次全历史采集</strong><span
          >只在你明确需要回填历史内容时开启；仍受单次上限与请求间隔约束。</span
        ></span
      >
    </label>
  </div>
  <svelte:fragment slot="footer">
    <button class="button secondary" type="button" on:click={() => (addOpen = false)}>取消</button>
    <button class="button" type="button" on:click={createSubscription} disabled={saving}
      >{saving ? '保存中…' : '添加订阅'}</button
    >
  </svelte:fragment>
</Modal>

<Modal
  bind:open={detailOpen}
  title={detail ? detail.creator_display_name : '订阅详情'}
  description={detail ? `${PLATFORM_META[detail.platform].name} · ${shortId(detail.id)}` : '正在读取…'}
  wide
>
  {#if detailLoading}
    <div class="detail-loading"><RefreshCw class="spin" size={20} />读取订阅运行记录…</div>
  {:else if detail}
    <dl class="key-value-list">
      <div class="key-value-row">
        <dt>状态</dt>
        <dd><StatusBadge status={detail.schedule.status} /></dd>
      </div>
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
        <dt>水位修订</dt>
        <dd>{detail.schedule.schedule_revision}</dd>
      </div>
    </dl>
    <h3 class="detail-heading">最近同步运行</h3>
    {#if detail.recent_runs.length === 0}
      <p class="detail-empty">暂无同步运行记录。</p>
    {:else}
      <div class="table-wrap">
        <table class="data-table">
          <thead><tr><th>Run</th><th>状态</th><th>发现</th><th>资产</th><th>开始</th></tr></thead><tbody
            >{#each detail.recent_runs as run}<tr
                ><td class="mono">{shortId(run.run_id)}</td><td><StatusBadge status={run.status} /></td><td
                  >{run.discovered_count}</td
                ><td>{run.asset_count}</td><td>{formatDate(run.started_at)}</td></tr
              >{/each}</tbody
          >
        </table>
      </div>
    {/if}
  {/if}
  <svelte:fragment slot="footer"
    ><button class="button secondary" type="button" on:click={() => (detailOpen = false)}>关闭</button
    ></svelte:fragment
  >
</Modal>

<style>
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

  .detail-loading {
    display: flex;
    min-height: 180px;
    align-items: center;
    justify-content: center;
    gap: 9px;
    color: var(--text-muted);
    font-size: 12px;
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
</style>
