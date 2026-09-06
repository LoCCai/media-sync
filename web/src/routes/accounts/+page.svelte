<script lang="ts">
  import { onDestroy, onMount } from 'svelte';
  import {
    ArrowRight,
    CheckCircle2,
    ExternalLink,
    LoaderCircle,
    Plus,
    RefreshCw,
    XCircle
  } from '@lucide/svelte';

  import { api, apiMessage } from '$lib/api/client';
  import EmptyState from '$lib/components/EmptyState.svelte';
  import PageHeader from '$lib/components/PageHeader.svelte';
  import Panel from '$lib/components/Panel.svelte';
  import PlatformMark from '$lib/components/PlatformMark.svelte';
  import StatusBadge from '$lib/components/StatusBadge.svelte';
  import { toast } from '$lib/stores/toast';
  import type { Account, CrawlerProfileAdoption, Platform } from '$lib/types/api';
  import { PLATFORM_META, shortId, statusLabel } from '$lib/utils/format';
  import { loginMethodLabel } from '$lib/utils/workbench';

  const platformOptions = Object.keys(PLATFORM_META) as Platform[];

  let accounts: Account[] = [];
  let loading = true;
  let adding = false;
  let adoptingAccountId = '';
  let error = '';
  let formPlatform: Platform = 'bili';
  let formName = '';
  let lastAdoption: CrawlerProfileAdoption | null = null;
  let destroyed = false;
  let loadRevision = 0;

  async function load(): Promise<void> {
    const revision = ++loadRevision;
    loading = true;
    error = '';
    try {
      const loaded = await api<Account[]>('/api/v1/accounts');
      if (destroyed || revision !== loadRevision) return;
      accounts = loaded;
    } catch (caught) {
      if (destroyed || revision !== loadRevision) return;
      error = apiMessage(caught);
    } finally {
      if (!destroyed && revision === loadRevision) loading = false;
    }
  }

  async function addAccount(): Promise<void> {
    if (destroyed || loading || adding || adoptingAccountId) return;
    const displayName = formName.trim();
    if (!displayName) {
      toast('请输入一个便于本地辨认的账户显示名。', 'danger');
      return;
    }
    adding = true;
    try {
      const created = await api<Account>('/api/v1/accounts', {
        method: 'POST',
        body: JSON.stringify({ platform: formPlatform, display_name: displayName })
      });
      if (destroyed) return;
      toast(created.created ? '本地账户已添加。' : '该账户已存在，已刷新账户列表。');
      formName = '';
      await load();
    } catch (caught) {
      if (!destroyed) toast(apiMessage(caught), 'danger');
    } finally {
      if (!destroyed) adding = false;
    }
  }

  async function adoptCrawlerProfile(account: Account): Promise<void> {
    if (destroyed || loading || adding || adoptingAccountId) return;
    adoptingAccountId = account.id;
    lastAdoption = null;
    try {
      const adopted = await api<CrawlerProfileAdoption>(
        `/api/v1/accounts/${account.id}/crawler-profile`,
        {
          method: 'POST',
          body: JSON.stringify({ expected_auth_revision: account.auth_revision })
        },
        120_000
      );
      if (destroyed) return;
      lastAdoption = adopted;
      await load();
      if (!destroyed) toast('已认领原生 MediaCrawler 登录会话。', 'success');
    } catch (caught) {
      if (!destroyed) toast(apiMessage(caught), 'danger');
    } finally {
      if (!destroyed) adoptingAccountId = '';
    }
  }

  onMount(() => void load());
  onDestroy(() => {
    destroyed = true;
    loadRevision += 1;
  });
</script>

