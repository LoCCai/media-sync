<script lang="ts">
  import { onDestroy, onMount } from 'svelte';
  import { Archive, Database, Film, FolderCheck, Images, RefreshCw, Search, Send } from '@lucide/svelte';

  import { api, apiMessage } from '$lib/api/client';
  import EmptyState from '$lib/components/EmptyState.svelte';
  import PageHeader from '$lib/components/PageHeader.svelte';
  import Panel from '$lib/components/Panel.svelte';
  import PlatformMark from '$lib/components/PlatformMark.svelte';
  import StatusBadge from '$lib/components/StatusBadge.svelte';
  import { toast } from '$lib/stores/toast';
  import type { LibraryAuthor, Platform, StartedOperation } from '$lib/types/api';
  import { buildExplorerQuery, EXPLORER_RESULT_LIMIT } from '$lib/utils/explorer';
  import { formatDate, PLATFORM_META, shortId } from '$lib/utils/format';

  let authors: LibraryAuthor[] = [];
  let loading = true;
  let acting = '';
  let error = '';
  let search = '';
  let platform: Platform | 'all' = 'all';
  let mounted = false;
  let listRequest = 0;
  let searchTimer: number | undefined;

  $: totalContent = authors.reduce((sum, item) => sum + item.content_count, 0);
  $: totalAssets = authors.reduce((sum, item) => sum + item.asset_count, 0);
  $: archivedAssets = authors.reduce((sum, item) => sum + item.archived_count, 0);
  $: exportedContent = authors.reduce((sum, item) => sum + item.exported_count, 0);
  $: hasFilters = Boolean(search.trim()) || platform !== 'all';

  async function load(): Promise<void> {
    if (!mounted) return;
    if (searchTimer !== undefined) window.clearTimeout(searchTimer);
    const request = ++listRequest;
    loading = true;
    error = '';
    try {
      const result = await api<LibraryAuthor[]>(
        buildExplorerQuery('/api/v1/library', {
          q: search,
          platform,
          limit: EXPLORER_RESULT_LIMIT
        })
      );
      if (request === listRequest) authors = result;
    } catch (caught) {
      if (request === listRequest) error = apiMessage(caught);
    } finally {
      if (request === listRequest) loading = false;
    }
  }

  function scheduleLoad(): void {
    if (!mounted) return;
    if (searchTimer !== undefined) window.clearTimeout(searchTimer);
    searchTimer = window.setTimeout(() => void load(), 280);
  }

  async function exportAuthor(author: LibraryAuthor): Promise<void> {
    acting = author.author_id;
    try {
      const started = await api<StartedOperation>('/api/v1/emby/export', {
        method: 'POST',
        body: JSON.stringify({ author_id: author.author_id })
      });
      toast(`${author.display_name} 的导出已启动 · ${shortId(started.operation_id)}`);
    } catch (caught) {
      toast(apiMessage(caught), 'danger');
    } finally {
      acting = '';
    }
  }

  function percent(done: number, total: number): number {
    return total ? Math.min(100, Math.round((done / total) * 100)) : 0;
  }

  function archiveLabel(author: LibraryAuthor): string {
    return (
      {
        empty: '无媒体',
        pending: '待归档',
        partial: '部分归档',
        complete: '完整归档'
      }[author.archive_state] ?? author.archive_state
    );
  }

  onMount(() => {
    const query = new URLSearchParams(window.location.search);
    search = (query.get('q') ?? '').trim().slice(0, 200);
    const requestedPlatform = query.get('platform');
    if (requestedPlatform && requestedPlatform in PLATFORM_META) platform = requestedPlatform as Platform;
    mounted = true;
    void load();
  });

  onDestroy(() => {
    listRequest += 1;
    if (searchTimer !== undefined) window.clearTimeout(searchTimer);
  });
</script>

