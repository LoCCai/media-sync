<script lang="ts">
  import { onMount } from 'svelte';
  import { Archive, Download, FileCheck2, HardDrive, RefreshCw, Search, Send } from '@lucide/svelte';

  import { api, apiMessage } from '$lib/api/client';
  import EmptyState from '$lib/components/EmptyState.svelte';
  import Modal from '$lib/components/Modal.svelte';
  import PageHeader from '$lib/components/PageHeader.svelte';
  import Panel from '$lib/components/Panel.svelte';
  import PlatformMark from '$lib/components/PlatformMark.svelte';
  import StatusBadge from '$lib/components/StatusBadge.svelte';
  import { mediaCrawlerGate } from '$lib/stores/onboarding';
  import { toast } from '$lib/stores/toast';
  import type { Asset, Platform, StartedOperation } from '$lib/types/api';
  import { formatBytes, formatDate, PLATFORM_META, shortId } from '$lib/utils/format';

  let assets: Asset[] = [];
  let loading = true;
  let acting = '';
  let error = '';
  let search = '';
  let platform = 'all';
  let status = 'all';
  let exportOpen = false;
  let exportAuthorId = '';

  $: filtered = assets.filter((item) => {
    const needle = search.trim().toLowerCase();
    return (
      (!needle || item.id.toLowerCase().includes(needle) || item.content_id.toLowerCase().includes(needle)) &&
      (platform === 'all' || item.platform === platform) &&
      (status === 'all' || item.status === status)
    );
  });
  $: verified = assets.filter((item) => ['verified', 'exported'].includes(item.status)).length;
  $: totalBytes = assets.reduce((sum, item) => sum + (item.size_bytes ?? 0), 0);

  async function load(): Promise<void> {
    loading = true;
    error = '';
    try {
      assets = await api<Asset[]>('/api/v1/assets?limit=1000');
    } catch (caught) {
      error = apiMessage(caught);
    } finally {
      loading = false;
    }
  }

  async function downloadAsset(asset: Asset): Promise<void> {
    acting = asset.id;
    try {
      const started = await api<StartedOperation>(`/api/v1/assets/${asset.id}/download`, {
        method: 'POST',
        body: JSON.stringify({ ...mediaCrawlerGate() })
      });
      toast(`资产下载已启动 · ${shortId(started.operation_id)}`);
    } catch (caught) {
      toast(apiMessage(caught), 'danger');
    } finally {
      acting = '';
    }
  }

  function prepareExport(asset?: Asset): void {
    exportAuthorId = asset?.author_id ?? '';
    exportOpen = true;
  }

  async function exportAuthor(): Promise<void> {
    if (!exportAuthorId.trim()) {
      toast('请输入作者 UUID。', 'danger');
      return;
    }
    acting = 'export';
    try {
      const started = await api<StartedOperation>('/api/v1/emby/export', {
        method: 'POST',
        body: JSON.stringify({ author_id: exportAuthorId.trim() })
      });
      toast(`媒体库导出已启动 · ${shortId(started.operation_id)}`);
      exportOpen = false;
    } catch (caught) {
      toast(apiMessage(caught), 'danger');
    } finally {
      acting = '';
    }
  }

  onMount(() => void load());
</script>