<div class="page">
  <PageHeader
    title="平台账户"
    description="平台登录直接使用原生 MediaCrawler；这里仅建立本地账户并认领已登录会话。"
  >
    <svelte:fragment slot="actions">
      <button
        class="button secondary"
        type="button"
        on:click={load}
        disabled={loading || adding || !!adoptingAccountId}
      >
        <RefreshCw class={loading ? 'spin' : ''} size={15} />刷新账户
      </button>
    </svelte:fragment>
  </PageHeader>

  <Panel title="登录并认领会话" description="按以下三步完成；本站不再重复实现平台登录。">
    <ol class="steps">
      <li class="step-card">
        <span class="step-number">1</span>
        <div>
          <strong>打开原生爬虫控制台</strong>
          <p>进入 MediaCrawler 自带的 WebUI。</p>
        </div>
        <a class="button small" href="/crawler/">打开 MediaCrawler <ExternalLink size={14} /></a>
      </li>
      <li class="step-card">
        <span class="step-number">2</span>
        <div>
          <strong>在原生界面完成登录</strong>
          <p>选择平台，通过二维码或 Cookie 登录；确认登录成功后停止爬虫任务。</p>
        </div>
      </li>
      <li class="step-card">
        <span class="step-number">3</span>
        <div>
          <strong>回来认领登录会话</strong>
          <p>找到相同平台的本地账户，点击“认领已登录会话”。</p>
        </div>
      </li>
    </ol>
  </Panel>

  {#if lastAdoption}
    <div class="notice success adoption-success" role="status" aria-live="polite">
      <CheckCircle2 size={18} />
      <div>
        <strong class="notice-title">登录会话已认领</strong>
        {PLATFORM_META[lastAdoption.platform].name}账户已标记为{statusLabel(
          lastAdoption.auth_status
        )}，现在可以创建作者订阅。
      </div>
      <a class="button small" href="/subscriptions">前往订阅 <ArrowRight size={14} /></a>
    </div>
  {/if}

  <Panel title="添加本地账户" description="显示名只用于本地辨认，不需要填写平台用户名。">
    <form class="account-form" on:submit|preventDefault={addAccount}>
      <div class="field platform-field">
        <label for="account-platform">平台</label>
        <select
          id="account-platform"
          class="select"
          bind:value={formPlatform}
          disabled={loading || adding || !!adoptingAccountId}
        >
          {#each platformOptions as platform}
            <option value={platform}>{PLATFORM_META[platform].name}</option>
          {/each}
        </select>
      </div>
      <div class="field name-field">
        <label for="account-name">显示名</label>
        <input
          id="account-name"
          class="input"
          bind:value={formName}
          placeholder={`例如：我的${PLATFORM_META[formPlatform].name}账号`}
          maxlength="200"
          autocomplete="off"
          disabled={loading || adding || !!adoptingAccountId}
        />
      </div>
      <button
        class="button add-button"
        type="submit"
        disabled={loading || adding || !!adoptingAccountId || !formName.trim()}
      >
        {#if adding}<LoaderCircle class="spin" size={15} />{:else}<Plus size={15} />{/if}
        {adding ? '添加中…' : '添加账户'}
      </button>
    </form>
  </Panel>

  <Panel title="账户列表" description={`${accounts.length} 个本地账户`} flush>
    {#if error}
      <div class="notice danger list-notice"><XCircle size={17} />{error}</div>
    {:else if loading}
      <div class="account-skeletons">
        {#each Array(3) as _}<div class="skeleton"></div>{/each}
      </div>
    {:else if accounts.length === 0}
      <EmptyState
        title="还没有本地账户"
        description="先在上方选择平台并添加账户，再到原生 MediaCrawler 完成登录。"
      />
    {:else}
      <div class="table-wrap">
        <table class="data-table account-table">
          <thead>
            <tr>
              <th>平台</th><th>账户</th><th>认证状态</th><th>登录方式</th><th class="action-cell">操作</th>
            </tr>
          </thead>
          <tbody>
            {#each accounts as account}
              <tr>
                <td>
                  <div class="inline-identity">
                    <PlatformMark platform={account.platform} />
                    <span class="cell-main">{PLATFORM_META[account.platform].name}</span>
                  </div>
                </td>
                <td>
                  <span class="cell-main">{account.display_name}</span>
                  <span class="cell-sub mono">{shortId(account.id)}</span>
                </td>
                <td><StatusBadge status={account.auth_status} /></td>
                <td>{loginMethodLabel(account.login_method)}</td>
                <td class="action-cell">
                  <button
                    class="button secondary small"
                    type="button"
                    on:click={() => adoptCrawlerProfile(account)}
                    disabled={loading || adding || !!adoptingAccountId}
                    title={`认领 ${PLATFORM_META[account.platform].name} 在原生 MediaCrawler 中保存的登录会话`}
                  >
                    {#if adoptingAccountId === account.id}<LoaderCircle class="spin" size={14} />{/if}
                    {adoptingAccountId === account.id ? '认领中…' : '认领已登录会话'}
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

<style>
  .steps {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 12px;
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .step-card {
    display: flex;
    min-width: 0;
    align-items: flex-start;
    gap: 11px;
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 14px;
    background: var(--surface-subtle);
  }

  .step-card > div {
    min-width: 0;
    flex: 1;
  }

  .step-card strong {
    display: block;
    color: var(--text);
    font-size: 12px;
    font-weight: 620;
  }

  .step-card p {
    margin: 4px 0 0;
    color: var(--text-secondary);
    font-size: 11px;
  }

  .step-number {
    display: inline-flex;
    width: 24px;
    height: 24px;
    flex: 0 0 auto;
    align-items: center;
    justify-content: center;
    border-radius: 999px;
    background: var(--accent-soft);
    color: var(--accent);
    font-size: 11px;
    font-weight: 700;
  }

  .step-card .button {
    flex: 0 0 auto;
  }

  .adoption-success {
    align-items: center;
  }

  .adoption-success > div {
    min-width: 0;
    flex: 1;
  }

  .account-form {
    display: grid;
    grid-template-columns: minmax(180px, 0.6fr) minmax(260px, 1.4fr) auto;
    align-items: end;
    gap: 12px;
  }

  .add-button {
    min-height: 38px;
  }

  .account-skeletons {
    display: grid;
    gap: 1px;
    padding: 12px 14px;
  }

  .account-skeletons div {
    height: 50px;
  }

  .list-notice {
    margin: 16px;
  }

  .action-cell {
    width: 176px;
    text-align: right !important;
  }

  @media (max-width: 980px) {
    .steps {
      grid-template-columns: 1fr;
    }

    .account-table {
      min-width: 760px;
    }
  }

  @media (max-width: 720px) {
    .account-form {
      grid-template-columns: 1fr;
    }

    .adoption-success {
      align-items: flex-start;
      flex-wrap: wrap;
    }

    .adoption-success .button {
      margin-left: 29px;
    }
  }

  @media (max-width: 520px) {
    .step-card {
      flex-wrap: wrap;
    }

    .step-card .button {
      width: 100%;
      margin-left: 35px;
    }
  }
</style>