<div class="page">
  <PageHeader title="媒体库" description="按作者搜索媒体目录，并下钻到对应内容与资产。">
    <svelte:fragment slot="actions">
      <button class="button secondary" type="button" on:click={load} disabled={loading}>
        <RefreshCw class={loading ? 'spin' : ''} size={15} />刷新
      </button>
    </svelte:fragment>
  </PageHeader>

  <section class="summary-grid library-summary">
    <div class="summary-item">
      <span class="summary-label">当前作者<Database size={16} /></span>
      <strong class="summary-value">{authors.length}</strong>
      <span class="summary-hint">最多返回 {EXPLORER_RESULT_LIMIT} 位</span>
    </div>
    <div class="summary-item">
      <span class="summary-label">内容<Film size={16} /></span>
      <strong class="summary-value">{totalContent}</strong>
      <span class="summary-hint">当前结果中的入库内容</span>
    </div>
    <div class="summary-item">
      <span class="summary-label">归档资产<Archive size={16} /></span>
      <strong class="summary-value">{archivedAssets}</strong>
      <span class="summary-hint">共 {totalAssets} 个资产</span>
    </div>
    <div class="summary-item">
      <span class="summary-label">导出记录<FolderCheck size={16} /></span>
      <strong class="summary-value">{exportedContent}</strong>
      <span class="summary-hint">成功发布的内容</span>
    </div>
  </section>

  <Panel title="作者媒体库" description={`${authors.length} 条服务端结果`} flush>
    <svelte:fragment slot="actions">
      <div class="filters library-filters">
        <div class="search-field">
          <Search size={14} />
          <input
            bind:value={search}
            on:input={scheduleLoad}
            aria-label="搜索作者"
            placeholder="作者名称或标识"
          />
        </div>
        <select class="select filter-select" bind:value={platform} on:change={load} aria-label="平台筛选">
          <option value="all">全部平台</option>
          {#each Object.entries(PLATFORM_META) as [value, meta]}
            <option {value}>{meta.name}</option>
          {/each}
        </select>
      </div>
    </svelte:fragment>

    {#if error}
      <div class="notice danger list-error">{error}</div>
    {:else if loading}
      <div class="loading-rows">
        {#each Array(4) as _}<div class="skeleton"></div>{/each}
      </div>
    {:else if authors.length === 0}
      <EmptyState
        title={hasFilters ? '没有匹配作者' : '媒体库还是空的'}
        description={hasFilters
          ? '调整搜索或平台筛选后再试。'
          : '完成订阅同步和资产下载后，可按作者发布到媒体库目录。'}
      >
        {#if !hasFilters}<a class="button secondary small" href="/subscriptions">查看订阅</a>{/if}
      </EmptyState>
    {:else}
      <div class="table-wrap">
        <table class="data-table library-table">
          <thead>
            <tr
              ><th>作者</th><th>内容</th><th>归档进度</th><th>已发布</th><th>最近内容</th><th class="actions"
                >操作</th
              ></tr
            >
          </thead>
          <tbody>
            {#each authors as author}
              <tr>
                <td>
                  <div class="inline-identity">
                    <PlatformMark platform={author.platform} />
                    <div>
                      <a
                        class="cell-main author-link"
                        href={`/contents?author_id=${encodeURIComponent(author.author_id)}`}
                      >
                        {author.display_name}
                      </a>
                      <span class="cell-sub">{PLATFORM_META[author.platform].name} · {author.remote_id}</span>
                    </div>
                  </div>
                </td>
                <td>
                  <a class="count-link" href={`/contents?author_id=${encodeURIComponent(author.author_id)}`}>
                    <span class="cell-main">{author.content_count}</span><span class="cell-sub">条内容</span>
                  </a>
                </td>
                <td>
                  <a
                    class="archive-progress"
                    href={`/assets?author_id=${encodeURIComponent(author.author_id)}`}
                  >
                    <div>
                      <span>{author.archived_count} / {author.asset_count}</span>
                      <span
                        >{archiveLabel(author)} · {percent(author.archived_count, author.asset_count)}%</span
                      >
                    </div>
                    <div class="progress-track">
                      <div
                        class="progress-bar"
                        style={`width:${percent(author.archived_count, author.asset_count)}%`}
                      ></div>
                    </div>
                  </a>
                </td>
                <td>{author.exported_count} 条</td>
                <td>{formatDate(author.last_published_at)}</td>
                <td class="actions">
                  <div class="row-actions">
                    <a
                      class="button ghost small"
                      href={`/contents?author_id=${encodeURIComponent(author.author_id)}`}
                    >
                      <Film size={14} />内容
                    </a>
                    <a
                      class="button ghost small"
                      href={`/assets?author_id=${encodeURIComponent(author.author_id)}`}
                    >
                      <Images size={14} />资产
                    </a>
                    <button
                      class="button secondary small"
                      type="button"
                      on:click={() => exportAuthor(author)}
                      disabled={!!acting}
                      ><Send size={14} />{acting === author.author_id ? '启动中…' : '导出 / 更新'}</button
                    >
                  </div>
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    {/if}
  </Panel>

  <div class="notice deferred-note">
    <FolderCheck size={17} />本页只展示安全目录与导出事实；Emby / Jellyfin
    树浏览、扫描和播放控制将在后续版本提供。
  </div>
</div>

<style>
  .library-filters {
    flex-wrap: nowrap;
  }

  .search-field {
    display: flex;
    width: 210px;
    min-height: 32px;
    align-items: center;
    gap: 7px;
    border: 1px solid var(--border-strong);
    border-radius: 6px;
    padding: 5px 9px;
    background: #fff;
    color: var(--text-muted);
  }

  .search-field:focus-within {
    border-color: #78a3f5;
    box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.09);
  }

  .search-field input {
    min-width: 0;
    border: 0;
    outline: 0;
    background: transparent;
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

  .author-link:hover,
  .count-link:hover .cell-main {
    color: var(--accent);
    text-decoration: underline;
    text-underline-offset: 3px;
  }

  .archive-progress {
    display: block;
    width: 210px;
    border-radius: 5px;
  }

  .archive-progress:hover {
    opacity: 0.78;
  }

  .archive-progress > div:first-child {
    display: flex;
    justify-content: space-between;
    gap: 10px;
    margin-bottom: 5px;
    color: #59677c;
    font-size: 10.5px;
  }

  .archive-progress .progress-bar {
    background: #4c617e;
  }

  .actions {
    text-align: right !important;
  }

  .row-actions {
    display: flex;
    justify-content: flex-end;
    gap: 3px;
    flex-wrap: nowrap;
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

  .deferred-note {
    align-items: center;
  }

  @media (max-width: 980px) {
    .library-table {
      min-width: 960px;
    }
  }

  @media (max-width: 720px) {
    .library-filters,
    .search-field,
    .filter-select {
      width: 100%;
    }

    .library-filters {
      flex-wrap: wrap;
    }
  }
</style>