<div class="page">
  <PageHeader title="资产与归档" description="跟踪媒体文件的发现、下载、校验与归档状态。">
    <svelte:fragment slot="actions">
      <button class="button secondary" type="button" on:click={load} disabled={loading}
        ><RefreshCw class={loading ? 'spin' : ''} size={15} />刷新</button
      >
      <button class="button" type="button" on:click={() => prepareExport()}><Send size={15} />导出作者</button
      >
    </svelte:fragment>
  </PageHeader>

  <section class="summary-grid asset-summary">
    <div class="summary-item">
      <span class="summary-label">全部资产<Archive size={16} /></span><strong class="summary-value"
        >{assets.length}</strong
      ><span class="summary-hint">当前数据库记录</span>
    </div>
    <div class="summary-item">
      <span class="summary-label">已校验<FileCheck2 size={16} /></span><strong class="summary-value"
        >{verified}</strong
      ><span class="summary-hint"
        >{assets.length ? Math.round((verified / assets.length) * 100) : 0}% 完成</span
      >
    </div>
    <div class="summary-item">
      <span class="summary-label">待下载<Download size={16} /></span><strong class="summary-value"
        >{assets.filter((item) => ['discovered', 'queued', 'failed_retryable'].includes(item.status))
          .length}</strong
      ><span class="summary-hint">包含可重试资产</span>
    </div>
    <div class="summary-item">
      <span class="summary-label">已知容量<HardDrive size={16} /></span><strong class="summary-value bytes"
        >{formatBytes(totalBytes)}</strong
      ><span class="summary-hint">仅统计已记录大小</span>
    </div>
  </section>

  <Panel title="资产清单" description={`${filtered.length} 条结果`} flush>
    <svelte:fragment slot="actions">
      <div class="filters asset-filters">
        <div class="search-field">
          <Search size={14} /><input bind:value={search} aria-label="搜索资产" placeholder="资产或内容 ID" />
        </div>
        <select class="select filter-select" bind:value={platform} aria-label="平台筛选"
          ><option value="all">全部平台</option>{#each Object.entries(PLATFORM_META) as [value, meta]}<option
              {value}>{meta.name}</option
            >{/each}</select
        >
        <select class="select filter-select" bind:value={status} aria-label="状态筛选"
          ><option value="all">全部状态</option><option value="discovered">已发现</option><option
            value="queued">排队中</option
          ><option value="downloading">下载中</option><option value="verified">已校验</option><option
            value="exported">已导出</option
          ><option value="failed_retryable">可重试</option><option value="failed_terminal">终止失败</option
          ></select
        >
      </div>
    </svelte:fragment>

    {#if error}
      <div class="notice danger list-error">{error}</div>
    {:else if loading}
      <div class="loading-rows">
        {#each Array(5) as _}<div class="skeleton"></div>{/each}
      </div>
    {:else if filtered.length === 0}
      <EmptyState
        title={assets.length ? '没有匹配资产' : '还没有媒体资产'}
        description={assets.length
          ? '调整搜索或筛选条件后再试。'
          : '订阅同步发现媒体后，资产会进入下载与校验流水线。'}
      />
    {:else}
      <div class="table-wrap">
        <table class="data-table asset-table">
          <thead
            ><tr
              ><th>资产</th><th>平台</th><th>类型</th><th>状态</th><th>大小</th><th>校验时间</th><th
                class="actions">操作</th
              ></tr
            ></thead
          >
          <tbody>
            {#each filtered as asset}
              <tr>
                <td
                  ><span class="cell-main mono">{shortId(asset.id)}</span><span class="cell-sub mono"
                    >内容 {shortId(asset.content_id)} · G{asset.generation}</span
                  ></td
                >
                <td
                  ><div class="inline-identity">
                    <PlatformMark platform={asset.platform} /><span class="cell-main"
                      >{PLATFORM_META[asset.platform].name}</span
                    >
                  </div></td
                >
                <td
                  ><span class="cell-main">{asset.kind}</span><span class="cell-sub"
                    >{asset.mime_type ?? `position ${asset.position}`}</span
                  ></td
                >
                <td><StatusBadge status={asset.status} /></td>
                <td>{formatBytes(asset.size_bytes)}</td>
                <td>{formatDate(asset.verified_at)}</td>
                <td class="actions"
                  ><div class="row-actions">
                    <button class="button ghost small" type="button" on:click={() => prepareExport(asset)}
                      ><Send size={14} />导出</button
                    ><button
                      class="button secondary small"
                      type="button"
                      on:click={() => downloadAsset(asset)}
                      disabled={!!acting}
                      ><Download size={14} />{acting === asset.id ? '启动中' : '下载 / 校验'}</button
                    >
                  </div></td
                >
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    {/if}
  </Panel>
</div>

<Modal bind:open={exportOpen} title="导出作者到媒体库" description="为该作者生成 Emby / Jellyfin 兼容目录。">
  <div class="field">
    <label for="export-author">作者 UUID</label><input
      id="export-author"
      class="input mono"
      bind:value={exportAuthorId}
      placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
    />
  </div>
  <div class="notice" style="margin-top:14px">
    <Send size={17} />导出采用暂存目录与原子发布；已有相同指纹时不会重复写入。
  </div>
  <svelte:fragment slot="footer"
    ><button class="button secondary" type="button" on:click={() => (exportOpen = false)}>取消</button><button
      class="button"
      type="button"
      on:click={exportAuthor}
      disabled={acting === 'export'}>{acting === 'export' ? '启动中…' : '开始导出'}</button
    ></svelte:fragment
  >
</Modal>

<style>
  .summary-value.bytes {
    font-size: 21px;
  }

  .asset-filters {
    flex-wrap: nowrap;
  }

  .search-field {
    display: flex;
    width: 180px;
    min-height: 32px;
    align-items: center;
    gap: 7px;
    border: 1px solid var(--border-strong);
    border-radius: 6px;
    padding: 5px 9px;
    color: var(--text-muted);
  }

  .search-field input {
    min-width: 0;
    border: 0;
    outline: 0;
    color: var(--text);
    font-size: 11px;
  }

  .filter-select {
    width: auto;
    min-height: 32px;
    padding-top: 4px;
    padding-bottom: 4px;
    font-size: 11px;
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

  @media (max-width: 980px) {
    .asset-filters {
      display: none;
    }

    .asset-table {
      min-width: 1000px;
    }
  }
</style>
